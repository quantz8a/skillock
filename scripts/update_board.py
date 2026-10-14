#!/usr/bin/env python3
"""Evaluate public skill repos with skillock and rewrite the Pages site plus the README."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from skillock.engine import Options, analyze, discover, load_skill  # noqa: E402

CATALOG = ROOT / "data" / "catalog.json"
HISTORY = ROOT / "data" / "history.json"
BOARD = ROOT / "data" / "board.json"
DOCS = ROOT / "docs"
README = ROOT / "README.md"
START = "<!-- leaderboard:start -->"
END = "<!-- leaderboard:end -->"
MAX_POINTS = 120
MAX_SKILLS = 200
PAGE = "https://quantz8a.github.io/skillock/"
SELF_REPO = "quantz8a/skillock"
INSTALL = "npx skills add quantz8a/skillock -g -y"
MIN_STARS = 5000
MAX_ROWS = 8
MAX_PER_REPO = 3
CATEGORIES = (
    {
        "title": "界面设计",
        "dirs": {
            "frontend-design",
            "ui-ux",
            "ui-ux-pro-max",
            "taste",
            "impeccable",
            "design-system",
            "web-design",
            "design",
        },
        "prefixes": ("ui-ux",),
        "seeds": (
            "nextlevelbuilder/ui-ux-pro-max-skill",
            "Leonxlnx/taste-skill",
            "pbakaus/impeccable",
            "anthropics/skills",
            "affaan-m/ECC",
        ),
        "pure": {
            "nextlevelbuilder/ui-ux-pro-max-skill",
            "Leonxlnx/taste-skill",
            "pbakaus/impeccable",
        },
        "query": "frontend-design OR ui-ux-pro-max OR taste-skill OR impeccable",
    },
    {
        "title": "省 token",
        "dirs": {"caveman", "ponytail"},
        "prefixes": (),
        "seeds": ("JuliusBrussee/caveman", "DietrichGebert/ponytail"),
        "pure": set(),
        "query": "caveman OR ponytail in:name",
    },
    {
        "title": "记忆",
        "dirs": {"mem-search", "mem-setup"},
        "prefixes": ("mem-",),
        "seeds": ("thedotmack/claude-mem",),
        "pure": set(),
        "query": "claude-mem OR mem-search in:name",
    },
    {
        "title": "规划",
        "dirs": {"writing-plans", "executing-plans", "brainstorming", "make-plan"},
        "prefixes": (),
        "seeds": ("obra/superpowers",),
        "pure": set(),
        "query": "writing-plans OR executing-plans in:name",
    },
    {
        "title": "审查",
        "dirs": {
            "code-review",
            "requesting-code-review",
            "receiving-code-review",
            "conventional-commit-review",
            "pr-review",
        },
        "prefixes": (),
        "seeds": ("mattpocock/skills", "obra/superpowers"),
        "pure": set(),
        "query": "code-review in:name",
    },
    {
        "title": "测试",
        "dirs": {"tdd", "test-driven-development", "webapp-testing"},
        "prefixes": (),
        "seeds": ("obra/superpowers", "anthropics/skills", "mattpocock/skills"),
        "pure": set(),
        "query": "test-driven-development OR webapp-testing in:name",
    },
    {
        "title": "调试",
        "dirs": {"systematic-debugging", "diagnosing-bugs"},
        "prefixes": (),
        "seeds": ("obra/superpowers", "mattpocock/skills"),
        "pure": set(),
        "query": "systematic-debugging OR diagnosing-bugs in:name",
    },
    {
        "title": "研究",
        "dirs": {"research", "deep-research"},
        "prefixes": (),
        "seeds": ("mattpocock/skills", "affaan-m/ECC"),
        "pure": set(),
        "query": "deep-research in:name",
    },
    {
        "title": "文档",
        "dirs": {"pdf", "docx", "pptx", "xlsx", "doc-coauthoring", "article-writing"},
        "prefixes": (),
        "seeds": ("anthropics/skills",),
        "pure": set(),
        "query": "doc-coauthoring OR article-writing in:name",
    },
    {
        "title": "安全",
        "dirs": {"agent-security-hardening", "security-guardian", "security"},
        "prefixes": (),
        "seeds": ("affaan-m/ECC",),
        "pure": set(),
        "query": "security-hardening in:name",
    },
)
BOARD_TITLES = "、".join(category["title"] for category in CATEGORIES)


def token():
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return out.strip()


def github_json(url, auth):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "skillock-leaderboard",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {auth}"} if auth else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def fetch_repo(repo, auth):
    try:
        data = github_json(f"https://api.github.com/repos/{repo}", auth)
    except urllib.error.HTTPError as err:
        return {"repo": repo, "error": f"HTTP {err.code}"}
    except urllib.error.URLError as err:
        return {"repo": repo, "error": str(err.reason)}
    return {
        "repo": repo,
        "stars": data.get("stargazers_count", 0),
        "pushed": (data.get("pushed_at") or "")[:10],
        "url": data.get("html_url") or f"https://github.com/{repo}",
        "branch": data.get("default_branch") or "main",
        "fork": bool(data.get("fork")),
    }


def hidden(parts):
    for part in parts:
        if part in {".git", "node_modules", "target", ".cursor"} or "cursor" in part.lower():
            return True
    return False


def skill_paths(tree):
    found = []
    for node in tree.get("tree") or []:
        if node.get("type") != "blob":
            continue
        path = node.get("path") or ""
        parts = path.split("/")
        if parts[-1] != "SKILL.md" or hidden(parts):
            continue
        found.append(path)
    found.sort()
    return found


def download(repo, branch, path, auth):
    quoted = urllib.parse.quote(path, safe="/")
    ref = urllib.parse.quote(branch, safe="")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{quoted}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "skillock-leaderboard",
            **({"Authorization": f"Bearer {auth}"} if auth else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def frontmatter_name(raw):
    text = raw.decode("utf-8", errors="replace")
    if not text.startswith("---"):
        return ""
    lines = text.splitlines()[1:]
    for line in lines:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def materialize(repo, branch, auth, dest):
    ref = urllib.parse.quote(branch, safe="")
    tree = github_json(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1", auth)
    paths = skill_paths(tree)
    truncated = bool(tree.get("truncated")) or len(paths) > MAX_SKILLS

    def write_one(path):
        raw = download(repo, branch, path, auth)
        relative = path
        if "/" not in path:
            name = frontmatter_name(raw) or "skill"
            relative = f"{name}/SKILL.md"
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    written = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(write_one, path) for path in paths[:MAX_SKILLS]]
        for future in as_completed(futures):
            try:
                future.result()
            except urllib.error.URLError:
                continue
            written += 1
    return written, truncated


def code_summary(findings):
    counts = Counter(item.code for item in findings)
    if not counts:
        return "通过"
    return ", ".join(f"{code} {count}" for code, count in counts.most_common(4))


def evaluate(repo, meta, auth, dest):
    written, truncated = materialize(repo, meta["branch"], auth, dest)
    if written == 0:
        return None, truncated
    files = discover([dest])
    skills = [load_skill(path) for path in files]
    report = analyze(skills, Options())
    errors = sum(item.level == "error" for item in report.findings)
    warnings = sum(item.level == "warning" for item in report.findings)
    return {
        "skills": len(report.skills),
        "startup_tokens": report.startup_tokens,
        "body_tokens": report.body_tokens,
        "errors": errors,
        "warnings": warnings,
        "codes": code_summary(report.findings),
        "truncated": truncated,
    }, truncated


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def fmt(n):
    return f"{n:,}"


def delta_text(delta):
    if delta is None:
        return "—"
    if delta > 0:
        return f"+{delta:,}"
    return f"{delta:,}"


def matches(path, category):
    parts = path.split("/")
    if not parts or parts[-1] != "SKILL.md" or hidden(parts):
        return False
    if path.startswith("docs/") or "/docs/" in f"/{path}":
        return False
    parent = parts[-2] if len(parts) > 1 else ""
    if parent in category["dirs"]:
        return True
    return any(parent.startswith(prefix) for prefix in category["prefixes"])


def search_repos(auth, query):
    quoted = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={quoted}&sort=stars&per_page=10"
    try:
        data = github_json(url, auth)
    except urllib.error.URLError as err:
        print(f"repo search failed: {err}")
        return []
    found = []
    for item in data.get("items") or []:
        name = item.get("full_name") or ""
        stars = item.get("stargazers_count") or 0
        if name and name.lower() != SELF_REPO and not item.get("fork") and stars >= MIN_STARS:
            found.append(name)
    return found


def install_command(repo, branch, path):
    if path.endswith("/SKILL.md"):
        folder = path[: -len("/SKILL.md")]
        target = f"https://github.com/{repo}/tree/{branch}/{folder}"
    else:
        target = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    return f"npx skills add {target} -g -y"


def cached_meta(repo, auth, cache):
    if repo not in cache["meta"]:
        cache["meta"][repo] = fetch_repo(repo, auth)
    return cache["meta"][repo]


def cached_skill_paths(repo, meta, auth, cache):
    if repo not in cache["paths"]:
        ref = urllib.parse.quote(meta["branch"], safe="")
        tree = github_json(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1", auth)
        cache["paths"][repo] = skill_paths(tree)
    return cache["paths"][repo]


def category_paths(repo, meta, auth, category, cache):
    paths = []
    for path in cached_skill_paths(repo, meta, auth, cache):
        if repo in category["pure"] or matches(path, category):
            paths.append(path)
    return paths[:12]


def evaluate_file(path):
    skill = load_skill(path)
    report = analyze([skill], Options())
    errors = sum(item.level == "error" for item in report.findings)
    warnings = sum(item.level == "warning" for item in report.findings)
    name = skill.name or path.parent.name
    return {
        "name": name,
        "startup_tokens": report.startup_tokens,
        "body_tokens": report.body_tokens,
        "errors": errors,
        "warnings": warnings,
        "codes": code_summary(report.findings),
    }


def _prefer_skill(row, current):
    def score(item):
        path = item["path"]
        primary = 0 if path.startswith("skills/") or "/skills/" in f"/{path}" else 1
        return (primary, -item["body_tokens"], path)

    return score(row) < score(current)


def ranked(rows):
    rows.sort(key=lambda row: (-row["startup_tokens"], -row["errors"], -row["body_tokens"], row["name"]))
    return rows


def markdown_table(rows):
    lines = [
        "| # | 技能 | 安装 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"| {i} | [{row['name']}]({row['file_url']}) | `{row['install']}` | [{row['repo']}]({row['url']}) | {fmt(row['stars'])} | {fmt(row['startup_tokens'])} | {fmt(row['body_tokens'])} | {row['errors']} | {row['warnings']} | {delta_text(row['delta'])} | {row['codes']} |"
        )
    return "\n".join(lines)


def readme_block(categories, updated):
    parts = [
        "测这些分类："
        + BOARD_TITLES
        + "。同一份正文只保留星数最高的那一处。排名按启动 token 从高到低，每 6 小时重测一次。安装列是一条命令。skillock 自己不进榜。完整页面：[Hana 测评]("
        + PAGE
        + ")。",
        "",
        f"最近一次测评：{updated}。",
        "",
    ]
    for category in categories:
        rows = category["rows"]
        parts.extend(
            [
                f"### {category['title']}",
                "",
                markdown_table(rows) if rows else f"这一期没有测到{category['title']}技能。",
                "",
            ]
        )
    return "\n".join(parts).rstrip() + "\n"


def html_row(index, row):
    command = escape(row["install"], quote=True)
    tone = "ok" if row["errors"] == 0 and row["codes"] == "通过" else "bad"
    change = ""
    if row.get("delta") not in (None, 0):
        change = f' · 较上次 {escape(delta_text(row["delta"]))}'
    return (
        "<li>"
        f'<span class="place">{index}</span>'
        '<div class="who">'
        f'<a class="skill" href="{escape(row["file_url"])}">{escape(row["name"])}</a>'
        f'<a class="repo" href="{escape(row["url"])}">{escape(row["repo"])}</a>'
        "</div>"
        f'<p class="facts">正文 {fmt(row["body_tokens"])} · 星 {fmt(row["stars"])} · <span class="{tone}">{escape(row["codes"])}</span>{change}</p>'
        '<div class="stat">'
        f"<b>{fmt(row['startup_tokens'])}</b><small>启动</small>"
        "</div>"
        f'<button type="button" data-cmd="{command}">安装</button>'
        "</li>"
    )


def html_section(index, category):
    rows = category["rows"]
    body = "".join(html_row(i, row) for i, row in enumerate(rows, start=1))
    if not body:
        body = f'<p class="empty">这一期没有测到{escape(category["title"])}技能。</p>'
    return (
        f'<section id="c{index}">'
        '<header class="cat">'
        f'<span>{index:02d}</span>'
        f"<h2>{escape(category['title'])}</h2>"
        "</header>"
        f"<ol>{body}</ol>"
        "</section>"
    )


def html_page(categories, failed, updated):
    sections = "\n".join(html_section(i, category) for i, category in enumerate(categories, start=1))
    jumps = "".join(
        f'<a href="#c{i}">{escape(category["title"])}</a>' for i, category in enumerate(categories, start=1)
    )
    fail_html = ""
    if failed:
        fail_html = '<p class="fail">没测到：' + escape(", ".join(failed)) + "</p>"
    command = escape(INSTALL, quote=True)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hana · 技能测评</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Unbounded:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #E6E0D4;
    color: #161616;
    font: 16px/1.45 "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", sans-serif;
  }}
  main {{ max-width: 980px; margin: 0 auto; padding: 12px 24px 80px; }}
  a {{ color: inherit; }}
  .hero {{
    display: grid;
    grid-template-columns: 188px 1fr;
    gap: 28px;
    align-items: end;
    padding: 28px 0 32px;
  }}
  .hero img {{ width: 188px; height: 188px; display: block; }}
  .kicker {{
    margin: 0 0 8px;
    color: #2A45F5;
    font: 700 13px/1 Unbounded, "Noto Sans SC", sans-serif;
    letter-spacing: 0.16em;
  }}
  h1 {{
    margin: 0;
    font: 700 clamp(64px, 9vw, 104px)/0.86 Unbounded, "Noto Sans SC", sans-serif;
    letter-spacing: -0.045em;
  }}
  .bar {{ width: 76px; height: 8px; margin: 16px 0 14px; background: #E24A2A; }}
  .lede {{ margin: 0; max-width: 34rem; font-size: 18px; }}
  .meta {{ margin: 8px 0 0; color: #3a342c; font-size: 14px; }}
  .install {{
    display: flex;
    width: min(100%, 640px);
    margin-top: 18px;
    border: 2px solid #161616;
  }}
  code {{
    flex: 1;
    min-width: 0;
    padding: 12px 14px;
    overflow-x: auto;
    background: transparent;
    font: 13px/1.4 ui-monospace, "SFMono-Regular", monospace;
    white-space: nowrap;
  }}
  button {{
    flex: none;
    border: 0;
    border-left: 2px solid #161616;
    background: #2A45F5;
    color: #E6E0D4;
    padding: 0 16px;
    font: 700 14px/1 "Noto Sans SC", sans-serif;
    cursor: pointer;
  }}
  button:hover {{ background: #161616; }}
  .jump {{
    position: sticky;
    top: 0;
    z-index: 3;
    display: flex;
    gap: 0;
    overflow-x: auto;
    margin: 0 -24px;
    padding: 0 12px;
    background: #E6E0D4;
    border-bottom: 2px solid #161616;
  }}
  .jump a {{
    flex: none;
    padding: 12px;
    color: #161616;
    text-decoration: none;
    font-weight: 500;
  }}
  .jump a:hover {{ background: #161616; color: #E6E0D4; }}
  section {{ padding-top: 8px; }}
  .cat {{
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin: 36px 0 0;
    padding-bottom: 10px;
    border-bottom: 2px solid #161616;
  }}
  .cat span {{
    color: #2A45F5;
    font: 700 14px/1 Unbounded, sans-serif;
  }}
  h2 {{
    margin: 0;
    font: 700 32px/1 Unbounded, "Noto Sans SC", sans-serif;
    letter-spacing: -0.04em;
  }}
  ol {{ list-style: none; margin: 0; padding: 0; }}
  li {{
    display: grid;
    grid-template-columns: 2rem minmax(0, 1fr) auto auto;
    grid-template-areas: "place who stat go" "place facts stat go";
    column-gap: 16px;
    align-items: center;
    padding: 16px 0 14px;
    border-bottom: 1px solid rgba(22, 22, 22, 0.16);
  }}
  .place {{
    grid-area: place;
    font: 700 18px/1 Unbounded, sans-serif;
  }}
  li:first-child .place {{ color: #E24A2A; }}
  .who {{ grid-area: who; min-width: 0; }}
  .skill {{
    display: block;
    overflow: hidden;
    color: #161616;
    font-weight: 700;
    font-size: 18px;
    text-decoration: none;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .skill:hover {{ color: #2A45F5; }}
  .repo {{
    display: block;
    overflow: hidden;
    color: #3a342c;
    font-size: 13px;
    text-decoration: none;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .facts {{
    grid-area: facts;
    margin: 2px 0 0;
    color: #3a342c;
    font-size: 13px;
  }}
  .ok {{ color: #161616; }}
  .bad {{ color: #E24A2A; }}
  .stat {{ grid-area: stat; text-align: right; }}
  .stat b {{
    display: block;
    font: 700 28px/1 Unbounded, sans-serif;
    letter-spacing: -0.04em;
  }}
  .delta, .stat small {{
    color: #3a342c;
    font: 12px/1.2 "Noto Sans SC", sans-serif;
  }}
  .stat small {{ display: block; margin-top: 4px; letter-spacing: 0.08em; }}
  li button {{ grid-area: go; height: 40px; }}
  .empty, .fail {{ margin: 16px 0; }}
  .fail {{ color: #E24A2A; }}
  @media (max-width: 720px) {{
    .place {{ align-self: start; padding-top: 3px; }}
    .hero {{ grid-template-columns: 1fr; gap: 8px; }}
    .hero img {{ width: 120px; height: 120px; }}
    h1 {{ font-size: 64px; }}
    .install {{ width: 100%; }}
    li {{
      grid-template-columns: 1.6rem minmax(0, 1fr) auto;
      grid-template-areas: "place who go" "place facts facts" "place stat stat";
      row-gap: 6px;
    }}
    .stat {{ text-align: left; }}
    .stat b {{ display: inline; margin-right: 8px; font-size: 22px; }}
    .stat small {{ display: inline; }}
  }}
</style>
</head>
<body>
<main>
<header class="hero">
  <img src="hana.jpg" alt="Hana">
  <div>
    <p class="kicker">SKILLOCK</p>
    <h1>Hana</h1>
    <div class="bar"></div>
    <p class="lede">公开技能按启动 token 排名。数字越大，装进去越占上下文。</p>
    <p class="meta">{escape(updated)} · 每 6 小时重测 · 同一份正文只留星数最高的一份 · <a href="https://github.com/quantz8a/skillock">skillock 不在榜上</a></p>
    <div class="install"><code>{escape(INSTALL)}</code><button type="button" data-cmd="{command}">安装 Hana</button></div>
  </div>
</header>
<nav class="jump">{jumps}</nav>
{sections}
{fail_html}
</main>
<script>
function copyText(text) {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    return navigator.clipboard.writeText(text).catch(function () {{ return fallbackCopy(text); }});
  }}
  return fallbackCopy(text);
}}
function fallbackCopy(text) {{
  var area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  var ok = document.execCommand("copy");
  area.remove();
  return ok ? Promise.resolve() : Promise.reject();
}}
document.querySelectorAll("[data-cmd]").forEach(function (btn) {{
  btn.addEventListener("click", function () {{
    var old = btn.textContent;
    copyText(btn.getAttribute("data-cmd")).then(function () {{
      btn.textContent = "已复制";
      setTimeout(function () {{ btn.textContent = old; }}, 1200);
    }});
  }});
}});
</script>
</body>
</html>
"""


