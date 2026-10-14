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
CATEGORY = "界面设计"
DESIGN_DIRS = {
    "frontend-design",
    "ui-ux",
    "ui-ux-pro-max",
    "taste",
    "impeccable",
    "design-system",
    "web-design",
    "design",
}
SEEDS = (
    "nextlevelbuilder/ui-ux-pro-max-skill",
    "Leonxlnx/taste-skill",
    "pbakaus/impeccable",
    "anthropics/skills",
    "affaan-m/ECC",
)
PURE = {
    "nextlevelbuilder/ui-ux-pro-max-skill",
    "Leonxlnx/taste-skill",
    "pbakaus/impeccable",
}
MIN_STARS = 5000
MAX_ROWS = 12
MAX_PER_REPO = 3


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


def is_design_skill(path):
    parts = path.split("/")
    if not parts or parts[-1] != "SKILL.md" or ".cursor" in parts:
        return False
    parent = parts[-2] if len(parts) > 1 else ""
    return parent in DESIGN_DIRS or parent.startswith("ui-ux")


def search_repos(auth):
    query = urllib.parse.quote("frontend-design OR ui-ux-pro-max OR taste-skill OR impeccable")
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&per_page=15"
    try:
        data = github_json(url, auth)
    except urllib.error.URLError as err:
        print(f"repo search failed: {err}")
        return []
    found = []
    for item in data.get("items") or []:
        name = item.get("full_name") or ""
        if name and name.lower() != SELF_REPO and not item.get("fork"):
            found.append(name)
    return found


def design_paths(repo, meta, auth):
    ref = urllib.parse.quote(meta["branch"], safe="")
    tree = github_json(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1", auth)
    paths = []
    for path in skill_paths(tree):
        if path.startswith("docs/") or "/docs/" in f"/{path}":
            continue
        if repo in PURE or is_design_skill(path):
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
        "| # | 技能 | 仓库 | 星 | 启动 token | 正文 token | 错误 | 警告 | 较上次 | 检查 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"| {i} | [{row['name']}]({row['file_url']}) | [{row['repo']}]({row['url']}) | {fmt(row['stars'])} | {fmt(row['startup_tokens'])} | {fmt(row['body_tokens'])} | {row['errors']} | {row['warnings']} | {delta_text(row['delta'])} | {row['codes']} |"
        )
    return "\n".join(lines)


def readme_block(rows, updated):
    parts = [
        "这一期只测界面设计。候选来自星数较高的仓库里、目录名是 `frontend-design`、`ui-ux`、`taste`、`impeccable`、`design-system`、`web-design` 的 `SKILL.md`。同一份正文只保留星数最高的那一处。排名按启动 token 从高到低，每 6 小时重测一次。skillock 自己不进榜。完整页面：[Hana 测评]("
        + PAGE
        + ")。",
        "",
        f"最近一次测评：{updated}。",
        "",
        "### 界面设计",
        "",
        markdown_table(rows) if rows else "这一期没有测到界面设计技能。",
        "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def html_page(rows, failed, updated):
    body = []
    for i, row in enumerate(rows, start=1):
        body.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td><a href=\"{escape(row['file_url'])}\">{escape(row['name'])}</a></td>"
            f"<td><a href=\"{escape(row['url'])}\">{escape(row['repo'])}</a></td>"
            f"<td class=\"num\">{fmt(row['stars'])}</td>"
            f"<td class=\"num\">{fmt(row['startup_tokens'])}</td>"
            f"<td class=\"num\">{fmt(row['body_tokens'])}</td>"
            f"<td class=\"num\">{row['errors']}</td>"
            f"<td class=\"num\">{row['warnings']}</td>"
            f"<td class=\"num\">{escape(delta_text(row['delta']))}</td>"
            f"<td>{escape(row['codes'])}</td>"
            "</tr>"
        )
    table = (
        "<h2>界面设计</h2>"
        "<table><thead><tr><th>#</th><th>技能</th><th>仓库</th><th>星</th><th>启动 token</th><th>正文 token</th><th>错误</th><th>警告</th><th>较上次</th><th>检查</th></tr></thead>"
        f"<tbody>{''.join(body) or '<tr><td colspan=\"10\">这一期没有测到。</td></tr>'}</tbody></table>"
    )
    fail_html = ""
    if failed:
        fail_html = "<p class=\"fail\">没测到：" + escape(", ".join(failed)) + "</p>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hana · 界面设计测评</title>
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
    <h1>界面设计</h1>
    <p class="meta">测评时间 {escape(updated)} · 每 6 小时一次 · 只测这一类技能</p>
    <p class="meta">同一份正文只保留星数最高的那一处。排名按启动 token 从高到低。<a href="https://github.com/quantz8a/skillock">skillock</a> 不在榜上。</p>
  </div>
</header>
{table}
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


def previous_startup(history, key):
    points = history.get("points") or []
    if not points or "startup" not in points[-1]:
        return None
    return points[-1]["startup"].get(key)


def candidate_repos(auth):
    names = list(SEEDS)
    for name in search_repos(auth):
        if name not in names:
            names.append(name)
    return names


def main():
    auth = token()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    history = load_json(HISTORY, {"points": []})
    rows = []
    failed = []
    seen_hash = {}
    with tempfile.TemporaryDirectory(prefix="skillock-design-") as tmp:
        root = Path(tmp)
        for repo in candidate_repos(auth):
            print(f"scan {repo}", flush=True)
            meta = fetch_repo(repo, auth)
            if "error" in meta:
                failed.append(f"{repo} ({meta['error']})")
                continue
            if meta.get("fork"):
                continue
            seeded = repo in SEEDS
            if meta["stars"] < MIN_STARS and not seeded:
                continue
            try:
                paths = design_paths(repo, meta, auth)
            except urllib.error.HTTPError as err:
                failed.append(f"{repo} (HTTP {err.code})")
                continue
            except urllib.error.URLError as err:
                failed.append(f"{repo} ({err.reason})")
                continue
            for path in paths:
                try:
                    raw = download(repo, meta["branch"], path, auth)
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
            target = root / repo.replace("/", "__") / relative
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
    rows = []
    counts = Counter()
    for row in ranked(list(collapsed.values())):
        if counts[row["repo"]] >= MAX_PER_REPO:
            continue
        rows.append(row)
        counts[row["repo"]] += 1
        if len(rows) >= MAX_ROWS:
            break
    history["points"].append(
        {"t": now.isoformat(), "startup": {row["key"]: row["startup_tokens"] for row in rows}}
    )
    history["points"] = history["points"][-MAX_POINTS:]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    updated = now.strftime("%Y-%m-%d %H:%M UTC")
    board = {"updated": now.isoformat(), "category": CATEGORY, "rows": rows, "failed": failed}
    BOARD.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n")
    DOCS.mkdir(exist_ok=True)
    logo = ROOT / "assets" / "hana.jpg"
    if logo.exists():
        shutil.copyfile(logo, DOCS / "hana.jpg")
    (DOCS / "index.html").write_text(html_page(rows, failed, updated))
    (DOCS / ".nojekyll").write_text("")
    replace_readme(readme_block(rows, updated))
    print(f"ranked {len(rows)} design skills, failed {len(failed)}")
    if failed:
        print("failed: " + "; ".join(failed[:12]))


if __name__ == "__main__":
    main()
