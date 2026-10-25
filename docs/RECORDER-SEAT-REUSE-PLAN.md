# Bounded generation-seat experiment

Authorized by “Proceed” after the DSP reuse results, 2026-10-22. Working artifact:
`scripts/check-recorder-seat-reuse.py`, native OS 1.16 CPU worker plus stock
SHARC ONESHOT under the previous stopped, exclusive emulator harness.

Keep eight physical registry/private seats. Issue unique tokens in experimental
namespace `0x7ffb0001..0x7ffbffff`, distinct from legacy Flex, BUF logical IDs and
FREEZE. Refuse token exhaustion without wrap. Native lookup searches eight
seats by immutable token and epoch; native registration uses a vacant seat,
not token arithmetic. Native stock unload still requires the previous modeled
exclusive certificate and actual native DSP diagnostic. A seat becomes vacant
only after the final owner has been unloaded. Native unlink/free removes dead
64-byte source descriptors, retaining live/frozen nodes. No PCM source stays
allocated after USE.

Run 100 native record/trim/USE transactions, keep one native FREEZE snapshot,
reclaim obsolete generations and prove stable BUF selection, bounded metadata,
allocator reuse and exact stock PCM at milestones. Repeat exactly. Focused
controls: eight occupied seats, stale token after seat/address reuse, active and
pending readers, frozen root, missing exclusive certificate, stale project,
allocation/publication failure and token exhaustion. Failed candidates may be
quarantined; never claim successful publication or recycle their token.

Normal builders, pinned runtimes, previous default payloads and hardware stay
unchanged. Use isolated CPU overlays and an isolated diagnostic build accepting
the new namespace; do not expand its scans or grant DSP retirement permission.
Capture, transport and exclusive-pause ownership remain modeled; no SAVE,
general live retirement fence, real-time or physical-device claim. Gain/sample
processing is stock and exact byte comparisons are the oracle. Record failed
runs; run unit suite and SINE at the stable milestone. Native state starts empty;
refusal preserves ownership, reset needs a new session, project changes refuse,
and frozen seats never become vacant through ordinary recording replacement.