def replace_readme(block):
    text = README.read_text()
    if START not in text or END not in text:
        raise SystemExit("README is missing leaderboard markers")
    pre, rest = text.split(START, 1)
    _, post = rest.split(END, 1)
    README.write_text(pre + START + "\n" + block + END + post)


def previous_startup(history, key):
    points = history.get("points") or []
    if not points or "startup" not in points[-1]:
        return None
    return points[-1]["startup"].get(key)


def candidate_repos(auth, category):
    names = list(category["seeds"])
    for name in search_repos(auth, category["query"]):
        if name not in names:
            names.append(name)
    return names


def collect(category, auth, history, root, cache):
    rows = []
    failed = []
    seen_hash = {}
    seeds = set(category["seeds"])
    for repo in candidate_repos(auth, category):
        print(f"scan {category['title']} {repo}", flush=True)
        meta = cached_meta(repo, auth, cache)
        if "error" in meta:
            failed.append(f"{repo} ({meta['error']})")
            continue
        if meta.get("fork"):
            continue
        if meta["stars"] < MIN_STARS and repo not in seeds:
            continue
        try:
            paths = category_paths(repo, meta, auth, category, cache)
        except urllib.error.HTTPError as err:
            failed.append(f"{repo} (HTTP {err.code})")
            continue
        except urllib.error.URLError as err:
            failed.append(f"{repo} ({err.reason})")
            continue
        for path in paths:
            key = (repo, path)
            try:
                if key not in cache["files"]:
                    cache["files"][key] = download(repo, meta["branch"], path, auth)
                raw = cache["files"][key]
            except urllib.error.URLError:
                failed.append(f"{repo} {path}")
                continue
            digest = hashlib.sha256(raw).hexdigest()
            current = seen_hash.get(digest)
            if current is not None and current["stars"] >= meta["stars"]:
                continue
            seen_hash[digest] = {"repo": repo, "path": path, "stars": meta["stars"], "raw": raw, "meta": meta}

    chosen = sorted(seen_hash.values(), key=lambda item: (-item["stars"], item["repo"], item["path"]))
    for item in chosen:
        repo = item["repo"]
        relative = item["path"]
        target = root / category["title"] / repo.replace("/", "__") / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item["raw"])
        measured = evaluate_file(target)
        key = f"{repo}/{measured['name']}"
        prev = previous_startup(history, key)
        branch = item["meta"]["branch"]
        file_url = f"https://github.com/{repo}/blob/{branch}/{item['path']}"
        measured.update(
            {
                "repo": repo,
                "stars": item["stars"],
                "url": item["meta"]["url"],
                "file_url": file_url,
                "path": item["path"],
                "install": install_command(repo, branch, item["path"]),
                "delta": None if prev is None else measured["startup_tokens"] - prev,
                "key": key,
            }
        )
        rows.append(measured)

    collapsed = {}
    for row in rows:
        key = (row["repo"], row["name"])
        current = collapsed.get(key)
        if current is None or _prefer_skill(row, current):
            collapsed[key] = row
    kept = []
    counts = Counter()
    for row in ranked(list(collapsed.values())):
        if counts[row["repo"]] >= MAX_PER_REPO:
            continue
        kept.append(row)
        counts[row["repo"]] += 1
        if len(kept) >= MAX_ROWS:
            break
    return kept, failed


