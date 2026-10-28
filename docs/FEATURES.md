# Feature boundaries

The latest local combination is [managed Sketch + Capicola R2 + ARP](SKETCH-CAPICOLA-ARP.md).
[Sketch/BUF R8](SKETCH-BUF-CHECKPOINT.md) remains the separate accepted experimental
hardware checkpoint. [STATUS.md](STATUS.md) distinguishes those evidence levels.

## Sketch and BUF

[BUF-WORKFLOW-CONTRACT.md](../BUF-WORKFLOW-CONTRACT.md) defines live buffer identity
and generation ownership. SONG opens Sketch; FUNC+SONG captures into its selected
BUF. Current managed builds remember recording settings per BUF, offer an
optional assignment popup, show loading state and attempt early slot setup.
Publishing a take updates its live BUF; choosing a track in the popup is separate.
FREEZE preserves a generation. Explicit Sketchbook export saves audio to +Drive.
Unsaved buffer audio and preferences are volatile; project persistence is excluded.

| Responsibility | Source entry points |
| --- | --- |
| Sketch controls and per-BUF preferences | `lab/sketch.py`, `lab/sketch_managed.py`, `lab/sketch_panel.py` |
| Assignment popup | `lab/sketch_assign.py` |
| H124–H127 aliases, loading and setup | `lab/buf_fixed_slots.py`, `lab/buf_selector.py`, `lab/buf_loading.py`, `lab/buf_startup.py` |
| Capture timing, stopped recording and cleanup | `lab/buf_next_bar.py`, `lab/buf_stopped.py`, `lab/buf_auto_retirement.py` |
| Generations, retirement and FREEZE | `lab/recorder_*`, `lab/buf_freeze.py` |
| Explicit audio export/readback | `lab/sketchbook_*`, `scripts/check-sketchbook-save.py` |
| Managed/combined builds | `scripts/build-sketch-managed.py`, `scripts/build-sketch-combined.py` |

Use [managed results](SKETCH-MANAGED-RESULTS.md) and
[assignment behavior](SKETCH-ASSIGN-POPUP.md) for current options. R8's control and
validation guide describes R8 specifically. Old one-bar/autoassignment prototypes
are historical. Automatic cleanup remains qualified for ONESHOT readers; the
combined STRETCH build does not broaden that qualification.

## Capicola and ARP

[Capicola](CAPICOLA.md) identifies the current author engine and the older
experiments. The current port specializes STRETCH and uses the native binary
CAPI switch. Shared address, reservation and callback helpers are still required.

The single keyboard ARP follows the selected track, including stopped transport.
Its CPU sources are `lab/arp_firmware.py`, `lab/arp_tempo.py` and associated ARP
modules. FUNC+KEYBOARD opens settings; G edits mode, and pushing G selects rate.
The combined builder chains ARP with Sketch's key, heartbeat and save/load hooks.
ARP's existing stored configuration is separate from volatile BUF settings.

## Preserved Flex, Plaits and earlier models

The older all-feature packager still supports Plaits and the existing Flex
save/bank workflow. They are not part of the Sketch/CAPI/ARP package. Flex and
BUF share recorder utilities but have distinct UI, adapters and validation.
A BUF result does not qualify a Flex package.

`lab/flex_buffer_core.py`, `lab/flex_quick_record.py`, `lab/flex_dsp_probe.py`,
`lab/recorder_gestures.py`, `lab/recorder_trigger_model.py` and
`lab/recorder_dsp_reuse.py` retain earlier buffer/scheduling/reuse models. Their
`flex_*` names do not make them the current native Flex or Sketch implementation.
Use `buf-models` explicitly for those tests.

## Test ownership

Start with `buf-selector`, `buf-recording`, `buf-save` or `buf-managed` for the
affected Sketch behavior. `buf` combines these and shared recorder support;
`sketch-build` adds explicit profile identity/placement checks when emitted code,
profiles or packaging change. Use `flex` for existing Flex and
shared recorder support, `capicola` for the current author port and its shared
helpers, and `capicola-history` for superseded engine experiments. `arp`,
`integration` and `core` cover their own areas. Combined selections deduplicate
shared tests. See [TESTING.md](TESTING.md) and `tests/suites.json`.
