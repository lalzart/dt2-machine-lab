# UP keyboard arp first experiment implementation gap register

> Status: active

The first emulator milestone passes. These gaps remain for later integration.

| ID | Gap | Severity | Owner/stage | Current decision | Proof required | Disposition |
|---|---|---|---|---|---|---|
| GAP-001 | Permanent code/state/stack placement and native clock owner | high | Firmware integration | Keep temporary emulator region/context calls | RAM/code reservation, caller ABI, scheduler/interrupt and worst-case work audit | open |
| GAP-002 | G menu OFF/UP selector and mode transitions | medium | UI integration | No G edit in first experiment | Guarded edit/draw routing; OFF parity and change-while-held checks | open |
| GAP-003 | Native transport state and changing tempo/rate | high | Sequencer integration | Fixed 102 BPM; observed PLAY/STOP button requests | Native state/tempo trace; internal/external clock, stop/restart and rate changes | open |
| GAP-004 | Generated-note recording and ordinary save/reload | medium | Recording integration | No arp recording/save claim | Live-recorded pitch/duration, playback bypass, quantization/overdub and project reload | open |
| GAP-005 | Saved arp settings and project compatibility | high | Persistence integration | Runtime only; do not serialize held keys/timers | Safe writer/reader, defaults, copy/clear/undo/reload and stock-project compatibility | open |
| GAP-006 | ORDER/RANDOM, HOLD, multiple tracks and MIDI input | medium | Later features | UP only, one track, no latch | Explicit ordering/seed/ownership contracts and independent acceptance cases | deferred |
| GAP-007 | Clean stock baseline and full OFF control parity | medium | Comparator expansion | Native OFF calls pass on prepared fixture | Separate stock cold boot and adapter-free complete control comparison | open |
| GAP-008 | Final output, real-time, hardware and listening | high | Device validation | Voice PCM only; no hardware action | Separate authorized device/timing/output checks and documented listening | deferred |
