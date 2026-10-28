# OS 1.16 Plaits upload preparation

The CPU correction and current verification are documented in [COLDFIRE-FIX.md](COLDFIRE-FIX.md).

> **2026-10-06 hardware failure:** the Plaits r1 handoff crashed after installation at CPU PC `0x40311a64`. The rank shim uses a MOVE addressing form excluded by ColdFire. Do not install/retry this candidate. User confirmed stock 1.16 recovery, normal boot and audio via Novation Launch Control 3 DIN OUT; the generic USB MIDI adapter produced no visible device reception. See [failure evidence](../out/hardware/plaits-1.16-first-trial-2026-10-06/HARDWARE-FAILURE.md). Earlier emulator checks below remain historical evidence only.

2026-10-06. A corrected **experimental manual-trial handoff** is now prepared:
[`READ-ME-FIRST.md`](../out/hardware/plaits-1.16-first-trial-2026-10-06/READ-ME-FIRST.md).
It is not hardware-validated or generally qualified. Earlier `.syx.disabled`
artifacts remain intentionally disabled; the initial candidate had a reload bug.
The final handoff uses the corrected container ending in SHA `b3d22f8`.
The agent has not sent firmware to hardware, committed or published changes.
The candidate includes the six-model Plaits controls experiment only.

## First trial scope: Plaits only

The user selected Plaits before Flex Lite for the first device experiment.
Flex Lite remains preserved in `lab/flex_*.py`, `scripts/try-flex-lite.py`,
its probe scripts and the [Flex Lite reports](history/flex/FLEX-LITE-UI-RESULTS.md).
Its tested record/stop/trim/USE flow assigns a temporary RAM sample to a
remembered track without the normal +Drive save dialog.

The current Flex Lite implementation uses host-side recorder services and
CPU emulator hooks. Its tests are valid emulator evidence; those services
are not embedded in this upload image. A hardware implementation is separate
work. `scripts/prepare-hardware-candidate.py` builds only
`build_cpu(family="controls")` and `build_blob(..., family="controls")`, with
exact expected MAIN and DSP content checks. It does not import or install
any Flex Lite adapter. Keep that separation for the first trial; adding
Flex Lite would require a new candidate and its own validation.

## Stock OS first

The user has upgraded from the reported 1.15A to official **1.16** and confirmed
normal playback, backups, and a DIN MIDI recovery interface. Our existing
patches and audio evidence are for **1.16**, not 1.17.
Installing 1.17 would require porting and revalidating the current patches.

