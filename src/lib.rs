//! Lockfile checks for [Agent Skills](https://agentskills.io/specification).
//!
//! `name` and `description` are loaded for every installed skill. The body is
//! loaded when a skill activates. skillock estimates both, then reports
//! duplicate names, description overlap, contradictory instructions, and
//! harness version pins that cannot be true at the same time.

#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

mod discover;
mod frontmatter;
mod pins;
mod sha256;

pub use discover::{discover, home_dir, local_roots, user_roots};
pub use pins::{canonical_product, Version};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    Error,
    Warning,
}

impl Level {
    pub fn as_str(self) -> &'static str {
        match self {
            Level::Error => "error",
            Level::Warning => "warning",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Finding {
    pub level: Level,
    pub code: &'static str,
    pub message: String,
}

#[derive(Clone, Debug)]
pub struct LoadedSkill {
    pub path: PathBuf,
    pub name: String,
    pub description: String,
    pub compatibility: Option<String>,
    pub metadata: BTreeMap<String, String>,
    pub body: String,
    pub sha256: String,
    pub parse_errors: Vec<String>,
    pub parse_warnings: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct SkillSummary {
    pub name: String,
    pub path: PathBuf,
    pub sha256: String,
    pub startup_tokens: usize,
    pub body_tokens: usize,
}

#[derive(Clone, Debug)]
pub struct Report {
    pub skills: Vec<SkillSummary>,
    pub findings: Vec<Finding>,
    pub startup_tokens: usize,
    pub body_tokens: usize,
}

#[derive(Clone, Debug)]
pub struct Options {
    pub startup_budget: usize,
    pub body_budget: usize,
    pub harness: BTreeMap<String, Version>,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            startup_budget: 4_000,
            body_budget: 5_000,
            harness: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LockEntry {
    pub name: String,
    pub path: String,
    pub sha256: String,
}

/// ASCII runs cost one token per four characters. Each non-ASCII character
/// costs one token. This is a budget, not a model tokenizer.
pub fn estimate_tokens(text: &str) -> usize {
    let mut tokens = 0usize;
    let mut ascii = 0usize;
    for ch in text.chars() {
        if ch.is_ascii() {
            if ch.is_whitespace() {
                tokens += ascii.div_ceil(4);
                ascii = 0;
            } else {
                ascii += 1;
            }
        } else {
            tokens += ascii.div_ceil(4);
            ascii = 0;
            tokens += 1;
        }
    }
    tokens + ascii.div_ceil(4)
}

pub fn load_skill(path: &Path) -> LoadedSkill {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(err) => {
            return LoadedSkill {
                path: path.to_path_buf(),
                name: String::new(),
                description: String::new(),
                compatibility: None,
                metadata: BTreeMap::new(),
                body: String::new(),
                sha256: String::new(),
                parse_errors: vec![format!("unreadable: {err}")],
                parse_warnings: Vec::new(),
            };
        }
    };
    let sha = sha256::hex(&sha256::sha256(&bytes));
    let text = match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(_) => {
            return LoadedSkill {
                path: path.to_path_buf(),
                name: String::new(),
                description: String::new(),
                compatibility: None,
                metadata: BTreeMap::new(),
                body: String::new(),
                sha256: sha,
                parse_errors: vec!["file is not UTF-8".into()],
                parse_warnings: Vec::new(),
            };
        }
    };
    match frontmatter::parse_document(&text) {
        Ok(doc) => LoadedSkill {
            path: path.to_path_buf(),
            name: doc.name.unwrap_or_default(),
            description: doc.description.unwrap_or_default(),
            compatibility: doc.compatibility,
            metadata: doc.metadata,
            body: doc.body,
            sha256: sha,
            parse_errors: doc.errors,
            parse_warnings: doc.warnings,
        },
        Err(err) => LoadedSkill {
            path: path.to_path_buf(),
            name: String::new(),
            description: String::new(),
            compatibility: None,
            metadata: BTreeMap::new(),
            body: String::new(),
            sha256: sha,
            parse_errors: vec![err],
            parse_warnings: Vec::new(),
        },
    }
}

pub fn analyze(skills: &[LoadedSkill], opts: &Options) -> Report {
    let mut findings = Vec::new();
    let mut summaries = Vec::new();
    let mut startup_tokens = 0usize;
    let mut body_tokens = 0usize;

    for skill in skills {
        let startup = estimate_tokens(&skill.name) + estimate_tokens(&skill.description);
        let body = estimate_tokens(&skill.body);
        startup_tokens += startup;
        body_tokens += body;
        summaries.push(SkillSummary {
            name: skill.name.clone(),
            path: skill.path.clone(),
            sha256: skill.sha256.clone(),
            startup_tokens: startup,
            body_tokens: body,
        });
        for err in &skill.parse_errors {
            findings.push(Finding {
                level: Level::Error,
                code: "spec-frontmatter",
                message: format!("{}: {err}", display_path(&skill.path)),
            });
        }
        for warning in &skill.parse_warnings {
            findings.push(Finding {
                level: Level::Warning,
                code: "spec-metadata",
                message: format!("{}: {warning}", display_path(&skill.path)),
            });
        }
        validate_spec(skill, &mut findings);
        if body > opts.body_budget {
            findings.push(Finding {
                level: Level::Warning,
                code: "body-budget",
                message: format!(
                    "{} body is {body} tokens, over the {} token activation budget",
                    skill_label(skill),
                    opts.body_budget
                ),
            });
        }
    }

    if startup_tokens > opts.startup_budget {
        findings.push(Finding {
            level: Level::Warning,
            code: "startup-budget",
            message: format!(
                "startup metadata is {startup_tokens} tokens, over the {} token budget. Agents load every name and description before a skill is chosen",
                opts.startup_budget
            ),
        });
    }

    duplicate_names(skills, &mut findings);
    pin_findings(skills, opts, &mut findings);
    overlap_findings(skills, &mut findings);
    contradiction_findings(skills, &mut findings);

    findings.sort_by(|a, b| {
        a.level
            .cmp(&b.level)
            .then(a.code.cmp(b.code))
            .then(a.message.cmp(&b.message))
    });
    summaries.sort_by(|a, b| b.body_tokens.cmp(&a.body_tokens).then(a.path.cmp(&b.path)));

    Report {
        skills: summaries,
        findings,
        startup_tokens,
        body_tokens,
    }
}

pub fn render(report: &Report) -> String {
    let errors = report
        .findings
        .iter()
        .filter(|f| f.level == Level::Error)
        .count();
    let warnings = report.findings.len() - errors;
    let mut out = format!(
        "{} skills · startup {} tokens · bodies {} tokens · {errors} errors · {warnings} warnings\n",
        report.skills.len(),
        report.startup_tokens,
        report.body_tokens
    );
    if !report.skills.is_empty() {
        out.push_str("\nlargest bodies\n");
        for skill in report.skills.iter().take(5) {
            out.push_str(&format!(
                "  {:>6}  {}\n",
                skill.body_tokens,
                display_path(&skill.path)
            ));
        }
    }
    if !report.findings.is_empty() {
        out.push('\n');
        for finding in &report.findings {
            out.push_str(&format!(
                "{}  {}  {}\n",
                finding.level.as_str(),
                finding.code,
                finding.message
            ));
        }
    }
    out
}

pub fn to_json(report: &Report) -> String {
    let mut out = String::new();
    out.push_str("{\n");
    out.push_str(&format!(
        "  \"startup_tokens\": {},\n  \"body_tokens\": {},\n  \"skills\": [\n",
        report.startup_tokens, report.body_tokens
    ));
    for (i, skill) in report.skills.iter().enumerate() {
        if i > 0 {
            out.push_str(",\n");
        }
        out.push_str(&format!(
            "    {{\"name\": \"{}\", \"path\": \"{}\", \"sha256\": \"{}\", \"startup_tokens\": {}, \"body_tokens\": {}}}",
            escape_json(&skill.name),
            escape_json(&display_path(&skill.path)),
            skill.sha256,
            skill.startup_tokens,
            skill.body_tokens
        ));
    }
    out.push_str("\n  ],\n  \"findings\": [\n");
    for (i, finding) in report.findings.iter().enumerate() {
        if i > 0 {
            out.push_str(",\n");
        }
        out.push_str(&format!(
            "    {{\"level\": \"{}\", \"code\": \"{}\", \"message\": \"{}\"}}",
            finding.level.as_str(),
            finding.code,
            escape_json(&finding.message)
        ));
    }
    out.push_str("\n  ]\n}\n");
    out
}

pub fn write_lock(path: &Path, cwd: &Path, report: &Report) -> std::io::Result<()> {
    let mut skills = report.skills.clone();
    skills.sort_by(|a, b| relative_path(cwd, &a.path).cmp(&relative_path(cwd, &b.path)));
    let mut text = String::from("# Generated by skillock. Do not edit by hand.\nversion = 1\n");
    text.push_str(&format!(
        "startup_tokens = {}\nbody_tokens = {}\nskill_count = {}\n",
        report.startup_tokens,
        report.body_tokens,
        skills.len()
    ));
    for skill in skills {
        text.push_str("\n[[skills]]\n");
        text.push_str(&format!("name = \"{}\"\n", escape_toml(&skill.name)));
        text.push_str(&format!(
            "path = \"{}\"\n",
            escape_toml(&relative_path(cwd, &skill.path))
        ));
        text.push_str(&format!("sha256 = \"{}\"\n", skill.sha256));
        text.push_str(&format!("startup_tokens = {}\n", skill.startup_tokens));
        text.push_str(&format!("body_tokens = {}\n", skill.body_tokens));
    }
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }
    fs::write(path, text)
}

pub fn read_lock(path: &Path) -> std::io::Result<Vec<LockEntry>> {
    let text = fs::read_to_string(path)?;
    let mut entries = Vec::new();
    let mut name = None;
    let mut rel = None;
    let mut sha = None;
    let flush = |entries: &mut Vec<LockEntry>,
                 name: &mut Option<String>,
                 rel: &mut Option<String>,
                 sha: &mut Option<String>| {
        if let (Some(name), Some(path), Some(sha256)) = (name.take(), rel.take(), sha.take()) {
            entries.push(LockEntry { name, path, sha256 });
        }
    };
    for line in text.lines() {
        let line = line.trim();
        if line == "[[skills]]" {
            flush(&mut entries, &mut name, &mut rel, &mut sha);
            continue;
        }
        if let Some(value) = line.strip_prefix("name = ") {
            name = Some(unquote_toml(value));
        } else if let Some(value) = line.strip_prefix("path = ") {
            rel = Some(unquote_toml(value));
        } else if let Some(value) = line.strip_prefix("sha256 = ") {
            sha = Some(unquote_toml(value));
        }
    }
    flush(&mut entries, &mut name, &mut rel, &mut sha);
    Ok(entries)
}

pub fn diff_lock(cwd: &Path, report: &Report, lock: &[LockEntry]) -> Vec<Finding> {
    let mut findings = Vec::new();
    let current: BTreeMap<String, &SkillSummary> = report
        .skills
        .iter()
        .map(|skill| (relative_path(cwd, &skill.path), skill))
        .collect();
    let locked: BTreeMap<&str, &LockEntry> = lock.iter().map(|e| (e.path.as_str(), e)).collect();
    for (path, skill) in &current {
        match locked.get(path.as_str()) {
            None => findings.push(Finding {
                level: Level::Warning,
                code: "lock-new",
                message: format!("{path} is not in the lockfile ({})", skill.name),
            }),
            Some(entry) if entry.sha256 != skill.sha256 => findings.push(Finding {
                level: Level::Warning,
                code: "lock-drift",
                message: format!("{path} changed since the lockfile"),
            }),
            Some(_) => {}
        }
    }
    for entry in lock {
        if !current.contains_key(&entry.path) {
            findings.push(Finding {
                level: Level::Warning,
                code: "lock-removed",
                message: format!("{} was locked and is no longer present", entry.path),
            });
        }
    }
    findings.sort_by(|a, b| a.code.cmp(b.code).then(a.message.cmp(&b.message)));
    findings
}

fn validate_spec(skill: &LoadedSkill, findings: &mut Vec<Finding>) {
    if skill.name.is_empty() {
        findings.push(Finding {
            level: Level::Error,
            code: "spec-name",
            message: format!("{}: name is required", display_path(&skill.path)),
        });
    } else if !valid_name(&skill.name) {
        findings.push(Finding {
            level: Level::Error,
            code: "spec-name",
            message: format!(
                "{}: name `{}` must be 1-64 lowercase letters, numbers, or single hyphens",
                display_path(&skill.path),
                skill.name
            ),
        });
    }
    if let Some(parent) = skill
        .path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|n| n.to_str())
    {
        if !skill.name.is_empty() && parent != skill.name {
            findings.push(Finding {
                level: Level::Error,
                code: "spec-dir",
                message: format!(
                    "{}: name `{}` does not match parent directory `{parent}`",
                    display_path(&skill.path),
                    skill.name
                ),
            });
        }
    }
    let desc_len = skill.description.chars().count();
    if desc_len == 0 || desc_len > 1024 {
        findings.push(Finding {
            level: Level::Error,
            code: "spec-description",
            message: format!(
                "{}: description must be 1-1024 characters (got {desc_len})",
                skill_label(skill)
            ),
        });
    }
    if let Some(compat) = &skill.compatibility {
        let len = compat.chars().count();
        if len == 0 || len > 500 {
            findings.push(Finding {
                level: Level::Error,
                code: "spec-compatibility",
                message: format!(
                    "{}: compatibility must be 1-500 characters when present",
                    skill_label(skill)
                ),
            });
        }
    }
}

