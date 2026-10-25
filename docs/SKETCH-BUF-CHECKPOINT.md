# Sketch/BUF R8 checkpoint

Digitakt II OS **1.16**, 2026-10-25. This is the accepted experimental resting
point before further feature work. The user reports R8 works on their device,
including the red SONG recording indicator; there is no installed-hash readback
or independent hardware test. Local checks and user observations are distinct.

## Working controls

| Control | Behavior |
| --- | --- |
| SONG tap | Open or close the small native Sketch menu. |
| Encoder A | Remember one selected BUF 1–4 independently of NORMAL DEST. |
| Encoders B/C/D/E | Native recorder SRC / CHAN / LEN / MON settings. |
| Encoder F | One volatile START BAR/NOW preference; BAR is the boot default. |
| FUNC+SONG | Capture to Sketch's remembered BUF from ordinary track pages, independently of the current track's sample. |
| FUNC+SONG while stopped capture runs | Finish that stopped take early. |
| FUNC+RECORD in Sketch | COPY: preserve the selected ready take through the FREEZE worker. |
| FUNC+STOP in Sketch | PASTE: assign that preserved take to the current ONESHOT track. Repeat PASTE shares the snapshot. |
| Hold SONG | Existing FREEZE shortcut; held-cycle ownership prevents a subsequent tap. |
| NO or bare STOP | Existing cancellation behavior. |
| Any of sixteen trig buttons, TRK, or TRIG/SRC/FLTR/AMP/FX/MOD | Leave topmost Sketch; the original event continues to stock handling. |

During playback, BAR waits for the next native bar; NOW captures immediately for
the selected length. Stopped recording starts immediately regardless of the
stored preference; the menu says `STOPPED:F+SONG NOW`. Active capture locks the
mode control. LEN 16/32/64 and the existing ten-second bound remain in force.

SONG requests the same steady-red value as stock RECORD only while BUF and the
native recorder both report capture. It returns to stock output after capture,
cancellation, or failure. Waiting for BAR and processing/publication are not red.
This indicator works when Sketch is closed; it adds no state or timer.

## Buffer and track behavior

- BUF 1–4 are stable global live identities backed by **H124–H127**. These four
  rows are reserved. Occupied ordinary samples refuse setup; there is no fallback
  slot search or reassignment menu. Ordinary A–H bank navigation is preserved.
- The SRC sample selector presents BUF aliases before A00 OFF. The underlying
  native slot label can still show H124–H127. A00/default sample behavior and
  native recorder DEST=NORMAL are unchanged.
- Multiple tracks may select the same live BUF. A successful publication changes
  its generation without assigning tracks. Failed or canceled candidates retain
  the previously committed take. Existing readers retain protected allocations.
- Selecting BUF in SRC stays linked to the live identity. Sketch COPY/PASTE
  selects a separately preserved snapshot, so later BUF recordings do not alter
  that snapshot. COPY is not persistence or the stock typed clipboard.
- Capture can begin while project samples load. A completed take may wait for
  safe slot setup/publication; old playable content remains until success.
  R6's native DISCARD cleanup after publication permits another capture.
- BUF, the selection, start preference, snapshots and clipboard are volatile.
  No project/audio persistence or dedicated BUF memory pool was added.
- COPY/FREEZE retains the existing eight-issued-snapshot session budget,
  including failed/quarantined identities; repeated PASTE shares its snapshot.

## Source map and boundaries

| Area | Current source |
| --- | --- |
| Native menu, global gesture routing, BAR/NOW and exits | `lab/sketch.py` |
| Fixed backing slots and sample-selector aliases | `lab/buf_fixed_slots.py`, `lab/buf_selector.py` |
| Timed native recording and publication | `lab/buf_next_bar.py` |
| Startup deferral and stopped capture | `lab/buf_startup.py`, `lab/buf_stopped.py` |
| COPY/PASTE frontend and SONG LED | `lab/sketch_copy.py`, `lab/sketch_led.py` |
| Composition, relocation and guards | `lab/sketch_device.py` |
| Generations, loading, retirement and FREEZE | Existing `recorder_*` and `buf_freeze.py` services |