The [official 1.16 archive](https://www.elektron.se/wp-content/uploads/2026/09/Digitakt_II_OS1.16_dist.zip)
was downloaded again from Elektron. Its extracted SYX matches our preserved
original and profile:
`278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec`.
Local stock file and release notes are under
`out/references/stock-upload-audit/`.

Elektron's included release notes describe the standard update: connect USB,
select the device's MIDI input/output in Transfer, drop the stock SYX on DROP,
and confirm YES on the device. Leave power on throughout the update and any
bootstrap update following the first restart. Then verify normal stock startup,
projects, samples and playback before considering a custom image.

Recovery uses FUNC at power-on, then TRIG 4, followed by Transfer's
“OS Upgrade via device startup menu” flow. The computer's MIDI OUT connects
to the device's **5-pin MIDI IN; startup-menu recovery does not support USB**.
See the [official manual, section 15.4](https://www.elektron.se/wp-content/uploads/2025/07/Digitakt-2-User-Manual_ENG_OS1.15A_250708.pdf).
The user subsequently confirmed the stock 1.16 upgrade, normal boot/playback,
backup of projects/presets/samples, and availability of the 5-pin MIDI recovery
interface/cable. These are user confirmations, not an agent-observed recovery
transfer or an independent backup audit.
Do not confuse OS recovery with a factory reset. The release notes warn that
downgrades are unsupported and can lose user content.

## What the community claim establishes

[Elekloader's author](https://www.reddit.com/r/Elektron/comments/1wxo0gl/elekloader_the_open_source_and_developer_friendly/)
describes main-OS-only builds and an unchanged bootloader as the recovery basis.
The [current source](https://github.com/irpina/elekloader/tree/d6449938154a98322a8c0d6844ad10260ab1e065)
reports an experimental DTII 1.17 UI/key mod working on hardware. That does not
test our 1.16 SHARC code. Its normal verifier deliberately refuses a changed
DSP section, so we do not describe our output as an Elekloader-verified mod.

An unchanged bootstrap in the file also does not mean an older machine cannot
receive a stock bootstrap update: 1.16 carries version `0x0201`. This is another
reason to perform the official upgrade separately. Recovery is a useful route,
not a proof that arbitrary custom code cannot damage persistent state or that
every failure is recoverable without service.

## Reproduction and checked output

An isolated read-only reference checkout lives at
`out/references/elekloader-upload-audit`, revision
`d6449938154a98322a8c0d6844ad10260ab1e065`. The script refuses another revision
or a dirty checkout. Existing DigiKit/Selache pins are unchanged. The reference
supplies its parser/compressor; the lab owns the two-section container policy.

```sh
python3 scripts/prepare-hardware-candidate.py out/runs/upload-example \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/upload-example \
  --elekloader-reference out/references/elekloader-upload-audit
```

Successful build: `out/runs/upload-preflight-final/manifest.json`.
Actual-firmware depacker report: `out/runs/upload-preflight-02/device-depacker.json`.
Both builds produce the same candidate SHA-256:
`43007364c3bd0e65e78b558a0700b9a082f92b0ee287099c2cafbdb9598d3fa1`.

Checked:

- Stock reconstruction is byte-identical to the downloaded original. The
  generic pinned writer assumed a `0x80` table area; 1.16 uses `0x90`. The lab
  builder retains the original table boundary and reserved bytes.
- Only MAIN (3) and DSP BLOB (7) change. Sections 2/bootstrap, 4/updater,
  5/build stamp and 8 remain identical, including their stored compressed bytes.
- Rebuilt MAIN and BLOB exactly match the prior pattern/audio candidates.
  This is a packaging change, not a new DSP algorithm or emulator patch.
- Transport checksums, counters, framing, container checksum, HMAC, section
  identity/destinations, padding and complete decoded content pass.
- The candidate is 2,238,624 SYX bytes; its container is 1,766,304 bytes.
  Starting at flash `0x80000`, it ends at `0x22f3a0`, below `0x380000`.
  Stock 1.16 accesses its persistent-store header at that boundary and operates
  on sectors `0x380000`/`0x3c0000`; exact instruction-byte guards are recorded
  in `lab/upload.py`. This is a conservative ceiling, not a complete partition map.
- Stock 1.16's loader stages MAIN at `0x40400000`. Simulated in-place
  decompression retains a minimum 2,303,057-byte gap from unread input.
- The actual hash-guarded 1.16 bootstrap depacker at `0x80000432`, run under
  Unicorn, decompresses stock section 8 and both changed sections exactly.
  This invocation uses separate scratch input/output; it is not a full boot.
- Five negative controls reject packet corruption, attempted bootstrap/updater
  replacement, an undeclared DSP change and wrong expected MAIN content.
  The 17 existing source tests, lint and formatting checks also pass.

The earlier failed run `upload-preflight-01` is retained. Its stock-layout
failure was fixed, not waived. The build manifest remains conservatively blocked;
the separately linked device-depacker report resolves that one listed check.

## Remaining work before recommending a device trial

1. Complete coupled CPU/DSP startup verification. Fresh CPU boot and isolated
   DSP initialization now pass separately, as detailed below.
2. Establish ownership of the Plaits DSP arena `0x20080000..0x200f2000` and
   validate wrapper register/mode/interrupt behavior through stock paths.
   Loader disjointness alone does not reserve runtime memory.
3. Verify sample-free initialization, the final mixer/output path, and project
   save/reload. Current audio evidence taps prepared voice buffers.
4. Establish a bounded first hardware test and physical timing measurements.
   Retired emulator instructions and slow host rendering are not hardware load.
5. Stock 1.16 operation, backup and DIN interface/cable availability are now
   user-confirmed. Recovery transfer itself has not been exercised.

Fresh DSP application-entry diagnostics now progress through peripheral setup;
see the reproducible command below. Coupled CPU/DSP startup remains separate.
Passing container integrity checks cannot substitute for these runtime checks.

## Fresh startup probes after the stock upgrade

The unchanged candidate was decoded into a fresh directory and its CPU MAIN
started at reset, with the candidate container backing emulated flash. No
inherited CPU/DSP snapshot or +Drive card was used. It reached the 400M CPU
instruction checkpoint and created nine tasks. See
`out/runs/upload-coldboot-01/run.py`, `run.log` and `result.json`.
This route models DSP handshakes; it is not a coupled CPU/SHARC startup.

Separately, stock and candidate DSP loader images were each loaded fresh and
the resolved initialization function at SW `0x1c15e3` was called. Both returned
after 1,243,446 emulator steps, with no observed overlay writes in
`0x20080000..0x200f2000`. See
`out/runs/upload-coldboot-01/dsp-init-final.json` and `dsp-init-retry.py`.
The one native fallback per call handles the outer return. The first script
attempt used an unavailable cleanup method after the stock case; its partial
report/log remain intact, and the corrected probe ran both cases.

This checks one initialization function, not the SHARC ROM/reset chain or
interrupt-driven runtime. No arena writes in this bounded call does not prove
that stock runtime never allocates or uses the arena.

The no-card CPU startup probe returned `PARTIAL_MAIN_OS` for both the candidate
and official stock 1.16. Both independently repeated arms agreed. Display
handoff, job pump and PIT3 were observed; mainloop and DTIM3 were not. Increasing
the candidate's post-intro observation from 10M to the standard 60M instructions
did not change that verdict. The reports are `bootcheck.json` in the candidate
and `out/runs/upload-stock-coldboot-01/` directories, plus candidate
`bootcheck-standard.json`. This failure is not evidence of a custom-only
regression, and it is not a passing startup result.

Repeating the candidate CPU boot with the known, read-only sample-card image
reached the main loop. The fresh reset ladder reached 400M instructions;
the subsequent 400M sample-loading run observed 672 mainloop entries, active
DTIM3, no terminal failure and zero fault pages. Two startup modals were closed
through actual panel events, producing a new `ready.snap`. Evidence is in
`out/runs/upload-card-coldboot-01/`: `run.py`, `load.log`, `close-modals.py`,
`close-modals.log` and `ready.json`. No old ready snapshot was imported.

The panel helper initially refused the new container hash. A run-local copy of
the stock Digitakt II panel definition adds only the exact checked candidate
hash and MAIN hash. `DT2_DEVICES` selects this file; pinned dependency files
and their default unknown-firmware rejection remain unchanged. The candidate
bytes were not modified. This closes the CPU startup/ready-state step under
the modeled DSP handshake; it does not close the coupled DSP boot, hardware
timing, final-output or runtime-arena ownership checks.

## Repeatable DSP application-entry diagnostic

Run the hash-guarded diagnostic with a new output directory:

```sh
python3 scripts/probe-dsp-startup.py out/runs/dsp-startup-example \
  --candidate-blob out/runs/upload-card-coldboot-01/sections/section_7_BLOB.bin \
  --peripheral-smoke
```

The script loads the stock or candidate loader bytes at application entry
`0x1c1338`; it does not import a prepared DSP snapshot, force a function return,
skip instructions, or patch firmware. It supplies a bounded list of peripheral
reset values and keeps unknown-register reads fatal. Reset values come from
Analog Devices' [ADSP-2156x Hardware Reference, revision 1.1](https://www.analog.com/media/en/dsp-documentation/processor-manuals/adsp-2156x_hwr.pdf),
read through this [copy of the ADI manual](https://manuals.plus/m/96545b862402a7fd803d3aa69d42e7bc81f9b966309702f114de7ff7f4680867)
after direct download failed. Figures 6-7/6-13/6-28 and 32-7 cover the SEC/SPU
values; appendix tables A-15/A-16, A-73..A-76 and A-80..A-82 cover DAI, PCG,
PINT and GPIO. In particular, PINT_ASSIGN resets to `0x101`, not zero.

The original native run stopped at SEC_CCTL after 7,576 instructions, equally
for stock and candidate. Adding the documented initial values exposed successive
SEC, SPU, PCG, GPIO, PINT and DAI reads. Earlier failures remain in ignored runs.
`out/runs/upload-dsp-startup-repeat-08/report.json` records two fresh runs of
each image: all four reached `0x1c0eea` at 500 million instructions without a
native trap and with identical exported register/overlay-state fingerprints.
SPI2 and SPORT4 DMA had been configured by firmware. This fingerprint excludes
the differing immutable firmware images; it does not mean those images match.

This is an instruction-bound checkpoint, not a declared completed boot.
Peripheral reset values alone do not implement register side effects, board
signals, interrupt timing or ROM-loader execution. The existing peripheral
model still has limited SEC masking/preemption and DMA coverage. The optional
smoke sends sixteen captured stock control frames through SPI2 DMA and clocks
SPORT4 with silent input; it is not a live CPU peer or a Plaits listening test.
The reports deliberately retain `hardware_ready: false`.

The initial DMA smoke (`upload-dsp-peripheral-01`) returned zero-filled SPI
replies and silent SPORT blocks in all sixteen events. Inspecting the pending
interrupts exposed an important harness omission: `_make_runner` defaults to
the simplified register-bank and stack models. Native interrupt entry requires
both full models. The reusable script now enables `stack_model` and
`bank_model` before transferring state to the native engine. A separate stock
probe with both enabled reached `0xb863c5` at 500M instructions and produced
changing nonzero SPI replies beginning with event three. SPORT remained silent
for these initial stock control frames; this is not a Plaits sound test.

The corresponding full-model repeated run is
`out/runs/upload-dsp-peripheral-final/`. Earlier simplified-model checkpoints
above remain diagnostic history, not proof of working interrupt-driven boot.
Only the full-model run should be used as the starting point for a CPU peer.
The current command still replays captured control data, so coupled CPU/DSP
startup, arena lifetime, meaningful final-output audio, and hardware timing
remain open. Firmware bytes and the pinned dependency checkouts are unchanged.

Completed result: all four full-model arms reached the 500M checkpoint without
a trap; each serviced sixteen SPI2 exchanges and sixteen 256-byte SPORT4 blocks.
Each image's startup state and event report repeated exactly. Reply data became
nonzero at event three. The initial SPORT blocks were all zero, so this still
does not establish audible final output. The exported startup dirty-page maps
contain no pages in the Plaits arena; that bounded observation is not proof of
runtime reservation or interrupt-safe use.

Stock and candidate reply hashes differ. A separate raw-byte capture in
`out/runs/upload-spi-reply-diff-output-01/reply-diff.json` localizes every
difference to wire offsets 2 and 3, starting at event three. All remaining
2,746 bytes agree in each of sixteen packets. The differing big-endian word
is consistently candidate = stock + `0x25e6` (9,702). Subsequent tracing
identifies the complete first four-byte word as elapsed EMUCLK, as follows.

### DSP reply timing field resolved

Fresh stock and candidate application-entry probes single-step the first
three SPI/SPORT events and watch both TX ring heads (`0x28266220` and
`0x28267220`). The writer is stock instruction `0x1c75c4`:
`DM(I4, M5) = R2`. Firmware reads EMUCLK into R14 at `0x1c74eb`, reads it
again into R0 at `0x1c75ab`, subtracts at `0x1c75ae`, swaps the two 16-bit
halves, and writes the result. SPI's per-halfword byte swap puts this on the
wire as a big-endian elapsed count. The complete clock/writer sequence is
byte-identical in stock and candidate images.

Evidence: `out/runs/upload-header-trace-source-01/` retains both probe
scripts, disassembly, logs and `timing-field.json`; fresh dynamic reports
are in `upload-header-trace-01/` and `upload-header-trace-plaits-01/`.
All sixteen previously captured packets pass the explicit check: the timing
word differs by 9,702 ticks after initial zero replies, and the remaining
2,744 bytes match exactly. The first observed writer executes 9,702 steps
later in the candidate's corresponding event as well.

This resolves the field's identity. The enabled native diagnostic clock
advances once per retired instruction (`native/sharc/src/lib.rs`); it is not
cycle-accurate. These counts do not establish physical DSP load or headroom,
and identifying timing does not clear the other runtime release checks.

Validation of the final diagnostic source: 17 source tests, Ruff and
`git diff --check` passed. SINE replay passed in
`out/runs/20261006T093710Z-test-6c5bf51a/manifest.json`. An earlier replay's
numeric result passed but its source-integrity guard correctly rejected edits
made during that run; that failed manifest is preserved.

## Final-check run, 2026-10-06

The user requested completion of local checks and explicitly reserved flashing
for themselves. No device connection, transfer or flash was performed.

- `upload-final-container-01`: fresh rebuild is byte-identical to the previous
  candidate (`43007364...d3fa1`), including stock bootstrap/updater sections.
  Its `device-depacker.json` passes all three actual-bootstrap decompressions.
- `upload-final-output-01`: two independent fresh DSP application-entry runs,
  full register-bank/stack/interrupt models, 150 preroll plus 256 captured
  Plaits-FM frames. No DSP snapshot, sample upload or instruction fallback.
  Both produce exactly the same 103,936 bytes of SPORT4 Q31 stereo output.
  SHA-256: `67fab78f67d27d0ed5978cad014bbcf76da20bcf468f4fd51b7e9757c99336d9`.
  Peak 0.435235, RMS 0.089438, zero saturated samples. This verifies a bounded
  sample-free voice-to-mixer-to-output path in the emulator. The WAV assumes
  48 kHz; it does not measure the physical device's clock.
- `upload-six-output-01`: fresh DSP startup, then 96-frame segments of all six
  models. MODEL is explicitly varied in an authenticated captured frame; this
  is a controlled DSP test, not six live CPU selections. All six final-output
  segments are nonzero, unclipped and distinct. Code `0x20080000..0x200c0000`,
  constant data `0x200c0000..0x200d0000`, and the 32-byte remap table remain
  byte-identical. This is bounded integrity evidence, not proof of permanent
  arena ownership across every stock workload.
- `upload-coupled-01`: 68 real CPU/DSP SPI exchanges, with actual DSP replies
  returned to the running CPU; 34 mainloop entries and zero fault pages. CPU
  starts from the earlier fresh-boot-derived ready snapshot; DSP starts fresh.
  Initial loader/handshake and LP0 sample transfers are still not coupled, and
  CPU SSI input uses the existing RxHandoverPeer. No notes occurred in this
  bounded live-link probe, so the output/audio check above remains separate.
- `upload-wrapper-abi-01`: actual wrapper entry/return breakpoints with full
  bank/stack models and interrupts enabled. Custom type 7 and stock type 0
  both preserve R/I/M/L/B registers and MODE1/MODE2; the stock arm allows only
  R4/R12 changes from the two original displaced instructions. This is not an
  exhaustive interrupt-preemption or reentrancy proof.

Each ignored run retains its probe source, input hashes and report. The original
firmware bytes and pinned dependencies remain unchanged. Earlier manifests
retain their original blocker lists; use these later reports for resolved
checks rather than rewriting historical results.

### Reload check found a release blocker

`upload-pattern-reload-01/capture.json` fails the normal panel temporary-pattern
save/edit/reload check. After FUNC+YES, an encoder edit, then FUNC+NO, the
firmware reports “Ptn reloaded from temp” and restores base HARM and stored
locks, but changes machine type 7 to type 0. Subsequent actual trigger frames
therefore use the sampler path: TIMB 11271 becomes 7 and locked 27143 becomes
519. This is not an audio-render comparison or a changed test expectation.
The original candidate remains disabled pending correction and revalidation.

### One-byte track-restore correction

A write trace (`upload-reload-trace-01`) located the actual type reset at
`0x400db326`. The stock restore span loads D2=8 at `0x400db2ea`, validates
`(uint8_t)(type + 1) < D2`, and masks invalid values to zero. Type 7 therefore
fails. `lab/plaits_controls.py` now changes only that bound to 9; D2 is reloaded
before validation of the adjacent serialized field.

The corrected MAIN differs from the prior candidate at exactly one byte:
`0x400db2eb`: `08` -> `09`. MAIN SHA-256:
`1b6dd1b8ec4d03156cb53a10d220badc91a59ea437dae6fa517cc6c5eb5d5f63`.
DSP bytes are unchanged, so the fresh-start DSP/audio/ABI results above still
apply to the exact DSP included in the corrected package.

The reusable CPU checks execute the real restore span for all 256 machine
bytes and four adjacent-field values (1,024 comparisons). Only type 7 changes;
the 0xff sentinel and all other stock outcomes, including adjacent fields,
remain exact. The prior 3,372 resolver/register and 368 transport cases pass.
All six compiled adapter checks pass in `upload-controls-fixed-01/report.json`.

`upload-pattern-reload-fixed-01/capture.json` repeats the same real panel
save/edit/reload test that failed. It now passes: machine 7, base values and
locks on steps 1/5/9/13 are restored exactly in actual trigger frames, including
TIMB 11271 and 27143. The run has zero CPU fault pages. This is temporary
pattern save/reload; durable project storage and power-cycle persistence remain
separate device qualifications. The failed pre-fix evidence is retained.

Corrected container: `out/runs/upload-corrected-container-01/manifest.json`,
SHA-256 `791a6bf0e331157fb30ecebcde56782d9517ffd8978fbba1b7534d190b3d22f8`.
The actual bootstrap depacker again passes sections 8/3/7 for these exact
bytes. Source tests (17), Ruff, diff checks and the complete SINE replay pass;
SINE report: `20261006T101528Z-test-5bac3446/manifest.json`.

`upload-corrected-coldboot-01` starts the corrected CPU image at reset, reaches
400M instructions and nine tasks, then runs 400M more with the known card:
672 mainloop entries, two jobs, active DTIM3 and zero fault pages. The
normal panel helper initially rejected the new firmware hash, as expected.
A run-local DTII device definition admits only the exact candidate and MAIN
hashes; two actual modal dismissals produce `ready.snap`. Dependency device
files and their unknown-image rejection remain unchanged. The ready state is
freshly derived, not the older prepared CPU checkpoint.

### Manual-trial handoff and remaining qualification

`out/hardware/plaits-1.16-first-trial-2026-10-06/` contains the corrected
experimental SYX, exact official 1.16 recovery SYX, official upgrade notes,
SHA256SUMS, a guide, and an evidence index. Copying the verified file into this
handoff did not change a byte. `upload-corrected-coupled-01` repeats the live
SPI check with the corrected CPU: 68 exchanges and zero fault pages.

This handoff is for the user's explicitly requested first manual experiment,
not a declaration that all earlier broad qualification gates are closed.
The guide names the remaining complete coupled-reset/LP0, arena-lifetime,
interrupt/reentrancy, durable-storage and physical-timing limits. Physical
results cannot be obtained by more local emulator tests. Use a disposable
project and Plaits on track 1; no hardware transfer was performed by the agent.
