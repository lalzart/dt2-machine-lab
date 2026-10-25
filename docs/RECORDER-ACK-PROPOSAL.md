# Native recorder request echo: frozen experiment

Digitakt II OS 1.16, 2026-10-21. User authorized proceeding from the diagnostic
round-trip recommendation. This is original transport/validation code, not a
new musical algorithm or a third-party DSP port. Existing instruction wrappers,
pinned toolchains and peripheral models are reused without dependency edits.

Working artifact: `check-recorder-ack.py` report showing a native ColdFire
request, native SHARC echo construction, guest-descriptor SPI2 transmission,
the original ColdFire receive driver and native receipt matching. Evidence is
target instructions in an emulator with explicit peripheral/callback fixtures.
No return value grants retirement, and no capture, UI or normal builder changes.

## Evidence and carrier decision

EVIDENCE: original SHARC SPI2 setup `0x1c7bd4(0xabc)` builds circular RX
descriptors at `0x2641b0/0x2641cc` and TX at `0x2641e8/0x264204`. These select
input rings `0x265220/0x264220` and reply rings `0x267220/0x266220`. Guest
descriptors contain byte aliases `0x282xxxxx`; no pointer is shared with CF.
The pinned native core already implements descriptor-driven `spi2_exchange()`.

EVIDENCE: original CF driver `0x400cd2bc` copies the previous receive staging
buffer to its caller **before** starting the next exchange. Original setter
`0x400cd2b0(0xabc)` sets the frame size. The existing DSPI2/eDMA model follows
the programmed descriptors; the CPU driver's body need not be intercepted.

EVIDENCE: the apparent spare halfword at DSP reply `+24` is not wholly free.
At `0x1c3241..0x1c324b`, a byte from `0x2528e8` is shifted 16 bits and ORed
with a masked 16-bit value, then stored at reply `+22`. Thus DSP byte `+24`
carries a stock flag and byte `+25` is zero padding. The failed whole-word
sentinel control is retained. The stock CPU trace read only reply `+22` in
1,109 exercised frames; it did not read `+24/+25`. This is a bounded trace,
not an exhaustive proof of every stock path. Capicola owns `+26/+27`.

SELECTED: use only DSP padding byte `+25`, arriving at CF wire offset `+24`
through the existing 16-bit byte swap. Preserve DSP flag byte `+24`, Capicola
`+26/+27`, all other reply bytes and the fixed `0xabc` frame. Scope is an
isolated guarded stock overlay. Production/composed-image approval is separate.

## Protocol and state

Existing FXR1 request and its validated SHARC epoch/generation/sequence are
unchanged. Echo is a receipt of that request, not reader completion. Emit 48
fragments cyclically, one per completed audio block. Fragment index `i=0..47`
selects word `i//16` from `[epoch, generation, sequence]`:

```
fragment = (i << 2) | ((word >> (2*(i & 15))) & 3)
```

There is no signal processing, gain, coefficient or smoothing change. The
receiver must match all 96 expected bits and all 48 ordered indexes. Values
192..255 are invalid. A new native request resets expected fields, fragment
progress, poll age and receipt status; older epoch/sequence requests are
refused locally. Exact same tuple/extent submission is idempotent. A conflicting
duplicate is refused. Higher epoch allows sequence restart.

SHARC snapshots validated request revision and fields, checks revision again,
resets fragment index on revision change and writes only the selected stock
reply bank's padding byte. Invalid bank pointers cause no write. It does not
write both banks while one could be in flight. Scratch is separate from the
previous observer. No request leaves stock padding unchanged.

CF phases: NONE, PENDING, CONFIRMED_RECEIPT, TIMED_OUT. Only PENDING advances
fragment matching. Index zero restarts a packet; unexpected indexes or bits
reset progress. Each native poll increments age; 192 polls without a match
times out and retains all storage. A confirmed receipt is idempotent. Newer
requests can supersede pending/confirmed/timed-out requests. These are
diagnostic transport states, never allocator permissions.

