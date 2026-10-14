//! Harness version pins found in `compatibility` and `metadata`.

use std::cmp::Ordering;

/// Longest phrases first so "claude code" wins over "claude".
const PRODUCTS: &[(&str, &str)] = &[
    ("claude code", "claude"),
    ("claude-code", "claude"),
    ("open claw", "openclaw"),
    ("openclaw", "openclaw"),
    ("open code", "opencode"),
    ("opencode", "opencode"),
    ("codex", "codex"),
    ("gemini", "gemini"),
    ("hermes", "hermes"),
    ("kiro", "kiro"),
    ("claude", "claude"),
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Version {
    parts: Vec<u64>,
}

impl Version {
    pub fn parse(input: &str) -> Option<Self> {
        let input = input.trim().trim_start_matches(['v', 'V']);
        if input.is_empty() {
            return None;
        }
        let mut parts = Vec::new();
        for piece in input.split('.') {
            if piece.is_empty() || !piece.chars().all(|c| c.is_ascii_digit()) {
                return None;
            }
            parts.push(piece.parse::<u64>().ok()?);
        }
        if parts.is_empty() {
            return None;
        }
        Some(Self { parts })
    }

    pub fn cmp_ver(&self, other: &Version) -> Ordering {
        let n = self.parts.len().max(other.parts.len());
        for i in 0..n {
            let a = self.parts.get(i).copied().unwrap_or(0);
            let b = other.parts.get(i).copied().unwrap_or(0);
            if a != b {
                return a.cmp(&b);
            }
        }
        Ordering::Equal
    }
}

impl std::fmt::Display for Version {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for (i, part) in self.parts.iter().enumerate() {
            if i > 0 {
                write!(f, ".")?;
            }
            write!(f, "{part}")?;
        }
        Ok(())
    }
}

/// Inclusive minimum, exclusive maximum. `max == None` means unbounded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Range {
    pub min: Version,
    pub max: Option<Version>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Pin {
    pub product: String,
    pub range: Range,
    pub raw: String,
}

pub fn canonical_product(name: &str) -> String {
    let key = name.trim().to_ascii_lowercase().replace('_', "-");
    for (phrase, id) in PRODUCTS {
        if *phrase == key {
            return (*id).to_string();
        }
    }
    key
}

pub fn ranges_overlap(a: &Range, b: &Range) -> bool {
    if let Some(max) = &b.max {
        if a.min.cmp_ver(max) != Ordering::Less {
            return false;
        }
    }
    if let Some(max) = &a.max {
        if b.min.cmp_ver(max) != Ordering::Less {
            return false;
        }
    }
    true
}

pub fn satisfies(version: &Version, range: &Range) -> bool {
    if version.cmp_ver(&range.min) == Ordering::Less {
        return false;
    }
    if let Some(max) = &range.max {
        if version.cmp_ver(max) != Ordering::Less {
            return false;
        }
    }
    true
}

pub fn intersect(a: Range, b: Range) -> Option<Range> {
    let min = if a.min.cmp_ver(&b.min) == Ordering::Less {
        b.min
    } else {
        a.min
    };
    let max = match (a.max, b.max) {
        (Some(x), Some(y)) => Some(if x.cmp_ver(&y) == Ordering::Less {
            x
        } else {
            y
        }),
        (Some(x), None) => Some(x),
        (None, Some(y)) => Some(y),
        (None, None) => None,
    };
    if let Some(max) = &max {
        if min.cmp_ver(max) != Ordering::Less {
            return None;
        }
    }
    Some(Range { min, max })
}

fn zero() -> Version {
    Version { parts: vec![0] }
}

fn bump_at(version: &Version, index: usize) -> Version {
    let mut parts = if version.parts.is_empty() {
        vec![0]
    } else {
        version.parts.clone()
    };
    let index = index.min(parts.len() - 1);
    parts.truncate(index + 1);
    parts[index] = parts[index].saturating_add(1);
    Version { parts }
}

fn bump_last(version: &Version) -> Version {
    let index = version.parts.len().saturating_sub(1);
    bump_at(version, index)
}

fn caret(version: Version) -> Range {
    let max = if version.parts.first().copied() == Some(0) {
        if version.parts.get(1).copied() == Some(0) {
            bump_last(&version)
        } else {
            bump_at(&version, 1.min(version.parts.len().saturating_sub(1)))
        }
    } else {
        bump_at(&version, 0)
    };
    Range {
        min: version,
        max: Some(max),
    }
}

fn prefix(version: Version) -> Range {
    Range {
        min: version.clone(),
        max: Some(bump_last(&version)),
    }
}

/// Parse one constraint such as `>=2.1.296`, `<2`, `^1.2.3`, or a bare `2026.9.8`.
pub fn parse_constraint(input: &str) -> Option<Range> {
    let s = input.trim();
    let (op, rest) = if let Some(rest) = s.strip_prefix(">=") {
        (">=", rest.trim())
    } else if let Some(rest) = s.strip_prefix("<=") {
        ("<=", rest.trim())
    } else if let Some(rest) = s.strip_prefix("==") {
        ("==", rest.trim())
    } else if let Some(rest) = s.strip_prefix('>') {
        (">", rest.trim())
    } else if let Some(rest) = s.strip_prefix('<') {
        ("<", rest.trim())
    } else if let Some(rest) = s.strip_prefix('^') {
        ("^", rest.trim())
    } else {
        ("", s)
    };
    let version = Version::parse(rest)?;
    if rest
        .chars()
        .any(|c| !(c.is_ascii_digit() || c == '.' || c == 'v' || c == 'V'))
        && !rest
            .trim_start_matches(['v', 'V'])
            .chars()
            .all(|c| c.is_ascii_digit() || c == '.')
    {
        return None;
    }
    Some(match op {
        ">=" => Range {
            min: version,
            max: None,
        },
        ">" => Range {
            min: bump_last(&version),
            max: None,
        },
        "<" => Range {
            min: zero(),
            max: Some(version),
        },
        "<=" => Range {
            min: zero(),
            max: Some(bump_last(&version)),
        },
        "==" => prefix(version),
        "^" => caret(version),
        _ => prefix(version),
    })
}

