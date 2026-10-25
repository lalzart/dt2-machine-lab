# Arp menu, modes and recorded-project persistence

Revision 1, authorized 2026-10-14: user asked to work on G menu control,
recording/saving, ORDER and RANDOM after the passing UP prototype.

## Working artifact and scope

A native OFF/UP/ORDER/RANDOM control core and a DigiKit OS 1.16 adapter with
a visible native G-slot selector, real panel input, recorded-note replay and
native project save/reload evidence. Continue one audio track (track 1),
one octave, 102 BPM sixteenths, 50% gate and no latch. Firmware packaging,
physical placement/timing, hardware, MIDI input and changing tempo stay out.
Preserve the first UP core, captures, pinned dependencies and unrelated work.
No commits, uploads or flashing.

## Behavior and equations

Mode IDs: OFF=0, UP=1, ORDER=2, RANDOM=3. G rotates through this bounded enum
without wrapping. Push has no new action. Keep E scale, F root and H fold.
Other tracks retain stock behavior and no editable arp selector.

UP retains the approved behavior. ORDER sorts distinct held pitches by first
accepted press time, not pitch. Duplicate pitches keep their position until
all contributions release; pressing that pitch again assigns a new position.
Selection chooses the first held stamp after the cursor, wrapping to the lowest.
Reject a new unique pitch without mutation if its 32-bit press serial is full.

RANDOM advances a 32-bit LCG once per generated note: r=(1664525*r+1013904223)
mod 2^32; q=(r>>21)&127; rank=(q*unique_held_count)>>7. Select that rank from
ascending distinct held pitches. Repeated selections are allowed. This is an
original bounded selector; no exact MicroFreak algorithm is claimed.
Seed=0x13579bdf. Reset, Stop, panic and a different mode reset the seed.
Same-mode selection is inert. All three modes retain counted release ownership,
invalid-input rejection, bounded sample-clock servicing and existing note-off
before note-on behavior. Mode changes flush the generated gate and active set
while retaining ownership until physical releases. First note follows one
sixteenth after PLAY. Runtime keys, gate, cursor and RNG are never serialized.

Native state is fixed-size, integer-only, caller-owned; no allocation/I/O in
the core. New state adds a 128-entry press-stamp table and order cursor to
the first core. The emulator region has checked non-overlapping code, wrappers,
state, strings and stack. Preserve borrowed CPU contexts and native ABI.

## Recording and saving

Collect physical chord notes, then send only generated on/off events through
the stock keyboard input API. In Live Recording, test that the actual pattern
receives those notes and durations. Native sequencer playback bypasses the
keyboard collector and must reproduce the realized phrase even in RANDOM.
Save and reload via original project serializer/MMC functions, with a private
sector overlay and an independently restored stock firmware instance. Never
write the original virtual card. No custom bytes enter the stock project format.

For saved mode configuration, first authenticate native project slot identity
and exact serialized project bytes. Use a separate versioned companion record
on the same modeled card, bound to slot and SHA-256 of those bytes. Missing,
invalid, failed or mismatched companion data defaults to OFF. Save only after
a successful native project write, verify record/readback, retain prior records
on failure and report partial persistence honestly. If native identity or
filesystem ownership cannot be authenticated, do not substitute heap pointers,
unsafe project padding or an unrelated host-side JSON file. Record the exact
remaining integration boundary instead. Pattern copy/undo semantics require
separate proof; no automatic claim follows from save/reload.

## Acceptance and evidence

Before execution, register exact UP/ORDER and seeded RANDOM vectors. Verify
ABI, bounds, duplicates, release/re-press, Stop, mode changes while held, seed
restart and invalid enum rejection. Compare unchanged UP and stock OFF.

Capture native menu pixels and G events; assert visible four-mode feedback,
clamping, push neutrality and neighboring E/F/H behavior. Capture generated
stock calls and DSP frames; compare repeated normalized events exactly.
Prove recorded playback pitches/count/durations without recollection, then
native saved/reloaded pattern equality in an independent firmware instance.
Test companion missing, corruption, wrong project and failed writes separately.

Register objective voice-PCM replay via the existing stock renderer, finite,
nonzero, nonclipping and exact-repeat checks. Require all source tests, doctor
and SINE replay. Use fresh bounded output directories, retain failures, freeze
source hashes during captures. Report source, CPU control, voice PCM, storage,
real-time, listening and physical hardware separately.
