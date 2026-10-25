# CAPI R2 — stock DSP boot-buffer overflow repaired

The initial author CAPI package is withdrawn after the reported hardware exception. R2 fixes a confirmed stock-loader buffer overflow while preserving the entire loaded DSP image and CPU image.

[R2 experimental OS1.16](../out/runs/capicola-reddit-r2-package-20261017-03/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_OS1.16.syx) — includes the author CAPI engine, Plaits R3, native Arp, managed Flex and the binary switch.

SYX SHA256: `764329c1324d8f666b82c40b2d3e31f4724721044ef8e0f89b070e46e973ea59`. File size: 2,280,352 bytes.

## Confirmed cause in the build

EVIDENCE: stock CPU MAIN allocates two 1MiB staging buffers at0x400cd174 and0x400cd19e. It places command3 in output byte0, then executes its own depacker at0x4013815c into output+1. Its output-size check at0x400cd20c happens after decompression.

The failed DSP image was 1,314,460 bytes. Running the actual MAIN routine on that exact candidate writes **265,885 bytes beyond the allocation**, destroying the boundary canary. The previous bootstrap-depacker test used a larger scratch buffer and a different routine. The previous CPU boot test loaded stock section7 while replacing MAIN; neither check exercised this size limit.

INFERENCE: heap corruption from this overflow plausibly explains the photographed invalid virtual callback during project handling. The photo appears to show PC0xa100a100, return0x401a1f72, object0x44fb8d34 and caller0x400447b0. We have not captured the complete physical crash state, so this is not a claim that the exact hardware exception was replayed.

## Repair

All-zero appended author ring and voice regions now use standard ADI FILL blocks, which stock firmware already uses for large zero-initialized regions. The boot stream becomes **626,332 bytes**, leaving **422,243 bytes** of staging headroom after command3. FILL changes the representation of zero memory, not its allocation or contents.

The old and new loader images produce **40,690,304 identical loaded bytes across109 regions**, including all code, constants, rings, voice state and boot entry points. MAIN remains exactly `574ba37b677c62a8cba8885652aa0ca25f4d3b7b93394e977739bb7c0e04e4cc`. The author renderer, matching search, timing, stereo paths, Plaits, Arp, Flex and UI controls retain their behavior.

`lab.upload.verify_candidate` now authenticates the actual stock allocation/check instructions and rejects packed DSP input above1MiB or decoded DSP output plus command above1MiB. A regression test rejects the original hardware-failed build and checks the one-byte boundary. This gate applies to every candidate containing section7.

## Accepted verification

| Check | Result |
|---|---|
| Actual MAIN depacker, failed candidate | Exact decoded bytes; allocation crossed; canary overwritten; 265,885-byte overflow detected |
| Actual MAIN depacker, R2 | Exact decoded bytes; no write outside allocation; canary intact |
| Final loader memory and CPU | Old/new loaded memory and entry points exact; MAIN byte-exact |
| Author host and native oracle | 14 host goldens;9native cases;271,680 reference samples bit-exact |
| Full native DSP routing |16stereo tracks/32voices; stock OFF exact; all six Plaits models exact; final-ring custom mute silent |
| DSP reset | Two independent500M-instruction resets retain all linked code/state and repeat exactly |
| CPU controls | Existing formatter/range/reverse/repacking/caption/status/ABI checks pass |
| Bootstrap/package | Sections8/3/7 actually decode exactly; protected sections unchanged; full package repeats exactly |
| Regression |235source tests, source-frozen SINE replay, Ruff and ready repair contract pass |

Exact reports, source/test hashes, candidate identity and canary evidence: [verification JSON](CAPICOLA-REDDIT-BOOT-FIX-VERIFICATION.json). The supplied photo is retained in the ignored hardware-crash run; original binaries and failed/probe runs remain intact. An additional whole-patched-container CPU-model probe refused startup because its upstream main-loop signature lookup is ambiguous with the existing extension; no full coupled startup claim is made from that probe.

## Reproduce

From dt2-machine-lab with the configured Python3.12 runtime:

```sh
python3 scripts/build-cpu-extension.py out/runs/<fresh-package> --all-features --capicola-reddit --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-dsp-boot-staging.py out/runs/<fresh-staging> --package out/runs/<fresh-package> --failed-package out/runs/capicola-reddit-package-20261017-04
python3 scripts/check-capicola-reddit.py out/runs/<fresh-native> --package out/runs/<fresh-package>
python3 scripts/check-capicola-reddit-routing.py out/runs/<fresh-routing> --package out/runs/<fresh-package>
python3 scripts/check-combined-firmware.py out/runs/<fresh-package> out/runs/<fresh-reset> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<fresh-package> --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

Build scripts re-exec configured Python automatically. The source suite runs with that same runtime via `-m unittest discover -s tests -q`. Do not treat an oversized decoded image as safe just because its compressed stream fits flash or a standalone DSP emulator boots it.

R2 is locally validated. Physical-device startup, the user's existing project state, real-time timing/cache behavior and listening remain separate confirmation. No firmware was sent to hardware, committed, pushed or published by this repair.