def main():
    auth = token()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = load_json(HISTORY, {"points": []})
    categories = []
    failed = []
    startup = {}
    cache = {"meta": {}, "paths": {}, "files": {}}
    with tempfile.TemporaryDirectory(prefix="skillock-board-") as tmp:
        root = Path(tmp)
        for category in CATEGORIES:
            rows, errors = collect(category, auth, history, root, cache)
            categories.append({"title": category["title"], "rows": rows})
            failed.extend(errors)
            for row in rows:
                startup[row["key"]] = row["startup_tokens"]
    history["points"].append({"t": now.isoformat(), "startup": startup})
    history["points"] = history["points"][-MAX_POINTS:]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    updated = now.strftime("%Y-%m-%d %H:%M UTC")
    board = {"updated": now.isoformat(), "install": INSTALL, "categories": categories, "failed": failed}
    BOARD.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n")
    DOCS.mkdir(exist_ok=True)
    logo = ROOT / "assets" / "hana.jpg"
    if logo.exists():
        shutil.copyfile(logo, DOCS / "hana.jpg")
    (DOCS / "index.html").write_text(html_page(categories, failed, updated))
    (DOCS / ".nojekyll").write_text("")
    replace_readme(readme_block(categories, updated))
    counted = sum(len(category["rows"]) for category in categories)
    print(f"ranked {counted} skills across {len(categories)} categories, failed {len(failed)}")
    if failed:
        print("failed: " + "; ".join(failed[:12]))


if __name__ == "__main__":
    main()
