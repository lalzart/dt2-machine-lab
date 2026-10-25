# Native stock arp gap register

> Status: first package failed its user device trial; follow-up under validation.

2026-10-15: user reports no arp on T1/UP/held chord with stopped or running
sequencer. A deliberately stale private keyboard flag reproduces this failure
in the emulator. Follow-up sync reads the original OS setting; exact physical
cause remains unconfirmed. Existing emulator successes do not close this gap.

Closed: native heap-backed state and UI task clock; G four-mode control;
registered mode vectors; native file/journal parity and failure guards;
slot-0 buffer/destination binding; native record/save/normal-menu recall/replay;
protected stock sections, container identity and bounded startup checks.

Open: physical upload/boot/timing and coupled DAC output, automatic card-backed
power-on mode recall, broader held-key/storage/view transitions, new-project
reset/creation, pause/external transport, tempo following, more tracks/MIDI,
pattern copy/undo/export/Transfer, companion cleanup and production release.
The first build requires released keys and stopped transport for storage.
Runtime state is one 8 KiB boot-lifetime allocation; no extra DSP is introduced.
The full-project SHA work adds storage-time CPU work; physical duration is
unmeasured. GUI storage tests use an explicitly slower interrupt cadence and
restore the ordinary model for panel gestures and music. The 400M no-card
startup checkpoint preserves patches but has not entered arp initialization.

D1: the user reports re-entering keyboard mode still does not produce arp.
Installed candidate and ordinary OFF playback are awaiting clarification.
The optional diagnostic build is a means to observe the failing stage, not a
second asserted fix. C is latched tick progression, not a cadence measurement;
N counts note-on calls, not voice audio. Full physical behavior remains open.
