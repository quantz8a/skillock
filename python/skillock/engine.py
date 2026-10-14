"""Checks shared with the Rust build: tokens, pins, overlap, contradictions."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

PRODUCTS = (
    ("claude code", "claude"),
    ("claude-code", "claude"),
    ("open claw", "openclaw"),
    ("openclaw", "openclaw"),
    ("open code", "opencode"),
    ("opencode", "opencode"),
    ("cursor", "cursor"),
    ("codex", "codex"),
    ("gemini", "gemini"),
    ("hermes", "hermes"),
    ("kiro", "kiro"),
    ("claude", "claude"),
)

STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "with", "when", "use", "used",
    "using", "user", "users", "this", "that", "from", "into", "by", "is", "are", "be", "as", "at",
    "it", "if", "do", "does", "skill", "skills", "agent", "agents", "you", "your", "they", "their",
    "not", "than", "then", "so", "can", "its", "per",
}

SKIP_DIRS = {".git", "target", "node_modules"}


@dataclass
class Version:
    parts: tuple

    @classmethod
    def parse(cls, text):
        raw = text.strip().lstrip("vV")
        if not raw:
            return None
        parts = []
        for piece in raw.split("."):
            if not piece or not piece.isdigit():
                return None
            parts.append(int(piece))
        return cls(tuple(parts)) if parts else None

    def cmp(self, other):
        n = max(len(self.parts), len(other.parts))
        for i in range(n):
            a = self.parts[i] if i < len(self.parts) else 0
            b = other.parts[i] if i < len(other.parts) else 0
            if a != b:
                return -1 if a < b else 1
        return 0

    def __str__(self):
        return ".".join(str(part) for part in self.parts)


@dataclass
class Range:
    min: Version
    max: Version | None


@dataclass
class Pin:
    product: str
    range: Range
    raw: str


def canonical_product(name):
    key = name.strip().lower().replace("_", "-")
    for phrase, ident in PRODUCTS:
        if phrase == key:
            return ident
    return key


def _zero():
    return Version((0,))


def _bump_at(version, index):
    parts = list(version.parts or (0,))
    index = min(index, len(parts) - 1)
    parts = parts[: index + 1]
    parts[index] += 1
    return Version(tuple(parts))


def _bump_last(version):
    return _bump_at(version, max(len(version.parts) - 1, 0))


def _prefix(version):
    return Range(version, _bump_last(version))


def _caret(version):
    if version.parts and version.parts[0] == 0:
        if len(version.parts) > 1 and version.parts[1] == 0:
            cap = _bump_last(version)
        else:
            cap = _bump_at(version, min(1, len(version.parts) - 1))
    else:
        cap = _bump_at(version, 0)
    return Range(version, cap)


def parse_constraint(text):
    s = text.strip()
    op = ""
    rest = s
    for candidate in (">=", "<=", "==", ">", "<", "^"):
        if s.startswith(candidate):
            op = candidate
            rest = s[len(candidate) :].strip()
            break
    version = Version.parse(rest)
    if version is None:
        return None
    if op == ">=":
        return Range(version, None)
    if op == ">":
        return Range(_bump_last(version), None)
    if op == "<":
        return Range(_zero(), version)
    if op == "<=":
        return Range(_zero(), _bump_last(version))
    if op == "^":
        return _caret(version)
    return _prefix(version)


def ranges_overlap(a, b):
    if b.max is not None and a.min.cmp(b.max) >= 0:
        return False
    if a.max is not None and b.min.cmp(a.max) >= 0:
        return False
    return True


def satisfies(version, span):
    if version.cmp(span.min) < 0:
        return False
    if span.max is not None and version.cmp(span.max) >= 0:
        return False
    return True


def intersect(a, b):
    low = b.min if a.min.cmp(b.min) < 0 else a.min
    if a.max is None:
        high = b.max
    elif b.max is None:
        high = a.max
    else:
        high = a.max if a.max.cmp(b.max) < 0 else b.max
    if high is not None and low.cmp(high) >= 0:
        return None
    return Range(low, high)


def _take_constraint(text):
    s = text.lstrip(" \t:(")
    if not s:
        return None
    op = ""
    rest = s
    for candidate in (">=", "<=", "==", ">", "<", "^"):
        if s.startswith(candidate):
            op = candidate
            rest = s[len(candidate) :].lstrip()
            break
    rest = rest.lstrip("vV")
    if not rest or not rest[0].isdigit():
        return None
    end = 0
    while end < len(rest) and (rest[end].isdigit() or rest[end] == "."):
        end += 1
    ver = rest[:end].rstrip(".")
    if not ver:
        return None
    span = parse_constraint(f"{op}{ver}")
    if span is None:
        return None
    raw = ver if not op else f"{op}{ver}"
    return span, raw


def pins_from_text(text):
    lower = text.lower()
    pins = []
    i = 0
    while i < len(lower):
        matched = False
        before_ok = i == 0 or not lower[i - 1].isalnum()
        if before_ok:
            for phrase, ident in PRODUCTS:
                end = i + len(phrase)
                if lower.startswith(phrase, i) and (end >= len(lower) or not lower[end].isalnum()):
                    taken = _take_constraint(lower[end:])
                    if taken:
                        span, raw = taken
                        pins.append(Pin(ident, span, f"{ident} {raw}"))
                    i = end
                    matched = True
                    break
        if not matched:
            i += 1
    return pins


def pins_from_metadata(metadata):
    pins = []
    known = {phrase: ident for phrase, ident in PRODUCTS if " " not in phrase}
    known.update({ident: ident for _, ident in PRODUCTS})
    for key, value in metadata.items():
        stripped = key.strip()
        if stripped.startswith("skillock."):
            stripped = stripped[len("skillock.") :]
        if stripped.lower() not in known and canonical_product(stripped) not in {ident for _, ident in PRODUCTS}:
            if stripped.lower() not in {phrase for phrase, _ in PRODUCTS}:
                continue
        if stripped.lower() not in known and stripped.lower() not in {ident for _, ident in PRODUCTS}:
            continue
        product = canonical_product(stripped)
        span = None
        raws = []
        bad = False
        for piece in value.split(","):
            piece = piece.strip()
            if not piece:
                continue
            nxt = parse_constraint(piece)
            if nxt is None:
                continue
            raws.append(piece)
            span = nxt if span is None else intersect(span, nxt)
            if span is None:
                pins.append(Pin(product, Range(_zero(), _zero()), f"{product} unsatisfiable ({value})"))
                bad = True
                break
        if bad or span is None:
            continue
        pins.append(Pin(product, span, f"{key} {','.join(raws)}"))
    return pins


def estimate_tokens(text):
    tokens = 0
    ascii_run = 0
    for ch in text:
        if ch.isascii():
            if ch.isspace():
                tokens += (ascii_run + 3) // 4
                ascii_run = 0
            else:
                ascii_run += 1
        else:
            tokens += (ascii_run + 3) // 4
            ascii_run = 0
            tokens += 1
    return tokens + (ascii_run + 3) // 4


@dataclass
class Frontmatter:
    name: str | None = None
    description: str | None = None
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    body: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def parse_document(raw):
    front, body = _split_frontmatter(raw)
    doc = _parse_frontmatter(front)
    doc.body = body.strip()
    return doc


def _split_frontmatter(raw):
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    raw = raw.lstrip("\n\r")
    if not raw.startswith("---"):
        raise ValueError("missing opening ---")
    rest = raw[3:]
    if rest.startswith("\r"):
        rest = rest[1:]
    if not rest.startswith("\n"):
        raise ValueError("missing newline after opening ---")
    rest = rest[1:]
    offset = 0
    for line in rest.splitlines(keepends=True):
        if line.rstrip("\n\r") == "---":
            return rest[:offset], rest[offset + len(line) :]
        offset += len(line)
    raise ValueError("unclosed frontmatter")


def _parse_frontmatter(front):
    lines = [line.rstrip("\r") for line in front.split("\n")]
    doc = Frontmatter()
    seen = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line[:1] in " \t":
            doc.errors.append(f"unexpected indent in frontmatter: {line}")
            i += 1
            continue
        key, value = _split_key(line)
        if key is None:
            doc.errors.append(f"expected key: value, got {line}")
            i += 1
            continue
        if key in seen:
            doc.errors.append(f"duplicate field `{key}`")
        seen.add(key)
        if value in {">", ">-", ">+", "|", "|-", "|+"}:
            text, i = _read_block(lines, i + 1, value.startswith(">"))
            _assign(doc, key, text)
            continue
        if value == "":
            if key == "metadata":
                meta, i, warnings = _read_metadata(lines, i + 1)
                doc.warnings.extend(warnings)
                doc.metadata.update(meta)
            else:
                i = _skip_nested(lines, i + 1, 0)
            continue
        text, i = _read_plain(lines, i + 1, _unquote(value))
        _assign(doc, key, text)
    return doc


def _split_key(line):
    if ":" not in line:
        return None, None
    key, value = line.split(":", 1)
    key = key.strip()
    if not key or " " in key:
        return None, None
    return key, value.strip()


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        inner = value[1:-1]
        out = []
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                i += 2
            else:
                out.append(inner[i])
                i += 1
        return "".join(out)
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _read_plain(lines, start, first):
    text = first
    i = start
    while i < len(lines):
        line = lines[i]
        if not line or line[:1] not in " \t":
            break
        trimmed = line.strip()
        if trimmed:
            if text and not text.endswith(" "):
                text += " "
            text += trimmed
        i += 1
    return text, i


def _read_block(lines, start, fold):
    collected = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line:
            collected.append("")
            i += 1
            continue
        if line[:1] not in " \t":
            break
        collected.append(line.strip())
        i += 1
    while collected and collected[-1] == "":
        collected.pop()
    if not fold:
        return "\n".join(collected), i
    out = []
    for line in collected:
        if line == "":
            if out and not out[-1].endswith("\n"):
                out.append("\n")
        elif not out or out[-1].endswith("\n"):
            out.append(line)
        else:
            out.append(" " + line)
    return "".join(out), i


def _indent(line):
    return len(line) - len(line.lstrip(" \t"))


def _read_metadata(lines, start):
    meta = {}
    warnings = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        indent = _indent(line)
        if indent == 0:
            break
        trimmed = line.strip()
        if trimmed.startswith("- "):
            warnings.append("skipped a list item directly under metadata")
            i += 1
            continue
        key, value = _split_key(trimmed)
        if key is None:
            warnings.append(f"skipped metadata line `{trimmed}`")
            i += 1
            continue
        if value == "":
            flat, i = _flatten(lines, i + 1, indent)
            warnings.append(f"metadata.{key} is not a string; flattened to `{flat}`")
            meta[key] = flat
        else:
            meta[key] = _unquote(value)
            i += 1
    return meta, i, warnings


def _flatten(lines, start, parent):
    parts = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent(line) <= parent:
            break
        trimmed = line.strip()
        if trimmed.startswith("- "):
            parts.append(_unquote(trimmed[2:].strip()))
        else:
            _key, value = _split_key(trimmed)
            if value:
                parts.append(_unquote(value))
        i += 1
    return ",".join(parts), i


def _skip_nested(lines, start, parent):
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent(line) <= parent:
            break
        i += 1
    return i


def _assign(doc, key, value):
    value = value.strip()
    if key == "name":
        doc.name = value
    elif key == "description":
        doc.description = value
    elif key == "license":
        doc.license = value
    elif key == "compatibility":
        doc.compatibility = value
    elif key == "allowed-tools":
        doc.allowed_tools = value.split()
    elif key == "metadata":
        doc.warnings.append("metadata must be a map of strings, not a scalar")


@dataclass
class Skill:
    path: Path
    name: str
    description: str
    compatibility: str | None
    metadata: dict
    body: str
    sha256: str
    parse_errors: list
    parse_warnings: list


@dataclass
class Finding:
    level: str
    code: str
    message: str


@dataclass
class Summary:
    name: str
    path: Path
    sha256: str
    startup_tokens: int
    body_tokens: int


@dataclass
class Report:
    skills: list
    findings: list
    startup_tokens: int
    body_tokens: int


@dataclass
class Options:
    startup_budget: int = 4000
    body_budget: int = 5000
    harness: dict = field(default_factory=dict)


def discover(roots):
    found = []
    seen = set()
    for root in roots:
        root = Path(root)
        if root.is_file() and root.name == "SKILL.md":
            _push(root, found, seen)
            continue
        _walk(root, 0, found, seen)
    found.sort()
    return found


def _walk(directory, depth, found, seen):
    if depth > 8 or not directory.is_dir():
        return
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for path in entries:
        if path.name in SKIP_DIRS or path.is_symlink():
            continue
        if path.is_dir():
            _walk(path, depth + 1, found, seen)
        elif path.name == "SKILL.md":
            _push(path, found, seen)


def _push(path, found, seen):
    try:
        key = path.resolve()
    except OSError:
        key = path
    if key not in seen:
        seen.add(key)
        found.append(path)


def local_roots(cwd):
    roots = []
    for rel in (".agents/skills", ".claude/skills", ".codex/skills", ".cursor/skills", "skills", "examples"):
        path = Path(cwd) / rel
        if path.is_dir():
            roots.append(path)
    return roots


def user_roots():
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        return []
    roots = []
    for rel in (".agents/skills", ".claude/skills", ".codex/skills", ".cursor/skills"):
        path = Path(home) / rel
        if path.is_dir():
            roots.append(path)
    return roots


def load_skill(path):
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as err:
        return Skill(path, "", "", None, {}, "", "", [f"unreadable: {err}"], [])
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return Skill(path, "", "", None, {}, "", digest, ["file is not UTF-8"], [])
    try:
        doc = parse_document(text)
    except ValueError as err:
        return Skill(path, "", "", None, {}, "", digest, [str(err)], [])
    return Skill(
        path,
        doc.name or "",
        doc.description or "",
        doc.compatibility,
        doc.metadata,
        doc.body,
        digest,
        doc.errors,
        doc.warnings,
    )


def _display(path):
    return str(path).replace("\\", "/")


def _relative(cwd, path):
    path = Path(path)
    try:
        rel = path.relative_to(cwd)
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


def _label(skill):
    return skill.name or _display(skill.path)


def _valid_name(name):
    if not name or len(name) > 64 or name.startswith("-") or name.endswith("-") or "--" in name:
        return False
    return all(ch.islower() or ch.isdigit() or ch == "-" for ch in name) and name.isascii()


def _content_words(text):
    words = []
    ascii_buf = []

    def flush():
        token = "".join(ascii_buf)
        ascii_buf.clear()
        if len(token) >= 2 and token not in STOPWORDS:
            words.append(token)

    for ch in text:
        if ch.isascii() and ch.isalnum():
            ascii_buf.append(ch.lower())
        elif not ch.isascii() and ch.isalnum():
            flush()
            token = ch
            if token not in STOPWORDS:
                words.append(token)
        else:
            flush()
    flush()
    return words


def _jaccard(a, b):
    left, right = set(a), set(b)
    shared = sorted(left & right)
    union = len(left | right)
    score = 0 if union == 0 else len(shared) / union
    return score, shared


def _polarity(sentence):
    lower = sentence.lower()
    forbid = any(phrase in lower for phrase in ("must not", "do not", "don't", "never"))
    require = ("always" in lower or "must" in lower) and "must not" not in lower
    if require == forbid:
        return None
    return "require" if require else "forbid"


def _sentences(body):
    out = []
    start = 0
    for i, ch in enumerate(body):
        if ch in ".!?\n":
            sentence = body[start:i].strip()
            if sentence:
                out.append(sentence)
            start = i + 1
    tail = body[start:].strip()
    if tail:
        out.append(tail)
    return out


def analyze(skills, opts):
    findings = []
    summaries = []
    startup_tokens = 0
    body_tokens = 0
    for skill in skills:
        startup = estimate_tokens(skill.name) + estimate_tokens(skill.description)
        body = estimate_tokens(skill.body)
        startup_tokens += startup
        body_tokens += body
        summaries.append(Summary(skill.name, skill.path, skill.sha256, startup, body))
        for err in skill.parse_errors:
            findings.append(Finding("error", "spec-frontmatter", f"{_display(skill.path)}: {err}"))
        for warning in skill.parse_warnings:
            findings.append(Finding("warning", "spec-metadata", f"{_display(skill.path)}: {warning}"))
        _validate(skill, findings)
        if body > opts.body_budget:
            findings.append(
                Finding(
                    "warning",
                    "body-budget",
                    f"{_label(skill)} body is {body} tokens, over the {opts.body_budget} token activation budget",
                )
            )
    if startup_tokens > opts.startup_budget:
        findings.append(
            Finding(
                "warning",
                "startup-budget",
                f"startup metadata is {startup_tokens} tokens, over the {opts.startup_budget} token budget. Agents load every name and description before a skill is chosen",
            )
        )
    _duplicates(skills, findings)
    _pins(skills, opts, findings)
    _overlap(skills, findings)
    _contradictions(skills, findings)
    findings.sort(key=lambda item: (0 if item.level == "error" else 1, item.code, item.message))
    summaries.sort(key=lambda item: (-item.body_tokens, _display(item.path)))
    return Report(summaries, findings, startup_tokens, body_tokens)


def _validate(skill, findings):
    if not skill.name:
        findings.append(Finding("error", "spec-name", f"{_display(skill.path)}: name is required"))
    elif not _valid_name(skill.name):
        findings.append(
            Finding(
                "error",
                "spec-name",
                f"{_display(skill.path)}: name `{skill.name}` must be 1-64 lowercase letters, numbers, or single hyphens",
            )
        )
    parent = skill.path.parent.name
    if skill.name and parent != skill.name:
        findings.append(
            Finding(
                "error",
                "spec-dir",
                f"{_display(skill.path)}: name `{skill.name}` does not match parent directory `{parent}`",
            )
        )
    desc_len = len(skill.description)
    if desc_len == 0 or desc_len > 1024:
        findings.append(
            Finding(
                "error",
                "spec-description",
                f"{_label(skill)}: description must be 1-1024 characters (got {desc_len})",
            )
        )
    if skill.compatibility is not None and (len(skill.compatibility) == 0 or len(skill.compatibility) > 500):
        findings.append(
            Finding(
                "error",
                "spec-compatibility",
                f"{_label(skill)}: compatibility must be 1-500 characters when present",
            )
        )


def _duplicates(skills, findings):
    groups = {}
    for skill in skills:
        if skill.name:
            groups.setdefault(skill.name, []).append(skill)
    for name, group in groups.items():
        if len(group) < 2:
            continue
        paths = ", ".join(_display(skill.path) for skill in group)
        findings.append(Finding("error", "duplicate-name", f"name `{name}` is used by {paths}"))


def _pins(skills, opts, findings):
    owned = []
    for skill in skills:
        collected = []
        if skill.compatibility:
            collected.extend(pins_from_text(skill.compatibility))
        collected.extend(pins_from_metadata(skill.metadata))
        by_product = {}
        for pin in collected:
            if "unsatisfiable" in pin.raw:
                findings.append(Finding("error", "pin-unsatisfiable", f"{_label(skill)}: {pin.raw}"))
                continue
            prev = by_product.get(pin.product)
            if prev is None:
                by_product[pin.product] = {"skill": _label(skill), "product": pin.product, "range": pin.range, "raw": pin.raw}
            else:
                merged = intersect(prev["range"], pin.range)
                if merged is None:
                    findings.append(
                        Finding(
                            "error",
                            "pin-unsatisfiable",
                            f"{_label(skill)} pins {prev['raw']} and {pin.raw} cannot both hold",
                        )
                    )
                else:
                    prev["range"] = merged
                    prev["raw"] = f"{prev['raw']}, {pin.raw}"
        owned.extend(by_product.values())
    grouped = {}
    for pin in owned:
        grouped.setdefault(pin["product"], []).append(pin)
    for product, group in grouped.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if not ranges_overlap(group[i]["range"], group[j]["range"]):
                    findings.append(
                        Finding(
                            "error",
                            "pin-conflict",
                            f"{product} pins do not overlap: {group[i]['skill']} wants {group[i]['raw']}, {group[j]['skill']} wants {group[j]['raw']}",
                        )
                    )
        installed = opts.harness.get(product)
        if installed is None:
            continue
        for pin in group:
            if not satisfies(installed, pin["range"]):
                findings.append(
                    Finding(
                        "error",
                        "pin-drift",
                        f"installed {product} {installed} is outside {pin['skill']} pin {pin['raw']}",
                    )
                )


def _pair_label(left, right):
    if left.name and left.name == right.name:
        return _display(left.path), _display(right.path)
    return _label(left), _label(right)


def _overlap(skills, findings):
    words = [_content_words(skill.description) for skill in skills]
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            if len(words[i]) < 6 or len(words[j]) < 6:
                continue
            score, shared = _jaccard(words[i], words[j])
            if len(shared) >= 4 and score >= 0.5:
                left, right = _pair_label(skills[i], skills[j])
                findings.append(
                    Finding(
                        "warning",
                        "overlap",
                        f"{left} and {right} may activate on the same request (shared: {', '.join(shared[:8])})",
                    )
                )


def _contradictions(skills, findings):
    lines = []
    for index, skill in enumerate(skills):
        for sentence in _sentences(skill.body):
            polarity = _polarity(sentence)
            if polarity is None:
                continue
            words = _content_words(sentence)
            if len(words) < 3:
                continue
            lines.append((index, polarity, words, sentence[:120]))
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if lines[i][0] == lines[j][0] or lines[i][1] == lines[j][1]:
                continue
            score, shared = _jaccard(lines[i][2], lines[j][2])
            if len(shared) >= 3 and score >= 0.6:
                findings.append(
                    Finding(
                        "warning",
                        "contradiction",
                        f"{_label(skills[lines[i][0]])} says \"{lines[i][3]}\", {_label(skills[lines[j][0]])} says \"{lines[j][3]}\"",
                    )
                )


def render(report):
    errors = sum(1 for item in report.findings if item.level == "error")
    warnings = len(report.findings) - errors
    lines = [
        f"{len(report.skills)} skills · startup {report.startup_tokens} tokens · bodies {report.body_tokens} tokens · {errors} errors · {warnings} warnings\n"
    ]
    if report.skills:
        lines.append("\nlargest bodies\n")
        for skill in report.skills[:5]:
            lines.append(f"  {skill.body_tokens:6}  {_display(skill.path)}\n")
    if report.findings:
        lines.append("\n")
        for finding in report.findings:
            lines.append(f"{finding.level}  {finding.code}  {finding.message}\n")
    return "".join(lines)


def to_json(report):
    import json

    return json.dumps(
        {
            "startup_tokens": report.startup_tokens,
            "body_tokens": report.body_tokens,
            "skills": [
                {
                    "name": skill.name,
                    "path": _display(skill.path),
                    "sha256": skill.sha256,
                    "startup_tokens": skill.startup_tokens,
                    "body_tokens": skill.body_tokens,
                }
                for skill in report.skills
            ],
            "findings": [
                {"level": finding.level, "code": finding.code, "message": finding.message}
                for finding in report.findings
            ],
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def write_lock(path, cwd, report):
    path = Path(path)
    skills = sorted(report.skills, key=lambda skill: _relative(cwd, skill.path))
    lines = [
        "# Generated by skillock. Do not edit by hand.",
        "version = 1",
        f"startup_tokens = {report.startup_tokens}",
        f"body_tokens = {report.body_tokens}",
        f"skill_count = {len(skills)}",
    ]
    for skill in skills:
        lines.append("")
        lines.append("[[skills]]")
        lines.append(f'name = "{_escape_toml(skill.name)}"')
        lines.append(f'path = "{_escape_toml(_relative(cwd, skill.path))}"')
        lines.append(f'sha256 = "{skill.sha256}"')
        lines.append(f"startup_tokens = {skill.startup_tokens}")
        lines.append(f"body_tokens = {skill.body_tokens}")
    text = "\n".join(lines) + "\n"
    if path.parent.as_posix() not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_lock(path):
    text = Path(path).read_text(encoding="utf-8")
    entries = []
    name = rel = sha = None

    def flush():
        nonlocal name, rel, sha
        if name is not None and rel is not None and sha is not None:
            entries.append({"name": name, "path": rel, "sha256": sha})
        name = rel = sha = None

    for line in text.splitlines():
        line = line.strip()
        if line == "[[skills]]":
            flush()
            continue
        if line.startswith("name = "):
            name = _unquote_toml(line[len("name = ") :])
        elif line.startswith("path = "):
            rel = _unquote_toml(line[len("path = ") :])
        elif line.startswith("sha256 = "):
            sha = _unquote_toml(line[len("sha256 = ") :])
    flush()
    return entries


def diff_lock(cwd, report, lock):
    findings = []
    current = {_relative(cwd, skill.path): skill for skill in report.skills}
    locked = {entry["path"]: entry for entry in lock}
    for path, skill in current.items():
        entry = locked.get(path)
        if entry is None:
            findings.append(Finding("warning", "lock-new", f"{path} is not in the lockfile ({skill.name})"))
        elif entry["sha256"] != skill.sha256:
            findings.append(Finding("warning", "lock-drift", f"{path} changed since the lockfile"))
    for entry in lock:
        if entry["path"] not in current:
            findings.append(
                Finding("warning", "lock-removed", f"{entry['path']} was locked and is no longer present")
            )
    findings.sort(key=lambda item: (item.code, item.message))
    return findings


def _escape_toml(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unquote_toml(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\\\", "\\")
