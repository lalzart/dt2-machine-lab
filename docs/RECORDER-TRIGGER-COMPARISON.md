# BUF recording trigger comparison

2026-10-21, OS 1.16. Compare double SAMPLING with stock-detected SAMPLING+YES,
without choosing a permanent shortcut. Both submit the same immutable BUF/
project/settings request. NORMAL and the opt-out BUF chord remain stock.
Long SAMPLING stays the proposed, dry FREEZE gesture.

The current bar source is unresolved: `pattern_clock.py` is a modeled SSI
cadence, and the arp's tempo accumulator is not a sequencer bar notification.
The existing `QuickRecord` contract takes injected bars and cannot map all
stock R.LEN/R.STRT settings. Do not infer a bar from panel ticks or wall time.
This iteration therefore remains **host structural / emulator dry run**:
WOULD ARM and test-supplied bar events may produce WOULD RECORD, never actual
capture, publication or FREEZE. The shared request boundary is the future
backend interface, not a claim that native quantized recording now works.

Implementation: separate double-only, chord-only and both-enabled trials;
an explicit BUF chord stock/next-bar option; original global ARM detection;
unchanged original recorder settings; no new native parameter/menu. In
chord-only mode a short SAMPLING release is immediate stock navigation.
Double-enabled mode retains the previous single-tap arbitration so its cost
can be compared. No rotation policy is silently changed.

Latch the native ProjectSettings recorder region (data+0x1ae..0x1d1), observed
through the original CHAN getter. Do not interpret its length/start values as
integer bars. Bind it to project epoch, kit pointer and selected BUF. Request
identity is independent of the trigger. Cancel on STOP/project/destination/
native recorder-busy transitions. Preserve other stock keys and manual input.
No target reservation, normal build, dependency, previous Flex path, save or
sample identity changes. No commit, upload or hardware flash.

Acceptance: pure request/next-boundary/epoch/cancellation tests; actual native
UART input and ARM caller traces; exact NORMAL and BUF-stock parity; double
versus chord request/settings equivalence; short-tap timing; encoders, holds,
late chords, repeated arming, recorder states and modifiers; explicit injected
bar controls; full unit suite, SINE replay and source-frozen provenance.

## Final executable results

**59 cases / 693 assertions PASS**, in
`out/runs/recorder-trigger-comparison-20261021-02/verification.json`.
**328 unit tests PASS** (316 previous plus 12 new); SINE replay **PASS** with
the identical 576-source map. All eight delayed UI replay completions preserve
registers/stack and CCR. Ruff check/format-check and doctor pass.

| Comparison | Result |
| --- | --- |
| Both triggers in `both` mode | Exact same backend plan: destination, project, kit, settings, ticket and clock fields |
| Primed TEST clock, separate double/chord trials | Exact same plan; current-bar duplicates do nothing; next TEST bar produces one WOULD RECORD |
| NORMAL single, double, hold, chord | Exact stock OLED sequences and native key events/timing; no delayed replay |
| BUF stock-arm option | Exact stock OLED/events; original ARM executes |
| BUF 1–4 next-bar chord | Selected destination latched; original ARM body suppressed; native state stays 0 |
| Cold MAIN, double and chord | Both latch MAIN without a prior MON read or external-input visit |
| Encoders during the chord | Actual performance edits retained; identical with double recognition enabled/disabled |
| Repeated arming | Either trial cancels its pending request without issuing another ticket |
| STOP/project/destination/busy controls | Pending request canceled; later injected bars cannot start it |
| Recorder ready/armed/capturing/background | Original manual start/stop behavior retained; no new request takeover |
| Trim/name | Completed PCM retained; no dry FREEZE takeover |
| Legacy prototype single/double/hold | Exact native events/timing and original OLED sequences match the retained previous prototype runs |

Every matrix case preserves its 16 sample assignments and observed
issued-identity/source/handle/page counts; native CPU control frames keep
advancing. These counters are not a whole-device heap or deadline benchmark.
Stock arm-waiting fixtures explicitly model external waiting status only in
native controller state 1, as in the previous investigation. MAIN is a
settings fixture; no native internal-audio capture is claimed.

Measured **release-event construction → original recorder draw**, at the
configured instruction/PIT clock:

| Press dwell, native panel ticks | Double enabled | Chord-only | Added double-mode wait |
| --- | --- | --- | --- |
| 6, short tap | 267.13 ms / 32 ticks | 0.46 ms / 0 ticks | **266.67 ms** |
| 24 | 118.59 ms / 14 ticks | 18.59 ms / 2 ticks | **100 ms** |
| 40, already past double deadline | 18.55 ms / 2 ticks | 18.55 ms / 2 ticks | **0 ms** |

