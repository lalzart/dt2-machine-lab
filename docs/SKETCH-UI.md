# Sketch UI prototype — OS 1.16

Small, explicit opt-in frontend over BUF. The implementation follows stages
1–2 of the root workspace's
[Sketch UI investigation](../../Digitect%20firmware%20research%20project/SKETCH-MODE-UI-INVESTIGATION.md)
and uses the older Song investigation as an address/ownership reference.
The user's requested tap/ARM/hold mapping supersedes the older brainstorm.

This page describes the default dry profile and its earlier results. The
optional [real ARM profile](SKETCH-ARM.md) now connects FUNC+SONG to the existing
next-bar recorder using an explicit BUF; held SONG remains dry.
The separate [FREEZE option](SKETCH-FREEZE.md) connects held SONG to the existing
snapshot worker and can be enabled alongside ARM. Both remain opt-in.

## Scope and controls

- SONG tap toggles Sketch on release. The press does not open stock Song UI.
- FUNC+SONG, in either order, logs one dry ARM intention. Holding or repeating
  the chord does not submit additional intentions or open/close Sketch.
- Hold SONG uses the native `0x29` milestone once for a dry FREEZE intention.
  Its release does not navigate. This is native panel ticks, not device timing.
- A selects BUF 1–4. B/C/D/E edit the existing global SRC/CHAN/R.LEN/MON through
  stock accessors and native encoder scaling. Stock MON source eligibility is
  retained; settings are not edited during recording/processing/trim.
- YES toggles the read-only frozen list. UP/DOWN switch its two four-row pages.
  No preview, assignment, saving or deletion is attached to the list.
- NO closes Sketch and continues to existing cancellation owners. STOP also
  continues to them. SAMPLING closes Sketch and reaches the ordinary recorder.

The page displays all four explicit EMPTY/READY labels, selected BUF, shared
settings, recorder state, a separate BUF phase and dry feedback. Unsupported
lengths show `!`; opening the page does not coerce R.LEN. LEN 16/32/64 are
supported; dry ARM refuses other lengths and a non-ready recorder. Dry FREEZE
refuses an empty BUF or a non-ready recorder. These are UI feedback checks, not backend admission,
lease acquisition or generation acceptance.

Outside the page, intentions remain observable as native scratch counters,
latched BUF and result. Opening the page displays the most recent result.
No toast/modal is created by a closed-page dry shortcut.

## Ownership and lifetime

`lab/sketch.py` owns one four-byte remembered BUF selection, initialized to
BUF 1 when the opt-in adapter is installed. It survives native view destruction
and ordinary recorder DEST=NORMAL. It lasts for this emulator session, including
project changes; it has no project/audio ownership and is not serialized.
This is a UI preference over four stable logical names, so it does not belong
in ProjectSettings, the recording transaction, a generation or a track.
There are no per-buffer recording presets. SRC/CHAN/LEN/MON remain shared.

The preference never writes the recorder's DEST. A press latches that preference
for the dry action; kit, project, BUF selection, normal DEST and backend epoch
changes cancel pending recognition. This adjustment deliberately differs from
the investigation's initial proposal to refuse when recorder DEST is NORMAL.
Future ARM integration must accept an explicit latched destination while
preserving the normal recorder's setting; it is not implemented here.

The view is a native base `View` plus native encoder scaler and a borrowed
ProjectSettings wrapper: 352 bytes including its shared control block, before
native helper allocations. It does not construct/copy `SamplerView`, its
waveform state, trim actions or manual recording key handler. Native controller
attachment takes a shared reference; local ownership is released after push.
Closing is deferred. Final shared disposal destroys the scaler and base View,
then releases its control block. The observed view pointer is cleared there.

The native View periodic callback refreshes status every 12 panel ticks without
requiring a key or encoder event. It only invalidates the view, skips a closed
view and handles tick wrap. Drawing cannot schedule another refresh reliably:
the controller clears the dirty flag after drawing. This callback makes no
recorder, waveform or worker requests. With real ARM enabled, it also observes
the admitted recording's lifecycle as described in [ARM feedback](SKETCH-ARM.md#live-feedback).

