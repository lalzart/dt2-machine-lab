# Flex save / discard screen — OS 1.16 R2

Implemented and verified in the emulator on 2026-10-19. The user reported that
R1's save workflow worked as expected on their device; this new discard revision
has not been transferred or tested on hardware by the agent.

## Flow

Open SAMPLING on a track with an unsaved accepted take. An original waveform
icon, track heading, RAM status and two aligned action rows replace the earlier
text-only screen. UP/DOWN selects **Save to +Drive** or **Discard take**. Save is
the default; YES opens the existing filename editor. NO goes back.

Discard requires another YES on a confirmation that says **ALL USES IN PROJECT**
and **CANNOT BE UNDONE**. NO returns to Save without changing PCM or writing a
file. Confirming clears this take's project-pool aliases and loaded sample slots,
detaches matching active-track base assignments and restores recording. Other
track controls, engines and unrelated takes are preserved.

This is a take-wide destructive action. Inactive pattern/lock numeric slot
references retain normal stock empty-slot behavior; the audio is deliberately
removed from the project. Undo or clipboard references cannot restore the audio.
The current project's stock slot numbers may subsequently be assigned new samples.

## Memory and ownership

The action marks the take's immutable identity as discarded before allowing the
CPU audio source to be freed. Resource operations reject that tombstone. Active
reader/save pins, a source-retirement owner or queued USE reject the action with
**TAKE BUSY OR CHANGED / PLEASE TRY AGAIN**, without partial deletion.

The existing source-free primitive is reused only after this explicit deletion
has invalidated the take and removed current aliases. This extends its previous
failed-candidate use; it does not infer that a published take is unreferenced.
The permanent descriptor and issued ID remain reserved. **The 32 issued-take
limit per boot is unchanged.** No general garbage collector or ID recycling is
introduced. Project persistence scrubs references to explicitly discarded IDs
that undo or a clipboard might restore, instead of attempting to save freed PCM.

## Verification

- **262 source tests pass** and scoped lint passes. Native tests cover all sample
  engines/tracks, selection/confirmation/cancel, context changes, shared aliases,
  busy/changed/saved captures, preserved ABI/SR, exactly-once source freeing,
  stale handles after source-address reuse and restored tombstone persistence.
- The exact packaged CPU's native UI flow records T1 and T9, adds a shared T3
  assignment as an explicit fixture, cancels discard, injects an outstanding
  reader and checks rejection, then discards successfully. The original allocator
  frees the 12,624-byte source allocation exactly once; net free heap increases
  7,424 bytes with the confirmation UI still allocated. No filesystem writes
  occur during discard. T1's PCM and all unrelated controls remain exact. T9 can
  record, USE and save again. Recorder and sector peers are modeled.
- A separate exact-package native check opens a handle before discard, rejects
  its later read without modifying the destination, restores a discarded
  reference as an undo/clipboard fixture, and successfully executes the original
  project writer. An independent unmodified stock CPU decodes that project:
  discarded slots remain empty, T9 is unassigned, and T1's surviving saved sample
  reloads with exact PCM.
- The earlier full save-screen flow still passes, including Stretch/Slice,
  track changes, cancel, injected open failure and independent stock PCM reload.
- Native reset/ready, initialized segments/BSS/canaries and actual MAIN DSP
  depacking pass. The overflowing withdrawn stream still fails as a negative.
  DSP bytes are unchanged. Omitting the save-screen flag reproduces the previous
  default any-track MAIN exactly. CPU, DSP and container builds repeat exactly.

[Actual screenshot gallery](../out/runs/flex-discard-packaged-flow-20261019-01/flow.html)
contains 12 unedited guest-framebuffer captures. PNG hashes and raw frames are
verified; cancellation returns the exact original menu. The existing save flow
has 16 additional actual captures. Full reports, reproduction runners, logs and
frozen sources are in `out/runs/flex-discard-verification-20261019-01/` and
[FLEX-DISCARD-VERIFICATION.json](FLEX-DISCARD-VERIFICATION.json).

## Package and reproduction

`out/runs/flex-discard-package-20261019-01/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_FLEX_SAVE_SCREEN_R2_DISCARD_OS1.16.syx`

SYX SHA-256: `b232f48b67b91f4bed237005370e2787ca555af15174481c366fe5da0afbb7e4`

MAIN SHA-256: `03c04d4532363b69ddf7e03455d8229e388942ed624f48224c956e303f68cd2f`

DSP SHA-256, unchanged: `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2`

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/FRESH-PACKAGE \
  --all-features --any-track --flex-save-screen \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-flex-discard.py out/runs/FRESH-DISCARD \
  --package out/runs/FRESH-PACKAGE \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
```

Physical DSP slot-clear timing, concurrent playback, save latency and worst-case
memory headroom remain unverified. This is an experimental OS; no hardware send,
Git staging, commit, push or publication was performed.
