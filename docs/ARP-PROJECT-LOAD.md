# Arp project recall and emulator optimization

Revision 1. User authorization: 2026-10-15 project load testing, final optimization and testing.

Retain the frozen ARP-INTEGRATION.md musical core, vectors, G behavior and track-one/102 BPM scope. This continuation changes only emulator project-lifecycle/storage adapters and tests. No dependency edits, hardware, commits or firmware packaging.

Bind normal project recall to the original OS1.16 cache loader's slot argument and returned project buffer, validate the node slot, then hash the complete current-format serialized bytes actually passed into Project::load. Consume the binding once. Apply the companion vector only after the original loader returns success; unknown identities, failed loads and missing/corrupt companions default to OFF. Panic closes the active gate and retains suppressed release ownership; recall never restores held notes or starts transport. Cache pointers alone are never project identities.

Optimize private byte/sector overlay synchronization by tracking changed sectors, preserving dict-compatible panel reads/writes and snapshot restore. Import changed guest sectors before a native transaction; publish only native sectors whose bytes changed afterwards. Removal must expose the original read-only image bytes. External replacement of the overlay must be rewrapped. No throttling of clock service or destination detection.

Acceptance: real project menu load gestures in the emulator restore saved UP, ORDER and RANDOM (with exact recorded pattern bytes), repeated cache hits work, unrelated loads and damaged companions default OFF; lifecycle tests retain release owners and reject mismatched buffers/slots. Optimized storage must match a full-copy reference for guest/native alternating writes, deletions and overlay replacement, with measured synchronization work reduced on no-op transactions. Full source tests, SINE replay, exact control/state/pattern parity against retained captures, native code audit and independent saved-project reloads pass. Native menu observations, offline voice PCM and physical hardware remain separate evidence.
