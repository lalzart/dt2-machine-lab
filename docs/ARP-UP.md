# UP keyboard arp, first emulator experiment

Revision 1, approved by the user on 2026-10-14: “Up order and random what I
want, but yeah let’s just start with up.” The intended eventual selector is
OFF / UP / ORDER / RANDOM. This experiment implements OFF and UP only.

The research baseline is the sibling workspace's ARP-FEASIBILITY.md. It
identified stock OS 1.16 keyboard note-on at 0x4011fe12, note-off at
0x4012020c, and the sample tick at 0x40966500. The first working artifact is
a native ColdFire UP core plus a DigiKit adapter and a captured control stream.
The adapter owns temporary emulator memory and hook placement. Permanent
firmware placement, G's draw/edit patch, persistence, MIDI input and hardware
are later milestones. No new SHARC sound engine is required.

## Frozen behavior

- One selected audio track, track 1 (zero-based 0), and an empty pattern on it.
- Resolved keyboard notes enter the arp after existing scale/root mapping.
- Capacity: 16 held key contributions, pitches 0–127, velocities 1–127.
- Duplicate pitches retain a reference count; releasing one contribution does
  not remove another held contribution at the same pitch.
- UP selects the lowest pitch, then the next greater pitch, wrapping to the
  lowest. Note velocity follows the most recent accepted press at that pitch.
- One octave, no latch, fixed sixteenth-note rate at the fixture's 102 BPM.
  Clock units are output samples at 48 kHz, with phase increment 408 per sample
  and step threshold 2,880,000. Preserve the remainder; gate is 1,440,000 units.
- Input and output events are distinct: collected keys do not directly sound;
  generated note-on/off events use stock note routines and bypass collection.
- Notes held before PLAY are collected. PLAY starts a fresh phase, and the
  first generated note is at the first sixteenth deadline after PLAY.
- Last active key release ends a generated gate immediately. Removing the
  currently sounding pitch also ends that gate. Other releases affect the
  next selection only.
- STOP, disable, track/pattern change and panic release the generated note,
  clear the active set and reset phase/order. Keep input ownership until each
  suppressed physical key releases; do not leak those releases into stock.
- Missed clock service over one second panics instead of emitting a catch-up
  burst. A 32-bit sample-tick wrap is normal unsigned subtraction.
- OFF is stock behavior. Unsupported tracks remain stock. Enabling requires
  no pre-existing direct keyboard notes; first experiment arms before input.
- No allocation or I/O inside the core. State is caller-owned and fixed-size.

## State and evidence

The core receives press, release, clock, mode and panic operations. It returns
at most one note-off and one note-on per operation. It stores enabled/play
state, phase, last tick, active gate, last chosen pitch, input counts,
velocities and retained suppressed-input ownership. Integer-only control
processing adds no gain or audio transformation. Invalid note/velocity/capacity
input fails without changing state. Reset returns all core bytes to the defined
initialized state, including owner counts. Panic preserves owner counts until
real releases arrive.

Core acceptance: native instruction legality, ABI preservation, ascending order,
duplicates, release, Stop/disable, restart, range endpoints, capacity rejection,
clock wrap, late-service panic, rational timing and repeatability. An independent
Python behavioral oracle is test-only; the adapter must use the native core's
decisions. A stock OFF comparator must retain native immediate key events.

Adapter acceptance: real keyboard input collection; the actual firmware sample
clock; expected C/E/G order in stock note calls and CPU-to-DSP frames; no extra
events after Stop/last release; preserved non-arp input. Register expected events
before execution, retain failed runs and source/input hashes. Repeat the same
bounded gesture sequence and compare musical event/tick records exactly. Core
timing quantizes by no more than one supplied clock block; adapter delivery
latency is measured separately and is not physical timing.

Voice PCM replay is a separate optional signal gate using the existing stock
sampler fixture. It cannot establish final DAC output, real-time operation,
hardware behavior or subjective quality. No oscillator/sampler code is changed.

## Ownership and decisions

Source and adapters live in this repository; pinned dependencies remain intact.
Temporary code/state/stack addresses are emulator-only and must be checked for
overlap. Native-call transactions preserve the borrowed CPU context. They are
diagnostic accommodations, not an on-device clock/interrupt ownership claim.

The implementation may add the native core, explicit experiment adapter,
focused tests and reproduction/results notes. It may not commit, publish,
flash hardware, package an update, overwrite firmware originals, silently
change dependencies or relax a failing tolerance. Existing unrelated changes
are preserved. Source is original control logic; no Arturia or Elektron code
is copied into the core. Firmware functions remain private runtime inputs.
