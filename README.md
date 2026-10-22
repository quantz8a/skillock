# skillock

<p align="center">
  <img src="assets/hana.jpg" alt="Hana" width="280">
</p>

<p align="center"><strong>Hana · 哈娜</strong></p>

**6 skills · startup 152 tokens · bodies 7356 tokens · 5 errors · 5 warnings**

The lockfile for agent skills. `SKILL.md` files never show up in GitHub's dependency graph, so nothing checks whether two skills can be installed together. skillock scans a directory and reports three things:

- how many tokens the skills load before one of them is even chosen
- instructions that say the opposite thing
- harness version pins that cannot all be true

Install the skill with one command:

```
npx skills add quantz8a/skillock -g -y
```

Python 3.9 or newer is enough to run the checker. Nothing to compile, and the same command runs on macOS, Linux, and Windows:

```
python3 -m pip install ./python
skillock check examples --harness opencode=2.0.1
```

From a checkout, without installing:

```
PYTHONPATH=python python3 -m skillock check examples --harness opencode=2.0.1
```

The Rust crate in this repository is the same checker. Apple silicon builds are on the [v0.1.0 release](https://github.com/quantz8a/skillock/releases/tag/v0.1.0). `optimize` is in the Python build.

That example pack is the failure mode already written down in public issue trackers: a skill that makes the agent slow, two skills that pin different OpenCode majors, and a pin the installed version has drifted past.

## What a clean skill looks like

```
1 skills · startup 70 tokens · bodies 158 tokens · 0 errors · 0 warnings
```

`skills/skillock/SKILL.md` is itself a skill. Agents that already load skills can be told to run this check when a new skill is added or a harness is upgraded.

## Checks

| Code | Level | Meaning |
| --- | --- | --- |
| `spec-name`, `spec-dir`, `spec-description`, `spec-frontmatter` | error | The file breaks the [Agent Skills](https://agentskills.io/specification) manifest rules |
| `duplicate-name` | error | Two directories claim the same skill name |
| `pin-conflict` | error | Two skills pin one harness to ranges that do not overlap |
| `pin-drift` | error | `--harness name=version` sits outside a skill's pin |
| `overlap` | warning | Two descriptions are close enough that both may activate |
| `contradiction` | warning | One body says always/must, the other says never/do not, about the same words |
| `body-budget` | warning | One skill's body exceeds the activation budget (default 5000 tokens) |
| `startup-budget` | warning | The sum of every name and description exceeds the startup budget (default 4000) |
| `lock-drift`, `lock-new`, `lock-removed` | warning | The tree no longer matches `SKILLOCK.toml` |

Pins are read from `compatibility` (`opencode >= 2`, `Claude Code >= 2.1.296`, a bare `openclaw 2026.9.8`) and from metadata keys named after the product (`skillock.opencode = ">=2,<3"`). A bare version matches that prefix and excludes newer components, which is the drift caveman users keep filing.

Token counts are a budget: four ASCII characters per token, one token per non-ASCII character. They are not a model tokenizer. The startup number matters more than the body number, because agents load every `name` and `description` up front and load a body only when that skill activates.

## Lockfile

```
skillock lock examples --harness opencode=2.0.1
```

`SKILLOCK.toml` records the path and SHA-256 of each skill. The next `skillock check` warns when a file moves. Exit status is 1 when any error is present. `--strict` does the same for warnings.

With no paths, skillock scans `./skills`, `./examples`, and the `.agents`, `.claude`, and `.codex` skill directories in the current project. `--user` adds the same directories under `$HOME`. Pass a directory to scan anywhere else, including a local Codex++ install.

## Optimize

```
PYTHONPATH=python python3 -m skillock optimize examples --harness opencode=2.0.1
```

On that example pack the plan is `keep 3 · drop 3 · startup 84 tokens`. It drops the invalid name, the duplicate, and the skill whose OpenCode pin excludes `2.0.1`. `planner` stays, and the report still says its body is over the activation budget. skillock does not edit or delete `SKILL.md` files. `--lock` writes the kept set to `SKILLOCK.toml`.

## 测评

<!-- leaderboard:start -->
测这些分类：界面设计、省 token、记忆、规划、审查、测试、调试、研究、文档、安全。同一份正文只保留星数最高的那一处。排名按启动 token 从高到低，每 6 小时重测一次。安装列是一条命令。skillock 自己不进榜。完整页面：[Hana 测评](https://quantz8a.github.io/skillock/)。

最近一次测评：2026-10-22 04:39 UTC。

### 界面设计

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [design-taste-frontend](https://github.com/Leonxlnx/taste-skill/blob/main/skills/taste-skill/SKILL.md) | `npx skills add https://github.com/Leonxlnx/taste-skill/tree/main/skills/taste-skill -g -y` | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 100,678 | 261 | 10,047 | 1 | 1 | 0 | spec-dir 1, body-budget 1 |
| 2 | [design](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/design/SKILL.md) | `npx skills add https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/design -g -y` | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 138,572 | 174 | 3,624 | 0 | 0 | 0 | 通过 |
| 3 | [impeccable](https://github.com/pbakaus/impeccable/blob/main/.opencode/skills/impeccable/SKILL.md) | `npx skills add https://github.com/pbakaus/impeccable/tree/main/.opencode/skills/impeccable -g -y` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 84,531 | 161 | 2,971 | 0 | 0 | 0 | 通过 |
| 4 | [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-ux-pro-max/SKILL.md) | `npx skills add https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max -g -y` | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 138,572 | 136 | 4,146 | 0 | 0 | 0 | 通过 |
| 5 | [taste](https://github.com/affaan-m/ECC/blob/main/skills/taste/SKILL.md) | `npx skills add https://github.com/affaan-m/ECC/tree/main/skills/taste -g -y` | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 285,840 | 131 | 4,060 | 0 | 0 | 0 | 通过 |
| 6 | [ui-styling](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-styling/SKILL.md) | `npx skills add https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-styling -g -y` | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 138,572 | 130 | 2,671 | 0 | 0 | 0 | 通过 |
| 7 | [design-system](https://github.com/affaan-m/ECC/blob/main/pi/core/skills/design-system/SKILL.md) | `npx skills add https://github.com/affaan-m/ECC/tree/main/pi/core/skills/design-system -g -y` | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 285,840 | 118 | 621 | 0 | 0 | 0 | 通过 |
| 8 | [frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | `npx skills add https://github.com/anthropics/skills/tree/main/skills/frontend-design -g -y` | [anthropics/skills](https://github.com/anthropics/skills) | 182,811 | 58 | 2,440 | 0 | 0 | 0 | 通过 |

### 省 token

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [caveman](https://github.com/JuliusBrussee/caveman/blob/main/plugins/caveman/skills/caveman/SKILL.md) | `npx skills add https://github.com/JuliusBrussee/caveman/tree/main/plugins/caveman/skills/caveman -g -y` | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 114,174 | 60 | 1,191 | 0 | 0 | 0 | 通过 |
| 2 | [ponytail](https://github.com/DietrichGebert/ponytail/blob/main/.openclaw/skills/ponytail/SKILL.md) | `npx skills add https://github.com/DietrichGebert/ponytail/tree/main/.openclaw/skills/ponytail -g -y` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 171,968 | 39 | 808 | 0 | 0 | 0 | 通过 |

### 记忆

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [mem-setup](https://github.com/thedotmack/claude-mem/blob/main/cowork/skills/mem-setup/SKILL.md) | `npx skills add https://github.com/thedotmack/claude-mem/tree/main/cowork/skills/mem-setup -g -y` | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 102,177 | 78 | 681 | 0 | 0 | 0 | 通过 |
| 2 | [mem-search](https://github.com/thedotmack/claude-mem/blob/main/plugin/skills/mem-search/SKILL.md) | `npx skills add https://github.com/thedotmack/claude-mem/tree/main/plugin/skills/mem-search -g -y` | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 102,177 | 74 | 2,023 | 0 | 0 | 0 | 通过 |

### 规划

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [brainstorming](https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/brainstorming -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 61 | 3,563 | 0 | 0 | 0 | 通过 |
| 2 | [executing-plans](https://github.com/obra/superpowers/blob/main/skills/executing-plans/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/executing-plans -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 50 | 4,763 | 0 | 0 | 0 | 通过 |
| 3 | [writing-plans](https://github.com/obra/superpowers/blob/main/skills/writing-plans/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/writing-plans -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 26 | 2,697 | 0 | 0 | 0 | 通过 |

### 审查

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md) | `npx skills add https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review -g -y` | [mattpocock/skills](https://github.com/mattpocock/skills) | 300,052 | 115 | 1,647 | 0 | 0 | 0 | 通过 |
| 2 | [receiving-code-review](https://github.com/obra/superpowers/blob/main/skills/receiving-code-review/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/receiving-code-review -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 69 | 1,577 | 0 | 0 | 0 | 通过 |
| 3 | [requesting-code-review](https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/requesting-code-review -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 35 | 749 | 0 | 0 | 0 | 通过 |

### 测试

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [webapp-testing](https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md) | `npx skills add https://github.com/anthropics/skills/tree/main/skills/webapp-testing -g -y` | [anthropics/skills](https://github.com/anthropics/skills) | 182,811 | 58 | 914 | 0 | 0 | 0 | 通过 |
| 2 | [tdd](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md) | `npx skills add https://github.com/mattpocock/skills/tree/main/skills/engineering/tdd -g -y` | [mattpocock/skills](https://github.com/mattpocock/skills) | 300,052 | 40 | 918 | 0 | 0 | 0 | 通过 |
| 3 | [test-driven-development](https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/test-driven-development -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 26 | 2,553 | 0 | 0 | 0 | 通过 |

### 调试

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [diagnosing-bugs](https://github.com/mattpocock/skills/blob/main/skills/engineering/diagnosing-bugs/SKILL.md) | `npx skills add https://github.com/mattpocock/skills/tree/main/skills/engineering/diagnosing-bugs -g -y` | [mattpocock/skills](https://github.com/mattpocock/skills) | 300,052 | 44 | 2,271 | 0 | 0 | 0 | 通过 |
| 2 | [systematic-debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) | `npx skills add https://github.com/obra/superpowers/tree/main/skills/systematic-debugging -g -y` | [obra/superpowers](https://github.com/obra/superpowers) | 303,228 | 29 | 2,484 | 0 | 0 | 0 | 通过 |

### 研究

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [deep-research](https://github.com/affaan-m/ECC/blob/main/skills/deep-research/SKILL.md) | `npx skills add https://github.com/affaan-m/ECC/tree/main/skills/deep-research -g -y` | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 285,840 | 110 | 1,493 | 0 | 0 | 0 | 通过 |
| 2 | [research](https://github.com/mattpocock/skills/blob/main/skills/engineering/research/SKILL.md) | `npx skills add https://github.com/mattpocock/skills/tree/main/skills/engineering/research -g -y` | [mattpocock/skills](https://github.com/mattpocock/skills) | 300,052 | 67 | 142 | 0 | 0 | 0 | 通过 |

### 文档

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [xlsx](https://github.com/anthropics/skills/blob/main/skills/xlsx/SKILL.md) | `npx skills add https://github.com/anthropics/skills/tree/main/skills/xlsx -g -y` | [anthropics/skills](https://github.com/anthropics/skills) | 182,811 | 254 | 2,033 | 0 | 0 | 0 | 通过 |
| 2 | [docx](https://github.com/anthropics/skills/blob/main/skills/docx/SKILL.md) | `npx skills add https://github.com/anthropics/skills/tree/main/skills/docx -g -y` | [anthropics/skills](https://github.com/anthropics/skills) | 182,811 | 227 | 1,606 | 0 | 0 | 0 | 通过 |
| 3 | [pptx](https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md) | `npx skills add https://github.com/anthropics/skills/tree/main/skills/pptx -g -y` | [anthropics/skills](https://github.com/anthropics/skills) | 182,811 | 201 | 5,377 | 0 | 1 | 0 | body-budget 1 |

### 安全

| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [agent-security-hardening](https://github.com/affaan-m/ECC/blob/main/pi/core/skills/agent-security-hardening/SKILL.md) | `npx skills add https://github.com/affaan-m/ECC/tree/main/pi/core/skills/agent-security-hardening -g -y` | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 285,840 | 104 | 2,688 | 0 | 0 | 0 | 通过 |
<!-- leaderboard:end -->

## 中文

标志叫 **Hana（哈娜）**。日语里这是常见的狗名，也是「鼻子」；韩语 하나 是「一」；中文就读哈娜。命令仍是 `skillock`。

skillock 扫一组 `SKILL.md`，回答三件事：启动时 name 和 description 占多少 token，哪些技能会一起触发并且指令相反，哪些 harness 版本钉不能同时成立。示例目录的第一行就是上面那个数。它不安装技能，也不替代任何一个 coding agent。

安装技能就一条命令：

```
npx skills add quantz8a/skillock -g -y
```

检查器先用 Python 版。`pip install ./python` 之后命令还是 `skillock`，macOS、Linux、Windows 同一套。不安装时：

```
PYTHONPATH=python python3 -m skillock check examples --harness opencode=2.0.1
```

Apple 芯片的二进制在 [v0.1.0](https://github.com/quantz8a/skillock/releases/tag/v0.1.0)。`optimize` 目前只在 Python 版里。

检查分两类。错误：`spec-name`、`spec-dir`、`spec-description`、`spec-frontmatter` 是清单不合规范；`duplicate-name` 是重名；`pin-conflict` 是两个技能把同一个 harness 钉在互不相交的版本上；`pin-drift` 是 `--harness` 给出的已装版本落在钉的外面。警告：`overlap` 是两条描述会抢同一次请求；`contradiction` 是一边 always/must、另一边 never/do not；`body-budget` 和 `startup-budget` 是正文或启动 token 超预算；`lock-drift`、`lock-new`、`lock-removed` 是目录和 `SKILLOCK.toml` 不一致。

版本钉读 `compatibility`，也读以产品名命名的 metadata，例如 `skillock.opencode = ">=2,<3"`。没写比较符的版本只匹配这个前缀，更后面的组件算漂移。token 是预算：4 个 ASCII 字符算 1 个，每个非 ASCII 字符算 1 个，不是模型分词器。启动数更要紧，因为每个 `name` 和 `description` 都会先被加载。

`skillock lock` 把留下的路径和 SHA-256 写进 `SKILLOCK.toml`。有错误时退出码是 1，`--strict` 连警告也算失败。不给路径时扫 `./skills`、`./examples`，以及项目里的 `.agents`、`.claude`、`.codex` 技能目录。`--user` 再加 `$HOME` 下的同名目录。

`skillock optimize` 自动收成一组能一起装的技能。它会拿掉不合规范的清单、重名里多出来的那份、已装版本对不上的钉；钉还是互斥时，拿掉和别人冲突最多的那一个。启动 token 仍超过 `--budget`（默认 4000）时，从 name 和 description 最大的开始拿掉。正文超预算只报告，不改写技能。它不编辑、不删除 `SKILL.md`。`--lock` 把留下的那一组写成锁文件。示例目录加上 `--harness opencode=2.0.1` 的结果是留下 3 个、拿掉 3 个、启动 84 token。`planner` 还在，正文仍然超过激活预算。

## What this is not

skillock does not download skills, run an agent, or pick a model. It checks the set you already installed.
