#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use std::env;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use skillock::{
    analyze, canonical_product, diff_lock, discover, load_skill, local_roots, read_lock, render,
    to_json, user_roots, write_lock, Level, Options, Version,
};

struct Cli {
    strict: bool,
    json: bool,
    write: bool,
    read_existing: bool,
    user: bool,
    lockfile: PathBuf,
    options: Options,
    paths: Vec<PathBuf>,
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    if args
        .iter()
        .any(|arg| arg == "-h" || arg == "--help" || arg == "help")
    {
        print_help();
        return ExitCode::SUCCESS;
    }
    let (command, rest) = match args.first().map(String::as_str) {
        Some("check") => ("check", &args[1..]),
        Some("lock") => ("lock", &args[1..]),
        _ => ("check", args.as_slice()),
    };
    let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    match parse_args(&cwd, rest) {
        Ok(mut cli) => {
            if command == "lock" {
                cli.write = true;
            }
            run(&cwd, &cli)
        }
        Err(err) => {
            eprintln!("skillock: {err}");
            eprintln!("run `skillock --help` for usage");
            ExitCode::from(2)
        }
    }
}

fn parse_args(cwd: &Path, args: &[String]) -> Result<Cli, String> {
    let mut cli = Cli {
        strict: false,
        json: false,
        write: false,
        read_existing: true,
        user: false,
        lockfile: cwd.join("SKILLOCK.toml"),
        options: Options::default(),
        paths: Vec::new(),
    };
    let mut i = 0;
    while i < args.len() {
        let arg = &args[i];
        match arg.as_str() {
            "--strict" => cli.strict = true,
            "--json" => cli.json = true,
            "--lock" => cli.write = true,
            "--no-lock" => cli.read_existing = false,
            "--user" => cli.user = true,
            "--budget" | "--body-budget" | "--harness" | "--lockfile" => {
                let value = args
                    .get(i + 1)
                    .ok_or_else(|| format!("{arg} needs a value"))?;
                match arg.as_str() {
                    "--budget" => {
                        cli.options.startup_budget = parse_usize(value, "--budget")?;
                    }
                    "--body-budget" => {
                        cli.options.body_budget = parse_usize(value, "--body-budget")?;
                    }
                    "--harness" => cli.options.harness = parse_harness(value)?,
                    "--lockfile" => cli.lockfile = cwd.join(value),
                    _ => {}
                }
                i += 1;
            }
            other if other.starts_with('-') => return Err(format!("unknown flag {other}")),
            other => cli.paths.push(PathBuf::from(other)),
        }
        i += 1;
    }
    Ok(cli)
}

fn parse_usize(value: &str, flag: &str) -> Result<usize, String> {
    value
        .parse::<usize>()
        .map_err(|_| format!("{flag} expects a non-negative integer, got {value}"))
}

fn parse_harness(value: &str) -> Result<BTreeMap<String, Version>, String> {
    let mut map = BTreeMap::new();
    if value.is_empty() {
        return Ok(map);
    }
    for piece in value.split(',') {
        let (name, version) = piece
            .split_once('=')
            .ok_or_else(|| format!("--harness entry `{piece}` should look like opencode=2.0.1"))?;
        let version = Version::parse(version)
            .ok_or_else(|| format!("cannot parse harness version `{version}`"))?;
        map.insert(canonical_product(name), version);
    }
    Ok(map)
}

fn run(cwd: &Path, cli: &Cli) -> ExitCode {
    let roots = if cli.paths.is_empty() {
        let mut roots = local_roots(cwd);
        if cli.user || roots.is_empty() {
            roots.extend(user_roots());
        }
        if roots.is_empty() {
            roots.push(cwd.to_path_buf());
        }
        roots
    } else {
        cli.paths.clone()
    };
    let files = discover(&roots);
    let skills: Vec<_> = files.iter().map(|path| load_skill(path)).collect();
    let mut report = analyze(&skills, &cli.options);
    if cli.read_existing && cli.lockfile.is_file() {
        match read_lock(&cli.lockfile) {
            Ok(lock) => report.findings.extend(diff_lock(cwd, &report, &lock)),
            Err(err) => {
                eprintln!("skillock: could not read {}: {err}", cli.lockfile.display());
                return ExitCode::from(2);
            }
        }
    }
    if cli.json {
        print!("{}", to_json(&report));
    } else if skills.is_empty() {
        println!("0 skills · no SKILL.md under the scanned paths");
    } else {
        print!("{}", render(&report));
    }
    if cli.write {
        if let Err(err) = write_lock(&cli.lockfile, cwd, &report) {
            eprintln!(
                "skillock: could not write {}: {err}",
                cli.lockfile.display()
            );
            return ExitCode::from(2);
        }
        if !cli.json {
            eprintln!("wrote {}", cli.lockfile.display());
        }
    }
    let errors = report.findings.iter().any(|f| f.level == Level::Error);
    let warnings = report.findings.iter().any(|f| f.level == Level::Warning);
    if errors || (cli.strict && warnings) {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}

fn print_help() {
    println!(
        "\
skillock — lockfile for agent skills

Usage:
  skillock check [options] [paths...]
  skillock lock  [options] [paths...]

With no paths, skillock scans ./skills, ./examples, and the
.agents, .claude, .codex, and .cursor skill directories in the
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
"
    );
}
