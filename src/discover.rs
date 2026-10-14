use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

const SKIP_DIRS: &[&str] = &[".git", "target", "node_modules"];

pub fn discover(roots: &[PathBuf]) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let mut seen = BTreeSet::new();
    for root in roots {
        if root.is_file() && root.file_name().and_then(|n| n.to_str()) == Some("SKILL.md") {
            push_file(root, &mut found, &mut seen);
            continue;
        }
        walk(root, 0, &mut found, &mut seen);
    }
    found.sort();
    found
}

fn walk(dir: &Path, depth: usize, found: &mut Vec<PathBuf>, seen: &mut BTreeSet<PathBuf>) {
    if depth > 8 {
        return;
    }
    let entries = match fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if SKIP_DIRS.contains(&name.as_ref()) {
            continue;
        }
        let file_type = match entry.file_type() {
            Ok(file_type) => file_type,
            Err(_) => continue,
        };
        if file_type.is_symlink() {
            continue;
        }
        if file_type.is_dir() {
            walk(&path, depth + 1, found, seen);
        } else if name == "SKILL.md" {
            push_file(&path, found, seen);
        }
    }
}

fn push_file(path: &Path, found: &mut Vec<PathBuf>, seen: &mut BTreeSet<PathBuf>) {
    let key = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    if seen.insert(key) {
        found.push(path.to_path_buf());
    }
}

pub fn local_roots(cwd: &Path) -> Vec<PathBuf> {
    [
        ".agents/skills",
        ".claude/skills",
        ".codex/skills",
        "skills",
        "examples",
    ]
    .into_iter()
    .map(|rel| cwd.join(rel))
    .filter(|path| path.is_dir())
    .collect()
}

pub fn user_roots() -> Vec<PathBuf> {
    let Some(home) = home_dir() else {
        return Vec::new();
    };
    [
        ".agents/skills",
        ".claude/skills",
        ".codex/skills",
    ]
    .into_iter()
    .map(|rel| home.join(rel))
    .filter(|path| path.is_dir())
    .collect()
}

pub fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}
