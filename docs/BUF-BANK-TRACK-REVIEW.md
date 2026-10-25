# BUF bank navigation, working state and startup review - OS 1.16

The user's device report: ordinary bank B reaches the first BUF backing row
(B17 in their project), then returns to A; edited sequences survive reboot;
startup still waits for ordinary sample loads; track selection should exit Sketch.
B17 is a project sample slot, not a physical PCM address. The original R2
package/source and the original sibling lab are preserved.

| Observation | Finding | Current action |
| --- | --- | --- |
| B bank jumps back at B17 | Cursor canonicalizes a backing slot into the BUF alias | Repair ordinary bank navigation |
| B17 cannot hold another sample | It is reserved for BUF; setup uses twelve free project slots | Preserve the guard; capacity redesign remains separate |
| Pattern edits survive restart | Matches documented stock active working-state recall | Preserve stock behavior |
| Startup recording waits for samples | Capture admission shares loading/allocator guards | Prove capture-before-publication in a separate experiment |
| Track selection leaves menu open | Sketch forwards the key without closing its view | Close on native TRK plus track selection |
| Proposed S/0 bank | Can name aliases, but does not add memory or slots | Defer presentation until storage requirements are settled |

## Confirmed selector defect and focused repair

The prior cursor callback calls the canonical inverse mapper on every ordinary
sample change. Reaching any logical BUF backing slot therefore normalizes the
view to bank A and selects the BUF alias. The arrow and bank-key handlers also
recognize a backing slot without first checking the current presentation bank.
The instruction regression reproduces B16 -> B17 -> BUF 1/A using R2 bytes.
This is a selector defect, not a loss of the rest of bank B's storage.

Opt-in `--navigation-fixes` establishes canonical BUF mapping at view construction
and preserves an already open BUF alias through native rebuild/subscription
callbacks. A normalized A/BUF view retains its alias; an ordinary backing row
retains its actual bank/row. In the extended A list, navigation uses the native list's selected rank,
so an ordinary A row and its BUF alias can share a slot without sharing a cursor.
Ordinary B-H arrows/bank navigation stays with the stock handlers. Reopening an
assigned BUF still selects the BUF alias. NO still restores the original slot.
No virtual rank enters the project parameter or DSP. A00 and NORMAL stay default.

## Slot capacity and replacement remain actual design limits

`recorder_worker_code.setup` reserves twelve presently free ordinary slots:
four logical BUF slots and eight private generation slots. It skips each bank's
OFF slot, project references and entries already in loader/cache tables. The
reserved table feeds the stock free-slot search filter and guarded load/unload/
clear paths. Once B17 is reserved for BUF 1, it cannot simultaneously hold an
unrelated normal sample. It is not permanently B17 in all projects. The prepared
native fixture uses 300-311 instead. Exhausting eligible slots prevents setup.

The navigation repair restores access past the reservation; it does not create
twelve new slots. A bank S/0 could be useful presentation, but aliases alone
still consume those backing slots and share the playback allocator. Do not
represent a new label as independent capacity or startup isolation. Supporting
extra actual identities requires auditing the CPU sample APIs, serializer,
track/sample locks, wire format, DSP descriptor table, bounds and retirement.
That backend redesign is not part of the navigation repair.

## Reboot recall is documented stock working-state behavior

Elektron's [OS 1.16 manual, section 5.2.1, printed page 16](https://www.elektron.se/wp-content/uploads/2026/09/Digitakt-2-User-Manual_ENG_OS1.16_260909.pdf#page=16)
says the device boots into the active working state. That state is separate
from explicitly saving a project snapshot. Prior local stock project-load
traces also observed its working-project autosave to slot 128; those historical
traces are references, not a new physical reboot comparison.

Sketch navigation/ARM/publication introduces no automatic call to Project::save.
The new profile changes only selector presentation and Sketch input handling.
Its existing volatile-project guard at 0x40043a30 / 0x400f5050 is retained: it
refuses those explicit save/load entries once BUF reservations are owned. That
is an existing persistence limitation, not a claim that every working-state
write path has been intercepted. Retaining sequence edits across reboot alone
is not evidence of a BUF save bug. No power-cycle equivalence test was run here.

BUF audio, reservations, and temporary generation references have a different
lifetime. A future persistence review must cover working-state serialization
and reboot recovery as well as explicit project save/load. Do not disable stock
working-state recall or promise BUF audio survival as a side effect of this fix.

## Startup wait: shared operation ownership, not the bank letter

`buf_next_bar.arm_only` rejects worker/stock-operation/mutation/loader busy before
recording admission; `initialize_buffers` does the same before slot setup.
The stock loader uses the shared CPU allocation vector at 0x405a0f64 and the
slot-to-allocation table at 0x405b5368. Loader work can grow/rearrange those data.
Moving BUF to H, S, or different code addresses does not establish ownership.
The observed 259/261/262 were ordinary project-load calls, not running FREEZE
jobs. The user's wait-then-success report is consistent with those guards.

The guards are per-operation, not a proven whole-batch-complete latch. An idle
gap with more queued loads is not sufficient to declare the allocator independent.
The repaired profile preserves every loading/allocator guard.

Recommended next experiment: prove that stock recorder capture/readback can run
while later project sample loads remain pending, before changing admission.
If that works, separate recording from pool publication: latch one logical BUF
and capture settings, retain the completed normalized take, wait for qualified
pool mutation, then initialize/load/publish through the existing worker. Cover
pending loads, STOP/NO, changed project/settings, failed publication and retained
source lifetime. Do not borrow recorder scratch as immutable BUF PCM. External
input is the simplest first probe; internal resampling can only record samples
that have actually loaded. Immediate capture during startup is unresolved here.

