"""Command line for the Python build of Hana."""

from __future__ import annotations

import sys
from pathlib import Path

from skillock.engine import (
    Options,
    Version,
    analyze,
    canonical_product,
    diff_lock,
    discover,
    load_skill,
    local_roots,
    optimize,
    plan_report,
    read_lock,
    render,
    render_plan,
    to_json,
    user_roots,
    write_lock,
)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg in ("-h", "--help", "help") for arg in args):
        print(_HELP)
        return 0
    if args and args[0] in ("check", "lock", "optimize"):
        command, rest = args[0], args[1:]
    else:
        command, rest = "check", args
    cwd = Path.cwd()
    try:
        cli = _parse(cwd, rest)
    except ValueError as err:
        print(f"skillock: {err}", file=sys.stderr)
        print("run `skillock --help` for usage", file=sys.stderr)
        return 2
    if command == "lock":
        cli["write"] = True
    if command == "optimize":
        cli["read_existing"] = False
        return _optimize(cwd, cli)
    return _run(cwd, cli)


def _parse(cwd, args):
    cli = {
        "strict": False,
        "json": False,
        "write": False,
        "read_existing": True,
        "user": False,
        "lockfile": cwd / "SKILLOCK.toml",
        "options": Options(),
        "paths": [],
    }
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--strict":
            cli["strict"] = True
        elif arg == "--json":
            cli["json"] = True
        elif arg == "--lock":
            cli["write"] = True
        elif arg == "--no-lock":
            cli["read_existing"] = False
        elif arg == "--user":
            cli["user"] = True
        elif arg in ("--budget", "--body-budget", "--harness", "--lockfile"):
            if i + 1 >= len(args):
                raise ValueError(f"{arg} needs a value")
            value = args[i + 1]
            i += 1
            if arg == "--budget":
                cli["options"].startup_budget = _usize(value, "--budget")
            elif arg == "--body-budget":
                cli["options"].body_budget = _usize(value, "--body-budget")
            elif arg == "--harness":
                cli["options"].harness = _harness(value)
            else:
                cli["lockfile"] = cwd / value
        elif arg.startswith("-"):
            raise ValueError(f"unknown flag {arg}")
        else:
            cli["paths"].append(Path(arg))
        i += 1
    return cli


def _usize(value, flag):
    if not value.isdigit():
        raise ValueError(f"{flag} expects a non-negative integer, got {value}")
    return int(value)


def _harness(value):
    found = {}
    if not value:
        return found
    for piece in value.split(","):
        if "=" not in piece:
            raise ValueError(f"--harness entry `{piece}` should look like opencode=2.0.1")
        name, version = piece.split("=", 1)
        parsed = Version.parse(version)
        if parsed is None:
            raise ValueError(f"cannot parse harness version `{version}`")
        found[canonical_product(name)] = parsed
    return found


def _collect(cwd, cli):
    if cli["paths"]:
        roots = cli["paths"]
    else:
        roots = local_roots(cwd)
        if cli["user"] or not roots:
            roots.extend(user_roots())
        if not roots:
            roots.append(cwd)
    files = discover(roots)
    return [load_skill(path) for path in files]


def _optimize(cwd, cli):
    skills = _collect(cwd, cli)
    if not skills:
        print("0 skills · no SKILL.md under the scanned paths")
        return 0
    plan = optimize(skills, cli["options"])
    if cli["json"]:
        import json

        sys.stdout.write(
            json.dumps(
                {
                    "startup_tokens": plan.startup_tokens,
                    "body_tokens": plan.body_tokens,
                    "harness": {name: str(version) for name, version in plan.harness.items()},
                    "keep": [_display_skill(skill) for skill in plan.kept],
                    "drop": [
                        {"reason": item.reason, "skill": item.skill.name, "detail": item.detail}
                        for item in plan.dropped
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    else:
        sys.stdout.write(render_plan(plan))
    if cli["write"]:
        try:
            write_lock(cli["lockfile"], cwd, plan_report(plan))
        except OSError as err:
            print(f"skillock: could not write {cli['lockfile']}: {err}", file=sys.stderr)
            return 2
        if not cli["json"]:
            print(f"wrote {cli['lockfile']}", file=sys.stderr)
    if not plan.kept:
        return 1
    report = analyze(plan.kept, cli["options"])
    errors = any(item.level == "error" for item in report.findings)
    warnings = any(item.level == "warning" for item in report.findings)
    if errors or (cli["strict"] and warnings):
        return 1
    return 0


def _display_skill(skill):
    return {"name": skill.name, "path": str(skill.path).replace("\\", "/")}


def _run(cwd, cli):
    skills = _collect(cwd, cli)
    report = analyze(skills, cli["options"])
    if cli["read_existing"] and cli["lockfile"].is_file():
        try:
            lock = read_lock(cli["lockfile"])
        except OSError as err:
            print(f"skillock: could not read {cli['lockfile']}: {err}", file=sys.stderr)
            return 2
        report.findings.extend(diff_lock(cwd, report, lock))
    if cli["json"]:
        sys.stdout.write(to_json(report))
    elif not skills:
        print("0 skills · no SKILL.md under the scanned paths")
    else:
        sys.stdout.write(render(report))
    if cli["write"]:
        try:
            write_lock(cli["lockfile"], cwd, report)
        except OSError as err:
            print(f"skillock: could not write {cli['lockfile']}: {err}", file=sys.stderr)
            return 2
        if not cli["json"]:
            print(f"wrote {cli['lockfile']}", file=sys.stderr)
    errors = any(item.level == "error" for item in report.findings)
    warnings = any(item.level == "warning" for item in report.findings)
    if errors or (cli["strict"] and warnings):
        return 1
    return 0


_HELP = """\
skillock — lockfile for agent skills

Usage:
  skillock check [options] [paths...]
  skillock lock  [options] [paths...]
  skillock optimize [options] [paths...]

optimize keeps a set that can be installed together. It drops an invalid
manifest, a duplicate name, a harness pin the installed version misses,
and, when pins still disagree, the skill that conflicts with the most
others. If startup tokens are still over --budget, it drops the largest
names and descriptions. It does not edit or delete SKILL.md files.
--lock writes that kept set to SKILLOCK.toml.

With no paths, skillock scans ./skills, ./examples, and the
.agents, .claude, and .codex skill directories in the
current project. Add --user to also scan those directories in $HOME.
If the project has none, the home directories are scanned anyway.

Options:
  --harness name=version[,name=version...]
      Installed harness versions. A skill pin that excludes one is an error.
  --budget N            Startup token budget for every name + description (default 4000)
  --body-budget N       Per-skill body budget, loaded on activation (default 5000)
  --lock                Write SKILLOCK.toml after check
  --lockfile PATH       Lockfile path (default ./SKILLOCK.toml)
  --no-lock             Do not compare against an existing lockfile
  --user                Also scan skill directories in $HOME
  --strict              Exit 1 on warnings as well as errors
  --json                Print the report as JSON
  -h, --help            Show this help

Token estimates use 4 ASCII characters per token and 1 token per
non-ASCII character. They are a budget, not a model tokenizer.

This is the Python build. It uses the standard library only.
"""