This supports the concern that ordinary short taps may feel less responsive
with double enabled. It is a modeled comparison, not physical input latency
or a listening/ergonomics result. The interactive emulator runs below real
time; its wall-clock hold/tap waits stretch and cannot decide device feel.

Useful actual 128×64 OLED captures, exported at integer scale:

- [Chord WOULD ARM](../out/runs/recorder-trigger-comparison-20261021-02/both-arm-chord/01-chord.png).
- [Next TEST bar WOULD RECORD](../out/runs/recorder-trigger-comparison-20261021-02/model-chord/81-next-test-bar.png).
- [Cold MAIN source](../out/runs/recorder-trigger-internal-source-20261021-after/01-main-source-no-monitor.png).
- [Changed original recorder controls](../out/runs/recorder-trigger-varied-settings-20261021-02/01-varied-recorder-settings.png).

The interactive panel opened/rendered/closed in
`recorder-trigger-comparison-window-20261021-02/`. The separate varied-settings
probe verifies its queued TEST-bar callback on the native GUI worker. Desktop
mouse ergonomics, real-time audio and device operation remain unverified.

## Implemented comparison

`TriggerComparisonUI` extends the existing opt-in dry recorder adapter. Both
front ends call **one** `ArmRequests.request()` path. Its immutable `ArmPlan`
has no trigger field: ticket, project epoch, kit pointer, selected BUF,
36-byte recorder-settings snapshot, clock identity and last observed bar.
No audio resource or identity is created. These are control-request tickets,
not sample-generation identities.

| Trial | Double SAMPLING | SAMPLING+YES with BUF next-bar option | Ordinary single tap |
| --- | --- | --- | --- |
| `double` | shared WOULD ARM request | original stock arm | previous 32-tick arbitration |
| `chord` | ordinary stock two-tap navigation | shared WOULD ARM request | immediate stock navigation |
| `both` | shared WOULD ARM request | same shared request | 32-tick arbitration remains |

`--buf-arm stock` restores original BUF chord arming. NORMAL always retains
the original chord regardless of trial/option. The new option is a launch
configuration, not a new native recorder-page parameter or saved project field.
Long SAMPLING remains once-only WOULD FREEZE in eligible BUF performance
contexts, including the chord-only trial. No shortcut is selected permanently.

### Native detection and settings

The original global handler at `0x40016b3a` checks YES plus physically held
SAMPLING and calls ARM `0x40015f9c`, return address `0x40016bae`. The comparison
intercepts **that authenticated call** for an eligible BUF next-bar chord,
skips its ARM body and leaves original key consumption/release handling in
place. The request trace records the actual caller and suppression. NORMAL,
the stock option, other callers, and recorder-local YES keep original handling.
The original ready-state ARM body would update controller state via
`0x4004d9e0` and queue work through `0x4002f47a`; the new request does neither.

The CHAN getter load at `0x4004ccc6` exposes the native ProjectSettings data
pointer. The snapshot reads its 36-byte recorder region without calling a
native function reentrantly from a GUI hook. Missing/new-project settings
refuse the request instead of arming with stale data. Site bytes and complete
OS 1.16 input hashes are authenticated. This observes CPU data; it does not
introduce a DSP pointer, target allocation or new hardware reservation.

