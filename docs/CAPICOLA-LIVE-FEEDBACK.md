# Capicola automatic SRC feedback

2026-10-08 revision 1. Continue the authorized local Capicola integration with
an optional `capicola-live-feedback` family. Preserve the previous feedback,
selection, controls and licensed analysis/playback implementations.

The OS1.16 generic parameter page owns a native title widget at view+0x6c,
with string at widget+0x48. Its vtable is401ed888, shared by SRC and other
parameter pages. The SRC title starts CAPICOLA. Patch the six-byte draw call
40016ec8 to the widget state getter4005b076. Before tail-calling that getter
with the unchanged argument, compare the current title with the desired
static18-character title. Use the existing4005b1e0 setter only on changes;
it owns the string assignment and redraw notification. Restrict by the vtable
and full CAPICOLA prefix; preserve registers and the original getter result.
No analysis, UI call from audio ISR, new writable global, or framebuffer writes.
The earlier event-only seam4006cf38 is insufficient for updates while idle;
it is not patched in the final candidate.

Wire v2 reuses only the already audited reply halfword at0x1a. Bits15..14=2,
bits13..4=project slot0..1023, bits3..0=the existing ten caption indices.
Preparing is reported as honest quarter ranges instead of a numeric percentage.
CPU checks the tag, caption index and current track1 transmitted SAMP; a stale
reply for a different slot is neutral. Invalid slots and off emit zero. Playback
readiness remains governed by HANDOFF/epoch, never by this informational word.
Same-slot reload WAIT/preparing clears READY on receipt of the native status;
the existing transport delay remains. This protocol does not carry a generation
identifier and does not claim instantaneous same-slot reload correlation.

Keep the12-second mono bound and8MiB reservation. Exact original MAIN hash and
zero-padding guards are required. Guard native instruction forms and every
changed byte. Test automatic progress/READY/WAIT/neutral changes without page
gestures, real SAMP editing with a held old reply, malformed tags/indices and
all-slot decode bounds, no updates for other machines/pages, unchanged stable
title, repeated builds and older image hashes, native loading/cancellation and
audio tolerances, full reply parity, units, Ruff and SINE. UI snapshots are
buffered native replies through DSPI2/eDMA, not coupled or physical timing.
Defer full project save/reload/power-cycle and hardware performance validation.
