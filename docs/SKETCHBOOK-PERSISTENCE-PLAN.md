# Sketchbook explicit sample saving

Digitakt II OS1.16, Sketch/BUF R10 continuation, 2026-10-25. The user approved
continuing the +Drive persistence implementation after the readback explanation.
This authorizes local implementation and validation through the stated slice,
without another proposal pause; no hardware transfer, commit or publication.

## Selected architecture and source lane

Source reimplementation: reuse this repository's owned Flex native file writer,
filename UI and earlier DSP-to-file reconstruction oracle. Preserve the current
DSP-only BUF/FREEZE playback and immutable generations. Replace the host-peek
surrogate with emitted CPU/SHARC instructions and the original peripheral paths.
The first working artifact is `scripts/check-sketchbook-save.py`, at native
target-instruction, modeled-peripheral, exact saved/reloaded PCM evidence level.

EVIDENCE: OS1.16 DSPI2 driver 0x400cd2bc clamps frame length to 0xbc0 bytes;
current audio frames use 0xabc. Its native RX staging is 0xbc0 bytes. The four
DSP DMA rings are 0x1000 bytes apart. Existing stock content occupies the first
0xabc bytes. The three small padding/status bytes are unsuitable for bulk audio.

SELECTED: an opt-in 0xbc0 frame adds a 260-byte tail. Preserve all first-0xabc
bytes, the existing CPU legacy destination and the original driver's RX/TX
staging addresses/limits. A wrapper receives the larger frame in a separate
3008-byte buffer and copies only the original 2748 bytes to the stock consumer.
DSP initialization uses the same larger size. Normal builds remain byte-exact.
Do not borrow live audio, meter, stock flag or Capicola status bytes.

One LP0 request binds epoch, immutable token, serial, private slot, expected DSP
header, PCM byte position and bounded byte count. The DSP validates the exact
resident header and range. Each audio block emits at most 224 PCM bytes with a
36-byte versioned envelope. Native CPU reception checks identity, ordered offset,
length, status and FNV-1a checksum before accepting bytes. Duplicate packets do
not advance progress. Missing/reordered/corrupt/stale packets cannot complete.
Requests and responses never contain a CPU-dereferenceable DSP pointer.
Before releasing the mutation lease, send a monotonically sequenced CLOSE and
require its matching checksummed acknowledgement. The DSP acknowledges only
after revoking its readback source. A lost close acknowledgement keeps the lease
held; it cannot authorize retirement of a potentially active reader.

Save holds the existing mutation exclusion and refuses active recording,
publication, retirement and project transitions. Playback is unchanged. Retain
80 native-file header/trailer bytes per generation before freeing its temporary
CPU source, not a full PCM copy. Save reads reconstruct original interleaved
big-endian PCM16 from immutable DSP planar channels and combine that with the
retained file metadata. Reuse the stock exclusive file writer, hash/length
verification and independent stock reload. Failure preserves all accepted takes.

All explicit exports target `/Sketchbook/<name>`. Create or validate that exact
directory; fail visibly when unavailable. Never fall back to `/recorded` and
never overwrite an existing file. Export does not replace live BUF or frozen H
associations, consume a FREEZE identity, recycle a token or enable project saves.
Automatic project restoration remains separate from individual named export.

Explicit audition additionally reconstructs one temporary native file in the
original CPU heap (at most 1,920,080 bytes). The stock preview reader owns this
snapshot until its original close, including asynchronous reads. Only that
reader can open/read it; a second preview refuses while it is owned. Download
uses the same generation lease/readback/CLOSE fence. Saving never uses this
full-file allocation. No disk file is created by audition. The frontend uses
verified unused holes in the existing retirement arena, with overlap checks.

## Exact state and control contract

- Init/reset: empty request, no save lease, no accepted tail and no saved marker.
- Metadata capture: preserve the exact header/trailer and token before CPU free.
- Begin: validate READY generation, project/kit/epoch, loader key and private pin;
  claim save exclusion once. Empty, unknown or busy refuses without a file write.
- Read: one serial at a time, 1..4096 bytes, nonwrapping serial; pin the generation
  until completion or failure. No allocation, filesystem access or waiting in DSP
  block processing. No GUI action changes the latched generation.
- Reply: packet magic is published last after all bytes/checksum and a request
  revision check. Native receiver accepts only the current exact envelope.
- Complete: verified file and reference; source/freeze/track associations intact.
- Failure/cancel/timeout: close/remove only the newly created destination,
  release save exclusion, retain the original take and all prior files.
- Freeze/capture/retirement/project changes during the lease: refuse; do not
  silently redirect the save. STOP/Panic and existing synthesis stay stock.
- UI mapping after backend proof: FUNC+SAMPLING > SKETCHBOOK, four EMPTY/READY
  BUF rows followed by ready frozen takes, selection, audition and named Save.
  Audition needs its own valid reader/lifetime check. No new machine or MIDI map.

PCM equations: for interleaved byte i, frame=floor(i/(2*channels)), channel is
floor(i/2) mod channels, byte is i mod 2. Read that byte in native big-endian
order from the selected DSP channel. Header/trailer and exact file hash remain
unchanged. FNV32 starts 2166136261; for every envelope/data byte excluding the
checksum field, h=(h XOR byte)*16777619 modulo 2^32. No gain, smoothing, random
state, audio coefficient or signal algorithm changes. Seed 0.

## Frozen experiment, ownership and evidence

Conditions: stock baseline; extended-frame idle; mono/stereo deterministic take;
CPU-source-released; freeze A then replacement B; exact save/reload; repeat;
empty/busy/stale slot; wrong epoch/token/serial/offset/count; short/corrupt/drop/
duplicate/reorder reply; timeout; duplicate file; missing/existing directory;
failed/short write; cancellation; guards and nonprotocol voice/reply equality.
The falsifier disables the readback emitter while retaining the normal writer:
it must fail without a saved reference or surviving partial destination.

Outputs: fresh ignored `out/runs/sketchbook-*` directories containing build
listings, source/input hashes, native request/reply traces, native files, stock
reload comparisons and reports. Keep failed runs. Tolerance is byte exact for
PCM, file metadata and preserved stock fields. Physical clock/DMA/cache timing,
listening, power loss and hardware installation are not inferred from this proof.

Implementation may choose instruction encodings and bounded scratch layout but
may not increase the transport above the stock 0xbc0 cap, borrow stock fields,
retain full CPU PCM as a hidden fallback, change accepted buffer/slot identities,
remove project guards, fake transport success or modify pinned dependencies.
The dedicated backend and opt-in composition precede any distributable package.

UNRESOLVED before testing: native stereo packing and byte order, SHARC compiler
semantics, complete field/voice parity, scheduling and exact write cancellation.
The 3008-byte frame costs additional wire time; physical deadline margin remains
unqualified even after functional emulator validation.
