#!/usr/bin/env python3
"""Crawl the curated skill repos and rewrite the Pages site plus the README table."""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.json"
HISTORY = ROOT / "data" / "history.json"
BOARD = ROOT / "data" / "board.json"
DOCS = ROOT / "docs"
README = ROOT / "README.md"
START = "<!-- leaderboard:start -->"
END = "<!-- leaderboard:end -->"
MAX_POINTS = 120
PAGE = "https://quantz8a.github.io/skillock/"
SELF_REPO = "quantz8a/skillock"
SEARCHES = (
    "filename:SKILL.md path:skills",
    "filename:SKILL.md path:.agents/skills",
    "filename:SKILL.md path:.codex/skills",
    "filename:SKILL.md path:.claude/skills",
)


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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def search_skill_repos(auth):
    found = {}
    for query in SEARCHES:
        url = "https://api.github.com/search/code?q=" + urllib.parse.quote(query) + "&per_page=100"
        try:
            data = github_json(url, auth)
        except urllib.error.HTTPError as err:
            print(f"search failed for {query}: HTTP {err.code}")
            continue
        except urllib.error.URLError as err:
            print(f"search failed for {query}: {err.reason}")
            continue
        for item in data.get("items") or []:
            repo = item.get("repository") or {}
            name = repo.get("full_name") or ""
            if not name or name.lower() == SELF_REPO:
                continue
            slot = found.setdefault(name, {"hits": 0, "url": repo.get("html_url") or f"https://github.com/{name}"})
            slot["hits"] += 1
    return found


def fetch(repo, auth):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "skillock-leaderboard",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {auth}"} if auth else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return {"repo": repo, "error": f"HTTP {err.code}"}
    except urllib.error.URLError as err:
        return {"repo": repo, "error": str(err.reason)}
    return {
        "repo": repo,
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "pushed": (data.get("pushed_at") or "")[:10],
        "url": data.get("html_url") or f"https://github.com/{repo}",
        "fork": bool(data.get("fork")),
    }


def load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def previous_stars(history, repo):
    points = history.get("points") or []
    if len(points) < 2:
        return None
    older = points[-2]["stars"].get(repo)
    return older


def week_stars(history, repo, now):
    cutoff = now - timedelta(days=7)
    chosen = None
    for point in history.get("points") or []:
        stamp = datetime.fromisoformat(point["t"])
        if stamp <= cutoff:
            chosen = point["stars"].get(repo)
    return chosen


def fmt(n):
    return f"{n:,}"


def delta_text(delta):
    if delta is None:
        return "—"
    if delta > 0:
        return f"+{delta:,}"
    return f"{delta:,}"


