//! A YAML subset large enough for Agent Skills frontmatter.
//!
//! Recognized fields: `name`, `description`, `license`, `compatibility`,
//! `metadata`, `allowed-tools`. Unknown keys are skipped. Lists under
//! `metadata` are flattened and reported, because the spec wants strings.

use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Frontmatter {
    pub name: Option<String>,
    pub description: Option<String>,
    pub license: Option<String>,
    pub compatibility: Option<String>,
    pub allowed_tools: Vec<String>,
    pub metadata: BTreeMap<String, String>,
    pub body: String,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

pub fn parse_document(raw: &str) -> Result<Frontmatter, String> {
    let (front, body) = split_frontmatter(raw)?;
    let mut doc = parse_frontmatter(front);
    doc.body = body.trim().to_string();
    Ok(doc)
}

fn split_frontmatter(raw: &str) -> Result<(&str, &str), String> {
    let raw = raw.strip_prefix('\u{feff}').unwrap_or(raw);
    let raw = raw.trim_start_matches(['\n', '\r']);
    if !raw.starts_with("---") {
        return Err("missing opening ---".into());
    }
    let rest = &raw[3..];
    let rest = rest.strip_prefix('\r').unwrap_or(rest);
    let rest = rest
        .strip_prefix('\n')
        .ok_or("missing newline after opening ---")?;
    let mut offset = 0;
    for line in rest.split_inclusive('\n') {
        let trimmed = line.trim_end_matches(['\n', '\r']);
        if trimmed == "---" {
            return Ok((&rest[..offset], &rest[offset + line.len()..]));
        }
        offset += line.len();
    }
    Err("unclosed frontmatter".into())
}

fn parse_frontmatter(front: &str) -> Frontmatter {
    let lines: Vec<&str> = front
        .split('\n')
        .map(|line| line.trim_end_matches('\r'))
        .collect();
    let mut doc = Frontmatter {
        name: None,
        description: None,
        license: None,
        compatibility: None,
        allowed_tools: Vec::new(),
        metadata: BTreeMap::new(),
        body: String::new(),
        errors: Vec::new(),
        warnings: Vec::new(),
    };
    let mut seen = BTreeMap::<String, ()>::new();
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        if line.trim().is_empty() {
            i += 1;
            continue;
        }
        if line.starts_with(' ') || line.starts_with('\t') {
            doc.errors
                .push(format!("unexpected indent in frontmatter: {line}"));
            i += 1;
            continue;
        }
        let Some((key, value)) = split_key(line) else {
            doc.errors.push(format!("expected key: value, got {line}"));
            i += 1;
            continue;
        };
        if seen.insert(key.clone(), ()).is_some() {
            doc.errors.push(format!("duplicate field `{key}`"));
        }
        if is_block_indicator(&value) {
            let fold = value.starts_with('>');
            let (text, next) = read_block(&lines, i + 1, fold);
            assign(&mut doc, &key, &text);
            i = next;
            continue;
        }
        if value.is_empty() {
            if key == "metadata" {
                let (map, next, warnings) = read_metadata(&lines, i + 1);
                doc.warnings.extend(warnings);
                doc.metadata.extend(map);
                i = next;
            } else {
                i = skip_nested(&lines, i + 1, 0);
            }
            continue;
        }
        let (text, next) = read_plain_continuation(&lines, i + 1, &unquote(&value));
        assign(&mut doc, &key, &text);
        i = next;
    }
    doc
}

/// Plain YAML scalars may continue on indented lines. Those lines fold into
/// the first line with spaces, which is how many SKILL.md descriptions are written.
fn read_plain_continuation(lines: &[&str], start: usize, first: &str) -> (String, usize) {
    let mut text = first.to_string();
    let mut i = start;
    while i < lines.len() {
        let line = lines[i];
        if line.is_empty() || !(line.starts_with(' ') || line.starts_with('\t')) {
            break;
        }
        let trimmed = line.trim();
        if !trimmed.is_empty() {
            if !text.is_empty() && !text.ends_with(' ') {
                text.push(' ');
            }
            text.push_str(trimmed);
        }
        i += 1;
    }
    (text, i)
}

fn assign(doc: &mut Frontmatter, key: &str, value: &str) {
    match key {
        "name" => doc.name = Some(value.trim().to_string()),
        "description" => doc.description = Some(value.trim().to_string()),
        "license" => doc.license = Some(value.trim().to_string()),
        "compatibility" => doc.compatibility = Some(value.trim().to_string()),
        "allowed-tools" => {
            doc.allowed_tools = value.split_whitespace().map(|s| s.to_string()).collect();
        }
        "metadata" => {
            doc.warnings
                .push("metadata must be a map of strings, not a scalar".into());
        }
        _ => {}
    }
}

fn is_block_indicator(value: &str) -> bool {
    matches!(value, ">" | ">-" | ">+" | "|" | "|-" | "|+")
}

