# Feature boundaries

Use **BUF** for the performance-buffer experiment and **Flex** for the existing
recording/save feature. They share recorder utilities, but have separate native
adapters, state and validation. A BUF result does not qualify a Flex package.

## BUF

Read [BUF-WORKFLOW-CONTRACT.md](../BUF-WORKFLOW-CONTRACT.md) for the intended
behavior and [the alignment note](BUF-WORKFLOW-ALIGNMENT.md) for current corrections.
The [continuous recording results](BUF-CONTINUOUS.md) record the later bounded
playing session, physical memory reuse, frozen playback and remaining gaps.
Earlier autoassignment and initialized-buffer requirements are prototype
limitations, not the product contract.

The native flow arms with SAMPLING+YES or opt-in Sketch FUNC+SONG, starts at the
next native first-step edge, records the selected one/two/four bars, waits for
stock normalization/loading and automatically publishes the take. Sketch held
SONG freezes its remembered BUF; SAMPLING plus encoder C push retains the older
selected-track FREEZE frontend. The manual record/trim/USE flow remains available.

The current adapter is an OS 1.16 emulator experiment with empty-buffer setup,
publication without assignment and normal 16-step/R.LEN-16/32/64 capture, bounded
by the existing ten-second limit. See [native durations](BUF-MULTIBAR.md). ONESHOT
readers are initially validated; unrelated machines do not gate recording.
Native saving, broader DSP/retirement compatibility and device placement remain
open. [Alignment results](BUF-WORKFLOW-ALIGNMENT.md) describe the current layer;
[earlier results](BUF-NEXT-BAR-RESULTS.md) retain the previous prototype.

| Responsibility | Source entry points |
| --- | --- |
| Next-bar capture and automatic publication | `lab/buf_next_bar.py`, `lab/buf_next_bar_ui.py` |
| Sketch selection, gestures and explicit-BUF FREEZE | `lab/sketch.py`, `lab/sketch_ui.py`, `lab/buf_freeze.py` |
| Selected-track FREEZE during playback | `lab/buf_performance.py`, `lab/buf_performance_ui.py` |
| Automatic obsolete-generation cleanup | `lab/buf_auto_retirement.py`, `lab/buf_auto_retirement_ui.py` |
| Native capture/publication and FREEZE workers | `lab/recorder_worker_*`, `lab/recorder_freeze_*` |
| Generation seats, native retirement and acknowledgements | `lab/recorder_seat_*`, `lab/recorder_native_retirement*`, `lab/recorder_ack*` |
| Reproduce Sketch duration/FREEZE validation | `scripts/check-sketch-dsp.py --lengths 32 64 --cancel-capture` |
| Earlier next-bar/continuous flow | `scripts/check-buf-next-bar.py`, `machines/buf-next-bar/contract.json` |
| Routine unit coverage | `./labctl unit buf` |

## Flex

Flex is the existing RAM-take recording, playback and persistence workflow. R5
saving uses the stock filename editor followed by the A-H RAM-bank chooser and
slot preview. Its Save/Discard and project-reference handling are independent
of the new BUF flow. [Flex R5 results](FLEX-BANK-SAVE-RESULTS.md) identify the
package and its validation boundaries.

| Responsibility | Source entry points |
| --- | --- |
| Native integration and build | `lab/flex_native.py`, `lab/flex_native_build.py` |
| Source memory and references | `lab/flex_memory.py`, `lab/flex_resources.py`, `lab/flex_retirement.py` |
| Save/Discard page and RAM banks | `lab/flex_save_screen.py`, `lab/flex_native_save.py`, `lab/flex_discard.py`, `lab/flex_bank.py` |
| Routine unit coverage | `./labctl unit flex` |

Existing all-feature builders contain Flex. They do not install the separate
BUF emulator adapter. No module move or rename is needed to combine test groups;
native hooks, emitted code and package builders retain their existing paths.

## Shared recorder support and earlier BUF models

`lab/flex_recorder.py` (input/takes), `lab/flex_heap.py`, `lab/pattern_clock.py`
and `lab/recorder_overlay.py` provide recorder/emulator support. Their tests form
the `recorder` group, included once when either BUF or Flex is selected.

Some early BUF files predate the name separation:

| Historical name | Actual role |
| --- | --- |
| `lab/flex_buffer_core.py` | Host model of buffer generations and roots |
| `lab/flex_quick_record.py` | Host scheduling model; does not supply the current native bar edge |
| `lab/flex_dsp_probe.py` | Restricted DSP allocation/reuse probe |
| `lab/recorder_gestures.py`, `lab/recorder_trigger_model.py` | Earlier modeled gesture/trigger policy |
| `lab/recorder_dsp_reuse.py` | Earlier reuse proof requiring a restricted pause certificate |

These belong to `./labctl unit buf-models`, despite the legacy `flex_*` names.
They remain available when working on those models. They are separate from both
the native BUF default checks and the Flex save/bank suite. Existing paths stay
valid for saved reports and experiment drivers.

Capicola, Arp, cross-feature integration and shared tooling have their own groups
in [the testing guide](TESTING.md). Earlier milestone summaries are preserved in
[experiment history](EXPERIMENT-HISTORY.md).

## Sketch UI

The [opt-in native Sketch prototype](SKETCH-UI.md) owns navigation and one
volatile BUF selection. Recorder settings remain shared; ARM/FREEZE shortcuts
are dry actions by default. Optional [ARM](SKETCH-ARM.md) and
[FREEZE](SKETCH-FREEZE.md) profiles connect those gestures to the native BUF
services. Existing BUF backend and Flex remain separate.