R8 is **Sketch/BUF only**. Older all-feature profiles retain their own Flex,
Arp, Plaits and Capicola adapters; they are preserved, not silently migrated.
The user's direction for a future complete OS is to replace the earlier Flex
workflow with BUF. That composition has not been implemented in this checkpoint.

The 360,448-byte reservation, reader/retirement guards and DSP match R7. R8 adds
112 bytes of LED code and one authenticated LED output hook, inside existing
space. Organization work must reproduce the same MAIN/DSP hashes. Do not move
slot numbers or change ownership to simplify the source layout.

The hash-pinned `BUF-WORKFLOW-CONTRACT.md` preserves the backend invariants.
Its older bare-trig wording is superseded by the controls above. Earlier feature
notes and [status history](STATUS-HISTORY.md) describe their recorded stages;
they are not the current control map or an instruction to rerun every experiment.

## Rebuild and focused validation

Use the configured Python 3.12 and private fixtures. From the repository root:

```sh
./labctl doctor
./labctl unit buf core
python3 -B scripts/build-sketch-checkpoint.py out/runs/r8-checkpoint-01
```

The builder selects configured Python, refuses a reused output directory, and
requires exact MAIN/DSP hashes from `profiles/sketch-buf-r8.json`. It produces
local MAIN/DSP files, not a new distributable OS or a hardware flash. Unit suites
are scoped; native instruction checks also need their explicit ColdFire bridge
configuration as described in [TESTING.md](TESTING.md).
The routine `buf` profile covers the accepted Sketch/Rust-bridge workflow;
`buf-full` retains earlier Unicorn instruction and retirement fixtures. The
current host's first-map SIGILL remains an explicit legacy harness limit.

The accepted native panel probe is preserved verbatim as
`lab/native/sketch_checkpoint_probe.rs`, with the existing
`lab/native/startup_capture_trace.rs`. Its inputs are private OS1.16, a verified
card image, DSP application reset state, and the lab-owned native boot adapter
at pinned DigiKit `38dfbe4ae88263511eed95691c07fc07e17b6f26`. That adapter is
prepared by `lab.native_migration.prepare_recorder_boot`; the startup recorder
observer follows `buf_startup.START_STOCK`, as in `scripts/check-buf-startup.py`.
It is an explicit integration probe, not part of routine unit execution. The
preserved local R8 run carries its exact input spec, runner and report. Reusing
that spec requires updating local paths and passing the rebuilt candidate through
the existing upload/container checks; a fresh clone alone lacks those inputs.

The [compact checkpoint record](checkpoints/SKETCH-BUF-R8.json) retains hashes,
native flow, and qualified hardware observations. Firmware, captures, generated
native crates, dependencies, and private fixtures stay outside commits.

| Accepted R8 artifact | SHA-256 |
| --- | --- |
| MAIN | `2c8ef46712e30d92afdab1562c3682ead425dcc5a583af64a41bd45320223c18` |
| DSP | `2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a` |
| Experimental SYX | `3de77c6ea2c5148b51c6cd823d0f72235e4c79cf83990c1d09f5ba9da229de1a` |

## Remaining work

ONESHOT is the initially qualified playback path. Broader machines, physical
timing, internal MAIN/keyboard resampling, listening/final output across all
conditions, power loss and persistence need their own bounded validation.
The modeled native recorder supplies external PCM and modeled peripheral cadence;
it does not establish those hardware properties.

Two extra R7 checks remain unqualified: a supposed keyboard test stayed on MOD,
and a sample-browser refusal assertion failed without establishing modal
ownership. Their failed parent remains preserved; successful ordinary-page and
BAR components were qualified separately. No handler was altered to satisfy
those assumptions. Avoid broadening those coverage claims in future notes.

Future work should start from this reproducible source checkpoint, change one
behavior at a time, and retain R8 as the comparison. A separate memory pool,
new sample bank, automatic project saves and native preview are not implicit
parts of this cleanup.
