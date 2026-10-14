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

## 同类技能

<!-- leaderboard:start -->
从 GitHub 的 `skills/`、`.agents/skills`、`.codex/skills`、`.claude/skills` 里扫到的技能仓库，按星数排序。每 6 小时爬一次。skillock 自己不进榜。完整页面：[Hana 排行](https://quantz8a.github.io/skillock/)。

最近一次写入 README 的爬取时间：2026-10-14 14:46 UTC。

### 技能包

| # | 仓库 | 星 | 较上次 | 最近推送 |
| ---: | --- | ---: | ---: | --- |
| 1 | [obra/superpowers](https://github.com/obra/superpowers) | 298,988 | — | 2026-10-10 |
| 2 | [mattpocock/skills](https://github.com/mattpocock/skills) | 290,721 | — | 2026-10-13 |
| 3 | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 279,034 | — | 2026-10-12 |
| 4 | [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 219,687 | — | 2026-04-20 |
| 5 | [anthropics/skills](https://github.com/anthropics/skills) | 181,073 | — | 2026-10-09 |
| 6 | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 163,305 | — | 2026-10-13 |
| 7 | [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | 160,021 | — | 2026-10-13 |
| 8 | [github/spec-kit](https://github.com/github/spec-kit) | 141,244 | — | 2026-10-14 |
| 9 | [garrytan/gstack](https://github.com/garrytan/gstack) | 136,381 | — | 2026-10-14 |
| 10 | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 135,739 | — | 2026-10-12 |
| 11 | [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | 121,272 | — | 2026-10-14 |
| 12 | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 106,522 | — | 2026-10-13 |
| 13 | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 96,046 | — | 2026-10-13 |
| 14 | [tt-a1i/archify](https://github.com/tt-a1i/archify) | 83,408 | — | 2026-10-14 |
| 15 | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 81,058 | — | 2026-10-13 |
| 16 | [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 77,090 | — | 2026-09-18 |
| 17 | [quran/quran.com-frontend-next](https://github.com/quran/quran.com-frontend-next) | 1,924 | — | 2026-04-27 |
| 18 | [karanhudia/borg-ui](https://github.com/karanhudia/borg-ui) | 1,661 | — | 2026-10-12 |
| 19 | [BiFangKNT/mtga](https://github.com/BiFangKNT/mtga) | 1,170 | — | 2026-06-18 |
| 20 | [nevalang/neva](https://github.com/nevalang/neva) | 1,084 | — | 2026-08-23 |
| 21 | [srid/emanote](https://github.com/srid/emanote) | 964 | — | 2026-07-26 |
| 22 | [ArtisanCloud/PowerX](https://github.com/ArtisanCloud/PowerX) | 382 | — | 2026-10-13 |
| 23 | [shift-editor/shift](https://github.com/shift-editor/shift) | 356 | — | 2026-10-14 |
| 24 | [membranedev/application-skills](https://github.com/membranedev/application-skills) | 267 | — | 2026-04-28 |
| 25 | [zacharyfmarion/openscad-studio](https://github.com/zacharyfmarion/openscad-studio) | 241 | — | 2026-08-19 |
| 26 | [theowenyoung/home](https://github.com/theowenyoung/home) | 115 | — | 2026-09-27 |
| 27 | [Sikao-Engine/KimiX](https://github.com/Sikao-Engine/KimiX) | 114 | — | 2026-10-14 |
| 28 | [Dwlad90/stylex-swc-plugin](https://github.com/Dwlad90/stylex-swc-plugin) | 112 | — | 2026-10-13 |
| 29 | [925236118/AlphaAgent](https://github.com/925236118/AlphaAgent) | 103 | — | 2026-10-08 |
| 30 | [AGI4Sci/SciForge](https://github.com/AGI4Sci/SciForge) | 82 | — | 2026-09-03 |
| 31 | [juspay/kolu](https://github.com/juspay/kolu) | 81 | — | 2026-10-14 |

### 省 token

| # | 仓库 | 星 | 较上次 | 最近推送 |
| ---: | --- | ---: | ---: | --- |
| 1 | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 111,727 | — | 2026-10-14 |
| 2 | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) | 83,323 | — | 2026-10-14 |

### 记忆

| # | 仓库 | 星 | 较上次 | 最近推送 |
| ---: | --- | ---: | ---: | --- |
| 1 | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 100,657 | — | 2026-10-13 |
<!-- leaderboard:end -->

## 中文

标志叫 **Hana（哈娜）**。日语里这是常见的狗名，也是「鼻子」；韩语 하나 是「一」；中文就读哈娜。命令仍是 `skillock`。

skillock 扫一组 `SKILL.md`，回答三件事：启动时 name 和 description 占多少 token，哪些技能会一起触发并且指令相反，哪些 harness 版本钉不能同时成立。示例目录的第一行就是上面那个数。它不安装技能，也不替代任何一个 coding agent。

先用 Python 版。`pip install ./python` 之后命令还是 `skillock`，macOS、Linux、Windows 同一套，不用按平台发 Rust 二进制。Rust crate 留在仓库里，平台安装包以后再发。

## What this is not

skillock does not download skills, run an agent, or pick a model. It checks the set you already installed.