Eligible performance views receive the shortcut after earlier modal owners.
A native route envelope cancels a pending cycle if no eligible view received
an event; modal-consumed releases retire only Sketch's own latches. STOP/NO
retain the existing BUF cancellation flag path. Conflicting SONG+arrow/TRIG
commands are suppressed in the opt-in surface. Stock Song data/arranger code
and project formats are untouched. Existing Song-enabled projects are not
converted or deactivated; disable Sketch to retain the original Song surface.

The native held-cycle consumption helper clears the repeat/hold timer. Calling
it on SONG press prevented the hold milestone in an early candidate. Sketch
instead returns consumption through ViewController and keeps its own cycle
state; ordinary event disposal and modal routing remain native.

## Installation and checks

`SketchUI(..., sketch_enabled=True, peer=...)` extends the existing NextBarUI
installer. Default `sketch_enabled=False` installs exactly its existing BUF
adapter and no Sketch hooks/state. No normal firmware builder includes Sketch.
All feature behavior is emitted ColdFire; Python installs guarded code and
observes native execution. Full stock MAIN hash, hook bytes, payload bounds and
instruction audit are checked before installation. The canvas uses a bounded 128x64 native bitmap clear through stock memset;
text still uses the native font/raster routines. The rectangle helper produced
changed-glyph-only redraws in the emulator, retained in the failed candidates.
The clear refuses other dimensions/stride and does not change panel pointers.
The only shared source edit extends the instruction audit to ordinary register ADD.L forms used here.

Run with the configured Python, from the machine lab:

```sh
./labctl doctor
# Python executable is recorded in .local/config.json.
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  scripts/check-sketch-ui.py out/runs/sketch-YOUR-FRESH-RUN
# Negative control, preserving the stock Song popup:
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  scripts/check-sketch-ui.py out/runs/sketch-disabled-YOUR-FRESH-RUN --disabled
./labctl unit buf
./labctl test sine --replay
# Two captures at most: existing manual capture/publication, five FREEZE aliases
# of that one take, then cancellation of an existing next-bar capture.
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  scripts/check-sketch-limits.py out/runs/sketch-limits-YOUR-FRESH-RUN
```

The panel driver forbids recorder ARM/START/STOP/DISCARD, BUF worker, FREEZE
submission, snapshot creation, assignment refresh and save entry points. The
original SamplerView factory is allowed only for the explicit final NORMAL
recorder check. Transaction/registry bytes remain exact except the existing
STOP/NO cancellation flag, checked separately. No capture is performed.
Sketch screenshots preserve the actual bitmap after its native draw returns;
ordinary pages use the existing native panel latch. The renderer can finish
without another diff call, so waiting only for a later diff is insufficient.
Pixels are never combined or rendered by Python. Runs retain failures as well as successful
candidates and record stable source hashes.

## Limits and next boundary

This is a CPU/UI emulator prototype in explicitly mapped scratch
`0x11100000..0x11108000`, not a device placement/build. Existing BUF/FREEZE
backend source, allocator/retirement policy, Flex, DSP and normal builders are
preserved. ARM/FREEZE integration, preview, persistence and new memory policies
remain outside this change. Source-stable results and screenshots are recorded
in `out/runs/sketch-ui-20261022-01/verification.json`.

The initial panel run exercised an empty frozen list. The follow-up driver
uses the ordinary recorder to publish one BUF and the existing FREEZE frontend
to create five snapshots of that same generation. It browses both pages without
changing the registry, cache headers or any track assignment. Targeted native
instruction tests reject stale epochs, uncommitted rows and mismatches in each
of the four cache-association words. No synthetic rows are inserted into the
panel run.

A native Save Project As NameView was exercised with tap, FUNC+SONG and hold:
Sketch/BUF state stayed exact, no jobs ran and NO canceled name entry. The
follow-up capture/list driver uses modeled recorder input and an LP0 control
peer, without DSP execution. SINE replay is independent DSP regression evidence;
it does not upgrade these UI observations to real-time audio or hardware
validation.

The next implementation boundary remains the investigation's stage 3: a shared
arm-only entry accepting the explicit BUF, and an atomic generation-specific
FREEZE acceptance shim. Neither is approximated by pressing YES, forging a
return address or calling the current track-derived FREEZE entry.

## Initial result (2026-10-23 JST)

- `./labctl doctor`: pinned dependencies, seven fixtures, three tools pass.
- `./labctl unit buf core`: 175 pass (123 BUF/recorder including eight focused
  Sketch tests, 52 core). No Capicola/Arp feature suites were run.
