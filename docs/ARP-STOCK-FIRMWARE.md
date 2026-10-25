# Native arp on stock OS 1.16

Revision 1. Authorized 2026-10-15: user requested a firmware build and then said
"do what you need" and "from a stock os first". This supersedes the earlier
prototype's packaging exclusion for this continuation only.

## Working artifact

A private `out/runs/<unique>/EXPERIMENTAL_ARP_STOCK_OS1.16.syx`, containing
only a guarded MAIN change to exact stock Digitakt II 1.16. DSP, bootstrap,
updater and other sections remain byte-identical. Working means target build,
container integrity and native CPU panel/record/project evidence without the
Python ArpUI/ArpIntegration services; physical timing and hardware are separate.
No commit, publication, dependency modification or device upload.

## Architecture and behavior

EVIDENCE: lab/arp_modes.py is the tested 2,254-byte original ColdFire core.
Reuse its four modes, fixed 102 BPM sixteenths, 50% gate, one octave and track 1.
UP ascending unique notes; ORDER first unique press; RANDOM LCG
r=(1664525*r+1013904223) mod 2^32, seed 0x13579bdf, rank=((r>>21)&127)*N>>7.
First note follows PLAY by one interval. More than 16 contributions rejected;
late service above 48,000 samples panics without catch-up bursts. Stock DSP
and recording quantization remain unchanged. This port does not add tempo or
MIDI support. G detents clamp OFF/UP/ORD/RND; G push and E/F/H remain stock.

INFERENCE to validate: service from the native Main OS UI queue loop, paced by
its ordinary tick events, is a suitable task context for the original keyboard
note APIs. No filesystem, heap allocation or borrowed CPU context in the hot
clock path. Lazily allocate a bounded lifetime state block with stock malloc in
this task; failure stays OFF. Put only a zero pointer in guarded image padding;
allocate runtime state from owned heap, never diagnostic 0x60000000 memory.
All emitted code/data fit individually guarded, non-overlapping stock padding
before reset-copy data. Native hooks preserve ABI and displaced stock bytes.

Input collectors accept only stock keyboard callers, current track 1 and active
keyboard view. Remember physical owner keys so releases in keyboard settings do
not leak stock notes. OFF and other tracks follow original APIs. Enabling with
outstanding direct notes is refused until release. Stop, destination change,
keyboard exit and project load close output and clear active notes; suppressed
release ownership remains until release. Runtime keys/clock/RNG never persist.

Save all 128 pattern mode bytes via native root file APIs only after native
project-save success. Retain stock project format. Authenticate companion
records to requested slot and SHA-256 of the exact serialized project. Reuse
AR16 v1 codec and checked two-bank journal semantics in lab/arp_persistence.py.
Use original OS SHA-256 and file operations, with native buffers and checked
return values; no Python hash or filesystem callbacks in the feature. Unknown,
missing, corrupt, conflicting or wrong-project records recall OFF. Native load
failure stays OFF; slot -1 live clones never trigger recall. Partial companion
save failure must be visible in native status and must preserve stock notes.
Hashing/file I/O run in original save/load task context, away from clock service.

## State and validation contract

Initialize exact core bytes plus zero modes/owner map; allocate once per boot.
Panic clears active counts/gate/phase/order/seed, retains owner counters. Mode
change uses existing core semantics. Project recall stops and never resumes
transport or held keys. No latch/freeze feature; disconnect/exit panics.
Non-finite handling N/A: integer-only core. State equality: exact core bytes at
equal sample ticks, normalized output notes/count/order at panel boundaries;
new task cadence is not required to match old host transaction timestamps.

Native expected first eight: UP 60,64,67,60,64,67,60,64; ORDER
67,64,60,67,64,60,67,64; RANDOM 64,64,60,60,60,64,67,60.
Run focused relocation/ABI, native panel/record and actual saved-mode tests;
OFF/other-track and invalid companion controls can falsify integration.
Test heap failure, stopped gate and load with held ownership. Rebuild exact,
classify all writes, preserve reset-copy data, reparse packed container with
independent decoders and compare protected sections. Use original bootstrap
native depacker and bounded startup when available. One stable full source
suite and required SINE regression. Retain bounded failures and source hashes.
Hardware, listening, physical timing, all tracks, tempo edits, copy/undo/export,
companion garbage collection and production release remain UNRESOLVED.
