# Sketch COPY/PASTE — OS 1.16

The opt-in `--copy-shortcuts` profile adopts FUNC+RECORD and FUNC+STOP inside
Sketch. COPY uses the existing BUF FREEZE worker to preserve the selected take.
PASTE assigns that immutable snapshot to the currently selected ONESHOT track
through the original sample-parameter accessor and setter. It changes only the
sample selection; copying does not assign a track. Held SONG remains FREEZE.

PASTE means assignment to the current track in this prototype.

## Controls and lifetime

1. Open Sketch with SONG and select a ready BUF with encoder A.
2. Hold FUNC and tap RECORD. `COPY: PRESERVING TAKE` becomes
   `COPIED / F+STOP:PASTE` after the original background job completes.
3. Select the destination track with TRK and its trig; reopen Sketch with SONG.
4. Hold FUNC and tap STOP. `PASTED TO TRACK n` confirms the sample selection.

PASTE can be repeated on other ONESHOT tracks. It reuses the same snapshot and
does not duplicate audio or create another frozen take. Recording a replacement
into the live BUF does not redirect the clipboard. Playback must continue during
FUNC+STOP; PASTE while capture/publication is active refuses without cancellation.
Bare STOP and NO keep their existing cancellation behavior. RECORD without FUNC,
PLAY, held-SONG recognition and keys in other views keep their original routing.
The prototype recognizes FUNC held before the RECORD/STOP press; adding FUNC to
an already pressed transport key does not retrospectively claim that key.

The clipboard is volatile Sketch state shared by its views, independent of the
stock typed clipboard and its undo data. View closure/track selection preserves
it. Its epoch, project, kit and pool must still match, and the frozen descriptor,
loader association and project association must all remain valid before PASTE.
Project/kit replacement, unloaded slots and stale completions refuse safely.
No clipboard or audio persistence has been added.

Every accepted COPY uses the existing snapshot identity budget: at most eight
issued snapshots per session, including failed/quarantined identities. COPY
therefore preserves a take even when it is never pasted. Rejected COPY requests
retain the previous clipboard; once a replacement COPY is accepted, its result
owns the clipboard. Older successful snapshots remain in the takes list.

Sketch PASTE has no paste-again undo: repeating it selects the same take. Stock
copy/paste and its undo behavior outside Sketch are unchanged. Broader sample
machine support and integration with the global clipboard are separate work.

## Implementation boundaries

`lab/sketch_copy.py` emits the small frontend and retains one descriptor/slot plus
context and request metadata. It occupies spare state/code space in the existing
Sketch arena; the device reservation remains 360,448 bytes. `sketch.py` routes
owned gestures ahead of its STOP cancellation latch, reads completion feedback
and displays messages. Foreign modals keep input priority; modal-owned releases
retire only the frontend's key latch.

The FREEZE admission, worker, loader, generation/retirement policy, fixed H slots,
DSP and stock clipboard code receive no changes. Without `--copy-shortcuts`, the
previous startup MAIN is byte-identical (`eea6d8bb...e6ba7c`); the preserved R4
profile also remains the comparison baseline. The new profile has no extra stock
hooks, and all composed parts outside the Sketch arena must match the baseline.

## Reproduce

From this staged lab, use its configured Python and existing native instruction
bridge. The focused suite is `test_sketch_copy` plus the adjacent Sketch,
startup, navigation, fixed-slot, placement and test-catalogue checks. It includes
the authentic stock setter behind explicit abstract-parameter service seams;
that instruction fixture alone is not a full native UI result.

Build the local MAIN/DSP experiment with:

```
scripts/build-sketch-device.py out/runs/copy-build-01 \
  --arm-diagnostics --clock-fix --buf-selector --performance-controls \
  --navigation-fixes --fixed-buf-slots --startup-capture --copy-shortcuts
```

The native integration command is:

```
scripts/check-buf-startup.py out/runs/copy-native-05 --copy-shortcuts \
  --fixtures /absolute/path/to/preserved/startup-integration/lab/out/runs
```

Use a fresh output name for every run. This builds an internal test container,
runs the established early-recording fixture, then native panel COPY/PASTE,
replacement B, busy PASTE and repeat PASTE on another track. The original native
driver is preserved; the test script adds a bounded validation-only extension.
Reports and rendered screens belong to the run directory. Native input, card
and peripheral cadence remain modeled. Physical timing, listening, device
behavior and a distributable experimental OS are not established here.

## Local results

- 76 focused tests pass with no errors, failures or skips. These include 11
  new grouped frontend checks, stock-setter instruction execution, cancellation,
  context/key validation, original profile hashes and unchanged backend/hooks.
- `copy-native-05` passes from CPU application reset with native DSP coupling:
  early native A recording, COPY through the unchanged worker, PASTE to T1,
  distinct modeled recording B, refused PASTE during capture without cancellation,
  then repeat PASTE of A to T5. One snapshot and one snapshot job are issued.
  Other track selections, NORMAL, playback, code and canaries remain intact.
- The native compatibility check uses the original SRC+RECORD / SRC+STOP page
  gestures outside Sketch and observes the original OS1.16 copy/paste routines.
  It does not create BUF jobs or replace the Sketch clipboard. No new global
  clipboard hooks are installed.
- The SINE replay passes. Its source inventory and the unit report differ from
  final source only in the native compatibility test's corrected gesture;
  firmware emitters, SINE inputs/binaries and unit tests are unchanged.
- Rendered native screens are saved as `copy-ready.png`, `paste-track-1.png`
  and `paste-track-5-after-B.png` in the final run. The footer fits the display;
  the copied-status line shows the complete PASTE shortcut.

Final MAIN: `f31a427d81afec033ff8c97bb33eaa2462ce27afb5a130adf4a5db149fdb519e`.
DSP remains `2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a`.
Reservation: 360,448 bytes. All 687 baseline source files remain preserved.

Earlier runs remain available: one compiler-only fixture failure, a native
rejection that exposed an extra pool-table offset in the new frontend, a passed
first A/B flow, and a compatibility test with the wrong gesture. The extra offset
was corrected without changing the backend. A preliminary SINE run invalidated
by source changes is retained separately from the passed final replay.

This validates native CPU controls, snapshot metadata and modeled capture/load
behavior. It adds no new frozen-voice/final-output/listening or hardware proof.
