# BUF with a playing native pattern

OS 1.16, 2026-10-22. Implementation of the
[performance increment](BUF-PERFORMANCE-PLAN.md). This is a separate BUF
emulator adapter; existing Flex R5 and normal firmware builds are preserved.
No package, commit, push, publication or hardware operation.

## Native input and transport

`lab/buf_performance.py` adds **hold SAMPLING and push encoder C** to freeze
the selected track's current BUF version while the native transport is playing.
It resolves the actual selected track and sample slot through original stock
getters, then matches one of the four BUF roots. The recorder's remembered
destination is unchanged. Ordinary SAMPLING taps, SAMPLING+YES, encoder rotation
and unrelated keys stay on their original paths. FUNC and other conflicting
modifiers, non-BUF tracks, a stopped transport, non-ready recording and unsafe
mutation contexts are refused without creating a snapshot.

The chord queues one original FREEZE job. C and SAMPLING release ownership
prevents a second request or recorder navigation. Epoch/kit changes refuse
the latched request before worker admission. The original automatic cleanup
already yields its lease to pending explicit FREEZE. Snapshot creation still
runs in the original native background service; the input handler performs no
PCM copy, allocator action, file write or assignment change. Snapshot outcome
is available through the existing native snapshot slot/name; no new success
overlay is provided.

`lab/buf_performance_ui.py` installs the guarded native bridge and observes
original source-57 exits, native input and the guest instruction writing the
FREEZE serial. The original native transport getter at `0x400d6726` reads the
real active/mode fields. A preparatory read-only clock trace observed repeated
sequencer-generated control triggers, step progression during PLAY and zero
transport flags after STOP:
`out/runs/buf-performance-clock-20261022-01/report.json`.

## Focused evidence

Nine executed ColdFire tests pass: selected BUF 1–4 independently of recorder
destination, stopped/non-BUF refusal, modifiers, exactly one request per chord,
both release orders, untouched ordinary keys, busy/recording/machine contexts,
automatic-lease priority, stale epoch/kit and register/stack preservation.
Deterministic native input replay is byte-identical. Prepared getter/context
fixtures are separate from the panel checks.

CPU-only actual-input probe passes:
`out/runs/buf-performance-gesture-20261022-04/report.json`.
The native instruction at `0x10f01352` writes the one FREEZE request; its worker
creates snapshot slot 312 while native PLAY remains active. The
[actual framebuffer](../out/runs/buf-performance-gesture-20261022-04/01-native-freeze-playing.png.png)
was inspected and remains on SRC. This probe does not render SHARC audio.

Failed probe records are preserved. The first script lacked the pinned tool
import path and did not execute its scenario. Subsequent native-input probes
correctly refused a non-BUF track: the trig-entry fixture left T16 selected,
and the diagnostic getter returned track index 15. Reselecting T1 through
original TRK+TRIG controls fixes the fixture; the eligibility guard is unchanged.
The refusal is retained as evidence that the remembered BUF destination does
not override the selected track. No failed outcome was rewritten as a pass.

All 415 unit tests pass: `out/buf-performance-unit-20261022-01.log`.
SINE replay passes on the frozen native payload and adapter sources:
`out/runs/20261022T081126Z-test-e4cf8af4/manifest.json`
(`out/buf-performance-sine-20261022-01.log`). The corrected panel driver is the
only executable-source difference from that manifest. Scoped Ruff check and
format checks pass for the four new Python files.

The first coupled scenario is preserved as failed:
`out/runs/buf-performance-20261022-01/report.json`. Native sequence counters
advanced but T1 emitted no note triggers, so its successful cleanup and file
oracles do not establish the musical workflow. A fast CPU-only reproduction
confirmed the missing notes. Completing USE and returning through the original
SRC and TRK+TRIG 1 controls before pattern entry fixes the panel setup. The
corrected CPU-only probe observes 17 native T1 triggers selecting slot 300 and
the actual FREEZE chord while PLAY remains active:
`out/runs/buf-performance-pattern-20261022-02/report.json`.

The corrected coupled scenario **passes**:
`out/runs/buf-performance-20261022-02/report.json`. A separate read-only evidence
audit also passes:
`out/runs/buf-performance-audit-20261022-01/verification.json`.

- Four distinct short stereo takes use one stable public BUF slot 300 and four
  distinct generation tokens. Native PLAY stays active through record/trim/USE
  for B, C and D, with actual T1 note triggers in each recording interval.
- Fourteen native T1 pattern triggers select slot 300. Original source-57
  exits show master steps 1–13. STOP clears the native transport; restart
  produces another real note at frame 9045. No host bar events or manual
  reader-drain pad notes are supplied.
- The native SAMPLING+C instruction at `0x10f01352` submits exactly one FREEZE
  request for selected BUF 1. Snapshot slot 312 retains A; all sixteen track
  assignments remain unchanged across the chord. The
  [coupled framebuffer](../out/runs/buf-performance-20261022-02/01-native-freeze-playing.png)
  shows the native SRC page with its stock CLEAR TRACK SEQUENCE setup message;
  it is not FREEZE success feedback. A new success overlay is still open work.
- Native policy submits B and C once each, and both native retirement
  transactions succeed while the pattern continues. Frozen A and current D
  remain allocated, with two linked source records and 32,768 bytes of
  recording DSP storage. No host retirement command or pause certificate is
  used. This scenario has no retained-reader timeout; the previous automatic
  cleanup scenario separately exercises that refusal and retry.
- All 32 raw voice buffers match original stock execution exactly for 9,393
  coupled blocks. Each take interval has finite, nonzero active T1 voice PCM;
  measured peaks are 0.16617–0.16666. Current D and frozen A also pass separate
  48-block comparisons against independently stock-loaded sample files.

The native DSP blob is unchanged from automatic cleanup:
`db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7`.
The executable sources remain stable during the run. The 850 inherited files
are preserved except for the intentional README/status pointers; pinned
dependencies remain clean. The existing Flex R5 package retains SHA-256
`668b5fa644427dffbe7d1bde757ac31ac1824fd8b28e5a8e647dd240f911b3b1`.
This is one bounded performance scenario, not completion of the separate
100-cycle native-retirement qualification.

## Reproduction

Use configured Python 3.12 and a fresh ignored output directory:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
"$LAB_PYTHON" -m unittest discover -s tests -p test_buf_performance.py -v
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-buf-performance.py out/runs/YOUR-UNIQUE-BUF-PERFORMANCE-RUN
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

The coupled scenario uses four deterministic short stereo takes. The existing
native panel recipe prepares pattern controls, then explicitly reselects the
BUF track before the chord. Capture input, LP0 delivery, SSI cadence, callback
delivery and SEC reset remain modeled. Native sequencer instructions produce
the musical progression; no TEST-bar event, host note scheduler or manual
reader-drain pad sequence is used. Audio comparison is raw stock voice PCM,
not final output, listening, hardware capture or physical timing.

## Remaining work

Recording still uses the original record/stop/trim/USE actions. Native
next-bar capture, selected-length completion and automatic USE are not bound.
The newly observed normal sequencer step is not yet a validated general bar
contract across tempo, length/scale, external clock and transport transitions.
All sixteen live kit tracks must still be ONESHOT. Native BUF readback/SAVE,
arbitrary project roots and transitions, shipping memory placement, device
feedback/timing and a combined Flex/BUF firmware remain separate work.
