# -*- coding: utf-8 -*-
"""配置加载与合并。

配置来源按优先级从高到低：

1. CLI 参数
2. ``PDM_*`` 环境变量
3. 项目级 ``.pdm.json``（当前目录向上查找）
4. 用户级 ``~/.config/pdm/config.json``
5. 内置默认值

:class:`Config` 是合并后的**不可变快照**；运行时资源（如 ``NoteStore``）
由 :class:`pdev.cli.context.AppContext` 构造。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from .note import NoteStatus

__all__ = [
    "Config",
    "ConfigError",
    "GitConfig",
    "NoteConfig",
    "QueryConfig",
    "IssueConfig",
    "DocConfig",
    "FeatConfig",
    "UIConfig",
    "GitHubConfig",
    "load_config",
    "save_config",
    "find_project_config",
    "resolve_doc_path",
    "PROJECT_CONFIG_NAME",
    "ENV_PREFIX",
]

PROJECT_CONFIG_NAME = ".pdm.json"
ENV_PREFIX = "PDM_"
USER_CONFIG_PATH = "~/.config/pdm/config.json"


class ConfigError(ValueError):
    """配置文件无法解析或内容非法。"""


# 旧格式 feat.doc 可能已含的根前缀：兼容读取时不再拼接
_DOC_ROOT_PREFIXES = ("docs/", ".pdm/docs/")


def resolve_doc_path(doc_dir: str, feat_doc: str) -> str:
    """把 ``feat.doc``（相对 ``doc.dir``）解析成项目内实际路径。

    - ``feat_doc`` 为空 → 返回 ``""``
    - ``doc_dir`` 为空 → 回退到 ``.pdm/docs``
    - ``feat_doc`` 已是旧格式（以 ``docs/`` 或 ``.pdm/docs/`` 开头）
      → 原样返回，不再拼接（避免 ``.pdm/docs/docs/...``）
    - 否则 → 拼成 ``<doc_dir>/<feat_doc>``
    """
    if not feat_doc:
        return ""
    if feat_doc.startswith(_DOC_ROOT_PREFIXES):
        return feat_doc
    root = doc_dir or ".pdm/docs"
    return f"{root.rstrip('/')}/{feat_doc}"


# ---------------------------------------------------------------------------
# 配置分段
# ---------------------------------------------------------------------------


@dataclass
class GitConfig:
    """git 相关。"""

    repo: str = "."
    auto_commit: bool = False


@dataclass
class NoteConfig:
    """笔记相关。"""

    default_status: NoteStatus = NoteStatus.NOTED
    require_detail: bool = False


@dataclass
class QueryConfig:
    """查询相关。"""

    default_limit: Optional[int] = None


@dataclass
class IssueConfig:
    """Issue 相关。"""

    store: str = "issues"


@dataclass
class DocConfig:
    """文档相关。

    ``dir`` 是 feat 设计文档的根目录。默认为 ``.pdm/docs``（不跟踪）；
    用户可改到可跟踪目录（如 ``docs``）使文档随代码分发。
    """

    dir: str = ".pdm/docs"


@dataclass
class FeatConfig:
    """Feat（开发记录）相关。"""

    store: str = ".pdm/feats"


@dataclass
class UIConfig:
    """TUI 外观与交互设置。

    ``theme`` 可选 Textual 内置主题名（如 ``textual-dark``、``nord``、
    ``gruvbox``、``dracula``、``monokai``、``catppuccin-mocha`` ……）。
    """

    theme: str = "textual-dark"
    commit_width: int = 0          # 提交条目最大宽度，0 = 不限制
    show_footer: bool = True


@dataclass
class GitHubConfig:
    """GitHub 同步相关。

    ``token`` 只应从环境变量 ``PDM_GITHUB_TOKEN`` 注入，不要写进 JSON。
    """

    repo: str = ""
    token: str = ""
    auto_push: bool = False


@dataclass
class Config:
    """合并后的运行时配置快照。"""

    store: str = ".pdm/notes"
    default_author: str = "human:unknown"
    color: bool = True
    json_output: bool = False
    editor: str = ""

    git: GitConfig = field(default_factory=GitConfig)
    note: NoteConfig = field(default_factory=NoteConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    issue: IssueConfig = field(default_factory=IssueConfig)
    doc: DocConfig = field(default_factory=DocConfig)
    feat: FeatConfig = field(default_factory=FeatConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)

    # --- 序列化 ---

    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 化的 dict。"""
        d = asdict(self)
        d["note"]["default_status"] = self.note.default_status.value
        # token 不外泄
        if d["github"].get("token"):
            d["github"]["token"] = "***"
        return d