| Event | Required effect |
| --- | --- |
| Init/reset | Zero private diagnostic state; no outstanding receipt |
| New request | Native publisher call; native expected tuple update; no sample mutation |
| Duplicate request | Same tuple/extent preserves diagnostic state; conflicting duplicate refuses |
| Lost/duplicate/reordered/corrupt fragment | No false receipt; restart or timeout; retain backing |
| Stale reply / changed epoch | Match only current tuple; retain backing |
| FREEZE and replacement | Existing immutable snapshot and old readers stay valid |
| Timeout / transport busy | No acknowledgement-based release; explicit timed-out status |
| Project change | Epoch echo only; no claim of project-root cleanup |
| Panic/rate change/reconnect | No production handler; all reuse remains disabled |

## Execution boundary and placement

ColdFire's request publisher remains the previous named LP0 capture boundary;
the request bytes are delivered by the modeled link into original SHARC LP0.
CF request construction and SHARC validation are native instructions. The
ordinary DSPI2 driver body, receive copy and echo matcher execute natively.

SHARC SPI2 descriptors are built by the original initializer. The prepared
snapshot lacks SEC source-register reset contents: explicitly seed the modeled
SEC source control/status bank with zero, matching the peripheral model's
absent-register default. Do not seed descriptors, current DMA pointers or
fabricate echo bytes. DMA movement/completion use the pinned native model.
Completion callback entry is modeled using original `0x1c77b4` with event
`0x20`; actual SEC interrupt dispatch is not proven. Native block calls remain
host scheduled. Physical timing, IRQ preemption and cache ordering remain open.

New diagnostic code/state use guarded emulator scratch: SHARC code
`0x200c0000..0x200c3fff`, data/context/stack `0x200f8000..0x200fbfff`; CF
`0x10900000..0x10903fff`. Existing observer arenas and all DSP PCM reservations
are preserved. No production memory placement is implied.

## Frozen acceptance and falsifying controls

Deterministic seed zero. Reuse the authenticated native worker A/B/FREEZE
captures from `recorder-freeze-queue-native-20261021-02`. Execute identical
wire/page histories on original stock and patched SHARC. Compare every exercised
voice buffer and all reply bytes except the single padding byte exactly, with
an independent fragment encoding oracle. Check old frozen A during/after B.

Literal conditions: no-request, native-spi-init, native-cf-driver, echo-a,
echo-b, frozen-root, delayed, dropped, duplicate, reordered, stale, corrupt,
supersede, timeout, transport-busy, byte-preservation, exact-pcm. Repeat the
whole probe with identical outputs. Native CF unit tests cover ABI, all fragment
bits/boundaries, tuple/extent ordering, duplicates and refusal without mutation.

The falsifying controls are full-word padding overwrite (stock flag changes),
stock-zero replies (never match), and stale prior-generation replies (never
confirm the new request). Fault injection replays, withholds, duplicates or
corrupts native-produced carrier bytes; it is named as a transport model. It
must not inject a successful CF status or build successful replies from Python.

Freeze source hashes before each run; retain source snapshots, linked listings,
patch bytes, request/reply captures, instruction counts, failed attempts and
exact-repeat comparison. Run the full unit suite, SINE replay and prior atomic
publication regression. Do not change expected baselines, pins, normal builds,
native recorder/FREEZE/legacy Flex, Plaits, Capicola or shortcuts. No hardware
transfer, flash, commit, push or publication is authorized.

UNRESOLVED after success: complete SEC/CPU interrupt integration, native LP0
publisher completion, exhaustive reply-field/composed-image compatibility,
hardware deadline, queued-trigger/root barrier, retirement, identity reuse,
native capture producer and DSP readback/SAVE. Stop any dependent part when its
gate is not established; report receipt transport at its actual evidence layer.
