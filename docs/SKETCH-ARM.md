# Sketch native ARM — OS 1.16

Authorized continuation of the Sketch UI prototype: connect FUNC+SONG to the
existing next-bar recorder, accepting Sketch's selected BUF independently of
normal recorder DEST. Held SONG remains dry. No DSP, FREEZE integration,
preview, persistence, memory-reclamation policy, packaging or hardware changes.

## Entry and ownership

`SketchUI(..., sketch_enabled=True, arm_enabled=True, peer=...)` enables the
real ARM profile. Both options default false, keeping the existing dry profile
and stock Song opt-out reproducible. `arm_enabled=True` requires Sketch enabled.

The native gesture action calls `buf_next_bar.ARM_ONLY(controller*, BUF)` from
the GUI event path, once per physical chord. It does not synthesize YES, forge a
return address, invoke START or start transport. BUSY, unsupported length and
other refusals are displayed separately from the original dry FREEZE feedback.

The shared service only admits a ready recorder, playing transport, supported
normal 16-step clock and R.LEN=16/32/64. The [duration extension](BUF-MULTIBAR.md)
latches one/two/four native bars and preserves the existing ten-second limit.
It initializes empty logical buffers through
the existing guarded setup, latches the explicit destination, then takes the
existing mutation lease. Native GUI polling still chooses START/STOP at the
existing first-step receipts; normalization, queued worker and publication
remain the original BUF path. No track assignment is attached to publication.

The transaction separately remembers the normal recorder DEST present at ARM.
It never writes that setting. A subsequent normal DEST change cancels the
transaction; choosing another Sketch preference after admission cannot redirect
the already latched target. This is one global UI selection, not presets.
Kit/project epoch, settings, clock and lease guards remain in force.

The original SAMPLING+YES wrapper retains its stock caller guard, NORMAL
fallback, boolean failure ABI and second-chord cancellation behavior. The new
shared entry is arm-only: a second request refuses without modifying or
canceling an admitted transaction. STOP/NO keep their existing cancellation
owners.

## Live feedback

An accepted Sketch ARM displays its admitted BUF and follows the native
transaction: WAIT BAR, RECORDING, PROCESSING, LOADING and CANCELLING, followed
by READY, CANCELLED, FAILED or STALE. READY requires the native publication
completion result; stopping capture or finishing normalization is insufficient.
The duration extension adds TOO LONG when the ten-second capture limit is exceeded.
Periodic view updates refresh the message without a key, and drawing refreshes
it immediately when Sketch is reopened after completion or cancellation.

The UI remembers the admitted transaction count, BUF and project/kit/epoch/pool
context. A replacement transaction or changed context produces STALE rather
than borrowing another job's success. Changing Sketch's BUF selection or
pressing SONG to navigate does not change the displayed recording target.
These session-only observation fields own no audio, leases or memory lifetimes.

Feedback still describes the latest action. A later FREEZE request, dry action
or refusal keeps its own message; the earlier recording cannot overwrite it.
Terminal messages remain visible until another action. The REC/BUF rows remain
the current backend activity display. No recording, cancellation, publication
or FREEZE code is changed by this feedback follow-up, and the default dry
profile does not poll ARM completion.

With real Sketch ARM enabled, NORMAL USE also honors the existing BUF mutation
lease. Its earlier DEST=0 shortcut bypassed the BUF entry busy check while its
worker dispatch could still observe that lease. The small gate uses the
existing native busy exit; an idle NORMAL USE executes the original entry.
This gate is not installed in the dry or disabled Sketch profiles.

## Verification

Use the configured Python from `.local/config.json`:

```sh
./labctl unit buf
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  scripts/check-sketch-arm.py out/runs/sketch-arm-YOUR-FRESH-RUN
./labctl test sine --replay
```

The driver permits one capture. It checks empty BUF 2 with DEST=NORMAL, stopped
transport and MAX-length refusals, arm-only repeat behavior, native start/stop,
automatic publication and exact preservation of all 16 track assignments.
Then it selects recorder BUF 3 through the original recorder, arms Sketch's
BUF 2 with the reverse chord order and cancels before recording with NO.
The driver forbids stock ARM, FREEZE/save submissions and SamplerView creation
except that explicit final recorder-setting check. It observes native calls
and destination writes, with no host-successful commit or direct invocation.