# ---------------------------------------------------------------------------
# 反序列化（宽松：未知键忽略，类型按 dataclass 字段推断）
# ---------------------------------------------------------------------------


_SEGMENTS = {
    "git": GitConfig,
    "note": NoteConfig,
    "query": QueryConfig,
    "issue": IssueConfig,
    "doc": DocConfig,
    "feat": FeatConfig,
    "ui": UIConfig,
    "github": GitHubConfig,
}


def _coerce(value: Any, target: Any) -> Any:
    """把原始值转成目标类型。"""
    if target is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if target is int:
        return int(value)
    if target is NoteStatus:
        return value if isinstance(value, NoteStatus) else NoteStatus(value)
    return value


def _apply_segment(cfg: Any, data: Mapping[str, Any]) -> None:
    """把一段 dict 写入 dataclass 实例，忽略未知键。"""
    if not isinstance(data, Mapping):
        return
    valid = {f.name: f.type for f in fields(cfg)}
    for key, raw in data.items():
        if key not in valid:
            continue
        # dataclass field.type 在 from __future__ import annotations 下是字符串
        declared = valid[key]
        setattr(cfg, key, _coerce_value(raw, declared, key))


def _coerce_value(value: Any, declared: Any, key: str) -> Any:
    """根据字段声明（可能是字符串）决定如何转换。"""
    if value is None:
        # null 一律视为“显式清空”（如 default_limit: null 表示不限）
        return None
    name = declared if isinstance(declared, str) else getattr(declared, "__name__", "")
    if name == "bool" or key in _BOOL_KEYS:
        return _coerce(value, bool)
    if name == "int" or key in _INT_KEYS:
        return _coerce(value, int)
    if name == "NoteStatus" or key == "default_status":
        return _coerce(value, NoteStatus)
    return value


_BOOL_KEYS = {
    "color", "json_output", "auto_commit", "require_detail", "auto_push",
    "show_footer",
}
_INT_KEYS = {"default_limit", "commit_width"}


def _merge_into(cfg: Config, data: Mapping[str, Any]) -> None:
    """把一层配置 dict 合并进 cfg（就地）。"""
    if not isinstance(data, Mapping):
        return
    top_keys = {f.name for f in fields(Config)}
    for key, value in data.items():
        if key in _SEGMENTS:
            _apply_segment(getattr(cfg, key), value)
        elif key in top_keys:
            setattr(cfg, key, _coerce_value(value, "", key))
        # 未知键忽略