fn valid_name(name: &str) -> bool {
    if name.is_empty()
        || name.len() > 64
        || name.starts_with('-')
        || name.ends_with('-')
        || name.contains("--")
    {
        return false;
    }
    name.chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

fn duplicate_names(skills: &[LoadedSkill], findings: &mut Vec<Finding>) {
    let mut by_name: BTreeMap<&str, Vec<&LoadedSkill>> = BTreeMap::new();
    for skill in skills {
        if skill.name.is_empty() {
            continue;
        }
        by_name.entry(skill.name.as_str()).or_default().push(skill);
    }
    for (name, group) in by_name {
        if group.len() < 2 {
            continue;
        }
        let paths: Vec<_> = group.iter().map(|s| display_path(&s.path)).collect();
        findings.push(Finding {
            level: Level::Error,
            code: "duplicate-name",
            message: format!("name `{name}` is used by {}", paths.join(", ")),
        });
    }
}

fn pin_findings(skills: &[LoadedSkill], opts: &Options, findings: &mut Vec<Finding>) {
    struct OwnedPin {
        skill: String,
        product: String,
        range: pins::Range,
        raw: String,
    }
    let mut owned = Vec::new();
    for skill in skills {
        let mut collected = Vec::new();
        if let Some(compat) = &skill.compatibility {
            collected.extend(pins::pins_from_text(compat));
        }
        collected.extend(pins::pins_from_metadata(&skill.metadata));
        let mut by_product: BTreeMap<String, OwnedPin> = BTreeMap::new();
        for pin in collected {
            if pin.raw.contains("unsatisfiable") {
                findings.push(Finding {
                    level: Level::Error,
                    code: "pin-unsatisfiable",
                    message: format!("{}: {}", skill_label(skill), pin.raw),
                });
                continue;
            }
            let label = skill_label(skill);
            match by_product.get_mut(&pin.product) {
                None => {
                    by_product.insert(
                        pin.product.clone(),
                        OwnedPin {
                            skill: label,
                            product: pin.product,
                            range: pin.range,
                            raw: pin.raw,
                        },
                    );
                }
                Some(prev) => match pins::intersect(prev.range.clone(), pin.range) {
                    Some(range) => {
                        prev.range = range;
                        prev.raw = format!("{}, {}", prev.raw, pin.raw);
                    }
                    None => findings.push(Finding {
                        level: Level::Error,
                        code: "pin-unsatisfiable",
                        message: format!(
                            "{label} pins {} and {} cannot both hold",
                            prev.raw, pin.raw
                        ),
                    }),
                },
            }
        }
        owned.extend(by_product.into_values());
    }

    let mut by_product: BTreeMap<String, Vec<&OwnedPin>> = BTreeMap::new();
    for pin in &owned {
        by_product.entry(pin.product.clone()).or_default().push(pin);
    }
    for (product, group) in &by_product {
        for i in 0..group.len() {
            for j in (i + 1)..group.len() {
                if !pins::ranges_overlap(&group[i].range, &group[j].range) {
                    findings.push(Finding {
                        level: Level::Error,
                        code: "pin-conflict",
                        message: format!(
                            "{product} pins do not overlap: {} wants {}, {} wants {}",
                            group[i].skill, group[i].raw, group[j].skill, group[j].raw
                        ),
                    });
                }
            }
        }
        if let Some(installed) = opts.harness.get(product) {
            for pin in group {
                if !pins::satisfies(installed, &pin.range) {
                    findings.push(Finding {
                        level: Level::Error,
                        code: "pin-drift",
                        message: format!(
                            "installed {product} {installed} is outside {} pin {}",
                            pin.skill, pin.raw
                        ),
                    });
                }
            }
        }
    }
}

fn overlap_findings(skills: &[LoadedSkill], findings: &mut Vec<Finding>) {
    let words: Vec<Vec<String>> = skills
        .iter()
        .map(|s| content_words(&s.description))
        .collect();
    for i in 0..skills.len() {
        for j in (i + 1)..skills.len() {
            if words[i].len() < 6 || words[j].len() < 6 {
                continue;
            }
            let (score, shared) = jaccard(&words[i], &words[j]);
            if shared.len() >= 4 && score >= 0.5 {
                let (left, right) = pair_label(&skills[i], &skills[j]);
                findings.push(Finding {
                    level: Level::Warning,
                    code: "overlap",
                    message: format!(
                        "{left} and {right} may activate on the same request (shared: {})",
                        shared.into_iter().take(8).collect::<Vec<_>>().join(", ")
                    ),
                });
            }
        }
    }
}

fn contradiction_findings(skills: &[LoadedSkill], findings: &mut Vec<Finding>) {
    struct Line {
        skill: usize,
        polarity: Polarity,
        words: Vec<String>,
        text: String,
    }
    let mut lines = Vec::new();
    for (index, skill) in skills.iter().enumerate() {
        for sentence in sentences(&skill.body) {
            let Some(polarity) = polarity(sentence) else {
                continue;
            };
            let words = content_words(sentence);
            if words.len() < 3 {
                continue;
            }
            lines.push(Line {
                skill: index,
                polarity,
                words,
                text: sentence.chars().take(120).collect(),
            });
        }
    }
    for i in 0..lines.len() {
        for j in (i + 1)..lines.len() {
            if lines[i].skill == lines[j].skill || lines[i].polarity == lines[j].polarity {
                continue;
            }
            let (score, shared) = jaccard(&lines[i].words, &lines[j].words);
            if shared.len() >= 3 && score >= 0.6 {
                findings.push(Finding {
                    level: Level::Warning,
                    code: "contradiction",
                    message: format!(
                        "{} says \"{}\", {} says \"{}\"",
                        skill_label(&skills[lines[i].skill]),
                        lines[i].text,
                        skill_label(&skills[lines[j].skill]),
                        lines[j].text
                    ),
                });
            }
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Polarity {
    Require,
    Forbid,
}

fn polarity(sentence: &str) -> Option<Polarity> {
    let lower = sentence.to_ascii_lowercase();
    let forbid = lower.contains("must not")
        || lower.contains("do not")
        || lower.contains("don't")
        || lower.contains("never");
    let require = lower.contains("always") || lower.contains("must");
    match (require && !lower.contains("must not"), forbid) {
        (true, true) | (false, false) => None,
        (true, false) => Some(Polarity::Require),
        (false, true) => Some(Polarity::Forbid),
    }
}

fn sentences(body: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    for (i, ch) in body.char_indices() {
        if matches!(ch, '.' | '!' | '?' | '\n') {
            let sentence = body[start..i].trim();
            if !sentence.is_empty() {
                out.push(sentence);
            }
            start = i + ch.len_utf8();
        }
    }
    let tail = body[start..].trim();
    if !tail.is_empty() {
        out.push(tail);
    }
    out
}

fn content_words(text: &str) -> Vec<String> {
    let mut words = Vec::new();
    let mut ascii = String::new();
    let flush_ascii = |ascii: &mut String, words: &mut Vec<String>| {
        if ascii.len() >= 2 && !is_stop(ascii.as_str()) {
            words.push(std::mem::take(ascii));
        } else {
            ascii.clear();
        }
    };
    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() {
            ascii.push(ch.to_ascii_lowercase());
        } else if !ch.is_ascii() && !ch.is_whitespace() && ch.is_alphanumeric() {
            flush_ascii(&mut ascii, &mut words);
            let token = ch.to_string();
            if !is_stop(token.as_str()) {
                words.push(token);
            }
        } else {
            flush_ascii(&mut ascii, &mut words);
        }
    }
    flush_ascii(&mut ascii, &mut words);
    words
}

fn jaccard(a: &[String], b: &[String]) -> (f64, Vec<String>) {
    let left: BTreeSet<&str> = a.iter().map(String::as_str).collect();
    let right: BTreeSet<&str> = b.iter().map(String::as_str).collect();
    let shared: Vec<String> = left
        .intersection(&right)
        .map(|s| (*s).to_string())
        .collect();
    let union = left.union(&right).count();
    if union == 0 {
        return (0.0, shared);
    }
    (shared.len() as f64 / union as f64, shared)
}

fn is_stop(word: &str) -> bool {
    STOPWORDS.iter().any(|stop| *stop == word)
}

const STOPWORDS: &[&str] = &[
    "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "with", "when", "use", "used",
    "using", "user", "users", "this", "that", "from", "into", "by", "is", "are", "be", "as", "at",
    "it", "if", "do", "does", "skill", "skills", "agent", "agents", "you", "your", "they", "their",
    "not", "than", "then", "so", "can", "its", "per",
];

fn pair_label(left: &LoadedSkill, right: &LoadedSkill) -> (String, String) {
    if !left.name.is_empty() && left.name == right.name {
        (display_path(&left.path), display_path(&right.path))
    } else {
        (skill_label(left), skill_label(right))
    }
}

fn skill_label(skill: &LoadedSkill) -> String {
    if skill.name.is_empty() {
        display_path(&skill.path)
    } else {
        skill.name.clone()
    }
}

pub fn display_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

pub fn relative_path(cwd: &Path, path: &Path) -> String {
    path.strip_prefix(cwd)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn escape_toml(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

fn unquote_toml(value: &str) -> String {
    let value = value.trim().trim_matches('"');
    value.replace("\\\"", "\"").replace("\\\\", "\\")
}

fn escape_json(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_estimate_counts_ascii_runs_and_cjk() {
        assert_eq!(estimate_tokens("abcd"), 1);
        assert_eq!(estimate_tokens("abcde"), 2);
        assert_eq!(estimate_tokens("你"), 1);
    }

    #[test]
    fn startup_budget_warns_when_metadata_is_large() {
        let skill = LoadedSkill {
            path: PathBuf::from("demo/demo/SKILL.md"),
            name: "demo".into(),
            description: "x".repeat(80),
            compatibility: None,
            metadata: BTreeMap::new(),
            body: String::new(),
            sha256: String::new(),
            parse_errors: Vec::new(),
            parse_warnings: Vec::new(),
        };
        let mut opts = Options::default();
        opts.startup_budget = 1;
        let report = analyze(std::slice::from_ref(&skill), &opts);
        assert!(report.findings.iter().any(|f| f.code == "startup-budget"));
    }
}
