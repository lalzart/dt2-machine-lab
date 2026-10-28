# Start here

This is the primary checkout for Digitakt II **OS1.16 firmware features**.
The sibling `Digitect firmware research project` owns emulator work and original
research evidence. `.deps/` and `.local/` are dependencies/private inputs, not
places to edit feature code. No commit, flash, dependency update or publication
is implied by a normal task.

## Orient in a few minutes

1. Read [STATUS.md](STATUS.md) for what is implemented, the current package,
   validation evidence and open limits. It is the source of current status.
2. Choose the feature guide and source below. Read that guide before editing;
   use [README](../README.md) when setup or dependency context is needed.
3. Inspect `git status --short`, then search the relevant `lab/`, `scripts/` and
   `tests/` files. Existing dirty work may belong to the user or another task.
4. Run the smallest relevant check. Broaden only for a shared change, a failure,
   a remaining risk or an explicit integration/release check.

The latest local combination is managed Sketch + CAPI + ARP. **R8 is a separate
accepted experimental hardware checkpoint**, not a shorthand for all later work.
[STATUS](STATUS.md) owns package hashes and evidence; don't infer success from a
newer filename. Unsaved BUF audio/settings are volatile; project persistence is
excluded. [Capicola](CAPICOLA.md) identifies the current author engine.

## Find the work and its checks

| Task | Guide and first source files | Smallest suite |
| --- | --- | --- |
| Sample list, aliases or backing slots | [Feature map](FEATURES.md); `lab/buf_selector.py`, `buf_fixed_slots.py`, `buf_freeze_slots.py` | `./labctl unit buf-selector` |
| Controls, capture, stop, COPY/PASTE or LED | [R8 controls](SKETCH-BUF-CHECKPOINT.md); `lab/sketch.py`, `buf_next_bar.py`, `buf_startup.py`, `buf_stopped.py` | `./labctl unit buf-recording` |
| Buffer settings, assignment or loading | [Managed results](SKETCH-MANAGED-RESULTS.md), [popup](SKETCH-ASSIGN-POPUP.md); `lab/sketch_managed.py`, `sketch_assign.py`, `buf_loading.py` | `./labctl unit buf-managed` |
| Explicit audio export or preview | [Managed results](SKETCH-MANAGED-RESULTS.md); `lab/sketchbook_*.py` | `./labctl unit buf-save` |
| Placement, flags or profile construction | [Combined build](SKETCH-CAPICOLA-ARP.md); `lab/sketch_device.py`, `sketch_combined*.py`, `scripts/build-sketch-*.py` | `./labctl unit sketch-build`; add affected behavior suites |
| Author Capicola engine | [Capicola](CAPICOLA.md); `lab/capicola_reddit.py`, `machines/capicola-reddit/` | `./labctl unit capicola` |
| Keyboard ARP | [Combined controls](SKETCH-CAPICOLA-ARP.md); `lab/arp_*.py` | `./labctl unit arp` |
| Shared composition or tooling | [Testing](TESTING.md); `lab/cpu_extension.py`, `resources.py`, `unit.py` | `integration` or `core`, plus affected suites |

`./labctl unit` / `unit buf` runs the current BUF behavior and recorder checks.
`unit sketch-build` explicitly runs profile identity, placement and boot-stream
checks. They are useful when builders change, not after every label edit.
Unit suites are separate from OS build commands. Builds retain their own byte,
layout and repeat guards; long native/audio workflows are separate commands too.
See [TESTING.md](TESTING.md) for runtime requirements and full coverage.

## Reuse the evidence

Feature results link the relevant run or package. Its ignored local `manifest.json`,
`verification.json` and reports identify sources, firmware, inputs and actual
checks. Match that identity before relying on a result. If the artifact is
missing, state the evidence limit instead of silently treating it as a pass.
Keep a short note in the affected guide/STATUS when behavior or evidence changes;
avoid adding another parallel status document for routine edits.

[History](history/README.md), [status history](STATUS-HISTORY.md), old frozen
proposals and the sibling investigation tree are reference material. Search them
only for a specific missing fact. Their old controls, pending tasks and test
counts do not govern current work. [Cleanup notes](REPO-CLEANUP-2026-10-28.md)
explain retained dependencies and moved files.
