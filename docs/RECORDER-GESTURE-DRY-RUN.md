# SAMPLING shortcuts — opt-in dry run

Implementation contract, 2026-10-20, OS 1.16. User authorized gesture recognition
and WOULD ARM / WOULD FREEZE feedback only. No recorder arm/start, FREEZE,
sample allocation, assignment, persistence or musical-bar scheduling may be
called by the recognizer. Normal firmware builds and earlier experiments stay
unchanged. The previous evidence is [the gesture investigation](RECORDER-PERFORMANCE-GESTURES.md).

The prototype will use a host state machine driven by the original native
panel events and panel timer. In BUF mode it will defer an ordinary SAMPLING
release until the 32-tick press-to-press double window expires. A matching
second press wins once; a lone hold wins once at 64 ticks. A recognized double
cannot subsequently become a hold. A held cycle and rapid third tap are
consumed through release. NORMAL is immediate stock passthrough.

Scope: ordinary performance dispatch, ready recorder state, BUF 1–4. Recorder,
armed/recording/trim, naming and other modal contexts retain stock handling.
Other buttons cancel pending recognition and retain their stock actions.
An encoder turn during a hold passes to the performance page; a turn following
a deferred single tap flushes that tap first, so it edits the recorder rather
than the page being left. Project/destination/context changes invalidate intent.

Only an ordinary delayed navigation event may be replayed through the stock
UI dispatcher, on the existing GUI task stack with registers/CCR preserved.
This bridge is emulator code and not a hardware installation. Feedback is an
explicit host overlay on a copy of the emulator's latched OLED, with an original
small bitmap font; it does not modify sample data or native display memory.
This is not native FREEZE or a native recorder binding.

Acceptance: deterministic unit timing/chord/epoch tests; original UART input
and native event traces; stock versus candidate NORMAL comparisons; delayed
single navigation timing; no recorder-operation side effects from dry gestures;
double/hold feedback without recorder navigation; encoder routing, cancellation,
triple/second-hold, modal and project controls; current unit suite and SINE replay.
Record source hashes and failed controls. Millisecond estimates and subjective
responsiveness must remain separate from physical device measurements.

## Implemented prototype

2026-10-21. The opt-in adapter is `lab/recorder_gesture_ui.py`, its pure input
model is `lab/recorder_gestures.py`, and the runnable entry point is
`scripts/check-recorder-gesture-dry.py`. Nothing imports this adapter into the
normal firmware build. Omitting `--dry-run` leaves gesture handling stock;
selecting NORMAL also bypasses recognition and delayed replay completely.

| Input, with BUF 1–4 selected on a tested performance page | Dry-run result |
| --- | --- |
| Short single tap | Delay ordinary recorder navigation until first press +32 panel ticks |
| Matching second press before that deadline | Show `WOULD ARM` / `BUF n NEXT BAR`; consume release; stay on the performance page |
| First press held through +64 ticks | Show `WOULD FREEZE` / `BUF n` once; consume ordinary release; stay on the performance page |
| Hold the second press of a double | Keep the one ARM intent; no later FREEZE |
| Rapid third tap | Consume the extra cycle; no recorder flash or second intent |
| Turn an encoder while holding SAMPLING | Forward the original rotation; keep the hold eligible |
| Release a short tap, then turn an encoder | Flush pending recorder navigation and deliver the turn after the recorder is drawn |
| Turn an encoder between double-tap presses | The preceding rule wins: navigate as a single tap; no WOULD ARM, even if native input later reports a fast double |
| Release a short tap, then press YES | Flush navigation and deliver YES to the original manual recorder |
| Other button, modified chord, project/destination/context change | Cancel pending recognition; retain stock button dispatch |

`NEXT BAR` describes the intended future command. This adapter has **no musical
bar clock, arm command, FREEZE command, sample assignment or persistence call**.
It does not check committed-buffer availability: an empty selected BUF can
show WOULD FREEZE. EMPTY/BUSY/capacity admission belongs to the later backend.

The adapter extends the existing `NormalBufferUI` C-destination experiment.
Its independent, ordinary manual recorder workflow remains available. In
particular, an explicit tap-then-YES or SAMPLING+YES can still start/arm stock
recording. That is preserved manual input, not an action from a dry intent.
Tests distinguish those calls from the no-command gesture cases.

### Actual native path versus host assistance

The native panel receives UART8/eDMA input and constructs the original OS 1.16
key events at `0x40114624`. The adapter observes the original key dispatcher
`0x40030bd0`, encoder dispatcher `0x40030b64`, performance key handler
`0x4005dc58`, recorder handler `0x40022c6e`, and GUI loop `0x40033d00`.
Recognition uses the original panel counter at `0x47ddec1c`, unwrapped from
its 12-bit cycle. It does not use the unmodeled DTIM timestamp or a host
wall-clock timeout. The original double window is 32 ticks; the stock hold
milestone is at +64. Native repeats and later milestones cannot retrigger it.

