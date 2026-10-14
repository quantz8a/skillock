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
这一期只测界面设计。候选来自星数较高的仓库里、目录名是 `frontend-design`、`ui-ux`、`taste`、`impeccable`、`design-system`、`web-design` 的 `SKILL.md`。同一份正文只保留星数最高的那一处。排名按启动 token 从高到低，每 6 小时重测一次。skillock 自己不进榜。完整页面：[Hana 测评](https://quantz8a.github.io/skillock/)。

最近一次测评：2026-10-14 15:13 UTC。

### 界面设计

| # | 技能 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [impeccable](https://github.com/pbakaus/impeccable/blob/main/.opencode/skills/impeccable/SKILL.md) | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 81,070 | 241 | 3,052 | 0 | 0 | 0 | 通过 |
| 2 | [imagegen-frontend-web](https://github.com/Leonxlnx/taste-skill/blob/main/skills/imagegen-frontend-web/SKILL.md) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 96,072 | 181 | 9,858 | 0 | 1 | — | body-budget 1 |
| 3 | [imagegen-frontend-mobile](https://github.com/Leonxlnx/taste-skill/blob/main/skills/imagegen-frontend-mobile/SKILL.md) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 96,072 | 178 | 10,796 | 0 | 1 | — | body-budget 1 |
| 4 | [design](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/design/SKILL.md) | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 135,743 | 174 | 3,606 | 0 | 0 | 0 | 通过 |
| 5 | [image-to-code](https://github.com/Leonxlnx/taste-skill/blob/main/skills/image-to-code-skill/SKILL.md) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 96,072 | 155 | 9,763 | 1 | 1 | — | spec-dir 1, body-budget 1 |
| 6 | [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-ux-pro-max/SKILL.md) | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 135,743 | 136 | 4,146 | 0 | 0 | 0 | 通过 |
| 7 | [taste](https://github.com/affaan-m/ECC/blob/main/skills/taste/SKILL.md) | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 279,060 | 131 | 4,060 | 0 | 0 | — | 通过 |
| 8 | [ui-styling](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-styling/SKILL.md) | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 135,743 | 130 | 2,671 | 0 | 0 | — | 通过 |
| 9 | [design-system](https://github.com/affaan-m/ECC/blob/main/pi/core/skills/design-system/SKILL.md) | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 279,060 | 118 | 621 | 0 | 0 | — | 通过 |
| 10 | [frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | [anthropics/skills](https://github.com/anthropics/skills) | 181,080 | 58 | 2,440 | 0 | 0 | 0 | 通过 |
<!-- leaderboard:end -->

## 中文

标志叫 **Hana（哈娜）**。日语里这是常见的狗名，也是「鼻子」；韩语 하나 是「一」；中文就读哈娜。命令仍是 `skillock`。

skillock 扫一组 `SKILL.md`，回答三件事：启动时 name 和 description 占多少 token，哪些技能会一起触发并且指令相反，哪些 harness 版本钉不能同时成立。示例目录的第一行就是上面那个数。它不安装技能，也不替代任何一个 coding agent。

先用 Python 版。`pip install ./python` 之后命令还是 `skillock`，macOS、Linux、Windows 同一套。Apple 芯片的二进制在 [v0.1.0](https://github.com/quantz8a/skillock/releases/tag/v0.1.0)。

## What this is not

skillock does not download skills, run an agent, or pick a model. It checks the set you already installed.
