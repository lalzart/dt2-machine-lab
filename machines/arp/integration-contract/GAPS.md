# Arp integration gap register

> Status: prototype with bounded integration gaps

## Closed within this prototype

EVIDENCE: native project slot 128 is saved and read afresh through original
APIs; separate restored firmware instances recover the exact full pattern and
mode companion. Companions authenticate the complete v5 project hash and slot.
Native file writing/readback works on private card overlays. Missing, corrupt,
mismatched and partial-write recovery cases have source tests. G drawing stays
inside its cell and stock E/F/H values change; G push has no arp assignment.

## Open gaps

- UNRESOLVED: normal GUI project-load slot association and automatic companion
  recall. Unknown GUI loads default OFF and retain suppressed release owners;
  that guard is tested with native core state and adapter events. Actual GUI
  save/load gestures remain separate from diagnostic native API validation.
- EVIDENCE: stock recording quantizes timing and very short gates. The seven
  ordinary captured gates replay at 3,552 samples; the shortened final gate
  plays back at 896 samples. Sample-exact performed-edge preservation is not
  proved or promised. Exact saved/reloaded duration bytes are proved.
- UNRESOLVED: diagnostic save/load requires released keys. Active-performance
  serialization, pattern copy/undo, project export/import/Transfer integration,
  companion cleanup, keyboard scale/root changes while held, and broader
  overlapping input generations need separate lifecycle evidence.
- DEFERRED: more tracks, MIDI input, tempo changes, latch, octave spans and an
  arp-specific G push action.
- DEFERRED: permanent firmware placement, on-device scheduler/interrupt safety,
  real-time timing, physical controls/audio, final mixer/DAC output, listening,
  packaging and release. Emulator memory is diagnostic, not a device layout.
