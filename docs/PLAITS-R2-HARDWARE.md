# Plaits r2 hardware observations — 2026-10-06

## Resolved track mismatch and user listening result

The supplied SRC-page photo shows SMP 16. After switching to track 1, the
user reported that the models and controls work and that the sound is good.
The earlier click/silence reports below were from unsupported track 16, not
an established track-1 DSP failure. This is user-confirmed hardware listening,
not a timed or exhaustive hardware regression suite. R2 boot and track-1
Plaits operation are now supported by the user's observations.

Remaining feedback: LEN should go beyond 64; MODEL should display voice names;
LFO assignment/modulation does not appear connected. Prevent selecting Plaits
on unsupported tracks until per-track state/routing is implemented.

Source inspection confirms that LEN still uses stock row 0xfd, with max raw
0x3f00 and its stock formatter, rather than a dedicated synthesis-duration row.
MODEL is numeric 0..5. LFO destination assignment was explicitly unimplemented;
upstream notes identify an owner-6/type-7 mismatch in the destination eligibility
path at 0x4003ae02. That is a lead, not proof of the whole routing fix: effective
modulation must also survive the raw-macro transport overrides. Shared sampler
metadata must retain stock behavior when implementing Plaits-specific controls.

### Earlier observations (superseded by the track-16 identification)

User reports r2 reached Plaits after installation. Default/model 0 produced a
short click. TUNE affected the result; HARM/MORP appeared ineffective, MODEL
changes appeared ineffective, TIMB sometimes produced glitches. Returning
controls to zero produced silence. The inherited Slice Length label is still
visible. On follow-up the user answered LEN/LEV as "64 and default"; interpreted
as LEN 64 and LEV default. Whether each model change was followed by a new
trigger, actual level value, track number, and the full SRC state remain
unconfirmed. These are user listening observations, not a captured hardware
control stream or proof that the custom DSP renderer executes correctly.

Code inspection: MODEL/pitch/LEN/LEV latch at a trigger; HARM/TIMB/MORP update
per voice call. Zero level explicitly produces zero gain. Metadata defines
macro defaults at display 64, but fresh-machine default initialization was not
validated; earlier emulator experiments used prepared state. LEN remains the
borrowed stock slice-length parameter, interpreted by the custom DSP as note
duration. Do not relabel shared stock metadata without isolating Plaits.

Next bounded observation: disposable track 1, explicit nonzero LEV, middle
macro values, MODEL 1, a new trigger after settings. Compare MODEL 2 with a new
trigger. This distinguishes unset defaults/trigger semantics from the reported
hardware control or DSP integration failure. No cause is yet established and
no new firmware has been built or transmitted for this symptom.

## Follow-up user observation

After returning HARM/MODEL/TIMB/MORP to zero, the voice is silent rather than
clicking. MODEL changes still appear ineffective. The user expects selecting
the machine on another track might restore the initial click, but has not
reported performing that comparison. Track number and actual SRC/AMP values
remain unconfirmed. Do not report the other-track idea as an observed result.

The DSP builder includes a zero-filled loader arena containing lane state,
so uninitialized lane RAM is a hypothesis about actual loading/runtime use,
not an established omission from the file. Actual payload execution, control
arrival, memory lifetime and real-time operation remain possible causes.
No further firmware change is justified solely by these observations.
