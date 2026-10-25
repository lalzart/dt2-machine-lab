# Author release CAPI replacement — OS1.16

**WITHDRAWN AFTER HARDWARE EXCEPTION.** The decoded DSP stream exceeds the stock CPU staging allocation. See [boot repair](CAPICOLA-REDDIT-BOOT-FIX.md). Passing checks below did not include that actual boot path.

The all-feature build now uses the shared author's release-default STRETCH engine. The old analyzed-keyframe implementation is replaced in the current package. Plaits R3, native Arp, managed Flex and the binary CAPI switch remain included. CAPI starts OFF; turn encoder C on STRETCH to enable it.

Artifact: [EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_OS1.16.syx](../out/runs/capicola-reddit-package-20261017-04/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_OS1.16.syx).

- SYX SHA256: `a70f91d7998253b3baeda919dc2156ec3fd51a4e3532462eb92591913879505a` (2,281,248 bytes).
- MAIN SHA256: `574ba37b677c62a8cba8885652aa0ca25f4d3b7b93394e977739bb7c0e04e4cc` — exact previous switch/Arp/Flex/Plaits CPU image.
- DSP SHA256: `d3ba7544cb4ae526293f2add762a7e3cef42a6854c2a173def8ba24ded481de2` (1,314,460 bytes).
- CPU, DSP and complete container repeat exactly. Protected firmware sections retain stock bytes.

## What changed

This is a direct port of hy3na-k1ng's supplied Digitakt implementation, using its default release configuration: CC_CLEAN, GEN_BLEND_FIXED=0.0f, GEN_BLEND_ZERO, GEN_WSOLA, GEN_BUILD=0. That release path reads PCM directly with Catmull-Rom interpolation and waveform-aligned splices; it bypasses the sparse-keyframe reconstruction. The original 640-sample leash/fade, search resolution, one-search-per-frame budget, stereo pairing and SHARC assembly fast paths are retained. No performance-driven reduction of fidelity was introduced.

The generated adapter relocates voice state and ring storage, reads our existing binary CAPI raw128..256 threshold, and preserves the tagged status reply protocol. There is no analyzed-bank preparation or WAIT phase. Switching follows the author's per-block dispatch, including immediate stock/author takeover; the previous trigger-only latch is retired. Only the STRETCH generator call is replaced; the author's extra REPITCH/GRID/SLICE/BARS and OS1.17 changes are outside this port.

The complete supplied source is pinned by archive SHA256 `87bb2b073dae7253d7694198eced9a63ea4313373eb5ac1573902560cf19ad23`. All 66 original files remain exact under [upstream](../machines/capicola-reddit/upstream/), including the AGPL license and author/Heavylight attribution. The ZIP has no Git commit identity. The lab's dependency pins remain unchanged.

## Verification

| Layer | Observation |
|---|---|
| Author host oracle | 14 published golden replays pass unchanged |
| Packaged SHARC entry | 9 STRETCH/retrigger/reverse/loop/pitch/time cases; all 271,680 samples bit-exact with the host oracle |
| Native frame routing | 16 independent stereo tracks, 32 voices, actual LP0 sample loading; OFF voice buffers and DAC ring exactly stock; ON uses author states |
| Preserved machines | All six Plaits models and seven other raw machine selections match the preserved R3 source buffers exactly; all six Plaits checks have nonzero output |
| Final output | 300 blocks / 9,600 stereo frames; ON/OFF differ; muting only the custom renderer gives zero final-ring RMS while source PCM remains unchanged |
| CPU controls | Formatter, raw ranges, reverse mapping, repacking, captions, reply aging and receiver ABI checks pass; CPU image byte-exact with prior binary-switch package |
| Startup | Two independent 500-million-instruction DSP reset runs retain Plaits and author code, constants, selector and static voice state; repeat fingerprints exact |
| Packaging | Actual stock bootstrap depacker reproduces sections8/3/7 exactly; result reused from the identical candidate bytes produced in run01, with explicit provenance beside this package |
| Regression | 233 source tests, Ruff on changed/new implementation files, valid ready source-port bundle, and source-frozen SINE replay pass |

Final-ring RMS: OFF `0.103894582`, ON `0.103944457`, custom-muted `0.000000000`. These are routing observations, not a listening-quality score. The author oracle comparisons cover the full waveform separately. Rendered [ON](../out/runs/capicola-reddit-routing-20261017-04/on.wav), [OFF](../out/runs/capicola-reddit-routing-20261017-04/off.wav), and [causal mute](../out/runs/capicola-reddit-routing-20261017-04/muted.wav) fixtures are retained.

Exact reports and all input/test hashes: [verification JSON](CAPICOLA-REDDIT-VERIFICATION.json). Reports live in the four `capicola-reddit-*-20261017-04` runs and the SINE run `20261017T133546Z-test-8e09381c`.

## Memory and resource placement

| Region | Placement / size |
|---|---|
| Plaits code | L2 0x20080000, 35,808 bytes |
| Author hot code | L1 0x2d7570, 26,870 bytes; original scratch/tape footprint retained through0x2df000 |
| Author cold code | L2 0x200a0000, 33,234 bytes |
| Author voice state | L2 0x200e0000, 32,768 bytes |
| Author ring slots | Existing reserved sample-pool memory, 655,360 bytes |
| Plaits constants/stacks/state | Same existing reservation, 204,800 bytes |

Total compiled custom code is 95,912 bytes. The existing 8MiB sample-pool reservation remains; no extra CPU code or CPU reservation is added. Loader overlap guards normalize L1 aliases and reject all collisions. Startup retention and modeled playback do not establish physical runtime ownership, cache behavior or deadline margin.

## Reproduce

Use the Python configured by `.local/config.json` (the scripts re-exec it automatically):

```sh
python3 scripts/build-cpu-extension.py out/runs/<fresh-package> --all-features --capicola-reddit --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-reddit.py out/runs/<fresh-native> --package out/runs/<fresh-package>
python3 scripts/check-capicola-reddit-routing.py out/runs/<fresh-routing> --package out/runs/<fresh-package>
python3 scripts/check-capicola-toggle-cpu.py out/runs/<fresh-cpu> --package out/runs/<fresh-package>
python3 scripts/check-combined-firmware.py out/runs/<fresh-package> out/runs/<fresh-startup> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<fresh-package> --elekloader-reference out/references/elekloader-upload-audit
# Use configured Python3.12 for the source suite.
./labctl test sine --replay
```

The default `--all-features` selects this same backend and icon. Old recipes remain available through explicit `--capicola-source`, `--capicola-quality`, or `--capicola-legacy`, with `--capicola-switch` where required. Earlier binaries, supplied ZIP, prior audit and all failed/probe runs remain intact.

## Corrections and remaining gaps

The pinned emulator cannot decode Selache's compact integer ADD form, so generated assembly expands only standalone integer ADDs to semantically identical full-width instructions. All linked instruction extents and target/host PCM are checked. A direct-call fixture initially omitted the two-word ABI frame header; fixing the harness removed the apparent audio mismatch without changing the algorithm. An L1 startup comparison initially compared physical addresses against loader aliases; the check now uses the correct alias. The final mute fixture uses straight-line stores so it can be placed without unresolved absolute local branches. Earlier source-drift runs are retained and excluded from accepted evidence.

Physical hardware, cache ownership, real-time deadline margin and listening quality remain unverified. CPU startup/component GUI behavior is inherited from the exact prior MAIN image; this pass does not claim a newly coupled CPU/DSP device boot. Nothing was flashed, committed, pushed or published.
