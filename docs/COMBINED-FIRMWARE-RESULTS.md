# Combined firmware build results — OS 1.16

Built a private **experimental Plaits R3 + managed streaming Flex + Capicola live
STRETCH R3** package. The user authorized local packaging on 2026-10-08. No
firmware was sent to the instrument, and no source was committed or published.

Package: `out/runs/combined-package-03/EXPERIMENTAL_PLAITS_R3_FLEX_CAPICOLA_OS1.16.syx`
(2,266,400 bytes). SHA-256:
`cb57ee53d106b3bf05e3562d74e8d8f45889112da55043a1fb46976552a60229`.
Runs 01, 02 and 03 produce the same package bytes. The final build's manifest
records the current source hashes, pinned dependencies, all patch writes,
compiled layout, preserved sections and container checks.

## Included behavior

| Feature | Included implementation |
| --- | --- |
| Plaits | Existing R3 six-model synthesis and controls; existing track-1 selection guard |
| Flex | Twenty-second mono/stereo USE, project persistence, named Save As, managed saved-source retirement, 32 KiB streaming scratch and native accounting |
| STRETCH | Capicola R3 behind the original type-2 machine; existing controls/locks, live PLAY and STRT/LEN edits, bounded crossfades and native active completion |
| Menu | Oneshot, Werp, Stretch, Repitch, Slice, Grid, PLAITS, MIDI; existing machine IDs retained |

Capicola supports eligible mono sources up to twelve seconds, with up to sixteen
prepared banks and thirty-two reader lanes sharing the existing eight-MiB
reservation. Bank density determines how many sources fit; unavailable,
unsupported or unready sources use stock STRETCH. The project sample pool is
392 MiB. Flex retains its thirty-two-issued-identities-per-boot limit.

## Composition and checks

The recipe is in [COMBINED-FIRMWARE.md](COMBINED-FIRMWARE.md), implemented by
`scripts/build-combined-firmware.py`. It reproduces the latest managed Flex/menu
intermediate exactly, then applies Capicola's six existing pool bounds using an
explicit new baseline guard. The legacy guard and resulting MAIN remain exact.
All ninety-six existing Flex/menu writes survive. Only the six pool immediates
change from the managed/menu intermediate; reset-copy data is unchanged.

Final MAIN SHA-256:
`0bd3c2989665ec5151d5b14d9fbe3d55ee1810b3698fc2d34e7a1f9daaea5531`.
The DSP remains byte-identical to the already validated live STRETCH R3 build:
`0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf`.
It contains 90,244 code bytes and 12,496 constant bytes, with working data in
the reserved sample-pool region.

| Check | Evidence | Result and scope |
| --- | --- | --- |
| Exact build / container | `out/runs/combined-package-03/manifest.json` | PASS; only sections 3 and 7 replaced, protected stored sections exact; two decoders agree; transport/integrity/staging/flash checks |
| Original bootstrap depacker | `out/runs/combined-package-03/device-depacker.json` | PASS; sections 8, 3 and 7 match exactly using actual stock instructions in scratch memory |
| Native allocator bounds | `out/runs/combined-memory-check-02/report.json` | PASS; 42 tail cases and 16 empty-branch cases; exact final MAIN; modeled helper boundaries |
| Legacy reservation | `out/runs/combined-legacy-memory-check-01/report.json` | PASS; prior MAIN SHA remains `7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3` |
| Separate CPU/DSP startup | `out/runs/combined-startup-check-02/report.json` | PASS with final source fingerprints; nominal 400M CPU instructions, nine tasks, all 102 writes retained; two fresh 500M DSP instruction runs retain code/constants/selector and matching PC/working-state fingerprints |
| Source suite | `out/runs/combined-source-tests-03.log` | PASS; 141 tests under the configured Python 3.12 runtime |
| SINE complete replay | `out/runs/20261008T135347Z-test-3f286dcb/manifest.json` | PASS; signal, exact baseline/repeat, stock isolation, clone parity, disabled-hook control and lifecycle |
| SINE source audit | `out/runs/combined-package-03/sine-source-audit.json` | PASS; all runtime/machine/profile/fixture inputs unchanged after replay; only package build/check utilities received import/inspection cleanup |
| Focused lint / diff whitespace | New builder, startup checker, reservation, boundary checker and three tests | PASS |

The final container ends at flash address `0x234960`, below the existing
conservative `0x380000` ceiling. MAIN in-place decoding retains a 2,307,826-byte
minimum gap. These are guarded container/staging checks, not hardware flashing.
The full native R3 playback results remain in
[CAPICOLA-STRETCH-R3-RESULTS.md](CAPICOLA-STRETCH-R3-RESULTS.md); this packaging
work does not change its DSP instructions or make a new real-time claim.

The initial source-suite invocation used system Python 3.10 and failed importing
the existing Python-3.12 CLI, skipping native checks. It is retained in
`out/runs/combined-source-tests-01.log`; the configured-runtime reruns pass.
Compiler warnings about the preserved `SoftClip` return remain unchanged; the
resulting DSP bytes match the validated image. No expectations were rewritten.

## Remaining limits

CPU startup uses the modeled DSP boot peer. DSP startup runs separately with
documented reset-value/peripheral models. Neither proves a coupled processor
boot, physical latency or simultaneous recording/playback headroom. Permanent
L2 instruction-code ownership, full native STRETCH phase/progress bookkeeping,
Flex identity recycling and full project/undo/clipboard-aware GC remain open.
The package stays experimental; device transmission requires a separate request.

## Repeat

```sh
python3 scripts/build-combined-firmware.py out/runs/UNIQUE-PACKAGE \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/UNIQUE-PACKAGE \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-owned.py out/runs/UNIQUE-MEMORY \
  --managed-baseline out/runs/UNIQUE-PACKAGE/MANAGED_FLEX_MENU_MAIN_OS.bin \
  --expected-main out/runs/UNIQUE-PACKAGE/PLAITS_R3_FLEX_CAPICOLA_MAIN_OS.bin
python3 scripts/check-combined-firmware.py out/runs/UNIQUE-PACKAGE out/runs/UNIQUE-STARTUP \
  --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

These scripts select the configured Python 3.12 automatically. Run source tests
with that same interpreter, as recorded in `.local/config.json`.
