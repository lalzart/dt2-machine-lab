# Current Capicola port

The active OS1.16 engine is the author release-default STRETCH port in
[`machines/capicola-reddit/upstream`](../machines/capicola-reddit/upstream/README.md),
built by `lab/capicola_reddit.py`. The `reddit` name identifies the original
intake; it is not a different engine. All 66 files match the user's
`dt2-capicola-main` snapshot. The source manifest and original license remain
unchanged. No upstream update is implied by this cleanup.

On STRETCH → SRC, encoder C is the binary CAPI switch: OFF uses stock STRETCH;
ON uses the author engine. This integration does not include the standalone
repo's REPITCH, SLICE/GRID modes, extended BARS or full UI2 changes.

## Builds to use

- [Sketch + Capicola + ARP](SKETCH-CAPICOLA-ARP.md): current managed BUF,
  assignment popup, early/loading behavior and selected-track ARP. Use
  `python3 -B scripts/build-sketch-combined.py out/runs/<fresh-name>`.
  Unsaved BUF audio and settings remain volatile; no project persistence.
- [Earlier all-feature R2](CAPICOLA-REDDIT-BOOT-FIX-RESULTS.md): includes
  Plaits and legacy Flex. `scripts/build-cpu-extension.py --all-features`
  packages the same author engine and switch by default.

The latest delivered Sketch combination is the **2026-10-27 switch correction**:
`out/runs/sketch-capi-arp-switchfix-package-20261027-01/`, SYX SHA-256
`8880c38aac968f24dc742cbb5e9ed398223214d465d127fba7f804ac5d5b5e8a`.
The preceding combined package omitted the switch drawing patch. The correction
changes two CPU bytes; the DSP is identical. See [status](STATUS.md) for evidence
and hardware limits. Neither this guide nor cleanup promotes a new checkpoint.

## Shared code that is still needed

| Source | Use in the current port |
| --- | --- |
| `lab/capicola_reddit.py` | Authenticated author source, generated overlay and compilation. |
| `lab/capicola_layout.py`, `lab/capicola_memory.py` | Shared addresses and 8 MiB sample-pool reservation. |
| `lab/capicola_automatic.py` | Register-preserving SHARC wrapper reused by the current status hook. |
| `lab/capicola_toggle.py`, `lab/capicola_ui.py` | CAPI parameter, formatting, feedback and stock binary-switch callback. |
| `lab/all_features_base.py` | Authenticated CPU base; Sketch extracts only its CAPI payload. |
| `lab/sketch_combined*.py` | Composition with Sketch and ARP. |

## Superseded experiments

`machines/capicola/`, `lab/capicola_quality.py`, `lab/capicola_source.py` and
related preparation/cache probes implement earlier analyzed-keyframe and
source-playback experiments. They are not the author engine above. Their old
R1/R2/R3 labels are separate from the author port's R2 packaging repair.

The OS packager no longer accepts `--capicola-legacy`, `--capicola-quality` or
`--capicola-source`. Historical commands using those switches describe old
artifacts, not current build recipes. Low-level `labctl ... capicola` mod/replay
commands and the standalone old check scripts remain research fixtures.

Run `./labctl unit capicola` for the current author port and shared integration.
Use `./labctl unit capicola-history` explicitly for the older engine experiments;
`all` still includes every test. [Archived reports](history/README.md) retain
prior results. Frozen proposal documents stay at their original paths because
historical checks authenticate their exact contents; they do not define current
product behavior. See [cleanup notes](REPO-CLEANUP-2026-10-28.md).