def short(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def ranked(rows):
    ok = [row for row in rows if "stars" in row]
    ok.sort(key=lambda row: (-row["stars"], row["repo"]))
    return ok


def markdown_table(rows):
    lines = ["| # | 仓库 | 星 | 较上次 | 最近推送 |", "| ---: | --- | ---: | ---: | --- |"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"| {i} | [{row['repo']}]({row['url']}) | {fmt(row['stars'])} | {delta_text(row['delta'])} | {row['pushed']} |"
        )
    return "\n".join(lines)


def readme_block(groups, updated):
    parts = [
        f"从 GitHub 的 `skills/`、`.agents/skills`、`.codex/skills`、`.claude/skills` 里扫到的技能仓库，按星数排序。每 6 小时爬一次。skillock 自己不进榜。完整页面：[Hana 排行]({PAGE})。",
        "",
        f"最近一次写入 README 的爬取时间：{updated}。",
        "",
    ]
    for title, rows in groups:
        parts.append(f"### {title}")
        parts.append("")
        if rows:
            parts.append(markdown_table(rows))
        else:
            parts.append("这一类这次没有爬到。")
        parts.append("")
    failed = []
    return "\n".join(parts).rstrip() + "\n", failed


def html_page(groups, failed, updated, rising):
    sections = []
    for title, rows in groups:
        body = []
        for i, row in enumerate(rows, start=1):
            body.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td><a href=\"{escape(row['url'])}\">{escape(row['repo'])}</a></td>"
                f"<td class=\"num\">{fmt(row['stars'])}</td>"
                f"<td class=\"num\">{escape(delta_text(row['delta']))}</td>"
                f"<td class=\"num\">{fmt(row['forks'])}</td>"
                f"<td>{escape(row['pushed'])}</td>"
                "</tr>"
            )
        sections.append(
            f"<h2>{escape(title)}</h2>"
            "<table><thead><tr><th>#</th><th>仓库</th><th>星</th><th>较上次</th><th>Fork</th><th>最近推送</th></tr></thead>"
            f"<tbody>{''.join(body) or '<tr><td colspan=\"6\">这一类这次没有爬到。</td></tr>'}</tbody></table>"
        )
    rise_html = ""
    if rising:
        items = []
        for row in rising:
            items.append(
                "<tr>"
                f"<td><a href=\"{escape(row['url'])}\">{escape(row['repo'])}</a></td>"
                f"<td>{escape(row['category'])}</td>"
                f"<td class=\"num\">{escape(delta_text(row['week']))}</td>"
                f"<td class=\"num\">{fmt(row['stars'])}</td>"
                "</tr>"
            )
        rise_html = (
            "<h2>近 7 日涨星</h2>"
            "<table><thead><tr><th>仓库</th><th>类</th><th>7 日</th><th>星</th></tr></thead>"
            f"<tbody>{''.join(items)}</tbody></table>"
        )
    fail_html = ""
    if failed:
        fail_html = "<p class=\"fail\">没爬到：" + escape(", ".join(failed)) + "</p>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hana · 同类技能排行</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #E6E0D4; color: #161616; font: 16px/1.45 "Iowan Old Style", Palatino, "Songti SC", serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display: flex; gap: 20px; align-items: center; }}
  img {{ width: 88px; height: 88px; }}
  h1 {{ font-size: 32px; margin: 0; letter-spacing: -0.03em; }}
  h2 {{ font-size: 20px; margin: 36px 0 8px; }}
  p {{ margin: 8px 0; }}
  a {{ color: #2A45F5; }}
  .meta {{ color: #3a342c; }}
  table {{ width: 100%; border-collapse: collapse; background: #f4f0e8; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #d9d1c3; vertical-align: top; }}
  th {{ font: 12px/1.2 ui-sans-serif, sans-serif; letter-spacing: 0.04em; }}
  td.num, th:nth-child(n+3) {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td:last-child {{ text-align: left; }}
  .fail {{ color: #E24A2A; }}
</style>
</head>
<body>
<main>
<header>
  <img src="hana.jpg" alt="Hana">
  <div>
    <h1>同类技能排行</h1>
    <p class="meta">爬取时间 {escape(updated)} · 每 6 小时一次 · 扫 GitHub 上的 SKILL.md</p>
    <p class="meta"><a href="https://github.com/quantz8a/skillock">skillock</a> 不在这张榜上。榜只按公开仓库的星数排列，不是安装建议。</p>
  </div>
</header>
{rise_html}
{''.join(sections)}
{fail_html}
</main>
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


def main():
    catalog = [item for item in json.loads(CATALOG.read_text()) if item["repo"].lower() != SELF_REPO]
    catalog_names = {item["repo"] for item in catalog}
    auth = token()
    discovered = search_skill_repos(auth)
    extra_names = [name for name in discovered if name not in catalog_names]
    extra_names.sort(key=lambda name: (-discovered[name]["hits"], name))
    targets = {item["repo"]: item["category"] for item in catalog}
    for name in extra_names[:40]:
        targets[name] = "技能包"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = load_json(HISTORY, {"points": []})
    previous = history["points"][-1]["stars"] if history["points"] else {}
    week_point = None
    cutoff = now - timedelta(days=7)
    for point in history["points"]:
        if datetime.fromisoformat(point["t"]) <= cutoff:
            week_point = point["stars"]

    rows = []
    failed = []
    for repo, category in targets.items():
        got = fetch(repo, auth)
        if "error" in got:
            failed.append(f"{repo} ({got['error']})")
            continue
        if got["fork"] and repo not in catalog_names:
            continue
        got["category"] = category
        prev = previous.get(got["repo"])
        got["delta"] = None if prev is None else got["stars"] - prev
        if week_point and got["repo"] in week_point:
            got["week"] = got["stars"] - week_point[got["repo"]]
        else:
            got["week"] = None
        rows.append(got)

    extras = sorted(
        (row for row in rows if row["repo"] not in catalog_names),
        key=lambda row: (-row["stars"], row["repo"]),
    )[:15]
    rows = [row for row in rows if row["repo"] in catalog_names] + extras

    history["points"].append(
        {"t": now.isoformat(), "stars": {row["repo"]: row["stars"] for row in rows}}
    )
    history["points"] = history["points"][-MAX_POINTS:]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    order = []
    for item in catalog:
        if item["category"] not in order:
            order.append(item["category"])
    groups = [(title, ranked([row for row in rows if row["category"] == title])) for title in order]
    rising = [row for row in rows if row["week"] not in (None, 0)]
    rising.sort(key=lambda row: (-row["week"], -row["stars"]))

    updated = now.strftime("%Y-%m-%d %H:%M UTC")
    board = {
        "updated": now.isoformat(),
        "groups": {title: group for title, group in groups},
        "failed": failed,
    }
    BOARD.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n")

    DOCS.mkdir(exist_ok=True)
    logo = ROOT / "assets" / "hana.jpg"
    if logo.exists():
        shutil.copyfile(logo, DOCS / "hana.jpg")
    (DOCS / "index.html").write_text(html_page(groups, failed, updated, rising[:8]))
    (DOCS / ".nojekyll").write_text("")
    replace_readme(readme_block(groups, updated)[0])
    print(f"crawled {len(rows)} repos, failed {len(failed)}")


if __name__ == "__main__":
    main()
