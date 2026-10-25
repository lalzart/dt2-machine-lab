# Optional CAPI comparison toggle

2026-10-13. Revision 3. Status: approved for local implementation by the user's
"Yes, let's go ahead and implement that." Source-reimplementation lane; this
adds routing/UI around the preserved engines, not a new stretching algorithm.

## Working artifact and scope

One optional OS 1.16 comparison build and its native CPU/DSP `report.json` under
`out/runs/<unique>`, at target-build/emulated-signal evidence. Preserve STRETCH
machine ID 2 and the seven existing controls. Expose CAPI on encoder C using
the dormant parameter 204, mirror 27, wire offset `0xde + track*0x60`.
No new machine ID, expanded DSP reservation, stereo Capicola, mid-note engine
handoff, dependency edits, hardware transfer, commit, or publication is allowed.
Local packaging is authorized as part of the previously requested firmware
integration; this option must not change the default package bytes.

## Exact control and engine policy

CAPI has raw range 0..256, default 0, display OFF below 128 and ON at/above 128.
Native range checks reject values outside that interval. The DSP accepts ON
only in 128..256; malformed wire values select stock at the next trigger.
Keep parameter ownership, storage and the native mirror routing of parameter
204; its label, range and formatter are the optional UI changes. Exhaustively
check its native setter/getter, transport, lock/recall and encoder behavior.
Existing projects default to stock in this comparison build; the ordinary
build retains its current automatic Capicola behavior.

For each of 32 lanes, at a real native trigger: OFF stops its Capicola reader
and returns to the untouched original renderer. ON delegates to the unchanged
R3 adapter, which selects Capicola only for a ready eligible bank. Without a
trigger, changing CAPI does not change that lane's latched backend. Keep source
invalidation, machine switch, finite completion, TUNE/BARS and live PLAY/trim
semantics. The two lanes of one track may briefly use different engines after
different triggers; report MIX rather than claiming a uniform backend.
Keep R1 reader, R2 cache, R3 wrapper, 12-second input, 8 MiB total reservation,
200 KiB working layout and all numeric tolerances byte-for-byte unchanged.

## Status protocol and CPU UI

Evidence: stock reply audit `out/runs/capi-toggle-audit-01/reply-audit.json`
preserves reply halfword +0x1a; neighboring words are written by stock and may
not be reused. Write only that halfword in the existing ping-pong SPI2 reply.
On each normal maintenance call broadcast one track, index AUTO.slices modulo
16, using `0xd000 | (track << 8) | state`. State 0 unknown/non-STRETCH,
1 WAIT (eligible, not ready, no active voice), 2 READY (prepared, idle), 3 CAPI
(active custom lanes only), 4 STOCK (active stock lanes only), 5 MIX (both),
6 UNSUP (idle ineligible source). Determine active status from native voice
active and the actual latched backend, never solely from the requested toggle.
READY describes the next trigger, not the current engine. No source identity
or persistence authority is inferred from this informational word.

After the original CPU SPI2 call returns, a bounded observer caches one status
byte per track and ages all sixteen byte entries; valid updates receive age 32,
each receive decrements positive ages, invalid packets clear the cache. Values
0/expired display unknown. This is asynchronous last-received-block information
with at most sixteen successful exchanges between track updates, not a physical
latency guarantee. The SRC draw hook verifies ParameterPageView, page 2, current
track 0..15 and machine 2. The audited view context at +0x74 is passed to the
original current-track getter. It updates the immutable 18-character caption
only when the status changes, then retains the original widget getter result.
Idle OFF takes precedence over WAIT/READY/UNSUP; active CAPI/STOCK/MIX reflects
actual playback even while a changed control awaits retrigger.

## Placement, reversibility and authority

