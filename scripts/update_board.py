#!/usr/bin/env python3
"""Evaluate public skill repos with skillock and rewrite the Pages site plus the README."""

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
TYPE_ORDER = ("省 token", "记忆", "设计", "规划", "综合")


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
    }


def skill_paths(tree):
    found = []
    for node in tree.get("tree") or []:
        if node.get("type") != "blob":
            continue
        path = node.get("path") or ""
        parts = path.split("/")
        if parts[-1] != "SKILL.md":
            continue
        if any(part in {".git", "node_modules", "target", ".cursor"} for part in parts):
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


def ranked(rows):
    rows = [row for row in rows if "startup_tokens" in row]
    rows.sort(key=lambda row: (-row["startup_tokens"], -row["errors"], row["repo"]))
    return rows


def markdown_table(rows):
    lines = [
        "| # | 仓库 | 技能 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for i, row in enumerate(rows, start=1):
        count = fmt(row["skills"])
        if row.get("truncated"):
            count += "+"
        lines.append(
            f"| {i} | [{row['repo']}]({row['url']}) | {count} | {fmt(row['startup_tokens'])} | {fmt(row['body_tokens'])} | {row['errors']} | {row['warnings']} | {delta_text(row['delta'])} | {row['codes']} |"
        )
    return "\n".join(lines)


def readme_block(groups, updated):
    parts = [
        "Hana 把每个公开仓库当成一组已经装上的技能，跑 skillock 的检查。启动 token 是还没选中任何一个技能之前就要付的成本，高的排在前面。每 6 小时重测一次。skillock 自己不进榜。完整页面：[Hana 测评]("
        + PAGE
        + ")。",
        "",
        f"最近一次测评：{updated}。",
        "",
    ]
    for title, rows in groups:
        parts.append(f"### {title}")
        parts.append("")
        if rows:
            parts.append(markdown_table(rows))
        else:
            parts.append("这一类这次没有测到。")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def html_page(groups, failed, updated):
    sections = []
    for title, rows in groups:
        body = []
        for i, row in enumerate(rows, start=1):
            count = fmt(row["skills"]) + ("+" if row.get("truncated") else "")
            body.append(
                "<tr>"
                f"<td>{i}</td>"
                f"<td><a href=\"{escape(row['url'])}\">{escape(row['repo'])}</a></td>"
                f"<td class=\"num\">{count}</td>"
                f"<td class=\"num\">{fmt(row['startup_tokens'])}</td>"
                f"<td class=\"num\">{fmt(row['body_tokens'])}</td>"
                f"<td class=\"num\">{row['errors']}</td>"
                f"<td class=\"num\">{row['warnings']}</td>"
                f"<td class=\"num\">{escape(delta_text(row['delta']))}</td>"
                f"<td>{escape(row['codes'])}</td>"
                "</tr>"
            )
        sections.append(
            f"<h2>{escape(title)}</h2>"
            "<table><thead><tr><th>#</th><th>仓库</th><th>技能</th><th>启动 token</th><th>正文 token</th><th>错误</th><th>警告</th><th>较上次</th><th>检查</th></tr></thead>"
            f"<tbody>{''.join(body) or '<tr><td colspan=\"9\">这一类这次没有测到。</td></tr>'}</tbody></table>"
        )
    fail_html = ""
    if failed:
        fail_html = "<p class=\"fail\">没测到：" + escape(", ".join(failed)) + "</p>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hana · 技能测评</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #E6E0D4; color: #161616; font: 16px/1.45 "Iowan Old Style", Palatino, "Songti SC", serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
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
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .fail {{ color: #E24A2A; }}
</style>
</head>
<body>
<main>
<header>
  <img src="hana.jpg" alt="Hana">
  <div>
    <h1>技能测评</h1>
    <p class="meta">测评时间 {escape(updated)} · 每 6 小时一次 · skillock 检查启动 token、正文 token、规范错误和冲突指令</p>
    <p class="meta"><a href="https://github.com/quantz8a/skillock">skillock</a> 不在这张榜上。每一类按启动 token 从高到低排列。</p>
  </div>
</header>
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


def previous_startup(history, repo):
    points = history.get("points") or []
    if not points or "startup" not in points[-1]:
        return None
    return points[-1]["startup"].get(repo)


def main():
    catalog = [item for item in json.loads(CATALOG.read_text()) if item["repo"].lower() != SELF_REPO]
    auth = token()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = load_json(HISTORY, {"points": []})
    rows = []
    failed = []
    with tempfile.TemporaryDirectory(prefix="skillock-board-") as tmp:
        root = Path(tmp)
        for item in catalog:
            repo = item["repo"]
            print(f"evaluate {repo}", flush=True)
            meta = fetch_repo(repo, auth)
            if "error" in meta:
                failed.append(f"{repo} ({meta['error']})")
                continue
            try:
                measured, _truncated = evaluate(repo, meta, auth, root / repo.replace("/", "__"))
            except urllib.error.HTTPError as err:
                failed.append(f"{repo} (HTTP {err.code})")
                continue
            except urllib.error.URLError as err:
                failed.append(f"{repo} ({err.reason})")
                continue
            if measured is None:
                failed.append(f"{repo} (no SKILL.md)")
                continue
            prev = previous_startup(history, repo)
            measured.update(
                {
                    "repo": repo,
                    "type": item.get("type") or "综合",
                    "url": meta["url"],
                    "pushed": meta["pushed"],
                    "delta": None if prev is None else measured["startup_tokens"] - prev,
                }
            )
            rows.append(measured)

    history["points"].append(
        {
            "t": now.isoformat(),
            "startup": {row["repo"]: row["startup_tokens"] for row in rows},
        }
    )
    history["points"] = history["points"][-MAX_POINTS:]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    order = [title for title in TYPE_ORDER if any(row["type"] == title for row in rows)]
    for row in rows:
        if row["type"] not in order:
            order.append(row["type"])
    groups = [(title, ranked([row for row in rows if row["type"] == title])) for title in order]
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
    (DOCS / "index.html").write_text(html_page(groups, failed, updated))
    (DOCS / ".nojekyll").write_text("")
    replace_readme(readme_block(groups, updated))
    print(f"evaluated {len(rows)} repos, failed {len(failed)}")
    if failed:
        print("failed: " + "; ".join(failed))


if __name__ == "__main__":
    main()
