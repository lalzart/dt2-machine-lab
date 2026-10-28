# Flex Lite: temporary recorded samples without a +Drive save

2026-10-06. Status: recorder investigation and the first synthetic RAM playback
prototype complete. See [the playback results](FLEX-LITE-RESULTS.md) and
[the OS 1.16 recorder findings](FLEX-LITE-RECORDER.md). Actual recorder input
and panel integration remain open.
Target: Digitakt II OS 1.16, initially one track in prepared DigiKit replay.
User idea clarified by the [shared conversation](https://chatgpt.com/share/6ac459a7-31b4-83ee-b643-ee6d3b7088ed):
sample something and immediately use it on a track without first saving it
to +Drive. Save becomes an optional later action.

## Recommendation

The intended workflow is:

`input -> record into RAM -> finish capture -> temporary sample slot -> stock playback`

`optional SAVE -> normal persistent sample / project assignment`

**INFERENCE:** Investigate a volatile sample resource using the existing
playback machines. A new sample renderer is not the starting requirement.
Stock start/end, pitch, reverse, loops and locks should be tested against the
temporary resource; their compatibility is a goal, not an automatic result of
installing a DSP pointer. Slice editing and Stretch may need extra metadata.

The earlier recommendation to build a loop-crossfade engine misread the
user's priority. Smooth loop transitions, ping-pong and other new playback
features are optional later ideas. The central feature is avoiding the
mandatory save-to-storage step before using a fresh recording.

First scope: one bounded recording, one temporary slot and one track. Finish
recording before publishing it for playback. Concurrent recording/playback,
overdub, internal resampling and multiple recorder buffers can follow once
capture, publication and lifetime are understood. This order is a proposed
engineering sequence, not a restriction imposed by the user.

The work lane is new design from documented behavior, not transplantation of
Octatrack firmware or exact sonic reproduction. No novelty claim is made.

## Reference behavior and existing overlap

**EVIDENCE, official manuals:**

- Elektron's [Octatrack MKII OS 1.40A manual](https://www.elektron.se/wp-content/uploads/2024/09/Octatrack-MKII-User-Manual_ENG_OS1.40A_210414.pdf),
  chapter 9 and Appendix A.2, describes RAM-backed Flex playback with slice/
  region selection, pitch/rate controls, looping, retriggers and timestretch.
  Track recorders and their buffers are separate facilities; Flex can play an
  assigned recorder buffer. Scenes/crossfader behavior belongs to the wider
  instrument, not just a sample renderer.
- Elektron's [Digitakt II OS 1.15 manual](https://www.elektron.se/wp-content/uploads/2025/06/Digitakt-2-User-Manual_ENG_OS1.15_250625-1.pdf),
  pp. 94, 96–100, already documents manual slice start/end/loop editing,
  reverse/forward loops, consecutive-slice playback and granular Stretch.
  The official URL failed to open during this check; these pages were read
  from the retained local PDF under the original workspace's
  `work/tasks/inv-sys-005/manual/`. This is a versioned comparison, not a claim
  about the latest public release.

| Direction | Value beyond existing machines | Main uncertainty |
| --- | --- | --- |
| Temporary recorded sample: selected direction | Use fresh audio without a persistent sample file | Recorder buffer, slot ownership, publication and optional save |
| Concurrent live-buffer performer: later | Play/manipulate audio while recording or resampling continues | Read/write synchronization, routing and replacement policy |
| New loop/crossfade engine: earlier alternate | Additional playback gestures | Separate DSP work; does not deliver the requested recording workflow |

Relative difficulty is an engineering judgment, not a measured schedule or
resource budget. Exact Octatrack effects, scenes, complete recorder system and
stretch sound are outside the first experiment.

## Current local evidence

Inspected machine-lab branch `codex/plaits-macro-controls`, HEAD
`c1a0ad675741339c5e154dcb5a58caa7b65b21c2`, with inherited dirty macro-control
work. The pinned `.deps/digikit` tree is clean at
`277760aad51b036a4756db051409d4d3b1eeccbc`. The original workspace DigiKit
checkout remains on `codex/dt2-sine-machine` at that base, with its local SINE
work preserved. The follow-up added an isolated probe and engineering notes;
no dependency or firmware bytes were changed.

**EVIDENCE, existing notes read rather than experiments rerun:**

- [Integration](../../INTEGRATION.md) establishes the prepared custom source hook,
  two channel lanes for track 1 and a 64-sample/96 kHz source-buffer contract.
  [Macro controls](../../PLAITS-CONTROLS.md) documents real CPU locks, continuous
  macro transport and compiled SHARC voice output. Final output, normal PLAY,
  persistence, all-track operation and physical timing remain open.
- DigiKit `docs/findings/15-sharc-sample-path.md` documents OS 1.16 sample-page
  transfer, the slot table, stereo sample pointers, lengths and rates, and
  firmware-loaded sample playback. This is a materially better starting point
  than the earlier open sample-transport questions. It is not yet a validated
  custom sampler's complete loading/unloading/lifetime contract.
- DigiKit `docs/findings/06-sharc-engine-and-startup.md`, “Where the SRC-page
  words go”, records a single trace in which the hidden CFADE word is read and
  discarded. That note still labels verification limits. Exposing its CPU
  control alone does not demonstrate an audible crossfade implementation.

The clarified chat's main architectural idea agrees with these notes, with
important qualifications from `04-coldfire-dsp-link.md`, “Sample data crosses
FlexBus to link port 0 on 1.16”:

- `sample_loader_load_sample(ref, slot)` at `0x40154540` currently resolves a
  storage reference, allocates memory, reads a file, publishes PCM pages and
  a slot header, then updates CPU bookkeeping and posts an event. It is not
  an established generic function accepting arbitrary recorder RAM.
- The lower-level `FUN_400cd638(tag, buf, hdr)` sends a 4 KiB page or header.
  It is a useful candidate to reuse after identifying the correct allocation
  and bookkeeping contract. Normal PCM pages and headers have different byte
  packing. CPU RAM addresses cannot simply become SHARC pointers.
- The SHARC slot record contains channel offsets, length, sample rate and
  stereo state. The slot reader resolves those into addresses for the voice.
  That supports storage-independent playback at this layer; it does not make
  CPU-side ownership, project references or save/reload disappear.
- The normal loader excludes slot zero in each 128-slot bank. The SHARC's
  separate slot `0x400` is used for preview. Neither apparent empty slots nor
  the preview slot should be appropriated without checking ownership.
- `#RECORD_START` appears in an engineering console path. It does not by
  itself establish the normal panel sampling path. The follow-up recovered
  the save boundary on 1.16 and exercised its CPU consumer with synthetic
  recorder data. It has not demonstrated fresh panel recording.

**EVIDENCE, follow-up probe:** The save consumer requests recorder PCM in
transient shared chunks and copies them under a lock before file writing.
The response address is not an independently owned recording buffer.

**INFERENCE:** Copy completed recorder chunks into an owned temporary resource,
connecting sample-memory allocation, page/header publication and CPU metadata.
Prefer preserving the stock renderer and transport format.
The Plaits adapter repurposes the sample-slot field for TIMB, so it is not a
suitable transport mapping for this work.

Firmware identity is recorded in [the 1.16 profile](../../../profiles/dt2-1.16/profile.json):
stock MAIN SHA-256 `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`,
stock BLOB `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
The follow-up rehashed MAIN and passed `./labctl doctor`, including fixture
hash checks, before running the isolated CPU probe.

## Smallest useful experiment

**HYPOTHESIS:** Completed recorded PCM can be published as a temporary sample
resource, selected by a track and played by the stock renderer, without
creating a persistent sample file first.

1. Trace the user-facing sampling action through capture and stop to save,
   discard and assignment. Identify buffer owner, address, length, format,
   channel layout, allocation/release and the first persistent-sample write.
   Do not assume the entire recording already exists in reusable RAM.
2. Prove the publication/playback half with deterministic generated PCM and
   an explicitly allocated temporary resource. Compare it with the same PCM
   loaded through the stock file path under identical captured controls.
   This is a synthetic-fixture test, not proof of audio-input recording.
3. Connect actual recorder output. Publish complete sample pages before making
   the descriptor selectable, respecting synchronization and interpolation
   guard requirements. Measure stop-to-play availability; avoid promising zero
   latency when a CPU-to-DSP transfer may still be necessary.
4. Exercise actual assignment/trigger, pitch, reverse, loop and locks. Verify
   no persistent sample file is created before explicit save, using storage
   tracing that distinguishes sample writes from unrelated firmware activity.
5. Check empty/cancelled/full capture, replacement while referenced, machine
   switch, stop and project change. Do not recycle memory while a voice can
   still read it. Initially stop/detach before replacement, or retain the old
   allocation until users of it finish; freeze this choice before coding.
6. Add optional save through the normal persistence path and test conversion
   to a durable assignment. A failed save must retain the temporary audio.
   Project reload must not resurrect dangling pointers to volatile samples.

Retain exact-repeat PCM, stereo/channel checks, stock isolation, an unpublished
slot negative, allocation bounds and sample-storage write evidence. Pure
publication should match stock PCM when initialized with identical descriptor,
guard, control and voice state. Any mismatch needs investigation rather than
relaxed expected output. Capture remains a separate evidence level.

Proposed artifacts are a recorder-path note, `source.wav`, `control.dtfr`,
`stock.f32`, `temporary.f32`, allocation/publication and storage traces, and
`report.json` in a fresh ignored run directory. This is a proposed experiment,
not a frozen implementation contract. UI names and shortcuts remain open.

## Project save and temporary-sample lifetime: proposed behavior

The user raised project saving as an explicit design case. The recommendation
below is not yet an agreed or implemented contract. **Explicit Save Project
should preserve the audio needed to restore the saved project**, including
temporary recordings. Recording and playing remain immediate; choosing to
save the project becomes another way to keep the audio, alongside Save Sample.

Proposed sequence: retain a stable version of each required temporary sample,
write it to +Drive with an automatically assigned identity, obtain valid
persistent references, then commit the project state referencing those versions.
This does not imply embedding PCM in the project file or introducing a new
project format. Directory placement and naming remain open. Reuse an unchanged
saved version rather than creating another file on every save.

The proposed saved set includes the complete sample pool retained by the
project, with references in all saved patterns and sample locks accounted for;
it must not be inferred from the currently audible track assignments alone.
The exact stock serialization and reference traversal still need tracing.

| Case | Proposed behavior |
| --- | --- |
| Save Project with completed temporary recordings | Preserve those recordings and their assignments before reporting success; no per-take naming step is required. |
| Reload that project | Restore the saved audio and playback settings. A Flex track remains able to record or replace its temporary audio. Saving does not require changing the track's machine. |
| Record again after saving | Create a new working version. Keep the previous saved audio intact until a later successful save deliberately updates the saved state. |
| Save while recording or replacing a take | For the first version, defer completion until capture has finished and a stable take is available. Never serialize a buffer while it is changing. |
| Save As, duplicated tracks, or shared samples | Saved audio versions may be shared only while immutable. Recording into one working buffer must not overwrite another project's saved audio; ordinary track copies should follow the eventual documented sharing rule. |
| Sample write or project commit fails, including full storage | Keep the playable RAM version and previous saved project intact; report failure. Any newly written but unreferenced audio can be retained for later safe cleanup. |
| Switch/reload project with unsaved takes | Offer save, discard or cancel before dropping the live resource. Abrupt power loss can only restore the last successfully saved audio. |
| Automatic state saving, if integrated | Define separately from explicit Save Project; do not silently promise audio recovery or introduce a full sample write on every parameter edit. |

Only make the project refer to newly saved samples after their writes have
succeeded. Retain old backing files until reference ownership across projects
is known; eager cleanup could break an older project or Save As copy. Confirm
the existing commit/recovery mechanisms before claiming failure-safe behavior.

The next persistence investigation is therefore the OS 1.16 project-save and
reload boundary: sample-reference serialization, complete slot coverage, save
completion/error propagation, and whether the existing file/reference APIs
can promote a temporary resource without disturbing current playback. The
recorder probe does not establish any of those behaviors. A useful later test
is capture A, save, capture B, reload and recover A exactly; after a successful
second save, reload must recover B. Injected save failures must preserve A on
disk and B in the live session.

## Decision and remaining work

**UNRESOLVED:** Normal recorder PCM ownership and retention; general slot
lifetime and shared references; panel assignment; optional save and reload; compatible
slice/stretch metadata; input/resampling routing; downstream output and real
sequencer traversal; hardware timing and memory headroom. Existing Plaits
results do not answer these recorder/resource questions.

The [recorder boundary note](FLEX-LITE-RECORDER.md) contains fresh 1.16
disassembly and 16 exact-repeat synthetic save-consumer vectors plus an
open-failure control. The subsequent [RAM playback prototype](FLEX-LITE-RESULTS.md)
now demonstrates owned allocation, controlled CPU track assignment, stock
mono/stereo playback, exact file-path parity and bounded detachment/replacement
without sample storage operations. It uses synthetic PCM and host source hooks.
The next step is connecting completed recorder chunks to that resource. The
actual recorder's DSPI1 peer remains a separate emulator gap. A fresh recording
played and manipulated through the panel without saving remains the eventual
functional milestone.

This note follows the repository's lightweight engineering-note convention.
Broad novelty/cultural research and a full algorithm contract are not needed
to answer this feasibility question; complete the implementation contract only
after choosing the musical behavior. The playback follow-up has its own frozen
contract and offline voice-buffer audio checks. No hardware action, commit or
publication was performed.