# ---------------------------------------------------------------------------
# 来源加载
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Dict[str, Any]:
    """读标准 JSON；文件不存在返回空 dict，格式错误则报错。

    不支持注释：配置文件可能被编辑器、jq、CI 等读取，保持严格 JSON 避免兼容问题。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件 {path} 解析失败：{e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件 {path} 顶层必须是对象")
    return data


def find_project_config(start: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """从 ``start``（默认当前目录）向上查找 ``.pdm.json``。"""
    cur = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _env_overrides(env: Mapping[str, str]) -> Dict[str, Any]:
    """把 ``PDM_*`` 环境变量转成嵌套 dict。"""
    out: Dict[str, Any] = {}

    def put(path: List[str], value: str) -> None:
        node = out
        for p in path[:-1]:
            node = node.setdefault(p, {})
        node[path[-1]] = value

    # 显式映射：环境变量名 -> 配置路径
    mapping = {
        "PDM_STORE": ["store"],
        "PDM_AUTHOR": ["default_author"],
        "PDM_EDITOR": ["editor"],
        "PDM_GIT_REPO": ["git", "repo"],
        "PDM_GIT_AUTO_COMMIT": ["git", "auto_commit"],
        "PDM_ISSUE_STORE": ["issue", "store"],
        "PDM_DOC_DIR": ["doc", "dir"],
        "PDM_FEAT_STORE": ["feat", "store"],
        "PDM_UI_THEME": ["ui", "theme"],
        "PDM_UI_COMMIT_WIDTH": ["ui", "commit_width"],
        "PDM_GITHUB_REPO": ["github", "repo"],
        "PDM_GITHUB_TOKEN": ["github", "token"],
        "PDM_GITHUB_AUTO_PUSH": ["github", "auto_push"],
        "PDM_QUERY_DEFAULT_LIMIT": ["query", "default_limit"],
    }
    for env_key, path in mapping.items():
        if env_key in env and env[env_key] != "":
            put(path, env[env_key])

    # --no-color 风格的反向开关
    if _truthy(env.get("PDM_NO_COLOR")):
        out["color"] = False
    if env.get("PDM_JSON"):
        out["json_output"] = True
    return out


def _truthy(v: Optional[str]) -> bool:
    return v is not None and v.strip().lower() in ("1", "true", "yes", "on")


def load_config(
    cli_overrides: Optional[Mapping[str, Any]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
    project_config: Optional[Path] = None,
    user_config: Optional[Path] = None,
    cwd: Optional[Path] = None,
    find: bool = True,
) -> Config:
    """按优先级合并各来源，返回 :class:`Config`。

    优先级（高 -> 低）：cli_overrides > 环境变量 > 项目配置 > 用户配置 > 默认。

    :param cli_overrides: 来自 CLI 的显式设置，值为 ``None`` 的键会被忽略。
    :param env: 环境变量映射，默认 ``os.environ``。
    :param project_config: 项目配置路径；``None`` 且 ``find`` 为真时向上查找。
    :param user_config: 用户配置路径，默认 ``~/.config/pdm/config.json``。
    :param cwd: 查找项目配置的起点。
    :param find: 是否自动向上查找项目配置。
    """
    cfg = Config()
    env = os.environ if env is None else env

    # 4. 用户级
    user_path = Path(user_config) if user_config else Path(USER_CONFIG_PATH).expanduser()
    _merge_into(cfg, _read_json(user_path))

    # 3. 项目级
    proj_path = project_config
    if proj_path is None and find:
        proj_path = find_project_config(cwd)
    if proj_path is not None:
        _merge_into(cfg, _read_json(Path(proj_path)))

    # 2. 环境变量
    _merge_into(cfg, _env_overrides(env))

    # 1. CLI（最高优先级）
    if cli_overrides:
        cleaned = {k: v for k, v in cli_overrides.items() if v is not None}
        _merge_into(cfg, cleaned)

    return cfg


# ---------------------------------------------------------------------------
# 写回（仅用于 TUI 改设置，如主题）
# ---------------------------------------------------------------------------


def save_config(
    updates: Mapping[str, Any],
    *,
    project_config: Optional[Path] = None,
    user_config: Optional[Path] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """把 ``updates``（嵌套 dict）合并写回配置文件，返回写入路径。

    优先写**项目配置**（``.pdm.json``，已存在或能向上找到）；找不到就写
    **用户配置**。这样 TUI 里切换主题后下次启动仍生效。

    - 保留文件里已有的其它键（深合并，只覆盖 ``updates`` 涉及的路径）
    - 输出始终是缩进 2 的标准 JSON（保证可读、可 diff）
    - ``github.token`` 不会被写入（敏感信息拒绝落盘）
    """
    target = _pick_write_target(project_config, cwd)
    if target is None:
        target = (Path(user_config) if user_config
                  else Path(USER_CONFIG_PATH).expanduser())

    data = _read_json(target)
    _deep_merge(data, _scrub(updates))

    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    target.write_text(text + "\n", encoding="utf-8")
    return target


def _pick_write_target(project_config: Optional[Path],
                       cwd: Optional[Path]) -> Optional[Path]:
    """决定写哪个文件：显式路径 > 已存在的项目配置 > 无。"""
    if project_config is not None:
        return Path(project_config)
    found = find_project_config(cwd)
    return found


def _scrub(updates: Mapping[str, Any]) -> Dict[str, Any]:
    """剔除不应落盘的敏感键。"""
    out: Dict[str, Any] = {}
    for key, value in updates.items():
        if isinstance(value, Mapping):
            out[key] = _scrub(value)
        elif key == "token":
            continue
        else:
            out[key] = value
    return out


def _deep_merge(base: Dict[str, Any], extra: Mapping[str, Any]) -> None:
    """把 extra 深合并进 base（就地）。"""
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