fn read_block(lines: &[&str], start: usize, fold: bool) -> (String, usize) {
    let mut i = start;
    let mut collected = Vec::new();
    while i < lines.len() {
        let line = lines[i];
        if line.is_empty() {
            collected.push(String::new());
            i += 1;
            continue;
        }
        if !(line.starts_with(' ') || line.starts_with('\t')) {
            break;
        }
        collected.push(line.trim().to_string());
        i += 1;
    }
    while collected.last().is_some_and(|line| line.is_empty()) {
        collected.pop();
    }
    let text = if fold {
        let mut out = String::new();
        for line in collected {
            if line.is_empty() {
                if !out.is_empty() && !out.ends_with('\n') {
                    out.push('\n');
                }
            } else if out.is_empty() || out.ends_with('\n') {
                out.push_str(&line);
            } else {
                out.push(' ');
                out.push_str(&line);
            }
        }
        out
    } else {
        collected.join("\n")
    };
    (text, i)
}

fn read_metadata(lines: &[&str], start: usize) -> (BTreeMap<String, String>, usize, Vec<String>) {
    let mut map = BTreeMap::new();
    let mut warnings = Vec::new();
    let mut i = start;
    while i < lines.len() {
        let line = lines[i];
        if line.trim().is_empty() {
            i += 1;
            continue;
        }
        let indent = indent_of(line);
        if indent == 0 {
            break;
        }
        let trimmed = line.trim();
        if trimmed.starts_with("- ") {
            warnings.push("skipped a list item directly under metadata".into());
            i += 1;
            continue;
        }
        let Some((key, value)) = split_key(trimmed) else {
            warnings.push(format!("skipped metadata line `{trimmed}`"));
            i += 1;
            continue;
        };
        if value.is_empty() {
            let (flat, next) = flatten_nested(lines, i + 1, indent);
            warnings.push(format!(
                "metadata.{key} is not a string; flattened to `{flat}`"
            ));
            map.insert(key, flat);
            i = next;
        } else {
            map.insert(key, unquote(&value));
            i += 1;
        }
    }
    (map, i, warnings)
}

fn flatten_nested(lines: &[&str], start: usize, parent_indent: usize) -> (String, usize) {
    let mut parts = Vec::new();
    let mut i = start;
    while i < lines.len() {
        let line = lines[i];
        if line.trim().is_empty() {
            i += 1;
            continue;
        }
        if indent_of(line) <= parent_indent {
            break;
        }
        let trimmed = line.trim();
        if let Some(item) = trimmed.strip_prefix("- ") {
            parts.push(unquote(item.trim()));
        } else if let Some((_, value)) = split_key(trimmed) {
            if !value.is_empty() {
                parts.push(unquote(&value));
            }
        }
        i += 1;
    }
    (parts.join(","), i)
}

fn skip_nested(lines: &[&str], start: usize, parent_indent: usize) -> usize {
    let mut i = start;
    while i < lines.len() {
        let line = lines[i];
        if line.trim().is_empty() {
            i += 1;
            continue;
        }
        if indent_of(line) <= parent_indent {
            break;
        }
        i += 1;
    }
    i
}

fn indent_of(line: &str) -> usize {
    line.chars().take_while(|c| *c == ' ' || *c == '\t').count()
}

fn split_key(line: &str) -> Option<(String, String)> {
    let (key, value) = line.split_once(':')?;
    let key = key.trim();
    if key.is_empty() || key.contains(' ') {
        return None;
    }
    Some((key.to_string(), value.trim().to_string()))
}

fn unquote(value: &str) -> String {
    let value = value.trim();
    if value.len() >= 2 && value.starts_with('"') && value.ends_with('"') {
        let inner = &value[1..value.len() - 1];
        let mut out = String::new();
        let mut chars = inner.chars();
        while let Some(c) = chars.next() {
            if c == '\\' {
                match chars.next() {
                    Some('n') => out.push('\n'),
                    Some('t') => out.push('\t'),
                    Some(other) => out.push(other),
                    None => out.push('\\'),
                }
            } else {
                out.push(c);
            }
        }
        return out;
    }
    if value.len() >= 2 && value.starts_with('\'') && value.ends_with('\'') {
        return value[1..value.len() - 1].replace("''", "'");
    }
    value.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn folded_description_and_metadata() {
        let raw = "---\nname: canvas\ndescription: >-\n  Line one\n  line two.\nmetadata:\n  author: me\n  version: \"1.0\"\n---\n\nBody here.\n";
        let doc = parse_document(raw).unwrap();
        assert_eq!(doc.name.as_deref(), Some("canvas"));
        assert_eq!(doc.description.as_deref(), Some("Line one line two."));
        assert_eq!(doc.metadata.get("author").map(String::as_str), Some("me"));
        assert_eq!(doc.metadata.get("version").map(String::as_str), Some("1.0"));
        assert_eq!(doc.body, "Body here.");
    }

    #[test]
    fn plain_description_continues_on_indented_lines() {
        let raw = "---\nname: backtest\ndescription: Use when an agent needs a backtest\n  protocol with fees and a benchmark.\nquantSkills:\n  project_type: skill\n---\n\nBody.\n";
        let doc = parse_document(raw).unwrap();
        assert!(doc.errors.is_empty(), "{:?}", doc.errors);
        assert_eq!(
            doc.description.as_deref(),
            Some("Use when an agent needs a backtest protocol with fees and a benchmark.")
        );
        assert_eq!(doc.body, "Body.");
    }
}