Results are retained under `out/runs/sketch-arm-20261023-01/`. Recorder input,
LP0 peer and cadence in this driver are modeled; this is CPU/UI evidence.
SINE replay is separate DSP regression evidence. Native Sketch/BUF addresses
remain emulator scratch, not device reservations or an installable OS image.

## Results — 2026-10-23 JST

- `./labctl doctor` and 130 scoped BUF tests pass, including five new focused
  cases for explicit admission, non-toggling repeats/refusal, mutation-lease
  ownership, both gesture orders and unchanged dry FREEZE. The legacy wrapper
  retains the original tests, including its boolean failure return.
- `native-01/report.json`: 16 checks pass, one START, one STOP, one publication,
  zero fault pages and stable sources. Empty BUF 2 publishes 112,928 stereo
  frames into logical slot 301. All other BUFs stay empty. No normal DEST write
  occurs during capture/publication, and all 16 track assignments remain exact.
- A second physical FUNC+SONG refuses as BUSY and does not cancel the first
  transaction. Reverse SONG-then-FUNC later admits BUF 2 while recorder DEST is
  BUF 3. NO cancels before START, releasing the lease and preserving the accepted
  generation/cache header and every assignment. Only one capture is performed.
- `dry-panel/report.json`: the existing 20-check dry profile still passes,
  with the shared ARM entry now also forbidden by its negative-control driver.
  `disabled/report.json` retains the original Song popup and no Sketch hooks.
- `filename-modal/report.json`: actual native NameView owns tap/chord/hold
  with real ARM enabled; Sketch/backend state stays exact, no ARM/capture/
  FREEZE/save calls occur, NO cancels name entry and zero fault pages are touched.
- SINE replay passes at
  `out/runs/20261022T223809Z-test-17f9f776/manifest.json`. Its complete source
  hashes match the final native run. No DSP source or normal firmware builder
  was edited. This is independent regression evidence, not coupled Sketch audio.

The original result used `ARM OK` as an admission acknowledgement; the live
feedback follow-up above replaces that message with the transaction lifecycle.
The capture source, input timing and LP0 peer remain modeled. No real-time,
listening, final-output, ADC or hardware result is claimed. Next is the explicit,
generation-specific FREEZE integration, followed by the combined DSP workflow
and target placement/build validation. No package, flash, commit or publication
was performed.

See the [verification index](../out/runs/sketch-arm-20261023-01/verification.json)
and [native screenshot gallery](../out/runs/sketch-arm-20261023-01/screenshots.html).
Earlier unit candidates retain the caught legacy return-ABI mismatch and a
translated-code-cache issue in the test stub; both are fixed without relaxing
their assertions. The modal driver's initial directory-preparation error began
no emulator or recording; its corrected run passes.

## Live feedback follow-up — 2026-10-23 JST

Evidence: `out/runs/sketch-feedback-20261023-01/`.

- 151 scoped BUF units pass, including four additional native instruction
  cases for phase/terminal results, stale/replacement context, newer-action
  ownership and refresh/draw target selection. No Capicola/Arp suites run.
- `native/report.json`: 21 checks pass, one 112,928-frame stereo capture and
  two cancellations before START. WAIT BAR, RECORDING, actual-publication READY
  and reopened CANCELLED are observed through ordinary panel input; a later
  BUSY refusal remains the latest message. All 16 assignments and the accepted
  take survive cancellation, recorder DEST stays independently selectable,
  sources stay stable and zero fault pages are touched.
- `dry/report.json`: all 20 no-recording panel/gesture checks pass, including
  original NORMAL recorder access; native ARM/FREEZE job entries remain forbidden.
- SINE compatibility replay passes at
  `out/runs/20261023T035537Z-test-3c005030/manifest.json`, using the exact same
  frozen sources as both native panel runs. Focused Ruff checks also pass.

See the [verification index](../out/runs/sketch-feedback-20261023-01/verification.json)
and [native screenshots](../out/runs/sketch-feedback-20261023-01/screenshots.html).

The backend emitters, DSP, FREEZE, retirement/memory policy and dependencies
remain unchanged. Failed/stale/loading/cancelling feedback has bounded native
instruction evidence, not injected success in a recording run. The previous
sealed device image does not contain these UI changes; no new device package
or hardware trial is part of this follow-up.
