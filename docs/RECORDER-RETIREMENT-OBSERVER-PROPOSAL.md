# Native retirement reader observer: bounded proposal

Authorized continuation, Digitakt II OS 1.16, 2026-10-21. Engineering extension
to the existing sampler; no new instrument, musical algorithm or UI. This
proposal is frozen before DSP edits. Results belong in a separate document.

## Working definition and authority

Working means an isolated probe report showing ColdFire instructions construct
a request, original SHARC LP0 dispatch accepts only the new experimental tag,
and a native post-block observer reports active reader pointers and DSP slot
roots without changing stock voice PCM. It does not mean native reclamation,
native readback/SAVE, a coupled duplex link, real-time fitness or device support.

Use pinned local DigiKit/Selache and authenticated stock firmware as execution
oracles. New observer/serializer code is original repository code, not a port
of a third-party DSP algorithm. Existing generated wrappers are reused from
the local machine-lab. Firmware bytes stay in ignored output. No dependency,
normal builder, Capicola reservation/status, shortcut or existing Flex change.

## Evidence and selected architecture

**EVIDENCE:** original LP0 callback at `0x1c7e35` loads the tag; `0xffffffff`
selects a sample header; valid page tags reach the stock page copier. A large
positive tag reaches the ignore/rearm path. CPU `0x400cd638` sends one fixed
4 KiB payload and supports long-word metadata order through its third argument.

**EVIDENCE:** stock reply consumers include `0x4002f0e6`, which reads banked
halfwords at reply offset `0xa9c`, and several consumers of reply `+0x1c`.
The frame tail is not generally unused. Capicola uses reply `+0x1a`.
The live emulator peer currently returns zeros; it does not model native SHARC
SPI transmit completion.

**SELECTED:** new opt-in LP0 tag `0x46585231` (positive, outside the page range),
with a versioned 64-byte request inside the fixed 4 KiB transport payload.
Unpatched stock must ignore it. A patched callback latches validated metadata,
then uses the stock rearm continuation. Post-block hook `0x1c75c5` runs a bounded
observer after the stock timing word is written, then replays both displaced
register reloads. This preserves the existing reply timing field; total observer
cost is measured independently through native instruction counts. Frame and
event contexts have separate scratch and stacks.

**UNRESOLVED:** no return field is appropriated. The observation remains in
experiment-owned SHARC memory. Its host inspection is explicitly diagnostic,
not a native acknowledgement delivered to ColdFire. No allocation or identity
can be recycled from this observation.

## Protocol, state and bounds

One outstanding request: magic, version, project epoch, immutable generation
ID, request sequence, logical allocation start, allocation bytes, complemented
sequence and final marker. Remaining words are zero. Accept only nonzero
epoch/sequence, native worker generation IDs 1–8, 8 KiB allocation alignment,
and spans inside the normal 392 MiB pool. Reject malformed, stale and conflicting
duplicate requests. Exact duplicate packets are idempotent. Larger epoch permits
sequence restart; a separate monotonically increasing local revision prevents
request ABA during observation. Revision exhaustion refuses new requests.

LP0 writes request fields then commits revision last. The frame observer reads
that revision, scans all 32 standard lanes and all 1,025 slot descriptors, then
checks the revision again before publishing results. Results include epoch,
generation, sequence, local revision, active-pointer mask, retained-inactive
pointer mask, slot-root count, status and observation serial. Publication writes
the result revision last. LP0 never creates a reader-clear result itself.

States are IDLE_UNSEALED, SLOT_ROOTED and ACTIVE. There is deliberately no
RETIRE_OK state. A later trigger can turn IDLE_UNSEALED back into ACTIVE.
The standard lane pointers do not close other machines' cached readers,
preview state, queued events, project roots, snapshots or DMA lifetimes.

| Operation | State effect |
| --- | --- |
| Initial load / reset | Zero experiment state; no request/result |
| Valid new request | Replace request, advance revision, invalidate old result |
| Exact duplicate | Increment diagnostic duplicate count; keep request/result |
| Invalid/stale packet | Increment rejection count; preserve committed request |
| Audio block | Recompute advisory masks/roots; never free or change PCM |
| Later trigger | Recompute ACTIVE even after an earlier idle observation |
| Higher project epoch | Supersede diagnostic request; no project resource cleanup |
| FREEZE / snapshot | Existing alias remains a descriptor root; no observer mutation |
| Panic, sample-rate change, reconnect, project recall | No new production handler; refuse reclamation; device behavior unverified |

All arithmetic is unsigned 32-bit. Request bounds prevent overflow into or
beyond Capicola's reservation. PCM gain, smoothing and normalization: N/A,
observer performs no signal processing. Fixed worst-case work is 32 lane
checks plus 1,025 descriptor checks per requested block. Measure emulator
instructions; do not translate them into hardware deadline guarantees.

## Frozen experiment and acceptance

Use the final queued-worker A/B/FREEZE captures as hashed inputs. Same wire
frames and pages go to an unchanged stock oracle and the patched engine.
Compare every exercised voice work-buffer byte and descriptor exactly.

Required cases: no request; stock ignored-tag control; valid request without
an audio block; active A while B publishes; independent generation B; frozen A
roots; all 32 lane bit positions; inactive retained pointers; natural completion;
late old trigger after idle; empty/zero/overflow/misaligned spans; bad marker,
version and sequence complement; stale epoch/sequence; duplicate and conflicting
duplicate; superseding request (including an explicit native cooperative fault
injection during a scan, not a hardware IRQ test); bounded root scan; non-protocol
reply bytes; exact repeat; native ColdFire serializer ABI and refusal.

The unsafe comparator ignores the active-reader mask and treats a clear slot
or an idle observation as permission. It must be falsified by an active or
late old reader. No baseline expectations may be regenerated to make it pass.

Retain source snapshots, compiler output, assembler width checks, patch-site
bytes, loader and report hashes, PCM comparison hashes, rejected controls and
instruction counts under unique ignored runs. Run the full unit suite, SINE
replay and existing atomic-publication control. Integration requires a separate
audited return carrier and native root/queued-control barrier. Hardware timing,
mid-instruction IRQ preemption and cache/peripheral ordering remain open.
