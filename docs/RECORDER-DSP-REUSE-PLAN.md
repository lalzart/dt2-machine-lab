# Restricted DSP reuse experiment

Authorized by the user's four-task attachment, 2026-10-22. This short plan
supersedes the previous requirement to finish a general retirement framework
before trying one controlled release.

Working artifact: `scripts/check-recorder-dsp-reuse.py`, OS 1.16 native CPU
unload and stock SHARC ONESHOT replay. New code is emulator-only scratch;
normal builders, dependencies, identity limits and hardware remain untouched.

Experiment: native recorder creates A then B in BUF 1. A native ColdFire
command checks the existing registry, snapshot roots, CPU cache aliases and
the actual native DSP diagnostic result. In an explicitly paused, stopped,
closed-world test it tombstones A, removes its project/private owner, and calls
stock unload. C must occupy the returned free extent with a new issued ID and
different exact PCM. Repeat within the existing eight-ID limit.

The test harness models the exclusive CPU/DSP pause and delivery of the DSP
diagnostic result to a CPU mailbox. This is an experimental ownership
certificate, **not** a native sequencer/transport retirement fence. Missing
certificate, active/retained reader, frozen root, pending selection, unexpected
alias, stale tuple or unknown descriptor refuses before mutation. The previous
DSP diagnostic always grants zero retirement permission; it stays unchanged.

Acceptance: allocator record removal/free-gap increase, native unload trace,
new allocation consuming that gap, exact stock-file ONESHOT output, stale-ref
rejection, no mutation on refusal, repeated bounded PCM reuse and unchanged
eight-issued-ID admission. CPU source memory is measured separately. Retain
failed runs. Exact repeat, full unit suite and SINE at the stable milestone.
No broad new observer, UI work, firmware package or identity recycling.

State: initialization has no certificate; valid proof is consumed once; refusal
leaves generation live; success leaves an irreversible tombstone and reserved
empty private slot. Frozen/current generations remain live. Project/kit changes
invalidate the command. Reset/reconnect requires a fresh experiment. SAVE and
general project ownership remain unresolved. Playback oracles use exact bytes,
not tolerance changes. Source baseline: branch `codex/plaits-macro-controls`,
HEAD `77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, inherited dirty work preserved.
