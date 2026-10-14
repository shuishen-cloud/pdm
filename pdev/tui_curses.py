# -*- coding: utf-8 -*-
"""curses 版只读浏览 TUI（tui-curses）。

设计见 ``doc/feat/tui-curses.md``。三条铁律：

1. **零依赖**：只用标准库 ``curses``，不 import textual/rich。
2. **分层**：``build_view`` / ``render_view`` 是纯函数，**不依赖 curses**，
   可脱离终端单测；只有 ``run`` 碰终端。
3. **显式按键分发**：主循环里直接 ``if`` 判断，没有全局 Binding、
   没有消息冒泡——Textual 版那三类框架 bug 在结构上不存在。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .git import GitRepo
from .note import CommitNote, NoteKind, NoteStatus
from .store import NoteStore

__all__ = [
    "CommitRow",
    "CursesView",
    "Selection",
    "build_view",
    "render_view",
    "run",
]

# 标准库 curses 在 `run()` 里**延迟导入**（见 `_load_curses`），
# 使纯函数层（build_view/render_view）在无 curses 平台也能 import 与单测。
curses = None  # 由 `_load_curses()` 填充；供测试注入 None 模拟不可用


def _load_curses():
    """延迟导入标准库 curses；不可用返回 None。"""
    global curses
    if curses is not None:
        return curses
    try:
        import curses as _c  # noqa: PLC0415
    except Exception:  # pragma: no cover - 平台差异
        return None
    curses = _c
    return _c

# 终端最小尺寸（低于此只给提示）
MIN_WIDTH = 60
MIN_HEIGHT = 10

_KIND_SHORT = {
    NoteKind.PROBLEM: "pro",
    NoteKind.BUG: "bug",
    NoteKind.PITFALL: "pit",
    NoteKind.DIFFICULTY: "dif",
    NoteKind.CONTROLLED_EXCEPTION: "exc",
}

_STATUS_MARK = {
    NoteStatus.OPEN: "○",
    NoteStatus.RESOLVED: "●",
    NoteStatus.NOTED: "·",
}


# ---------------------------------------------------------------------------
# 数据视图（纯数据，无 curses）
# ---------------------------------------------------------------------------


@dataclass
class CommitRow:
    """提交栏的一行。"""

    commit: str          # 完整 hash
    label: str           # 已截断的显示文本


@dataclass
class Selection:
    """当前选中位置。"""

    commit: int = 0                     # 提交栏光标
    note: int = 0                       # 笔记栏光标
    focus: int = 0                      # 焦点栏 0=提交 1=笔记 2=详情


@dataclass
class CursesView:
    """待渲染的纯数据视图。"""

    commits: List[CommitRow] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    detail: List[str] = field(default_factory=list)
    focus: int = 0
    cursor: List[int] = field(default_factory=lambda: [0, 0, 0])


# ---------------------------------------------------------------------------
# 宽度工具（与 Textual 版同一算法；此处自带一份以免依赖 rich/textual）
# ---------------------------------------------------------------------------


def _display_width(text: str) -> int:
    """近似显示宽度（CJK 算 2）。"""
    import unicodedata

    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _ellipsize(text: str, width: int) -> str:
    """按显示宽度截断，超出用 … 代替。"""
    if width <= 0:
        return ""
    if _display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    out: List[str] = []
    used = 0
    budget = width - 1
    for ch in text:
        w = _display_width(ch)
        if used + w > budget:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def _pad(text: str, width: int) -> str:
    """按显示宽度右侧补空格到 width（超长先截断）。"""
    text = _ellipsize(text, width)
    gap = width - _display_width(text)
    return text + " " * max(0, gap)


# ---------------------------------------------------------------------------
# 纯函数：数据 → 视图
# ---------------------------------------------------------------------------


def _commit_infos(git, commits: Sequence[str]) -> dict:
    """批量取 commit 元信息（git 不可用时返回空）。"""
    if git is None or not getattr(git, "available", False):
        return {}
    infos = {}
    for c in commits:
        try:
            info = git.commit_info(c)
        except Exception:
            info = None
        if info is not None:
            infos[c] = info
    return infos


def build_view(store: NoteStore, git, selection: Selection) -> CursesView:
    """把 store/git 数据转成视图。**纯函数，不 import curses、不碰终端。**"""
    selection = selection or Selection()

    # 1. 提交栏：优先 git 历史（新→旧），非 git 仓库则退回笔记里的 commit
    commits: List[str] = []
    infos = {}
    if git is not None and getattr(git, "available", False):
        try:
            history = git.log()
        except Exception:
            history = []
        for info in history:
            commits.append(info.hash)
            infos[info.hash] = info
    if not commits:
        # 无 git：用笔记里出现过的 commit（去重保序）
        seen = set()
        for note in store.all():
            if note.commit not in seen:
                seen.add(note.commit)
                commits.append(note.commit)

    rows = []
    for c in commits:
        info = infos.get(c)
        subject = getattr(info, "subject", "") if info else ""
        label = f"{c[:8]}  {subject}" if subject else c[:8]
        rows.append(CommitRow(commit=c, label=label))

    # 2. 选中提交的笔记
    cur = min(max(selection.commit, 0), max(0, len(rows) - 1))
    cur_commit = rows[cur].commit if rows else None
    notes: List[CommitNote] = store.by_commit(cur_commit) if cur_commit else []

    note_lines = []
    for n in notes:
        mark = _STATUS_MARK.get(n.status, "·")
        short = _KIND_SHORT.get(n.kind, "?")
        note_lines.append(f"{mark} [{short}] {n.title}")

    # 3. 详情：选中笔记的全字段
    detail: List[str] = []
    if not rows:
        detail = ["（无提交）"]
    elif not notes:
        detail = [f"提交  {cur_commit[:8]}", "", "（该提交暂无笔记）"]
    else:
        idx = min(max(selection.note, 0), len(notes) - 1)
        n = notes[idx]
        detail = _note_detail(n, rows[cur].commit, infos.get(rows[cur].commit))

    return CursesView(
        commits=rows,
        notes=note_lines,
        detail=detail,
        focus=min(max(selection.focus, 0), 2),
        cursor=[cur, min(max(selection.note, 0), max(0, len(notes) - 1)), 0],
    )


def _note_detail(note: CommitNote, commit: str, info) -> List[str]:
    """一条笔记的详情行（纯文本）。"""
    lines = []
    subject = getattr(info, "subject", "") if info else ""
    lines.append(f"提交  {subject or commit[:8]}")
    lines.append(f"作者  {note.author.raw}")
    lines.append(f"类型  {note.kind.value}   状态 {note.status.value}")
    if note.severity is not None:
        lines.append(f"严重  {note.severity.value}")
    if note.files:
        lines.append(f"文件  {', '.join(note.files)}")
    if note.tags:
        lines.append(f"标签  {', '.join(note.tags)}")
    if note.catches:
        lines.append(f"捕获  {', '.join(note.catches)}")
    lines.append("")
    lines.append(note.title)
    if note.detail:
        lines.append("")
        lines.extend(note.detail.splitlines())
    if note.verifications:
        lines.append("")
        lines.append("验证")
        for v in note.verifications:
            target = v.target or v.command or v.note or ""
            lines.append(f"  {v.kind.value}  {target}")
            if v.method:
                lines.append(f"    方法  {v.method}")
            if v.expected:
                lines.append(f"    期望  {v.expected}")
    return lines


# ---------------------------------------------------------------------------
# 纯函数：视图 → 每行字符串
# ---------------------------------------------------------------------------


def render_view(view: CursesView, height: int, width: int) -> List[str]:
    """把视图渲染成 ``height`` 行字符串。**纯函数，不 import curses。**

    过小终端返回单行提示（仍凑满 height 行），不崩。
    """
    height = max(1, int(height))
    width = max(1, int(width))

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        hint = f"终端太小（{width}x{height}），至少需要 {MIN_WIDTH}x{MIN_HEIGHT}"
        out = [_ellipsize(hint, width)]
        out += [""] * (height - 1)
        return out

    # 三栏宽度（两个分隔符各占 1 列）
    inner = width - 2
    cw = inner // 3
    nw = inner // 3
    dw = inner - cw - nw

    focus = min(max(view.focus, 0), 2)
    cur = view.cursor if view.cursor else [0, 0, 0]

    def col_lines(items: List[str], selected: int, w: int, focused: bool) -> List[str]:
        """一栏的可见行（滚动到选中项）。"""
        n = max(1, height - 2)              # 减去标题行与底栏
        start = 0
        if selected >= n:
            start = selected - n + 1
        chunk = items[start:start + n]
        lines = []
        for i, text in enumerate(chunk):
            idx = start + i
            mark = ">" if (focused and idx == selected) else " "
            lines.append(mark + _pad(text, max(0, w - 1)))
        while len(lines) < n:
            lines.append(" " * w)
        return lines

    head = _pad(f"选择  {focus}", width)
    c_lines = col_lines([r.label for r in view.commits], cur[0], cw, focus == 0)
    n_lines = col_lines(view.notes, cur[1] if len(cur) > 1 else 0, nw, focus == 1)
    d_lines = col_lines(view.detail, 0, dw, focus == 2)

    body = []
    for i in range(max(1, height - 2)):
        body.append(f"{c_lines[i]}│{n_lines[i]}│{d_lines[i]}")

    foot = _pad("q 退出  j/k 移动  Tab/1/2/3 切栏  h/l 左右", width)
    return [head] + body + [foot]


# ---------------------------------------------------------------------------
# IO 层：唯一碰 curses 的地方
# ---------------------------------------------------------------------------


def _enter_curses(stdscr, store: NoteStore, git, key_reader) -> int:
    """curses 主循环。只在 ``curses.wrapper`` 内被调用。"""
    c = _load_curses()
    c.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    sel = Selection()
    while True:
        h, w = stdscr.getmaxyx()
        view = build_view(store, git, sel)
        lines = render_view(view, h, w)

        stdscr.erase()
        for y, line in enumerate(lines[:h]):
            try:
                stdscr.addstr(y, 0, line)
            except c.error:
                pass                    # 末行末列写入属已知限制，忽略
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"),):
            return 0
        if key in (c.KEY_DOWN, ord("j")):
            sel = _move(sel, view, +1)
        elif key in (c.KEY_UP, ord("k")):
            sel = _move(sel, view, -1)
        elif key in (c.KEY_LEFT, ord("h")):
            sel = Selection(sel.commit, sel.note, (sel.focus - 1) % 3)
        elif key in (c.KEY_RIGHT, ord("l")):
            sel = Selection(sel.commit, sel.note, (sel.focus + 1) % 3)
        elif key == ord("\t"):
            sel = Selection(sel.commit, sel.note, (sel.focus + 1) % 3)
        elif key in (ord("1"), ord("2"), ord("3")):
            sel = Selection(sel.commit, sel.note, key - ord("1"))


def _move(sel: Selection, view: CursesView, delta: int) -> Selection:
    """按焦点栏上下移动光标（到头则停）。"""
    if sel.focus == 0:
        n = len(view.commits)
        return Selection(min(max(sel.commit + delta, 0), max(0, n - 1)),
                         0, sel.focus)
    if sel.focus == 1:
        n = len(view.notes)
        return Selection(sel.commit,
                         min(max(sel.note + delta, 0), max(0, n - 1)),
                         sel.focus)
    return sel


def run(store: NoteStore, cwd: str = ".", config=None,
        stdout=None) -> int:
    """启动 curses 只读浏览界面；返回退出码。

    非 tty 或 curses 不可用 → 提示并返回 2（不进入 curses）。
    """
    import sys

    out = stdout if stdout is not None else sys.stdout
    if not getattr(out, "isatty", lambda: False)():
        print("pdm ui --curses 需要交互式终端", file=sys.stderr)
        return 2
    c = _load_curses()
    if c is None:
        print("当前平台不支持 curses", file=sys.stderr)
        return 2

    git = GitRepo(cwd)
    try:
        return c.wrapper(_enter_curses, store, git, None)
    except KeyboardInterrupt:
        return 130