- `complete/report.json`: 20 native panel checks pass, source hashes stable,
  zero fault pages, two dry ARM intentions and one empty-BUF FREEZE refusal.
  All five native encoders, view destruction/recreation, secondary list,
  STOP/NO forwarding and the original NORMAL recorder factory pass.
- `disabled-complete/report.json`: original Song popup, no Sketch hooks;
  source hashes stable, zero faults.
- `filename-modal/report.json`: actual stock NameView owns tap/chord/hold;
  Sketch/BUF bytes unchanged, no forbidden calls, no audio capture or save.
  Reproducer: `probe-filename-modal.py` beside this verification directory.
- SINE replay: `out/runs/20261022T150101Z-test-5af54cba/manifest.json`, passed
  with final source hashes stable. This is independent DSP regression evidence.

Screenshots: [menu](../out/runs/sketch-ui-20261022-01/complete/02-selected.png),
[frozen list](../out/runs/sketch-ui-20261022-01/complete/03-frozen-list.png),
[dry ARM](../out/runs/sketch-ui-20261022-01/complete/04-dry-arm.png),
[dry FREEZE](../out/runs/sketch-ui-20261022-01/complete/05-dry-freeze-empty.png).
The [gallery](../out/runs/sketch-ui-20261022-01/screenshots.html) shows the raw
native bitmap captures. Later emulator panel latches can expose an intermediate
comparison buffer; no claim about hardware panel timing follows from these PNGs.

Earlier candidates and failed screenshot/provenance attempts remain in the
same ignored audit directory. The first SINE run failed its source-stability
check while UI edits were still in progress; the final replay passes. No
firmware package, commit, publication or hardware operation was performed.

## Follow-up: populated list and concurrent capture (2026-10-23 JST)

Audit: `out/runs/sketch-limits-20261023-01/verification.json`.
The production change adds the native periodic refresh described above.
The bottom navigation hint is also raised three pixels so its full glyphs fit
inside the bitmap, with a blank row separating it from dry feedback.

- 125 scoped BUF tests pass, including ten Sketch tests. The two additions
  cover refresh/throttling/closed views/tick wrap and populated-page/stale-row
  filtering. No unrelated feature suites were run.
- `native-final/report.json`: 24 checks pass, two native START calls, five
  committed snapshots (slots 312–316), stable sources and zero fault pages.
  The original manual recorder captures/publishes 81,984 stereo frames. Sketch
  stays open and refreshes without keys, protects capture settings and allows
  its independent BUF selection to change without redirecting recording.
  Dry ARM/FREEZE remain BUSY feedback with exact worker/registry state.
- Both populated pages are drawn through stock text/raster helpers. Browsing
  preserves all registry records, frozen cache headers and 16 track assignments.
  The existing next-bar frontend then starts a second capture. Ordinary STOP
  reaches its existing cancellation owner while Sketch is open, discards that
  new take and preserves the published BUF and all five snapshots/assignments.
- `panel/report.json`: all 20 no-recording panel checks still pass.
  `disabled/report.json`: stock Song opt-out still passes. Modal routing and
  cancellation instruction checks remain in the scoped suite.
- SINE replay passed at
  `out/runs/20261022T203112Z-test-b333b5e0/manifest.json`. This and the capture
  run precede only the final three label-coordinate changes. The saved payload
  comparison confirms every other emitted byte is identical. A separate
  zero-recording native layout probe verifies the final menu/list glyphs and
  repeated full redraws; no additional capture or DSP replay was needed for
  this label placement adjustment.

The initial native candidate was retained as failed: its prepared pattern was
128 steps, so the existing 16-step admission guard refused the second capture.
A zero-recording clock probe confirmed the normal 16-step native setup before
the final run. Three captures were started across the initial and final runs;
the other panel/layout/clock checks record nothing. The earlier import failure
also started no emulator or recording.

The [gallery](../out/runs/sketch-limits-20261023-01/screenshots.html) contains
unaltered native captures, including both populated pages, the recording state
and post-cancellation state. These remain CPU/UI observations with modeled
input and an LP0 control peer, not DSP audio, physical timing or hardware
validation. No ARM/FREEZE integration, preview, persistence, BUF/FREEZE backend,
audio memory policy, firmware package or hardware operation was added.