Recognition, cancellation, the input queue and feedback composition are
**host Python**. The feedback is drawn over a copy of the latched 128×64 OLED;
the original guest framebuffer remains available for exact comparisons. An
original small 5×7 font is used for the diagnostic overlay. This is not a
native display widget or a target firmware UI patch.

Only delayed ordinary SAMPLING navigation and its following value-only UI
inputs are replayed through original dispatch. A 54-byte ColdFire bridge in
an explicit emulator-only mapping at `0x10500000` saves/restores D0–D7, A0–A7
and CCR on the current GUI task stack. Every completed replay checks those
registers and CCR at its resume site. This is not a target memory reservation
and does not borrow Capicola memory. Only authenticated stock patch-site
bytes are accepted. No recorder or FREEZE worker is invoked by the bridge on
behalf of a WOULD intent.

Recorder navigation activates asynchronously. An early implementation could
return to an encoder handler before the recorder had become the active view.
The final adapter queues at most 16 cloned 24-byte, value-only native inputs,
waits for the original recorder draw (`0x40021de0`), then replays each input
through its original dispatcher. Epoch/kit/destination changes and a 64-tick
navigation timeout cancel stale work. A too-late second SAMPLING tap follows
this same original navigation path. Queue exhaustion fails the diagnostic;
a production overflow policy is not implemented or stress-tested.

The gesture scope is a **native routing gate**, not an exhaustive page-ID
allowlist. SRC, AMP, FLTR and LFO are exercised. A recorder-handler visit,
armed/capturing/trim state, other held key, or existing publication job blocks
admission. Keyboard, mute, song, arbitrary modal stacks and the combined
legacy Flex R5 package remain separate integration audits.

### Reproduce

Run from `dt2-machine-lab`, with the configured Python 3.12/private OS 1.16
fixture available. The scripts re-exec that interpreter and run doctor.
Each output directory must be fresh.

```sh
./labctl doctor
python3 scripts/check-recorder-gesture-matrix.py out/runs/MY-gesture-matrix
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-gesture-window \
  --dry-run --destination 1 --window --window-seconds 600
```

The window uses DigiKit's original panel/OLED controls. `S` is SAMPLING down/up,
Return is YES, Escape is NO, and `F` is FUNC. On the recorder page C selects
NORMAL/BUF 1–4; return to SRC to try the performance gestures. Omitting
`--dry-run` provides a stock gesture control. The window shows actual guest
instruction throughput: gesture time stretches with a slow emulator. Its
wall-clock feel cannot qualify physical button latency. The ten-second smoke
test opened, refreshed and closed the panel with control frames advancing;
it is not an ergonomics or audio-performance test.

For one deterministic case:

```sh
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-gesture-double \
  --dry-run --case double
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-gesture-normal \
  --dry-run --destination 0 --case double
```

All screenshots, native event/recorder-call traces, stage hashes, frozen source
copies and bridge results are in each run's `report.json` and PNG files.

## Executed results

The final matrix is **56 cases / 452 assertions PASS** in
`out/runs/recorder-gesture-dry-matrix-20261021-02/verification.json`.
The source manifest SHA-256 is
`c797e44c926fa07d825e62a67567a095d90390592d1359a625b4d421aea06832`
(573 sources). All children retain the same source map. The supplemental
`recorder-gesture-dry-20261020-audit-01/final-verification.json` checks source
preservation, the encoder-gap result, native draws, ABI preservation, tests,
SINE, formatting and the interactive smoke against that map.

| Test | Observed result |
| --- | --- |
| NORMAL single/double/hold, enabled versus disabled | Exact original OLED sequences **and native key events/timing**; no delayed replay |
| BUF 1–4 fast double | One WOULD ARM for the selected destination; no recorder navigation or command |
| Hold / 260-tick extended hold / held second double press / triple | Once-only recognition; later repeat/milestone flags cannot retrigger; double never becomes FREEZE |
| SRC, AMP, FLTR, LFO (native MOD button) | Hold intent stays on the tested performance page |
| After PLAY input | Single, double, hold and encoder-hold execute; does not prove musical bar position, notes or audible playback |
| A/C turns during hold | Actual playback-parameter changes exactly match stock kit bytes; no deferred/replayed turns; one WOULD FREEZE |
| C immediately after a released tap | All queued inputs reach original recorder rotation; final DEST matches stock; playback kit bytes unchanged |
| YES immediately after a released tap | Original manual recorder reaches state 2, with no WOULD intent |
| Existing SAMPLING+YES/NO, FUNC orders, C-push orders, double STOP | Stock dispatch retained; pre-threshold chords cancel dry recognition; reverse FUNC OLED matches stock |
| Recorder ready, waiting-arm model, capture foreground/background, trim, name | No dry takeover; completed PCM preserved; filename OLED remains unchanged |
| Project epoch / destination / busy changes | Pending intent canceled; these are explicit injected controls, not complete project-load or allocator-pressure tests |
| Encoder in the double-tap gap, separate focused probe | Native fast-double flags 0x5 still arrive, but early single navigation wins; no WOULD ARM; C edits recorder DEST |

