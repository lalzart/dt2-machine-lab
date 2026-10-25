# Author release STRETCH backend

Pinned source from the user-supplied `dt2-capicola-main (1).zip`, archive SHA256
`87bb2b073dae7253d7694198eced9a63ea4313373eb5ac1573902560cf19ad23`.
The ZIP contains no Git revision. All 66 original files are retained byte exact
under `upstream/`; `source-manifest.json` authenticates them at every build.

Source: https://github.com/hy3na-k1ng/dt2-capicola. License: GNU AGPL version 3
or later, as supplied in upstream/LICENSE. Preserve the author's and Heavylight
Industries / Matthew Nielsen's attribution. The original Capicola provenance
and scope are described in upstream/README.md and upstream/capicola_c99/capicola.c.
No source from proprietary firmware is included here. Original upstream scripts
are reference material; the lab does not invoke their install/flash workflow.

`lab/capicola_reddit.py` generates a separate build overlay, retaining the release
WSOLA flags, PCM interpolation, matching search, stereo and assembly paths.
Voice state moves to L2 0x200e0000; ring storage moves into our existing 8 MiB
reservation. Compact integer ADDs expand to equivalent full-width instructions
because our pinned emulator lacks their compact encoding. CAPI dispatch uses our
existing raw128..256 ON threshold; a separate status shim preserves the CPU reply
protocol. Only the stock STRETCH call is patched. Existing Plaits code is built
separately with its working state relocated into the same reservation as before.

`--all-features` now selects this backend and the binary switch by default.
`--capicola-source`, `--capicola-quality`, and `--capicola-legacy` retain prior
experiments explicitly. No dependency is upgraded. Approved scope and evidence
requirements are in contract/. Final outcomes, hashes, commands and any gaps live
in docs/CAPICOLA-REDDIT-RESULTS.md, outside the frozen implementation source set.
