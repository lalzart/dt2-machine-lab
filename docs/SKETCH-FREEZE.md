# Sketch native FREEZE — OS 1.16

Held SONG can now request an immutable snapshot of Sketch's selected BUF through
the existing background FREEZE service. It neither assigns a track nor changes
normal recorder DEST. The default dry profile and ARM-only profile remain available.

## Enable and use

```python
SketchUI(..., sketch_enabled=True, arm_enabled=True, freeze_enabled=True, peer=...)
```

`freeze_enabled` defaults false and requires Sketch enabled. It may also be used
with ARM disabled. SONG tap still toggles the native Sketch view; FUNC+SONG keeps
the existing ARM behavior; the native held-SONG milestone requests FREEZE once
per physical hold. Repeats do not resubmit and release does not navigate.
YES opens the existing read-only frozen list. No preview, assignment, file save,
deletion or persistence is added. One UI BUF preference remains session-scoped;
SRC/CHAN/LEN/MON remain shared settings without per-BUF presets.

Feedback distinguishes FREEZE QUEUED, FREEZE READY, BUSY, EMPTY, LIST FULL,
REFUSED and FAILED. Completion comes from the original worker completion count,
not the previous job's result. The last action is not a continuously updated
job history; a subsequent action can replace that feedback.

## Admission and generation lifetime

`lab/buf_freeze.py` adds a native `SUBMIT(BUF 1..4)` entry. It does not use the
selected track, recorder DEST or synthetic panel input to choose its source.
While IRQs are briefly masked, it validates the committed generation and both
complete logical/private cache associations, captures the generation descriptor,
key, private pin, logical slot, project, pool, kit and epoch, and claims the
existing FREEZE mutation lease. This prevents replacement/retirement from
changing the admitted source while the queue waits. This protected section only
reads/writes registers and memory and calls the pure native generation lookup;
stock recorder getters and worker-service calls run with the original IRQ mask.

The existing queue emitter has optional admission and queue-failure callbacks.
Its default payload stays byte-identical. The new entry supplies the existing
queue context and uses its stock small-function/service ABI. An optional gate
extends the original worker/task/epoch/kit checks with the exact admitted source,
project and pool. The original snapshot body, cache-hit association, quarantine,
reader ownership, allocator, issued identities and retirement policy are unchanged.
Completion/queue failure clear the new request marker and release the existing
lease through the existing path. Sampling+C retains its original entry and gate
semantics when the explicit request marker is clear.

Busy recorder/armed capture, shared mutation work, in-flight stock sample work
and pending legacy requests refuse before queueing. Empty/uninitialized or
inconsistent source associations refuse without reserving a snapshot. The
existing eight issued snapshot identities remain the session limit. A FREEZE
request conservatively refuses during an automatic-retirement lease; it does
not add a handoff or new memory policy. A ready BUF can be frozen with transport
stopped; ARM retains its playing/normal-16-step restrictions.

Selection changes after admission do not redirect or cancel the worker. Pending
recognition still cancels if its context changes before admission. Modal routing,
STOP/NO capture cancellation and the normal recorder remain under their existing
owners. The normal USE mutation-lease gate is enabled with either real action.

## Reproduce

Use the configured Python in `.local/config.json`:

```sh
./labctl doctor
./labctl unit buf
"$LAB_PYTHON" -B scripts/check-sketch-freeze.py out/runs/sketch-freeze-FRESH
"$LAB_PYTHON" -B scripts/check-sketch-ui.py out/runs/sketch-dry-FRESH
"$LAB_PYTHON" -B scripts/check-sketch-ui.py out/runs/sketch-disabled-FRESH --disabled
./labctl test sine --replay
```

The FREEZE driver caps recording at two takes. It observes native panel input,
START/STOP, publication, snapshot worker and completion, and records native bitmap
PNGs. It forbids host commit/direct calls, stock ARM, file saves and unexpected
SamplerView construction. Recorder input, SSI cadence and LP0 are modeled in this
CPU/UI driver. SINE replay is separate DSP regression evidence.

## Current limits

This is an emulator adapter with scratch addresses, not a device-ready image.
The [combined native DSP voice validation](SKETCH-VALIDATION.md) now passes.
Final mixed output, real-time timing, listening, physical input/output,
target placement and packaging remain separate gates. No native preview, saving,
persistence or new memory-reuse features are included. No firmware is flashed,
packaged, committed or published by this task.

## Results — 2026-10-23 JST

Evidence is retained under `out/runs/sketch-freeze-20261023-01/`:

- Doctor and 138 scoped BUF tests pass. Eight new focused cases cover explicit
  admission, atomic lease ownership, complete source associations, generation/
  project changes, queue failure, duplicate holds, refusals and completion.
  The default queue payload is byte-identical to the preserved baseline.
- `native-01/report.json`: 13 checks pass with two START/STOP/publications,
  one real FREEZE and zero fault pages. BUF 2 publishes A (112,928 stereo frames,
  token `0x7ffb0001`) then B (112,960 frames, token `0x7ffb0002`). Normal DEST
  stays NORMAL, no destination write occurs and all 16 assignments stay exact.
- A single 1.6-second modeled SONG hold admits exactly one native worker job;
  completion returns frozen slot 312 and shows FREEZE READY. The distinct
  snapshot reference shares A's original cache association. Its descriptor,
  complete cache header, inline name and project reference remain byte-exact
  after B replaces the current BUF. These are CPU metadata/association checks,
  not a coupled DSP audio comparison of A and B.
- Empty/uninitialized FREEZE refuses without setup or queueing; holding SONG
  while recording refuses BUSY. Selecting empty BUF 3 after freezing BUF 2
  refuses without freezing the selected track or the previous BUF.
- The default dry panel passes 20 checks and forbids both shared real entries;
  stock Song opt-out passes three checks. An actual native NameView owns
  tap/chord/hold with real ARM and FREEZE enabled; Sketch and BUF state remain
  exact, no job/capture/save occurs and zero fault pages are touched.
- Independent SINE replay passes at
  `out/runs/20261023T000715Z-test-e69f69e1/manifest.json`. Its source hashes match
  the final native and all three negative-control runs. Ruff and source-
  preservation checks pass; unrelated inherited files and DSP sources remain
  unchanged. The native admission test observes IRQ masking during source
  lookup and restoration before stock queue submission, with the lease already
  claimed at that boundary.

See the [verification index](../out/runs/sketch-freeze-20261023-01/verification.json)
and [native screenshot gallery](../out/runs/sketch-freeze-20261023-01/screenshots.html).
No additional capture/reuse loop was run for this UI milestone. The subsequent
[combined DSP validation](SKETCH-VALIDATION.md) passes; target placement/startup/
build validation remains the next hardware-preparation gate.