All 56 matrix cases preserve the 16 track sample assignments and the observed
issued-identity/source/handle/page counts, with CPU control frames advancing.
Fifteen completed WOULD cases (excluding the deliberate late-YES stock ARM)
have **no original recorder draw after setup**, independently of the host's
navigation log. All 21 replay completions preserve registers/stack and CCR.
This is not a whole-heap benchmark or a continuous audio deadline measurement.

Quiet ARM tests explicitly model a nonzero external status at `0x400cd702`
while the native state is 1. Reports flag/count that assistance. Generic
emulator input otherwise falsely progresses an armed zero-frame producer;
this model tests key handling, not native threshold detection. The filename
fixture uses stock NORMAL capture/name and explicitly seeds BUF selection to
test modal exclusion. It is not a native BUF naming/persistence test.

### Single-tap responsiveness

Measured from the **original release-event construction** to the **original
recorder draw**, using PIT instructions divided by the configured 132 million
instructions/second. Approximate panel cadence is 120 ticks/second in this
model. Neither measurement includes physical switch scanning/debounce.

| Press dwell, panel ticks | Stock release→draw | Dry release→draw | Added modeled delay |
| --- | --- | --- | --- |
| 6, short tap | 0 ticks / 0.46 ms | 32 ticks / 267.13 ms | **266.67 ms** |
| 24, longer tap | 2 ticks / 18.59 ms | 14 ticks / 118.59 ms | **100.00 ms** |
| 40, past double deadline but before hold | 2 ticks / 18.55 ms | 2 ticks / 18.55 ms | **0 ms** |

Yes: short ordinary taps gain enough modeled delay to plausibly feel less
responsive. That is an inference from the measured wait, not a physical
ergonomics result. NORMAL has no added wait. An encoder or YES after release
can flush navigation early, with the encoder-gap tradeoff below. Double intent
appears at the matching second press; hold intent appears at +64 ticks
(approximately 0.53 modeled seconds), without waiting for release. Feedback
lasts 120 ticks and expires even if the key remains held.

Unit tests exercise the strict 31/32-tick boundary, repeat/duplicate edges,
64-tick hold, cancellation and context epochs. Executable native probes cover
fast and late taps; a dense native scheduling/jitter sweep around the exact
deadline has not been run. Do not choose a physical threshold from these data.

### Regression and retained artifacts

**316 unit tests PASS** (302 inherited plus 14 new timing/state tests), in
`out/recorder-gesture-dry-unittest-20261021-02.log`. SINE replay **PASS** in
`out/runs/20261020T155027Z-test-62be3922/manifest.json`, with the same 573-source
map. Its exact-repeat/baseline, stock-isolation and lifecycle checks pass at
the existing voice-buffer boundary. Ruff check and format-check pass for all
six new Python files. Doctor passes; all 568 inherited source files and all
50 inherited unit files match their initial hashes. Final tests are copied
into the audit's `frozen-tests/` directory.