fn take_constraint(input: &str) -> Option<(Range, String)> {
    let s = input.trim_start_matches(|c: char| c.is_whitespace() || c == ':' || c == '(');
    if s.is_empty() {
        return None;
    }
    let (op, rest) = if let Some(rest) = s.strip_prefix(">=") {
        (">=", rest.trim_start())
    } else if let Some(rest) = s.strip_prefix("<=") {
        ("<=", rest.trim_start())
    } else if let Some(rest) = s.strip_prefix("==") {
        ("==", rest.trim_start())
    } else if let Some(rest) = s.strip_prefix('>') {
        (">", rest.trim_start())
    } else if let Some(rest) = s.strip_prefix('<') {
        ("<", rest.trim_start())
    } else if let Some(rest) = s.strip_prefix('^') {
        ("^", rest.trim_start())
    } else {
        ("", s)
    };
    let rest = rest.trim_start_matches(['v', 'V']);
    if !rest.starts_with(|c: char| c.is_ascii_digit()) {
        return None;
    }
    let end = rest
        .find(|c: char| !(c.is_ascii_digit() || c == '.'))
        .unwrap_or(rest.len());
    let ver = rest[..end].trim_end_matches('.');
    if ver.is_empty() {
        return None;
    }
    let range = parse_constraint(&format!("{op}{ver}"))?;
    let raw = if op.is_empty() {
        ver.to_string()
    } else {
        format!("{op}{ver}")
    };
    Some((range, raw))
}

fn is_boundary_before(text: &str, index: usize) -> bool {
    if index == 0 {
        return true;
    }
    !text[..index]
        .chars()
        .next_back()
        .is_some_and(|c| c.is_ascii_alphanumeric())
}

fn is_boundary_after(text: &str, index: usize) -> bool {
    !text[index..]
        .chars()
        .next()
        .is_some_and(|c| c.is_ascii_alphanumeric())
}

pub fn pins_from_text(text: &str) -> Vec<Pin> {
    let lower = text.to_ascii_lowercase();
    let mut pins = Vec::new();
    let mut i = 0;
    while i < lower.len() {
        let mut matched = false;
        if is_boundary_before(&lower, i) {
            for (phrase, id) in PRODUCTS {
                let end = i + phrase.len();
                if lower[i..].starts_with(phrase) && is_boundary_after(&lower, end) {
                    if let Some((range, raw)) = take_constraint(&lower[end..]) {
                        pins.push(Pin {
                            product: (*id).to_string(),
                            range,
                            raw: format!("{id} {raw}"),
                        });
                    }
                    i = end;
                    matched = true;
                    break;
                }
            }
        }
        if !matched {
            let step = lower[i..].chars().next().map(|c| c.len_utf8()).unwrap_or(1);
            i += step;
        }
    }
    pins
}

pub fn pins_from_metadata(metadata: &std::collections::BTreeMap<String, String>) -> Vec<Pin> {
    let mut pins = Vec::new();
    for (key, value) in metadata {
        let stripped = key.trim().strip_prefix("skillock.").unwrap_or(key);
        let known = PRODUCTS.iter().any(|(phrase, id)| {
            !phrase.contains(' ') && (*phrase == stripped.to_ascii_lowercase() || *id == stripped)
        });
        if !known {
            continue;
        }
        let product = canonical_product(stripped);
        let mut range: Option<Range> = None;
        let mut raws = Vec::new();
        for piece in value.split(',') {
            let piece = piece.trim();
            if piece.is_empty() {
                continue;
            }
            if let Some(next) = parse_constraint(piece) {
                raws.push(piece.to_string());
                range = Some(match range.take() {
                    Some(prev) => match intersect(prev, next) {
                        Some(merged) => merged,
                        None => {
                            pins.push(Pin {
                                product: product.clone(),
                                range: Range {
                                    min: zero(),
                                    max: Some(zero()),
                                },
                                raw: format!("{product} unsatisfiable ({value})"),
                            });
                            continue;
                        }
                    },
                    None => next,
                });
            }
        }
        if let Some(range) = range {
            pins.push(Pin {
                product,
                range,
                raw: format!("{} {}", key, raws.join(",")),
            });
        }
    }
    pins
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn installed_patch_satisfies_lower_bound_and_not_upper() {
        let installed = Version::parse("2.0.1").unwrap();
        let lower = parse_constraint(">=2").unwrap();
        let upper = parse_constraint("<2").unwrap();
        assert!(satisfies(&installed, &lower));
        assert!(!satisfies(&installed, &upper));
        assert!(!ranges_overlap(&lower, &upper));
    }

    #[test]
    fn newer_calver_is_outside_a_bare_pin() {
        let installed = Version::parse("2026.10.3").unwrap();
        let pinned = parse_constraint("2026.9.8").unwrap();
        assert!(!satisfies(&installed, &pinned));
        let same = Version::parse("2026.9.8").unwrap();
        assert!(satisfies(&same, &pinned));
    }

    #[test]
    fn free_text_finds_two_products() {
        let pins = pins_from_text("Requires opencode >= 2. Works with Claude Code >= 2.1.296");
        let products: Vec<_> = pins.iter().map(|p| p.product.as_str()).collect();
        assert!(products.contains(&"opencode"));
        assert!(products.contains(&"claude"));
    }
}
