# BUF native next-bar capture and automatic USE

OS 1.16, 2026-10-22. Separate ONESHOT emulator adapter. Implementation follows
[the frozen next-bar plan](BUF-NEXT-BAR-PLAN.md). Existing Flex R5, normal
builders, dependencies and prior performance sources are preserved.

The selected slice is **SAMPLING+YES on an initialized selected BUF, one bar,
then automatic USE**. This fixes capture length to one normal 16-step cycle;
it does not map the existing R.LEN/MAX setting into bars. The original source
and channel remain in use. Clock, project, kit, selection and settings checks
can refuse or cancel the request. Existing SAMPLING+C FREEZE remains installed.

Native source-57 code observes progression; native GUI service performs
controller start/stop; original normalization and queued BUF copy/load execute;
a native completion callback assigns only a fully loaded valid candidate.
The interrupt performs no capture, allocation, file work or publication.
Capture, SSI/LP0 delivery and SEC reset remain modeled. No hardware operation,
firmware package, commit, push or publication.

## Corrections and retained candidates

The first panel candidate refused before capture. A read-only native diagnostic
measured the clock selector's result as 0, raw selector word 1. The initial
expected result 1 was wrong. The corrected guard still refuses other results.
Artifacts: `out/runs/buf-next-bar-cpu-20261022-01/` and
`out/runs/buf-next-bar-mode-20261022-01/`.

The next CPU candidate completed a 56,464-frame capture and native automatic
USE, but its phase audit found that 15 -> 0 is one step before the native
first-step note. Known grid notes 1/5/9/13 occur with native counters
1/5/9/13. That candidate therefore proves duration/orchestration, not correct
next-bar phase: `out/runs/buf-next-bar-cpu-20261022-02/`. Its clock/cancel
controls pass for those earlier sources. The initial coupled candidate was
interrupted during setup, and is retained as failed rather than qualification:
`out/runs/buf-next-bar-coupled-20261022-01/`.

The corrected interrupt requires 15 -> 0 followed by 0 -> 1, refuses an
initial PLAY as a completed bar, and emits each receipt once. The final driver
requires both first-step receipts and a real first-step note before the native
counter advances to step 2. The read-only phase evidence is
`out/runs/buf-next-bar-audit-20261022-01/bar-phase-audit.json`.
Pre-correction plans/contracts and source snapshots are retained; failed
reports and expected outcomes were not rewritten.

Thirteen focused ColdFire tests pass, including original short controller
start/reset/discard bodies and explicit native stubs at normalization/worker
boundaries. They cover full-cycle versus duplicate/jump/unsupported clock,
missed/late boundary refusal, cancellation, stale settings, queued publication,
worker/assignment failure, NORMAL/other ARM callers, stack/register preservation
and deterministic repeat. Final focused log:
`out/buf-next-bar-unit-focused-20261022-05.log`.

The corrected CPU panel scenario passes, including both first-step note
alignment assertions:
`out/runs/buf-next-bar-cpu-20261022-03/report.json`. The later payload adds the
stale-project ownership guard covered by the thirteenth test; the coupled run
uses that final payload. The final-source negative controls also pass:
`out/runs/buf-next-bar-no-clock-20261022-03/report.json` and
`out/runs/buf-next-bar-cancel-20261022-03/report.json`. Missing receipts and
STOP-before-bar produce neither capture nor publication.

All 428 tests pass (`out/buf-next-bar-unit-20261022-01.log`). SINE replay passes
with sources identical to the coupled run:
`out/runs/20261022T094300Z-test-55fc38ee/manifest.json`
(`out/buf-next-bar-sine-20261022-01.log`). Scoped Ruff checks pass.

The final coupled scenario **passes**:
`out/runs/buf-next-bar-coupled-20261022-02/report.json`. Its separate read-only
evidence audit passes:
`out/runs/buf-next-bar-audit-20261022-01/verification.json`.

- One SAMPLING+YES request is admitted away from the bar boundary. Native
  first-step receipts occur at frames 8400 and 11930, both counter 1/pulse 0.
  The known first-step pattern note occurs before counter 2 on both occasions.
  Controller START and STOP originate in native GUI service code, with normal
  interrupt masks. No bar is supplied by the host.
- Recording spans those two consecutive receipts: **56,480 stereo frames**,
  112,960 native clock ticks. Reported start/stop delay is zero at the model's
  32-tick block-clock resolution. This is not measured physical capture latency.
- Original normalization reaches state 4; the existing native background
  copy/load worker succeeds; the native completion assigns BUF slot 300 with
  a new generation token. Captured and published PCM match exactly. No
  post-arm record/stop/trim/YES input occurs. There is one start, stop and USE.
- The native pattern continues with ten actual T1 note triggers, including
  a note after automatic USE. Its active voice PCM is finite and nonzero.
  All 32 voice buffers match original stock execution for the reported
  **12,858 blocks** through the performance before final STOP; final STOP
  frames are also compared by the same per-frame assertion.
- Frozen A remains in snapshot slot 312 and its private allocation remains
  intact. Current B and frozen A each match an independently stock-loaded
  sample for 48 playback blocks. Both current/frozen roots stay pinned, so
  this two-take scenario requires no automatic retirement submission.

The native DSP blob is byte-identical to the prior playing-pattern BUF flow:
`db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7`.
Final source maps match SINE and both final negative controls. The 860
inherited files are preserved except for intentional README/status pointers;
dependencies remain clean. The existing Flex R5 package retains SHA-256
`668b5fa644427dffbe7d1bde757ac31ac1824fd8b28e5a8e647dd240f911b3b1`.

## Reproduction

Use the configured Python 3.12 and fresh ignored output names:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
"$LAB_PYTHON" -m unittest discover -s tests -p test_buf_next_bar.py -v
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-buf-next-bar.py out/runs/YOUR-UNIQUE-NEXT-BAR-RUN
```

Add `--cpu-only` for native control/capture/publication without SHARC evidence.
The negative controls use `--cpu-only --no-clock` or
`--cpu-only --cancel-before-bar`. Required aggregate checks are
`"$LAB_PYTHON" -m unittest discover -s tests -v` and `./labctl test sine --replay`.

## Boundaries

Initialization currently requires a manually accepted BUF take. All sixteen
tracks must be ONESHOT. Length is one bar, normal 16-step master only; source
settings edits cancel. NORMAL destination and other stock ARM callers retain
the original function. Stopped or ineligible BUF requests are refused.

Automatic USE means assignment after successful native loading; it does not
promise publication before the first note of the following bar. Measured
controller delay has the model's block-clock resolution and is not physical
DSPI capture latency or sample-accurate hardware quantization. Other lengths,
scales, external clock, tempo transitions, status feedback, save/recall and
shipping memory placement remain open. Unknown project ownership prevents
publication and does not discard a different project's recorder or release a
foreign lease. Such a context is quarantined; recovery across arbitrary
project transitions still requires separate work. Normalization's remote
audio operation is modeled; this does not establish live internal/external
capture, final output, listening, physical timing or hardware operation.