The [official OS 1.15A manual, p. 69](https://www.elektron.se/wp-content/uploads/2025/07/Digitakt-2-User-Manual_ENG_OS1.15A_250708.pdf#page=69)
describes R.STRT as PLAY-versus-threshold start, and R.LEN in sequencer steps
or MAX. That documentation does not supply a next-bar notification. It is
supporting specification, not an executed OS 1.16 timing test. This prototype
preserves raw settings and does not silently replace R.STRT or round lengths
to integer bars.

### Shared request policy

One pending request is allowed. Either input can cancel the same pending
request by repeating an arm gesture; no second ticket is issued for cancel.
STOP, project/kit/destination change, publication busy or an existing native
recording cancels stale pending work. Missing settings refuse. These are
prototype policies, not a completed capture lifecycle or reader-retirement
protocol. Existing armed/capturing/trim/naming contexts retain their stock
actions; a recorder-local YES can still manually record or stop, as before.

An unclocked request can display WOULD ARM, but cannot produce WOULD RECORD.
For the explicit model experiment, a TEST boundary primes clock 1/bar 10
before arming. Duplicate bar 10 is ignored; bar 11 returns exactly one
would-start receipt. Missed boundaries, clock resets, stale epochs and a first
clock observation arriving only after arm cannot start the request. All of
this is host control logic. There is no elapsed-time fallback or actual
recorder call, and no automatic length/stop/commit path.

There is no authoritative native running flag in this dry request model.
WOULD ARM may appear with transport stopped; injected TEST bars do not prove
real stopped/running admission. Define that policy with the native clock
provider rather than starting transport or capture implicitly.

## Run the trials

From `dt2-machine-lab`, with the existing configured Python 3.12 and private
OS 1.16 fixture. Scripts select that interpreter automatically. Use fresh
ignored output names.

```sh
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-double \
  --dry-run --compare-trigger double --window --window-seconds 600
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-chord \
  --dry-run --compare-trigger chord --window --window-seconds 600
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-both \
  --dry-run --compare-trigger both --model-bars --window --window-seconds 600
```

The normal emulator panel is reused: C on the recorder selects NORMAL/BUF
1–4; return to SRC for performance triggers. `S` is SAMPLING down/up and
Return is YES. The title/banner identifies the trial. With `--model-bars`,
the external **Advance TEST bar (no capture)** button posts a token for the
emulator GUI worker; it is not a device control or native musical clock.
The overlay says WOULD ARM / WOULD RECORD / ARM CANCELED / ARM REFUSED.
Guest display memory and original stock widgets are preserved.

For a deterministic command rather than the interactive window:

```sh
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-double-bars \
  --dry-run --compare-trigger double --case double --model-bars
python3 scripts/check-recorder-gesture-dry.py out/runs/MY-chord-bars \
  --dry-run --compare-trigger chord --case arm-chord --model-bars
python3 scripts/check-recorder-trigger-comparison.py out/runs/MY-comparison
```

Normal builds and launchers do not import the new comparison adapter. Omitting
`--compare-trigger` retains the previous dry prototype; omitting `--dry-run`
disables recognition. Stock NORMAL/BUF-opt-out ARM continues executing native
controller instructions: the dry guarantee applies to the **new next-bar and
FREEZE intents**, not to explicit original manual/arming input.

## Interaction findings and recommendation

Chord-only avoids the ordinary navigation delay. Keeping double recognition
enabled still costs that delay, even if the performer normally uses the chord.
Both trials are therefore necessary; running only `both` would hide the
responsiveness advantage of a chord-only binding. The measurements use
the native release-event constructor and original recorder draw, not host
wall time or switch debounce. Physical feel has not been tested.

The previous encoder policy is intentionally unchanged: a turn between taps
flushes pending single navigation, so C edits recorder DEST and a later fast
second press does not arm. The successful quick-record double stays on the
performance page only when no such turn intervenes. Chording while the
encoder hand keeps turning is exercised independently; the native parameter
edits are preserved, with no recorder navigation in the new next-bar path.

Long press remains a proposed FREEZE input. A chord completed before the hold
deadline cancels the hold. A performer who waits past the threshold and then
presses YES still produces WOULD FREEZE followed by WOULD ARM. No real action
occurs in this prototype, but that late-chord policy must be resolved before
either native backend is connected. Holding after a completed chord produces
no later FREEZE. NORMAL retains its original behavior throughout.

Recommendation: keep separate opt-in trials rather than select a permanent
binding. Chord-only is the lower-risk baseline for navigation responsiveness;
double remains useful to compare for one-button operation, with its delay and
encoder-gap limitation visible. Neither emulator throughput nor a modeled
quarter-second wait proves target ergonomics or real-time audio performance.

## Internal-source bootstrap correction and retained controls

The first 57-case matrix passed for its initial external-input settings.
Further static inspection found that MON draw at `0x40022316` can branch
around `0x4004cd02` for internal sources. A fresh MAIN fixture, with no cached
settings and **zero MON getter reads**, reproduced ARM REFUSED. This was a
functional limitation, not a reason to relax the settings guard.

The observer now uses CHAN's `0x4004ccc6` load, called by the original recorder
draw before the source-dependent MON branch. The same cold MAIN fixture now
latches source 16 and queues the request, again with zero MON reads. Both
double and chord cold-MAIN cases were added to the complete rerun. MAIN is
seeded through the original source getter before the first draw and shown on
the original display; this proves settings/bootstrap handling, not internal
audio production or capture.

Retained controls under `out/runs/`:

- `recorder-trigger-comparison-20261021-01/`: initial 57 cases / 663 assertions;
  source revision still uses the MON observer. Not the final source run.
- `recorder-trigger-internal-source-20261021-before/`: expected refusal,
  `negative-control`, no native recording. Input fixture SHA is retained.
- `recorder-trigger-internal-source-20261021-after/`: same input fixture,
  successful bootstrap with the corrected CHAN observer.
- `recorder-trigger-varied-settings-20261021-02/`: original B/E/F encoder edits
  change CHAN/MON/R.LEN, then both native triggers latch identical changed
  settings. Only the control ticket differs in this same-session comparison.
  An explicit model cancel separates the requests; no capture/completion is
  implied. The external GUI TEST-bar callback is posted through its queue and
  consumed on the emulator GUI worker, producing one WOULD RECORD with native
  recorder state still 0.

No expected stock audio/UI baseline was regenerated. Earlier runs and their
source snapshots remain intact. The MAIN fixture and varied-settings fixture
are retained run-local scripts in `recorder-trigger-compare-audit-20261021-01/`,
with their own hashes and standard source manifests.

## Native integration still required

The shared recording backend itself is **not newly connected**. The existing
manual recorder/BUF implementation is preserved; this work compares the two
front ends at one request boundary. The next prototype needs an authenticated
sequencer bar event, its transport/clock epoch and pattern/scale semantics,
then a safe native worker entry to start capture with the latched destination
and settings. Cover internal/external clock, tempo/scale changes, missed
notifications, STOP/restart, project changes and length completion before
automatic publication. Do not substitute an arp phase or elapsed panel time.

Actual BUF capture/commit still has its previously documented host assistance.
Native FREEZE's worker/lifetime gates, safe generation retirement, native SAVE
readback and full project/voice coexistence remain separate work. Nothing here
adds file operations, recycles sample identities or establishes audio deadlines.

## Provenance and regression reproduction

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus preserved inherited dirty work.
DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`. Authenticated OS **1.16** MAIN:
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
Final standard source manifest SHA-256:
`2d9aa921b4b3b4c5cef1597afd3d7da976ddf7e35dfa6377042961cf440aa897`.

The audit is `out/runs/recorder-trigger-compare-audit-20261021-01/`.
Its `final-verification.json` verifies all 59 report hashes/source maps, SINE,
unit-file hashes, UI ABI, prior prototype parity and supplemental controls.
It preserves 569 of the 573 inherited source files byte-for-byte. Only four
previous opt-in prototype files change: `recorder_gestures.py` (default-on
double flag), `recorder_gesture_ui.py` (additional diagnostic labels),
`recorder_gesture_window.py` (trial banner/TEST-bar button), and
`check-recorder-gesture-dry.py` (comparison fixtures/arguments). All 51 inherited
unit files are unchanged; the new unit file makes 52. Frozen final tests are
retained separately because the standard source map excludes most unit files.

New repository additions: `lab/recorder_trigger_model.py`,
`lab/recorder_trigger_ui.py`, `scripts/check-recorder-trigger-comparison.py`,
`tests/test_recorder_trigger_model.py`, and this document. No normal builder,
native Flex, Plaits, Capicola or dependency source changes. No hardware upload,
flash, commit or publication. Initial and intermediate source captures remain
in their original run directories, including pre-correction frozen copies in
the first matrix's child runs.

Exact final regression commands:

```sh
./labctl doctor
python3 scripts/check-recorder-trigger-comparison.py out/runs/recorder-trigger-comparison-20261021-02
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" -m unittest discover -s tests -v
./labctl test sine --replay
```

Those output names already exist; use new names to rerun. Final logs are
`out/recorder-trigger-comparison-unittest-20261021-02.log` and
`out/recorder-trigger-comparison-sine-20261021-02.log`. SINE's manifest is
`out/runs/20261021T035005Z-test-7c8e60e8/manifest.json`; its output is the
existing prepared voice-buffer boundary, not final DAC audio or a concurrent
gesture/audio deadline test.

Retained supplementary reproductions with fresh output paths:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-trigger-compare-audit-20261021-01/check-varied-settings.py out/runs/NEW-varied-settings
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-trigger-compare-audit-20261021-01/check-internal-source.py out/runs/NEW-internal-source
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-trigger-compare-audit-20261021-01/check-final.py
```

The final command verifies the retained artifacts. The pre-correction expected
refusal requires its retained MON-observer source revision; it is not the
expected result of the final CHAN-observer implementation.
