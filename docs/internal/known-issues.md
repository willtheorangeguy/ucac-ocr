# Pool Headcount — Known Issues

Concrete defects and gaps found while writing this repository's documentation.
**Nothing here was changed** — each one needs a code, configuration, or
licensing decision rather than a documentation one.

Ordered by severity. See [`docs/roadmap.md`](../roadmap.md) for the narrative version,
which also covers deliberate non-goals.

**1 open:** 1 medium.

## 1. Calibration requires B-pass tasks that the default profile does not create

**Severity:** Medium

**Where:** `app/calibration.py:32-34`; `app/preprocessing.py:265-266`; `app/config.py:18`

**What:** The calibration command unconditionally selects a B header task with next(...). The default VERIFICATION=off setting skips creation of B tasks. The selection therefore raises StopIteration (surfacing as RuntimeError in the coroutine) before the benchmark request loop when run with the default profile.

**Why it matters:** The documented live benchmark cannot run with the shipped default settings, which prevents operators from obtaining its date/first-row comparison report.

**Suggested fix:** Either make calibration explicitly construct its A/B benchmark independently of the production profile, or validate the required profile before creating records. Until then, use an isolated DATA_DIR with VERIFICATION=always and ROUGH_COUNTS=false as documented in docs/testing.md.