## Track-selection exit

The opt-in profile closes Sketch on the initial TRK press as native track selection
starts, and forwards the event to the stock controller. The native controller
handles track listeners before per-view input; a view-only shortcut cannot
reliably see the complete gesture. The existing route envelope verifies that
Sketch is the actual top view before closing it. The actual Sketch owner must match; repeat,
release and an unrelated modal owner cannot close it. Bare trigs retain existing
performance/step behavior, and owned SONG chords retain their current precedence.
Closing the menu does not cancel an admitted recording or change its destination.

## Reproduction and evidence

Use the configured Python 3.12 and the existing explicit Rust ColdFire bridge.
The new `tests/test_buf_navigation.py` covers the R2 B17 failure, all 1024 ordinary
slot cursor values, both directions through the 132-row A list, backing rows in
other banks, construction/reopen, reserved load denial, all bare track-key events, TRK press and modal/SONG precedence,
modal ownership, and exact R2 output when the new flag is disabled.

The final candidate MAIN is
`df5d524e037e2412aeaadb31e01108ebae381fb551aa002118d4d09aafdacf0c`;
DSP remains `2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a`.
Thirty-two focused instruction checks pass (8 new, 14 selector, 10 controls),
plus six test-catalogue checks. The new alias case also covers native cursor
callbacks inside the absolute setter and mappings where BUF occupies A01-A04.
Final results: the targeted `buf-navigation-native-06/report.json` passes one
113,344-frame stereo NOW capture/publication (112,942-frame duration target),
tracks 1/5/16, bare trigs, six page exits and track selection during capture.
Input PCM matches the modeled source; normal DEST, all assignments, CPU code
and canaries remain intact. SINE, stream/upload, exact repeated build and package
verification pass. The bank component from run 04 uses identical selector bytes;
its enclosing failed run is still marked failed. Hardware is untested.

[Experimental R3 and use notes](../out/runs/buf-navigation-experimental-01/package/README.md),
[final native track/recording report](../out/runs/buf-navigation-native-06/report.json),
[track 5 after exit](../out/runs/buf-navigation-native-06/flow/track-exit-5.png), and
[Sketch after publication](../out/runs/buf-navigation-native-06/flow/now-ready.png).

Firmware SHA-256: `52572626a99ec228c1cf8c6499d044cee88b7a0866083608a88bb690c683b341`.

Retained earlier runs:

- `buf-navigation-native-01` stopped before recording because the test inspected
  the mapping before native selector initialization.
- `buf-navigation-native-02` traversed C43-C56, then stopped on an assumption that
  fast encoder packets would land exactly at B127; they stopped at B126.
- `buf-navigation-native-03` proved B127 and H127 with native arrows and passed
  ordinary bank traversal, then exposed a genuine reopen regression: the native
  post-construction callback reset the alias to its ordinary backing bank.

Those three candidates share MAIN `cec2e438407483de5f4b582c74a264f738afa26efa2a211d199d1a39d30915e9`.
The final selector correction preserves alias context through that callback;
ordinary bank rows keep their ordinary context. Its instruction regression
models the actual callback during rebuild/subscription. No new UI state word,
DSP change or reservation expansion was required. `buf-navigation-native-04` passed the reopen and bank/NO subflow, then
failed on TRK exit: the stock controller consumed the gesture before Sketch's
per-view handler. Its bank subflow is retained as component evidence with exact
selector bytes and the executed assertion prefix authenticated. It is not
reported as a passing full run. The final controller-only follow-up avoids
repeating those bank interactions and checks tracks 1/5/16 plus active recording.

`buf-navigation-native-05` stopped before CPU execution because a test-only
`track_only` argument reached the firmware builder. After the SINE run completed,
one independent driver argument was removed. The final build/native/upload
sources match. SINE has that one explicit test-driver variance; all firmware,
DSP and SINE production sources remain exact, and its passing manifest is kept.
See `harness-correction.json` in the stage parent for the exact before/after hashes.

Native peripherals/recorder input remain modeled. No physical power-cycle,
startup overlap, extra slot namespace, new PCM allocation, hardware transfer or
DSP change is claimed.

## Reproduce the opt-in profile

Set `LAB_PYTHON` to the interpreter in `.local/config.json`. For the 32 focused
checks, set `PYTHONPATH=tests` and `DT2_BUF_SELECTOR_CORE` to the preserved
`buf-selector-implementation-20261023-01/lab/out/runs/selector-core-01/libcfselector.dylib`,
then run `"$LAB_PYTHON" -B -m unittest test_buf_navigation test_buf_selector test_sketch_controls -v`.
The default legacy Unicorn core is not the validated execution path for these
checks on this host. Six `test_unit_suites` catalogue checks also pass.

Build into a fresh ignored output directory:

```sh
"$LAB_PYTHON" -B scripts/build-sketch-device.py out/runs/UNIQUE-BUILD \
  --arm-diagnostics --clock-fix --buf-selector --performance-controls --navigation-fixes
```

The final native command is `scripts/check-native-buf-recording.py` with a fresh
output, `--native-upstream` pointing to the preserved DigiKit 38dfbe4 checkout,
and `--clock-only --performance-controls --now-only --navigation-fixes --track-only`.
This runs one NOW recording/publication after the menu checks. Existing BAR and
FREEZE backend code remains exact; the run is not another long reuse soak.
