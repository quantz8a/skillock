"""The example pack must report the same gap as the Rust tests."""

import unittest
from pathlib import Path

from skillock.engine import (
    Options,
    Version,
    analyze,
    discover,
    estimate_tokens,
    load_skill,
    parse_constraint,
    parse_document,
    ranges_overlap,
    satisfies,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


class ExamplePackTest(unittest.TestCase):
    def test_reports_the_gap(self):
        files = discover([EXAMPLES])
        self.assertEqual(len(files), 6, files)
        skills = [load_skill(path) for path in files]
        options = Options(harness={"opencode": Version.parse("2.0.1")})
        report = analyze(skills, options)
        found = {item.code for item in report.findings}
        for code in (
            "spec-name",
            "spec-dir",
            "duplicate-name",
            "pin-conflict",
            "pin-drift",
            "overlap",
            "contradiction",
            "body-budget",
        ):
            self.assertIn(code, found, report.findings)
        self.assertEqual(report.startup_tokens, 152)
        self.assertEqual(report.body_tokens, 7356)
        errors = sum(item.level == "error" for item in report.findings)
        warnings = sum(item.level == "warning" for item in report.findings)
        self.assertEqual(errors, 5)
        self.assertEqual(warnings, 5)
        self.assertGreater(report.body_tokens, report.startup_tokens)

    def test_pins(self):
        installed = Version.parse("2.0.1")
        lower = parse_constraint(">=2")
        upper = parse_constraint("<2")
        self.assertTrue(satisfies(installed, lower))
        self.assertFalse(satisfies(installed, upper))
        self.assertFalse(ranges_overlap(lower, upper))
        pinned = parse_constraint("2026.9.8")
        self.assertFalse(satisfies(Version.parse("2026.10.3"), pinned))
        self.assertTrue(satisfies(Version.parse("2026.9.8"), pinned))

    def test_plain_description_continues(self):
        doc = parse_document(
            "---\nname: backtest\ndescription: first line\n  second line\n---\n\nbody\n"
        )
        self.assertEqual(doc.description, "first line second line")
        self.assertEqual(doc.body, "body")
        self.assertEqual(doc.errors, [])

    def test_token_budget_rounds_up(self):
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)
        self.assertEqual(estimate_tokens("ab cd"), 2)
        self.assertEqual(estimate_tokens("哈"), 1)


if __name__ == "__main__":
    unittest.main()
