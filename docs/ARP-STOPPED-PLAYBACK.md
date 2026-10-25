# Arp while the sequencer is stopped

Revision 1, 2026-10-19. Authorized by the user's request to play the arp while
the sequencer is stopped, at the current pattern BPM. Native control maintenance;
implementation and local validation are in scope. No hardware upload or commit.

## Selected architecture and frozen experiment

EVIDENCE: the existing OS1.16 tempo/rates arp uses the original BPM*120 getter
at 0x4002d744 and the audio sample counter at 0x40966500. The heartbeat supplies
PLAY as an explicit clock-enable condition; the native core accepts held notes
while stopped. Existing keyboard/track/pattern lifecycle checks own note input.

Selected implementation: add an opt-in `stopped_playback` variant. At heartbeat,
clock enabled = PLAY OR (Keyboard mode AND held arp notes). Reuse the same native
tempo getter, sample counter, rational phase, rate, half-gate and output APIs.
No second scheduler, new hook, state allocation or DSP edit. Keep the original
clock core, original build defaults and the user-confirmed R2 artifact exact.

Stopped first chord begins after one selected note interval, like existing PLAY.
Starting PLAY during that chord preserves arp phase and note order. STOP retains
the original panic: it silences the current chord and consumes its later key
releases; a fresh chord then arpeggiates while stopped. All-key release closes
the gate. OFF, keyboard exit, track/pattern/project changes, invalid tempo and
late-service safety retain their existing behavior. This change does not add
latch, MIDI input, other tracks, swing or external-sync guarantees.

State equivalence: with PLAY active, output notes, phase, gate and ownership must
match the original native heartbeat for the same events and sample timestamps.
Stopped held input is the sole intentional behavior difference. Existing AR16
settings and 8192-byte state remain unchanged. Original source is lab-owned;
existing Capicola/Plaits licenses and source lineage are untouched.

Comparator: execute candidate and preserved default native ColdFire instructions
against independent rational sample deadlines. Cover UP/ORDER/RANDOM, four rates,
30/102/120/127.5/300 BPM, live tempo edits, stopped/PLAY handoff, all-key release,
STOP, mode OFF, keyboard exit, sample wrap and delayed service. Native heartbeat
tests must execute the real tempo getter and clock/output path; only owner/UI
object selection and note endpoints may be modeled. The old stopped heartbeat
must remain silent. Code/stack/register and state-boundary checks remain active.

Panel acceptance: actual stopped keyboard chord and changing BPM through the
stock Tempo menu produce ordered native note calls while PLAY stays zero and
the sample counter advances. Use exact packaged MAIN, captured control frames
and a uniquely named ignored run; no Python arp scheduling. Then release all keys,
start/stop sequencer and confirm no stuck gate. Test playing/recording compatibility.

Build a separately named all-feature OS1.16 candidate. Require repeat build,
unchanged R2 DSP and protected sections, actual bootstrap decompression, CPU
controls, source suite and applicable replay checks. Preserve failures and all
artifacts with hashes; never regenerate expected hashes to hide a regression.
Physical timing, listening and new-candidate hardware remain unverified.

Working artifact: `EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ARP_STOPPED_R1_OS1.16.syx`.
Evidence target: target-build plus bounded native CPU/panel/control transport.
Baseline and pre-edit sources: `out/runs/stopped-arp-baseline-20261019-01/`;
R2 SHA256 `764329c1324d8f666b82c40b2d3e31f4724721044ef8e0f89b070e46e973ea59`.

The separate resource monitor request still needs menu integration and validated
live measurement sources; it is not silently included in this arp candidate.