Exact additional commands used:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" -m unittest discover -s tests -v
./labctl test sine --replay
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-gesture-dry-20261020-audit-01/check-gap-encoder.py out/runs/NEW-gap-encoder
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-gesture-dry-20261020-audit-01/check-final.py
```

The last command verifies retained final artifacts; the matrix command above
creates a fresh complete reproduction. The gap probe is a run-local UART
fixture, imports the unchanged production adapter, and hashes both itself and
the same standard source map. It never connects a backend.

Final interactive smoke: `out/runs/recorder-gesture-dry-window-20261021-02/`.
Actual 128×64 OLED captures exported at integer scale:

- [WOULD ARM](../out/runs/recorder-gesture-dry-matrix-20261021-02/double/03-second-held.png).
- [WOULD FREEZE](../out/runs/recorder-gesture-dry-matrix-20261021-02/hold/02-still-held.png).
- [NORMAL stock-equivalent recorder](../out/runs/recorder-gesture-dry-matrix-20261021-02/normal-1-single/04-complete.png).
- [Encoder-gap navigation](../out/runs/recorder-gesture-dry-gap-encoder-20261021-01/02-encoder-flushed.png).

The encoder-gap PNG catches the first recorder frame, still showing BUF 1;
the later guest DEST state is 2 before its label is redrawn. The trace, not
that transient frame, establishes the changed destination.

## Interaction decision and backend boundary

Hold recognition is feasible while the encoder hand keeps editing performance
parameters. Keep the pair **opt-in**: double-tap has both a single-navigation
delay and an encoder-gap conflict. A hold alone, or SAMPLING+C alone, does not
need double-tap arbitration; the added single delay comes from double-tap.
The comparison remains open, rather than a selected permanent binding.

The focused encoder-gap probe starts on BUF 1. First SAMPLING press/release is
at ticks 253/256; C rotates while the double window is still open. Navigation
is replayed at 261 and the recorder draws at 263. C now edits DEST to BUF 2.
The second press arrives at 267 with native flags **0x5** (a genuine fast
double), but the recorder already owns input: **no WOULD ARM** occurs.
Playback kit bytes stay unchanged. This is a confirmed limitation for
continuous encoder use during double-tap, not a successful performance flow.
It preserves tap-then-edit behavior at the cost of that competing intent.

Letting rotations continue on the visible performance page while awaiting a
second tap is a plausible next dry-run policy. Then an ordinary single tap
cannot promise that an immediate turn edits the recorder. Buffering rotations
until the decision would instead add knob latency. Compare those policies
explicitly before promoting double-tap; this prototype does not silently
choose a new interpretation. Hold is the stronger current performance
candidate, subject to the late-chord conflict below. C push avoids these
double-tap issues, but still occupies the encoder hand the user wants free.

There is one confirmed conflict that must precede any real FREEZE binding:
hold SAMPLING through the threshold, then press YES. WOULD FREEZE has already
appeared at tick 317; the original ARM follows at tick 333. Earlier chords
cancel the hold and retain stock behavior. A recognizer cannot predict a
later chord. Deferring FREEZE to release would resolve that ordering but
would change the snapshot time; disabling the hold in additional contexts or
keeping the explicit C chord are other policies to compare. The dry run
exposes this ambiguity without taking a snapshot or consuming an identity.

Next-bar recording, a stopped-transport policy, cancellation of an already
armed request, and the native job/feedback path remain unconnected. The
future request must latch/recheck the project, selected destination, settings
and buffer generation against an authoritative musical clock. The existing
[native FREEZE diagnostic](RECORDER-FREEZE-NATIVE-RESULTS.md) already shares
resident PCM through metadata on a stock loader cache hit; it needs no PCM
readback for that operation. Connecting it still requires a safe native GUI/
worker request, target placement, concurrency and reader-lifetime handling.
Its paused/IPL-7 diagnostic and host-assisted BUF capture are not upgraded by
this recognizer. DSP-to-CPU readback for later native SAVE remains a separate
dependency, rather than a prerequisite for metadata-only FREEZE.

Do not widen the routing gate to unaudited pages or connect either backend
until those conflicts and context rules are tested. No physical button feel,
debounce, target timing, audio deadline, active-voice continuity or coupled
sequencer/audio performance is established here. SINE replay is a separate
regression test, not a simultaneous audio test of the gesture window.

## Failed controls retained

- Initial encoder replay returned before asynchronous recorder activation.
  Those exploratory runs remain under `recorder-gesture-dry-*-20261021-01`
  and `-02`. The bounded input queue now waits for the original draw. The
  early captures do not prove that a wrong playback parameter was changed.
- A single small C turn reached original recorder rotation but did not change
  DEST in both stock and candidate. The native scaler filters the first
  turn; forcing an expected destination change would have been incorrect.
  The final after-tap test uses two C turns and compares with stock. The
  strengthened hold test uses A and C turns and compares exact kit bytes.
- The first complete matrix,
  `out/runs/recorder-gesture-dry-matrix-20261021-01/`, failed its LFO setup:
  `StopIteration` while looking up a button named LFO. Stock calls that panel
  button **MOD**. It sent no gesture in that case. The driver now explicitly
  maps LFO to MOD and retains the alias in its report. The failed matrix,
  source snapshot and process failure remain intact; it is not counted as a
  passing matrix. No baseline expectations were regenerated.

## Source provenance

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, with inherited dirty/staged/untracked
work. DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`. OS **1.16** MAIN SHA-256:
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
The initial audit is `out/runs/recorder-gesture-dry-20261020-audit-01/`.
Standard source manifests include the lab/scripts/machines/profiles/fixtures;
unit-file hashes are also recorded separately because the standard manifest
does not include `tests/test_*.py`.

Only this document, the three new `lab/recorder_gesture*.py` files, two new
`scripts/check-recorder-gesture-*.py` files and `tests/test_recorder_gestures.py`
are repository source/documentation additions. Run-local audit/probe drivers
and captures stay in ignored `out/`. Existing Flex, BUF, FREEZE, Plaits, Capicola and stock
sources and dependencies are preserved. No device package was prepared for
installation, and nothing was committed, flashed or uploaded.
