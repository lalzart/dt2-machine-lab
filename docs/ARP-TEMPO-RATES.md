# Native arp tempo, rates and selector UI

Revision 1, 2026-10-16. Authorized continuation: user reports the installed arp
now works as expected, asks for other BPMs, quarter/eighth/sixteenth/thirty-second
rates and a better stock UI selector. The installed hash and reason for delayed
initial success are unconfirmed. Preserve every previous candidate and source
behavior when the new build option is omitted. No hardware upload or publication.

## Selected design

EVIDENCE: exact stock Digitakt II OS1.16 MAIN SHA256
57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d.
Original getter 0x4002D744 reads 0x402B62BC. Its writer 0x40138C98 accepts the
selected clock source and stores tempo in BPM*120 integer units. The original
internal tempo editor clamps to 3600..36000 (30..300 BPM), increments 120 per
whole BPM and 12 per displayed decimal. Ready fixture value 12240 = 102 BPM.
This avoids a separate tempo setting and whole-BPM rounding.

EVIDENCE: 3052 initialized static Bitmap objects with bounded geometry and
MAIN-backed data were catalogued from the stock ready image, including animation
frames. The G placeholder is Bitmap 0x44F34A78, 17x17, data 0x402C8E3C: the dotted
empty-slot outline. The previous port overprinted this stock asset. Icon atlases,
a complete overview and 17 font-resource inventories are retained in the private
discovery run. These are version-specific static/ready-state resources, not a
claim to every dynamically created screen image.

Choose the existing named-text enum style used by Keyboard Scale/Root Note.
Suppress only the stock G placeholder bitmap call. Show ARP, a large OFF/UP/ORD/
RND value and the smaller note rate. Push G (key47) toggles focus to RATE; turning
G edits 1/4,1/8,1/16,1/32. In rate focus show RATE, the large rate and small mode.
Other keyboard controls, G with modifiers and other tracks retain stock handling.
No diagnostic readouts in the normal tempo/rates candidate. Track 1 remains.

## Clock and state contract

Per-sample phase advance = current original tempo in BPM*120. Interval thresholds
are 345600000,172800000,86400000,43200000 for quarter,eighth,sixteenth,32nd.
Gate length is half the selected threshold. At 48 kHz this is exactly
60/(BPM*notes_per_beat) seconds. At 300 BPM with the existing 48000-sample lateness
bound, elapsed*tempo + phase <= 2073600000, below signed 32-bit maximum.
Read tempo before every native clock service; preserve beat phase and gate on
live tempo edits. No bursts: at most one off and one on per service; skipped
intervals preserve modulo phase. Invalid/out-of-range tempo panics safely.
Rates change closes the current output and resets phase while retaining held
input and mode order. First note remains one interval after PLAY. STOP and
project/keyboard/pattern transitions retain previous panic/release semantics.
External-clock operation and swing alignment are unverified and not promised.

Keep the original core and its legacy fixed clock untouched. Add a separate
native clock emitter and optional --tempo-ui composition. Without the option,
MAIN must remain exactly the keyboard-fix baseline
5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310.
Use the same guarded caves and one 8192-byte allocation. New words begin at4480,
away from original core, AR16 scratch and optional D1 data. No DSP section edits.

Per-pattern configuration is packed mode | rate_index<<2, where rate_index
0,1,2,3 means 1/4,1/8,1/16,1/32. Defaults are OFF and1/16 (packed8).
Native journal v2 keeps AR16 magic, filenames, 210-byte extent and two-bank
sequence/hash validation, and writes version2 with packed bytes0..15. Import v1
mode bytes0..3 as the same mode with1/16. Recognize both versions before choosing
an inactive bank; preserve unrecognized files. Missing/corrupt/conflicting data
recalls OFF/1/16. Never write v2 from the legacy build. Old firmware may fall
back to its retained v1 bank or OFF when presented with v2; exports still do not
carry companions automatically. Runtime clock, focus, held keys and RNG do not
persist. Snapshot packed settings before storage; no live callbacks in hash I/O.

## Working artifact and acceptance

A fresh private stock-only EXPERIMENTAL_ARP_STOCK_OS1.16_TEMPO_RATE_R1.syx.
Working level: target build plus native emulator timing/UI/project evidence.
User listening success applies only to the prior installed build; this new
candidate needs a separate physical result. No flash, commit or publication.

Independent timing oracle: rational sample deadlines for tempos30,60,90,102,
120,127.5,180,240,300 at all four rates. At exact sample calls, onset and gate
within one sample; panel cadence may add one observed service interval. Compare
UP/ORDER/RANDOM order, long-run fractional phase, tempo edits, rate edits with
held notes, sample wrap, late-service no-burst, invalid tempo, OFF and stock
controls. Test actual native getter with mapped original state and real panel
Tempo edits; do not substitute Python tempo/arp callbacks.

Check G rotation and push focus, modifier/release guards, default1/16, and stock
E/F/H. Render and inspect the actual firmware UI after final source changes.
Check v1 import, v2 codec, mixed versions, inactive-bank failures, all rate/mode
values, full native save/load and ordinary recorded notes where available.
Run focused checks during edits, then one stable aggregate source suite; SINE
only for changed DSP/adapter concerns. Build exact repeat, protected-section and
container checks, original loader depack and bounded startup. Retain failed and
superseded runs. Freeze executable source before long checks; separate report
backfill from implementation drift. Listening, hardware scheduling/headroom,
external clock, swing, other tracks and broader lifecycle remain open.
