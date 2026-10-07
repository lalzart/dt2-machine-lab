# Plaits r1 hardware failure and ColdFire correction

2026-10-06. The user recovered official OS 1.16 through Transfer Recovery mode,
using `LC3 1 To DIN Out` on a Novation Launch Control 3 and its physical OUT
connected to Digitakt II IN. The user confirmed normal startup and audio.
The generic USB2.0-MIDI adapter (VID 1a86, PID 752d) did not show reception
on either exposed output. The agent performed no hardware transfers.

## Defect and narrow correction

The hardware exception displayed `V04 M0 P40311A64`. At that exact address,
our rank-table shim began with `move.l #$40311a84,8(sp)`. The next MOVE used
the same prohibited immediate-to-displacement combination. NXP's ColdFire
Programmer's Reference Manual Rev. 3, printed pages 4-47/4-48, excludes this
source/destination pairing. This explains the observed startup exception;
it is a CPU instruction defect, not evidence of physical DSP damage.

Source: https://www.nxp.com/docs/en/reference-manual/CFPRM.pdf

`lab/coldfire.py` replaces the 22-byte shim plus six verified zero bytes with:

```asm
move.l  a0,-(sp)
lea     $40311a84,a0
move.l  a0,12(sp)
lea     64(a0),a0
move.l  a0,16(sp)
movea.l (sp)+,a0
jmp     $401aab60
```

The save shifts the caller's begin/end arguments by four bytes. The routine
restores A0 and SP, preserves other registers, return address and map argument,
and leaves CCR as the original final MOVE would. Scratch storage is four bytes
below SP, not shared global state. It fits within the existing 32-byte slot.

Reversing this guarded 28-byte replacement reproduces the exact failed r1
MAIN hash. All other MAIN bytes and the DSP are unchanged. The pinned DigiKit
checkout remains clean; the correction is owned by the lab and is currently
applied to the Plaits `controls` family. Historical SINE/VA/trio/bank CPU
builders remain emulator-only baselines and must not be used for hardware.

Failed r1 MAIN: `1b6dd1b8ec4d03156cb53a10d220badc91a59ea437dae6fa517cc6c5eb5d5f63`

Corrected MAIN: `4c226dfe863005324782f2931d2ad5e0c9142d8d8f85701c3e1a5065ed6fdc3f`

## Preventing the same missed check

The builder classifies every changed byte as code or data and decodes the
emitted CPU instruction subset independently of Unicorn and generic 68000
disassembly. It checks MOVE addressing combinations and rejects unreviewed
opcodes, addressing forms, and truncated instructions. All current 182 patch
regions (including data) and 467 instructions pass. This is a version-scoped
check of the emitted subset, not a complete ColdFire validator or whole-OS
correctness proof. Data regions are separately listed; executable changes
cannot hide in unclassified image differences.

The original faulting instruction is a rejection control. A separate emulator
check confirms the exact same bad instruction is still accepted by Unicorn:
an emulator-only boot cannot stand in for the encoding check. Unknown MAIN
changes are refused by the reverse-to-r1 hash guard; future changes require a
new explicit review rather than silently updating a golden output.

## Checks and reproduction

```sh
./labctl doctor
python3 -m unittest discover -s tests -v
python3 scripts/check-coldfire-cpu.py out/runs/<fresh-cpu-check>
python3 scripts/capture-pattern.py out/runs/<fresh-pattern> --machine plaits
./labctl test sine --replay
```

- 22 source tests passed, including the exact illegal opcode, other prohibited
  MOVE pairs, supported alternatives, truncated/unknown opcodes and byte guard.
- `out/runs/coldfire-cpu-check-final/report.json`: 256 rank ABI cases, all 32
  CCR combinations and deterministic randomized registers/stack data;
  3,372 resolver/register cases, 368 transport cases, 1,024 restore cases,
  complete parameter accessors, UI/range checks and stock metadata checks pass.
- `out/runs/coldfire-pattern-final/capture.json`: prepared panel editing,
  locks, two loops and stop/edit/restart pass, with zero faulted pages.
- `out/runs/20261006T112747Z-test-33c956e3/manifest.json`: SINE replay passed.

The prior hardware-failure evidence and original handoff files remain under
`out/hardware/plaits-1.16-first-trial-2026-10-06/`; the r1 SYX remains withdrawn.
This correction has not been tested on physical hardware. Physical timing,
long-session behavior, all-track use and durable project persistence remain
unqualified. Flex Lite remains excluded from the Plaits candidate.

## Completed candidate checks and local handoff

- `out/runs/coldfire-pattern-reload-final/capture.json`: real panel temporary
  save/edit/reload preserves machine, macros and locks; zero fault pages.
  Reproduction: preserved `out/runs/upload-pattern-reload-source-01/probe.py`
  with a fresh output directory and `--machine plaits`.
- `out/runs/coldfire-coldboot-final/rank-result.json`: corrected rank routine
  executed during fresh-reset continuation; A0/SP/return/map preserved and
  begin/end arguments correct. The initial 400M checkpoint was too early to
  observe the call; that failed probe is retained rather than counted as passing.
- `out/runs/coldfire-coldboot-final/ready.json` and `load.log`: standard guirun
  startup with `--intro-timers pit3` reached 673 main-loop entries, two jobs,
  no terminal failure or faulted pages, then dismissed both actual modal windows.
  The helper first failed to locate its cwd-relative devices directory;
  separate close.py used the explicit pinned directory and succeeded.
- Generic bootcheck with default timers returned PARTIAL_MAIN_OS (PIT3/vector
  handover) for both r1 and r2. See prior-r1-bootcheck.json and resume.json.
  Those are not passing results; standard startup above is separate evidence.
  No timer implementation was changed.
- `out/runs/coldfire-corrected-container-final/manifest.json`: exact reconstruction,
  section isolation, unchanged tested DSP, placement and five rejection controls.
- `out/runs/coldfire-corrected-container-final/device-depacker.json`: actual stock
  bootstrap decompressor reproduced all three tested sections exactly.

Rebuild (fresh output path required):

```sh
python3 scripts/prepare-hardware-candidate.py out/runs/<fresh-container> \
  --elekloader-reference out/references/elekloader-upload-audit \
  --cpu-check out/runs/coldfire-cpu-check-final/report.json \
  --pattern-check out/runs/coldfire-pattern-reload-final/capture.json
python3 scripts/check-upload-depacker.py out/runs/<fresh-container> \
  --elekloader-reference out/references/elekloader-upload-audit
```

The builder retains its conservative offline/release-blocked manifest and
`.syx.disabled` output. After reviewing the separate checks, an exact copy is
available for a limited manual experiment in
`out/hardware/plaits-1.16-coldfire-r2-2026-10-06/`, with README, evidence index,
stock recovery file and verified SHA256SUMS. This is a trial handoff, not
closure of physical timing, full coupled boot, arena ownership or persistence gaps.

r2 SYX SHA-256:
`5f95f0e705170056cedaf5134e96867c5f2ebdad3b95e489a7504e4bc68a9b57`.

All files remain local and uncommitted. No MIDI or firmware was sent.
