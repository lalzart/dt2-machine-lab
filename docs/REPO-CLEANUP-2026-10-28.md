# Repository cleanup — 2026-10-28

Purpose: make the current Sketch/CAPI/ARP path unambiguous while preserving
working firmware bytes, user changes and reproducible evidence.

Changes:

- Removed the obsolete `--capicola-legacy`, `--capicola-quality` and
  `--capicola-source` options and their packaging branches. The OS packager uses
  the author port for `--all-features`; the current Sketch combination is unchanged.
- Deleted two unused early probe entry points: `probe-capicola-target.py` and
  `probe-capicola-stretch-path.py`. No active source imports or calls either.
- Split current `capicola` checks from explicit `capicola-history`. Every existing
  test module remains owned once, and `all` still includes all tests.
- Archived 38 superseded Capicola, Flex and Sketch documents/verification records;
  updated Markdown links. [History index](history/README.md) maps old paths.
- Replaced the stale feature map, added a documentation map and current Capicola
  guide, and corrected STATUS to point at the delivered switch-fixed OS.
- In the sibling research workspace, archived the early machine-lab proposal
  and ARP feasibility note, and removed the redundant retired-counselor stub.

Retained intentionally: the 66 authenticated author source files and licenses;
old engine sources used by explicit historical checks; shared CAPI memory/layout,
SHARC wrapper and UI helpers; frozen proposal documents/contracts; all original
firmware, runs, failed evidence, dependencies and unrelated work. The older
low-level `labctl ... capicola` experiments are identified as historical, rather
than silently changed into a different build.

Before editing, saved both repositories' non-ignored working files, hashes,
Git HEAD identities, dirty diffs and status under the ignored local directory
`out/runs/repo-cleanup-20261028-01/`. `lab-before.tar.gz` and
`research-before.tar.gz` are recovery snapshots, not new checkouts. No commit,
push, dependency update, hardware operation or generated-firmware deletion.

Validation results are recorded in that directory's verification.json. This
cleanup makes no new hardware or audio-quality claim.

Verified results:

- 324 BUF/core/integration/current-Capicola/historical-Capicola tests pass. All
  82 test modules remain in the catalogue, with no duplicate ownership.
- Fresh Sketch/CAPI/ARP OS, MAIN, DSP and CPU layout match the delivered switch
  correction exactly. The accepted R8 MAIN/DSP and earlier author R2 all-feature
  OS also rebuild byte-for-byte. No new audio replay was needed for unchanged
  firmware bytes.
- All 66 original author files and 55 protected proposal documents are unchanged.
  No unintended changes among the two repositories' original files were found.
- Local Markdown link audit: no new broken links. Existing historical references
  to unavailable local material remain recorded separately. Ruff, diff whitespace
  checks and `labctl doctor` pass. Retired CLI options refuse before creating output.

The detailed local [verification record](../out/runs/repo-cleanup-20261028-01/verification.json)
contains report hashes and recovery archive identities. The cleanup is uncommitted.

## Follow-up: routine tests and agent navigation

Measured before removing anything: the routine BUF/core selection took 5.77s
for 235 tests on this host with its configured Rust bridge, with no skips.
No exact duplicate test bodies were found. Unit suites run separately from OS
builds; long coupled recorder/audio workflows also require explicit commands.

- Extracted 12 full-profile build checks from mixed behavior modules into
  `tests/test_sketch_builds.py`. Together with the 12 existing device build
  checks they form explicit `sketch-build`. Original assertions remain covered.
- Added `buf-selector`, `buf-recording`, `buf-save` and `buf-managed` selections.
  `buf` still combines current behavior and shared recorder support. `buf-full`
  and `all` retain build coverage and the earlier native fixtures.
- After selection changes, BUF/core passed 211 tests in 3.04s, no skips;
  focused `buf-managed` passed 33 in 0.72s, no skips. The 24 explicit build checks
  also passed. These are local timings, not OS compile-time improvements.
- Made [docs/README.md](README.md) the task/source/check entry point and updated
  both repositories' agent instructions. STATUS remains the current status
  source; feature guides point to existing evidence and historical work stays
  available for targeted lookup.

This follow-up changes tests and navigation only. It keeps the original cases,
builder integrity guards and firmware sources. No OS or audio replay was needed.
Recovery snapshots, moved-test mapping, timings and preservation checks are in
the local [verification record](../out/runs/test-navigation-cleanup-20261028-01/verification.json).
