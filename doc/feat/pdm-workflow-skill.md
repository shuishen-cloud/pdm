# AI 代理开发工作流技能（pdm-workflow）

> 先于实现编写。把本项目的开发纪律封装成 pi 技能，让 AI 代理在开发时
> 自动遵循 doc → test → feat → fix → close，并经 pdm 门面提交。

## 问题

`pdm` 已经把**阶段顺序**做成提交门面，但门面只约束"怎么提交"，不约束
"AI 代理该按什么流程工作"。代理容易：

- 直接 `git commit`，绕过 `pdm feat commit`；
- 写完代码才补设计（违反 doc 先行）；
- 不记笔记、不绑验证，导致 `commit-no-note` / `note-no-verify` 欠账；
- 不知道 `.pdm` 本地数据、验证、风险项等设计思想，用错命令。

需要一个技能，把**流程纪律 + 命令用法 + 设计思想**在需要时喂给代理。

## 规范

Agent Skills 规范：目录含 `SKILL.md`，frontmatter 声明 `name` /
`description`，正文是直接指令。pi 启动只加载 name/description，命中任务
时才加载全文。

```
.pi/skills/pdm-workflow/
├── SKILL.md                     # 核心流程指令（何时触发、怎么做）
├── references/
│   ├── commands.md              # 完整命令与参数
│   ├── design-doc.md            # 设计文档该写什么
│   └── data-model.md            # 数据结构与设计思想
└── scripts/
    └── pdm                      # 定位项目根的 pdm 包装器
```

## 接口

- `name: pdm-workflow`（小写+连字符，≤64 字符）
- `description`：含**做什么**与**何时用**，供路由
- `scripts/pdm`：从任意子目录向上找含 `pyproject.toml`/`.pdm.json` 的根，
  优先 `./run.sh`，其次 `.venv/bin/pdm`，最后 PATH

## 日志

- skill 本身不打日志；pi 加载失败会输出诊断 warning。

## 兜底

- 找不到 pdm 可执行文件 → 报错并提示建虚拟环境（退出码 127）
- frontmatter 非法 → pi 拒绝加载并告警（本设计经 `loadSkillsFromDir`
  验证零诊断）

## 实现与校验结果（收尾）

实现于本次提交。用 pi 的 `loadSkillsFromDir` 实测：skill 被正确加载，
`diagnostics` 为空。frontmatter 用真实 `yaml` 解析器校验：name 合法、
description 485 字符。

`scripts/pdm` 实测：从项目根与 `pdev/` 子目录均能正确定位并执行。

### 本次发现的异常

1. 从子目录执行 pdm，子命令用相对 cwd 找 `.pdm/feats`，会显示"无 feat"
   → 包装脚本先 `cd` 到项目根再 exec。
