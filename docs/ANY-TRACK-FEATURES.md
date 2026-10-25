# Remove fixed track-1 routing

Revision 1, 2026-10-19. Status: implementation authorized by the user's request
to remove track-1 restrictions, with a movable single-track fallback if simpler.
Lane: source-reimplementation maintenance of the lab-owned integration around
the licensed Plaits engines and native arp. The working stopped-arp R2 package
and pre-edit sources are frozen at `out/runs/track-unlock-baseline-20261019-01/`.

## Evidence and selected design

EVIDENCE: Capicola's current author engine already has 32 reader lanes across
16 tracks. Native Flex accepts destination indices 0..15 and retains samples
independently; its recorder is shared. Neither requires a new track-unlock patch.
Plaits CPU transport and DSP addresses are fixed to T1; the arp explicitly
checks selected track zero, emits stock notes to track zero and hides G elsewhere.

Selected arp design: one keyboard arp follows the selected track 1..16. Share
the existing per-pattern mode/rate settings rather than introducing 16 persistent
arp engines or a new assignment setting. Track changes panic the old track before
updating the output destination; consume later owned key releases. Stopped clock,
BPM, rates, order/RNG, no latch and AR16 v1/v2 persistence stay unchanged. Input
note hooks only collect physical keyboard notes for the current selected track;
sequencer playback and other tracks remain stock. This is the user's simpler
single-active-track option, with no fixed track number.

Selected Plaits design: allow machine type 7 on all 16 tracks; generalize raw
macro transport and repack guards using the real CPU strides (142 bytes for
control mirrors, 154 bytes for machine selectors). Preserve all six original
engine functions and math, model/duration semantics, controls, locks and LFOs.
Generalize DSP lane = (voice - 0x2412cc)/0x1d8 over 0..31, track = lane/2;
note words stride 2, parameter blocks stride 0x60. Keep an independent 352-byte
BankLane per lane. Its 11264-byte interval is inside existing reserved, zeroed
state at offset 0x21000..0x23c00, below handoff at 0x24000. No larger reservation.

The existing Capicola author source, zero-fill repair, Flex allocator/storage,
bootloader and updater are unchanged. All changes are optional `--any-track`;
old build flags must reproduce their previous CPU/DSP/package bytes exactly.
Deliver a separately named experimental all-feature OS1.16 SYX that also retains
stopped arp. No flash, commit, index changes, dependency edits or publication.

## Frozen equivalence and experiment

Reference: the supplied author CAPI release remains pinned; Plaits reference is
the exact old six-model engine/wrapper on track 1 and a relocated input/control
oracle for other tracks. CPU code and engine dependency hashes are frozen in
the baseline source copy. Plaits core/tables retain MIT attribution; author CAPI
retains its AGPL notices. Only lab-owned routing wrappers change.

Require bit-exact T1 Plaits PCM where generated math permits it; if compiler
register allocation changes floating evaluation, stop and investigate rather
than silently widening tolerances. Equivalent track-local inputs must render
the same PCM on T1/T2/T8/T16 for all six models. Distinct-track interleaving must
match independent single-track runs and leave other lane state unchanged. Test
silence, trigger/retrigger, model change, simultaneous Plaits/CAPI/stock tracks,
level extremes and finite output. Seed 0x13579bdf; 48 kHz output, native 64-sample
DSP calls. Retain PCM/control/report hashes in unique ignored runs; retain all
failures. The old DSP on a non-T1 track must fail the new-feature comparator.

CPU acceptance: execute real permission and repack routines across 16 tracks,
all stock machine types and raw macro extremes. Native full-width transport must
preserve stock tracks and all non-overwritten macro fields/registers. Real panel
selects a non-T1 track, opens Keyboard settings, adjusts G, plays stopped and
records ordered notes to that track only. Compare two selected-track transitions
with held inputs, mode OFF, key release, invalid track and pattern/project recall.
AR16 bytes must remain the same for identical mode/rate vectors.

Package/reset: source suite, original default hash reproduction, source-frozen
SINE, actual bootstrap decompression, CPU reset/canaries, code/state overlap and
1 MiB DSP staging gates. Existing CAPI stereo/final-ring and Flex destination
checks are retained. Native code/frame/instruction results do not prove physical
load, full coupled cold boot, flash safety, simultaneous 16-track capacity or
listening. Working level: target-build plus bounded native control/PCM evidence.

## State and UI contract

Initialize: existing zeroed reservations; arp OFF/1/16. Plaits lanes are separate
and initialized by their own trigger. STOP/Panic: close current arp gate on its
owning track, clear held active set, preserve later key-release ownership.
Track change: same panic before destination replacement; new track uses current
pattern arp mode/rate. Pattern/project recall: existing panic and AR16 semantics.
Plaits machine exit: clear only that lane's active state and fall through to
stock; other tracks retain state. Freeze/reconnect: N/A, no new feature/provider.
Recovery/failure: reject unknown images, patch bytes, overflow and source drift;
do not repair firmware or storage on a device. G mode/rate UI is available on
every valid selected track; no new selector or persistent control is introduced.

Working artifact: `EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_OS1.16.syx`.