The current managed Flex build leaves only 117 fragmented cave bytes. Preserve
all those existing allocations, including zero-filled mutable state. Append new CPU code, descriptor, immutable strings and 32 status/age bytes to
MAIN at 0x40320000. Execute them in internal SRAM at 0x8000f180, below 0x80010000.
The original reset first copies data to SRAM and then clears external RAM from
0x40312000 through 0x47e28470. Revision 1's execution at the append address fails
that native clear; its proposal and failed startup remain in the audit run.
Extend only the second copy routine's guarded source-end immediate from
0x4031ff60 to the aligned appended image end. Keep every original initialized
SRAM byte and both clear bounds unchanged. The original initialized SRAM ends
at 0x8000f0e0; the append alignment leaves 160 zero bytes before the new payload.
The new payload has a 3712-byte ceiling; the remaining SRAM tail still clears.
Both decoded native CPU code spans have zero static references to this SRAM tail
(99.86% and 97.14% coverage). This does not prove absence of computed references:
require bounded startup retention, panel/locks/reply checks and leave permanent
physical ownership deferred. Guard the exact comparison
MAIN baseline `0bd3c2989665ec5151d5b14d9fbe3d55ee1810b3698fc2d34e7a1f9daaea5531`.
Original reset-copy data through the original image end is unchanged; only its second source-end immediate extends. Check
bounded fresh CPU startup and retention; permanent runtime ownership and
physical operation remain unresolved device gates, not build claims.

Use a separate `capicola-stretch-toggle` compile family including/renaming the
unchanged R3 machine. Keep this layer in `lab/capicola_toggle.py` and the optional
family; only dispatch/metadata/formatting/SPI observer/draw and the documented reset-copy end patch sites may change. `--capi-toggle` is explicit. With it omitted, require original MAIN,
DSP `0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf` and SYX
`cb57ee53d106b3bf05e3562d74e8d8f45889112da55043a1fb46976552a60229` exactly.
Pad only the optional DSP code block to a 32-bit loader boundary, retaining every
assembled instruction byte. The unaligned 91882-byte block lost its last partial
word in native packing; the audit isolates one byte at 0x200966e8. Check all
linked code, constants and selector bytes before and after bounded startup.
Source authority is the clean machine-lab revision
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, preserving the inherited AGPL
Capicola notices and MIT Plaits lineage. Owned stock firmware stays private.

## Frozen experiment and acceptance

Seed 1. Same hash-guarded LP0 and CPU wire captures as R3. Use mono 512-frame
synthetic tones, plus one unsupported stereo source and forced pressure/invalid
generation fixtures. Native block size 32. At block 0 assign, before readiness
trigger ON and require stock; after preparation trigger OFF and compare stock;
at block 4 change ON without trigger and require continued stock; at block 8
retrigger and compare R3; at block 12 change OFF without trigger and require
continued Capicola; at block 16 retrigger and compare stock. Repeat forward,
reverse and looping modes, pitch/tempo settings and sixteen mixed tracks.
OFF renderer/master PCM must be exact to original stock; ON must match preserved
R3 at max 1e-4 / RMS 1e-5 (exact where identical execution permits). A deliberately
ignored OFF control must differ on a non-silent fixture. Check simultaneous
lanes, reload, failure, source retirement, finite completion and other machines.

Native CPU checks must cover descriptor/mirror/range/formatter/reverse map,
stored values and locks, late transport repacking, original control parity,
status decoding/aging, ABI/register preservation and SRC/other-page isolation.
Retain screenshots and actual panel-to-wire captures, buffered DSP reply replay
and validation reports. Run source tests, required SINE replay, deterministic
build, protected-section/container checks, original bootstrap depacking and
separate CPU/DSP startup. Retain failed runs; never rewrite old expectations.
Reset/recall equality is normalized musical state plus exact wire/PCM checks;
diagnostic cache ages and host timestamps are excluded. Listening, physical
timing, coupled live feedback and full project-storage/undo lifecycle are
separate evidence levels. Results belong in a separate note so this approved
proposal fingerprint stays stable.
