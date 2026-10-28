# All-feature experimental OS — Digitakt II 1.16

This document describes the preserved earlier backend. Add `--capicola-legacy` to its all-feature build command to reproduce that backend. The current default uses the [shared author release engine](CAPICOLA-REDDIT-RESULTS.md).

A later [CAPI quality candidate](history/capicola/CAPICOLA-QUALITY-RESULTS.md) adds the optional
`--capicola-quality` profile. The package documented below remains the exact
default/reference build; the quality candidate has its own artifact and checks.

This is an actual local `.syx` OS package combining Plaits, Capicola time
stretch, Arp and managed Flex. It is built by
`scripts/build-cpu-extension.py --all-features`. No firmware has been sent to
hardware, committed, pushed or published.

| Feature | Included behavior |
| --- | --- |
| Plaits R3 | Six models, named MODEL, HARM/TIMB/MORP modulation and 100–12,800 ms duration; existing track-1 restriction |
| Time stretch | Existing Capicola R3 renderer behind STRETCH, live PLAY/trim updates, native completion and CAPI OFF/ON on encoder C |
| Arp | Native track-1 OFF/UP/ORDER/RANDOM, stock tempo, quarter/eighth/sixteenth/32nd rates, G mode/rate focus and native project companion persistence |
| Flex | Up to twenty seconds mono/stereo, native USE, named Save As, project persistence, streaming scratch and managed saved-source retirement |

CAPI starts OFF. Enable it on STRETCH with encoder C. Its existing twelve-second
eligible-mono-source limit, sixteen shared banks, thirty-two reader lanes,
8 MiB reservation and unsupported/unready stock fallback remain. Flex retains
its existing thirty-two-issued-identities-per-boot limit. The sample pool is
392 MiB. This integration does not implement new algorithms or expand those
capacities.

## CPU composition

The recipe first reproduces the exact previously validated Plaits R3/Flex/CAPI
CPU baseline (`7f911a1e...`). It removes the old Flex placements with exact byte
guards and proves that reapplying them restores that complete baseline.
Plaits code, descriptors, extended parameter rows, menu order, CAPI helpers
and the six sample-pool bounds remain byte-identical to their reviewed versions.

The 54-byte early loader now occupies the reviewed free interval beginning
`0x402fc718`. Plaits keeps its original `0x403117c4..0x40312000` allocation.
Arp and Flex retain the same payload bytes and addresses as the prior DDR
experiment: 15,217 payload bytes within `0x47e8b000..0x47e9b000`, a 64 KiB
reservation. They share one project-save hook with Arp prepare, Flex prepare,
the original writer, Arp commit and unconditional cleanup.

CAPI's existing extended SRAM initializer is retained. The segment chain is
appended after its source data at `0x403203f4`; the early loader copies DDR
payloads before original reset helpers copy SRAM data and clear external BSS.
Original initialized SRAM bytes and reset-clear bounds are preserved. Native
startup checks verify the real resulting runtime addresses.

`lab/cpu_fixture.py` installs this exact image into authenticated prepared
fixtures for lifecycle tests. It populates CAPI's SRAM destination directly
and never writes the appended source over a running fixture's live BSS.
Prepared-fixture installation is separate from the native reset test.

The DSP is rebuilt twice and must reproduce the existing Plaits/CAPI toggle
image exactly:
`cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7`.
Only MAIN and SHARC BLOB sections change; protected stored sections remain
identical. The lab dependency pins remain unchanged.

## Reproduce

Use fresh ignored output directories. Scripts select the configured Python
3.12 runtime. The explicit native adapter requires the inspected clean DigiKit
revision `ed57b4758d45d435d07da37ce06b4090afab843b`, Rust 1.98.0 and cached
Cargo dependencies; it builds offline without editing that checkout.

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/<package> --all-features \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-cpu-extension-boot.py out/runs/<package> out/runs/<boot> \
  --native-upstream <clean-digikit-ed57b475-checkout>
python3 scripts/check-capicola-toggle-cpu.py out/runs/<controls> \
  --package out/runs/<package>
python3 scripts/check-combined-firmware.py out/runs/<package> out/runs/<startup> \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-toggle-native.py out/runs/<playback> \
  --package out/runs/<package>
python3 scripts/check-flex-lifetime.py out/runs/<flex> --package out/runs/<package> \
  --frames 960000 --stereo --heap-trace
