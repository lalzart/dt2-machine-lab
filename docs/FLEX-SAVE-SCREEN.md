# Flex save screen prototype — OS 1.16

The user approved this flow on 2026-10-19: an accepted, unsaved Flex recording
on the selected track opens a visible save screen through SAMPLING. Changing
the sample playback machine or selecting another track must not lose the take
or its saved status. New recording on that track remains blocked until saving
succeeds. NO exits without saving; playback and parameter editing remain usable.

This is native CPU/UI work. The sample player, audio processing, existing
recording format and DSP image are outside this change. No hardware transfer,
commit or publication is authorized. Existing builds must remain reproducible
without the opt-in feature.

## State and interaction

- Identify the accepted take from the selected track's base sample assignment,
  independently of its sample playback machine. Sequencer sample locks do not
  retarget the save dialog. Ordinary samples, MIDI and synthesis tracks retain
  their stock sampling entry.
- The recording identity owns saved status. Tracks that share the same take
  share its successful save. A track change never clears another take's state.
- An unsaved take opens a native screen with the track number, unsaved status,
  YES to save to +Drive, and NO to go back. YES opens the original filename
  editor with a captured take/project identity. No new shortcut is required.
- Cancel, collision, changed project, allocation or write failure preserve the
  take and its unsaved status. No overwrite and no silent discard are added.
- A verified successful native save promotes references using the existing
  save transaction. The next SAMPLING entry returns to the original recorder.
  Existing successful project-save exports also count as saved.
- The block applies to the selected track. Other tracks remain available for
  recording. The actual start routes must be guarded as well as screen entry.
- The recorder's remembered USE destination must not send a newly permitted
  recording back to a different blocked track.

## Acceptance

Use a fresh ignored output directory and authenticate stock OS 1.16 MAIN and
pinned DigiKit. Preserve pre-edit sources in
`out/runs/flex-save-screen-baseline-20261019-01/`.

Execute native CPU checks for machine-independent lookup, unsaved/saved state,
track isolation and shared aliases; keep existing save failure/ABI negatives.
Drive actual firmware UI through record, trim, USE, machine change, track away
and back, save screen, cancel, filename editor, failed save, successful save,
and restored recorder. Capture the guest framebuffer at each relevant step;
screenshots must not be mockups or composited UI. Independently reload saved
PCM with stock firmware, verify playback controls remain unchanged, run the
source suite and required SINE replay, and verify default build parity.

Passing CPU and prepared-emulator UI checks do not establish physical controls,
real-time storage latency, audio continuity, or hardware recording behavior.
