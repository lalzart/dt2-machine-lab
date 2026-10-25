# Capicola replacement recovered and rechecked

The earlier chat was interrupted by a possible-cybersecurity-risk error during
remote context compaction. Its R2 repair files survived. This run recovered,
rebuilt and independently rechecked that repair; no additional CPU or DSP source
edits were needed.

The user-supplied `dt2-capicola-main (1).zip` and all 66 retained upstream files
match exactly. The author engine is already the default CAPI backend for
`--all-features`, with the existing switch, Plaits R3, native Arp and managed Flex.
All 532 source fingerprints and 39 test fingerprints match the earlier accepted
repair record. Originals, failed builds and unrelated work were preserved.

## Rebuilt experimental OS 1.16

[R2 SYX](../out/runs/capicola-repair-recheck-20261017-01/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_OS1.16.syx)

SHA-256: `764329c1324d8f666b82c40b2d3e31f4724721044ef8e0f89b070e46e973ea59`

Size: 2,280,352 bytes. The fresh default build is byte-identical to the earlier R2.
Use R2 when referring to this repair; the original hardware-failed candidate
remains withdrawn.

## Confirmed repair and fresh checks

Executing the actual stock MAIN depacker reproduces a 265,885-byte staging
overflow with the failed build. R2 encodes zero-initialized regions as ADI FILL
blocks: 626,332 decoded bytes plus the command byte fit the 1 MiB allocation,
leaving 422,243 bytes. The boundary canary stays intact. Loaded memory is exact
across 40,690,304 bytes in 109 regions; CPU MAIN and entry points are unchanged.
The build guard rejects the old oversized stream.

Fresh verification passed:

- 235 source tests and pinned dependency/fixture doctor.
- 14 upstream host goldens and nine native engine cases with bit-exact PCM.
- 16 stereo tracks / 32 lanes, stock OFF and all six Plaits models exact;
  modeled final-ring output and causal custom-mute control.
- CPU switch/control/transport checks.
- Two independent 500-million-instruction DSP resets with exact repetition.
- Actual bootstrap decompression, protected-section checks and repeated build.

[Machine-readable recheck record](../out/runs/capicola-repair-recheck-20261017-01/recheck-verification.json)
contains report paths and hashes. The previous SINE replay report was
hash-authenticated against the unchanged sources; SINE was not rerun here.

## Reproduce

From the lab root, choose fresh output directories:

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/<fresh-package> --all-features --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-dsp-boot-staging.py out/runs/<fresh-staging> --package out/runs/<fresh-package> --failed-package out/runs/capicola-reddit-package-20261017-04
python3 scripts/check-capicola-reddit.py out/runs/<fresh-native> --package out/runs/<fresh-package>
python3 scripts/check-capicola-reddit-routing.py out/runs/<fresh-routing> --package out/runs/<fresh-package>
python3 scripts/check-capicola-toggle-cpu.py out/runs/<fresh-cpu> --package out/runs/<fresh-package>
python3 scripts/check-combined-firmware.py out/runs/<fresh-package> out/runs/<fresh-reset> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<fresh-package> --elekloader-reference out/references/elekloader-upload-audit
```

Build/check scripts select the configured Python 3.12 runtime automatically.
For source tests, use that runtime with `-B -m unittest discover -s tests -q`.

## Remaining evidence limits

The overflow is demonstrated; the exact photographed hardware exception and
any persistent project damage were not reproduced or repaired on a device.
The reset test exercises the DSP separately and skips CPU startup for the native
extension. The previous full-container CPU-model probe stopped on an ambiguous
main-loop signature. There is no full coupled CPU/DSP startup result.
Physical startup, existing device projects, timing and listening remain
unverified. No hardware upload, commit, push or publication occurred.
