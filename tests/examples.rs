use std::collections::BTreeSet;
use std::path::PathBuf;

use skillock::{analyze, discover, load_skill, Options, Version};

fn examples() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("examples")
}

fn codes(report: &skillock::Report) -> BTreeSet<&'static str> {
    report.findings.iter().map(|finding| finding.code).collect()
}

#[test]
fn example_pack_reports_the_gap_the_issue_trackers_describe() {
    let files = discover(&[examples()]);
    assert_eq!(
        files.len(),
        6,
        "expected the six example skills, found {files:?}"
    );
    let skills: Vec<_> = files.iter().map(|path| load_skill(path)).collect();
    let mut options = Options::default();
    options
        .harness
        .insert("opencode".into(), Version::parse("2.0.1").unwrap());
    let report = analyze(&skills, &options);
    let found = codes(&report);
    for code in [
        "spec-name",
        "spec-dir",
        "duplicate-name",
        "pin-conflict",
        "pin-drift",
        "overlap",
        "contradiction",
        "body-budget",
    ] {
        assert!(
            found.contains(code),
            "missing {code} in {found:?}\n{}",
            skillock::render(&report)
        );
    }
    assert!(report.body_tokens > report.startup_tokens);
}
