---
name: skillock
description: Check agent skills for token budget, conflicting instructions, duplicate names, and incompatible harness version pins. Use when installing skills, when an agent gets slower after skills are added, or when a skill breaks after a harness upgrade.
license: MIT
metadata:
  author: skillock
  version: "0.1.0"
---

Run `skillock check` in the directory that contains the skills. Pass installed harness versions with `--harness opencode=2.0.1,claude=2.1.299`.

The first line of the report is the budget. Errors mean duplicate names, a broken Agent Skills manifest, version pins that cannot be true together, or an installed harness sitting outside a pin. Warnings mean two descriptions may activate on the same request, two bodies give opposite always/never instructions, or a body is over the activation budget.

Write `SKILLOCK.toml` with `skillock lock` after accepting the report. Do not edit that file by hand.
