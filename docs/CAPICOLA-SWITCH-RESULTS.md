# CAPI binary switch graphic — OS1.16

CAPI now reuses the stock AMP RSET OFF/ON switch in place of the Crossfade
encoder dial. The local all-feature source-playback package contains the change:

`out/runs/capicola-switch-package-20261017-02/EXPERIMENTAL_ALL_FEATURES_CAPI_SOURCE_SWITCH_OS1.16.syx`

SYX SHA256: `2e357e49f485fd27f76b8a1ca110201cfa4135f02aac3bb51a5815cb6ae28bb1`
MAIN SHA256: `574ba37b677c62a8cba8885652aa0ca25f4d3b7b93394e977739bb7c0e04e4cc`
DSP SHA256: `5c48264d391070718b1f1120fc170cb9d3aafd997824d77c30bfab3ff5319945`

Only MAIN bytes `0x401C267E` and `0x401C267F` differ from the preceding
source-playback package. They select the existing stock switch callback template
in the native UI initializer for parameter 204. No new drawing code, image assets
or runtime allocations are added; DSP bytes are identical. Parameter values,
encoder handling, OFF/ON formatting and audio routing are untouched.

The prepared UI fixture replaces only the callback's manager/invoker, retaining
its own stateless one-byte function allocation. It never aliases another
callback's heap pointer. A bounded execution of the actual patched native
initializer also clones the stock switch template and selects the expected
renderer. This is initializer evidence, not a complete cold-start claim.

Native UI evidence: `out/runs/capicola-switch-ui-20261017-02/manifest.json` and
`capi-switch-off.png`, `capi-switch-on.png`, `capi-switch-off-again.png` in that
directory. OFF→ON→OFF through encoder C preserves stored/wire values 0→256→0,
executes the stock switch renderer at each value, and produces no CPU faults.
Both switch positions were visually checked. All 230 source tests, focused Ruff
and whitespace checks pass. Build and container reconstruction repeat exactly.
The actual OS1.16 bootstrap depacker reproduces sections 8, 3 and 7 exactly;
`device-depacker.json` and `ui-verification.json` in the package bind the final
candidate and source identity to these checks.

Reproduce using a fresh ignored directory and the configured Python 3.12 runtime:

```sh
python3 scripts/build-cpu-extension.py out/runs/<package> --all-features --capicola-source --capicola-switch --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<package> --elekloader-reference out/references/elekloader-upload-audit
```

The switch option is explicit so older package recipes remain reproducible.
Plaits, source Capicola, Arp and managed Flex are retained. No firmware was sent
to hardware, committed, pushed or published. Physical-device UI remains untested.