python3 scripts/check-arp-firmware.py out/runs/<arp-flex> --package out/runs/<package> \
  --tempo-ui --shared-save --mode order --tempo 120 --record --storage \
  --flex-take --instruction-limit 12500000000
python3 scripts/check-upload-depacker.py out/runs/<package> \
  --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

Run `python -m unittest discover -s tests -v` with the configured interpreter.
The all-feature tests additionally prove unchanged DDR segments, retained
Plaits cave bytes, one save-hook owner, explicit profile rejection, complete
repeat, and fixture initialization without clobbering live BSS.

## Evidence boundaries

CPU reset uses the native ColdFire emulator with modeled boot peripherals.
It resolves observation addresses from authenticated stock, then installs the
experimental MAIN before the first reset instruction. The reset hook and
loader execute as guest code; disabling the hook must fail segment comparison.
DSP reset and playback are separate runs. Prepared GUI/loader checks model
recorder input, sample-transfer peripherals and card sectors, while native
code performs allocation, assignment, filesystem and project operations.

These checks do not establish coupled CPU/SHARC cold startup, physical input,
physical timing/headroom, cache coherence, worst-case stack/DDR ownership,
USB/Overbridge or hardware behavior. Existing STRETCH progress bookkeeping,
Flex identity recycling and broader undo/clipboard lifetime gaps remain.
Exact artifacts and accepted results are recorded in `ALL-FEATURES-VERIFICATION.json`.


## Completed local build and checks

The final package is
`out/runs/all-features-package-20261017-03/EXPERIMENTAL_ALL_FEATURES_PLAITS_CAPI_ARP_FLEX_OS1.16.syx`
(2,272,032 bytes). SHA-256:
`f5ac5b25cff226517cfbd730a44a3c7b08e71d57e4280977c4dfc2aff16e6a8c`.
MAIN is `0b962b8925fbcc68559bd3d23ac45467c531cd8b19399dfdaa918a9142019f98`.

The build repeats exactly, retains protected sections and passes framing,
authentication, two-decoder and original-bootstrap depacking checks. Native
CPU reset reaches ready, executes 39 stock main-loop calls into DDR, preserves
code/canaries and passes the disabled-loader negative. Native controls cover
all six Plaits models and CAPI formatting/permission/transport helpers.
Two independent DSP resets match. DSP playback reproduces stock OFF exactly
and the preserved Capicola implementation with zero measured difference,
including sixteen mixed tracks and 56 other-machine parity blocks.

A single GUI session with active Arp and a published stereo Flex take now
passes normal project save and menu recall. The observed save order is Arp
prepare, Flex prepare, stock writer, Arp commit, cleanup. All 121,740 pattern
bytes survive; mode/rate and recorded pitches `67,64,60,67,64,60,67,64` return.
Flex's durable reference and track assignment survive, its saved source retires,
and a complete native file read and twelve fresh transfer pages match the
original stereo take. There are no guest fault pages. This session models the
recorder/DSP-transfer peers; it is not coupled SHARC audio playback.

The first combined run is retained as failed: its observer wrongly demanded
PCM retransmission on a valid loader cache hit. A native backing read and
fresh-upload diagnostic showed the data was intact. The corrected observer
checks the backing directly, releases only matching fixture cache aliases via
native teardown, then requires both channels of a fresh upload to match.
The complete GUI scenario was rerun successfully. No guest firmware bytes
changed during this correction. Both immutable source freezes and every
original report remain linked in the verification record.

A separate Arp-to-Plaits fixture captures the actual type-7 CPU transport and
replays it through the compiled DSP voice path: repeated PCM is exact and a
muted-trigger negative is silent. The fixture seeds Plaits on track 1; it does
not establish panel selection, coupled cold boot or final physical output.
The twenty-second stereo Flex lifecycle, 226 source tests, focused Ruff checks,
whitespace check and stable-source SINE replay also pass.

[Machine-readable verification](ALL-FEATURES-VERIFICATION.json) records exact
artifacts, hashes, source versions, retained failure and evidence boundaries.
Physical timing, boot/install behavior and hardware readiness remain open.

## Source-playback CAPI candidate

The separate `out/runs/capicola-source-package-20261017-03/EXPERIMENTAL_ALL_FEATURES_CAPI_SOURCE_OS1.16.syx` includes the same Plaits/Arp/Flex CPU with a new source-oriented CAPI reader, source grain handoffs and native mono/stereo. [Exact identity, validation and limits](history/capicola/CAPICOLA-SOURCE-RESULTS.md). Earlier reference and quality packages remain preserved.
