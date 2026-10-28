# Sketch/BUF experimental package — OS 1.16

User authorization, 2026-10-23: prepare a local Sketch-only experimental firmware
and validate its exact package bytes. For a future combined OS, BUF/Sketch
replaces the previous Flex implementation. Preserve the old feature profiles
as reference; do not stack the two recorder implementations. No hardware
transfer, flash, commit or publication is part of this task.

## Build and validation

The delivery folder is
[`out/runs/sketch-experimental-20261023-01/package/`](../../../out/runs/sketch-experimental-20261023-01/package/README.md).
Its manifest records `local-experimental-package-validated`. The
standalone profile starts from exact Digitakt II OS 1.16; it does not include
Arp, Plaits, Capicola, the previous Flex implementation or DigiKit's OS1.17 runtime.
Firmware and dependency sources remain unchanged.

Package: `EXPERIMENTAL_SKETCH_BUF_OS1.16.syx`, 2,235,040 bytes.
SHA-256: `c1d7c3bf2119537c23b4b74e4ba6f09b81a8ed835d2d79d9e42bda85378d47b3`.

| Result | Exact evidence |
| --- | --- |
| Reproducible current MAIN/DSP; identical to validated recorder package | [Build](../../../out/runs/sketch-candidate-build-20261023-02/manifest.json) |
| Container/seal/checksums, protected sections and depack/staging bounds pass; native sender transmits 339,073 exact bytes plus terminal, with both busy holds | [Upload](../../../out/runs/sketch-candidate-upload-20261023-03/report.json) |
| Full-container CPU application reset and independent DSP application startup pass; Sketch renders, CPU code/canaries intact, 1,620 LP0 units, 6,878 DSP frames, zero missing blocks | [Startup](../../../out/runs/sketch-candidate-startup-20261023-02/report.json) |
| Wrong-container and stale-source evidence are refused without creating a delivery folder | [Two controls](../../../out/runs/sketch-experimental-20261023-01/negative-controls.json) |
| Exact delivered bytes, sources, proofs and remaining limits | [Package manifest](../../../out/runs/sketch-experimental-20261023-01/package/manifest.json) |

Scoped BUF/core/integration units: 238 pass. Focused Ruff and format checks pass.
The last startup-launcher correction resolves the upload path and clarifies
report wording; firmware and unit-tested modules remain exact. Reuse the prior
same-firmware SINE and stock-output evidence; no DSP/adapter behavior changes
justify repeating those audio experiments.

The MAIN in-place depack minimum gap is 2,111,963 bytes. DSP staging has 709,503
bytes of output headroom after its command byte. Container flash end is
`0x22e8d0`, below the guarded `0x380000` ceiling. These are local bounds, not a
physical memory or flash-ownership proof.

The fresh MAIN and DSP images match the already validated native recorder
package byte-for-byte. Reuse its A -> FREEZE A -> B -> active cancellation flow,
four retained reader lanes, shared selectors, stock-file PCM oracle and saved
voice/master/DAC-ring/reply comparisons. Packaging runs no new recordings.
The earlier outer flow report retains its original comparator failure; its
passing standalone flow and corrected saved replay are authenticated by the
[connection evidence index](../../../out/runs/native-buf-connect-20261023-01/verification.json).

`check-sketch-boot-upload.py` now accepts a reproducible current CPU build,
rather than requiring equality to the historical CPU from the DSP-format fix.
It additionally checks all 820 bytes of the stock upload routine. Historical
DSP loaded-byte/FILL equivalence, malformed-stream refusal, independent Python
and Rust checks, package integrity and native sender/backpressure checks remain.

`check-native-sketch.py` accepts a matching build/upload pair and a startup-only
mode. It constructs the complete candidate through the authenticated-reference
adapter and executes CPU application reset with native DSP coupling. The DSP
starts independently at its loader application entry. This does not execute
the physical bootstrap, DSP ROM or physical SPI receiver.

`package-sketch-experimental.py` refuses unsuccessful, mismatched or drifted
build/upload/startup evidence. It authenticates the prior recorder artifacts,
requires identical MAIN/DSP/container bytes, rechecks the container and DSP
stream, then delivers a copy with hashes and limitations. Only the two validator
scripts and this packager may differ from the recorder proof's source inventory.

## Reproduction

Use fresh ignored directories for each command:

```sh
./labctl doctor
python3 scripts/build-sketch-device.py out/runs/YOUR-BUILD
python3 scripts/check-sketch-boot-upload.py out/runs/YOUR-BUILD out/runs/YOUR-UPLOAD \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
python3 scripts/check-native-sketch.py out/runs/YOUR-STARTUP \
  --build out/runs/YOUR-BUILD --upload-proof out/runs/YOUR-UPLOAD --boot-only \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
python3 scripts/package-sketch-experimental.py \
  out/runs/YOUR-BUILD out/runs/YOUR-UPLOAD out/runs/YOUR-STARTUP out/runs/YOUR-PACKAGE \
  --workflow-proof out/runs/native-buf-connect-20261023-01/verification.json
```

The launchers select configured Python 3.12 and leave pinned dependencies and
the clean native-upstream checkout unchanged. The packager deliberately refuses
a future firmware change until matching recorder evidence is supplied.

Preserved development attempts: a planning-note edit to the hash-pinned BUF
contract was refused and restored byte-exact; the future Flex decision is kept
in the README and this note. The first startup-only launcher attempt failed on
a relative upload path before CPU execution; its absolute-path correction is
included in the final source freeze. Earlier runs and logs remain intact in
the [development notes](../../../out/runs/sketch-experimental-20261023-01/development-notes.json).

## Remaining device limits

Physical DSP ROM/SPI ready and short-tail acceptance, RAM/cache/DMA/stack
ownership, recorder hardware and normalization, real-time timing and listening
remain unverified. The newer native capture flow qualifies stereo LEN16;
LEN32/64 have separate older-runtime evidence, and mono remains unqualified.
The normal 16-step clock, ten-second cap and conservative retirement guards
remain. Publication can arrive after the following bar's first trigger.
ONESHOT is the proven playback path. BUF/FREEZE persistence and +Drive saving
remain separate work.

Keep the known-good stock image and backups available for a separately
authorized hardware trial. A passing local package does not establish device
recovery or general hardware safety.
