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

Python 3.9 or newer is enough. Nothing to compile, and the same command runs on macOS, Linux, and Windows:

```
python3 -m pip install ./python
skillock check examples --harness opencode=2.0.1
```

From a checkout, without installing:

```
PYTHONPATH=python python3 -m skillock check examples --harness opencode=2.0.1
```

The Rust crate in this repository is the same checker. Packaged binaries for each platform come later; this build does not need them.

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

## 测评

<!-- leaderboard:start -->
Hana 把每个公开仓库当成一组已经装上的技能，跑 skillock 的检查。启动 token 是还没选中任何一个技能之前就要付的成本，高的排在前面。每 6 小时重测一次。skillock 自己不进榜。完整页面：[Hana 测评](https://quantz8a.github.io/skillock/)。

最近一次测评：2026-10-14 15:00 UTC。

### 省 token

| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 28 | 1,507 | 24,014 | 6 | 6 | — | duplicate-name 6, overlap 6 |
| 2 | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | 12 | 688 | 25,813 | 5 | 1 | — | spec-name 5, overlap 1 |
| 3 | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 12 | 669 | 10,154 | 6 | 2 | — | duplicate-name 6, overlap 2 |

### 记忆

| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 37 | 2,503 | 70,501 | 24 | 19 | — | overlap 12, spec-name 8, spec-dir 7, body-budget 7 |

### 设计

| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 22 | 4,600 | 57,928 | 1 | 172 | — | overlap 171, duplicate-name 1, startup-budget 1 |
| 2 | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 14 | 1,527 | 90,128 | 11 | 7 | — | spec-dir 11, body-budget 7 |
| 3 | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 13 | 1,326 | 26,720 | 6 | 6 | — | duplicate-name 6, overlap 6 |

### 规划

| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [garrytan/gstack](https://github.com/garrytan/gstack) | 65 | 1,680 | 686,275 | 1 | 48 | — | body-budget 46, overlap 2, duplicate-name 1 |
| 2 | [tt-a1i/archify](https://github.com/tt-a1i/archify) | 5 | 561 | 10,797 | 0 | 0 | — | 通过 |
| 3 | [github/spec-kit](https://github.com/github/spec-kit) | 2 | 171 | 2,005 | 0 | 0 | — | 通过 |

### 综合

| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 200+ | 14,970 | 456,631 | 46 | 37 | — | duplicate-name 46, overlap 24, body-budget 10, spec-metadata 2 |
| 2 | [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 200+ | 6,714 | 162,041 | 26 | 16837 | — | overlap 16836, spec-name 15, spec-dir 11, startup-budget 1 |
| 3 | [anthropics/skills](https://github.com/anthropics/skills) | 20 | 2,592 | 73,871 | 2 | 4 | — | body-budget 4, spec-description 1, spec-dir 1 |
| 4 | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 25 | 2,479 | 88,922 | 0 | 2 | — | body-budget 2 |
| 5 | [mattpocock/skills](https://github.com/mattpocock/skills) | 38 | 1,597 | 42,766 | 0 | 1 | — | spec-metadata 1 |
| 6 | [obra/superpowers](https://github.com/obra/superpowers) | 15 | 709 | 42,498 | 0 | 3 | — | body-budget 3 |
| 7 | [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 1 | 63 | 601 | 0 | 0 | — | 通过 |
<!-- leaderboard:end -->

## 中文

标志叫 **Hana（哈娜）**。日语里这是常见的狗名，也是「鼻子」；韩语 하나 是「一」；中文就读哈娜。命令仍是 `skillock`。

skillock 扫一组 `SKILL.md`，回答三件事：启动时 name 和 description 占多少 token，哪些技能会一起触发并且指令相反，哪些 harness 版本钉不能同时成立。示例目录的第一行就是上面那个数。它不安装技能，也不替代任何一个 coding agent。

先用 Python 版。`pip install ./python` 之后命令还是 `skillock`，macOS、Linux、Windows 同一套。Apple 芯片的二进制在 [v0.1.0](https://github.com/quantz8a/skillock/releases/tag/v0.1.0)。

## What this is not

skillock does not download skills, run an agent, or pick a model. It checks the set you already installed.
