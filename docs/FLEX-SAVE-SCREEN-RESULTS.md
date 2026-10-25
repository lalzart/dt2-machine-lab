# Flex save screen — native OS 1.16 candidate

Implemented and emulator-validated on 2026-10-19. An unsaved accepted Flex take
now opens a visible save screen through **SAMPLING**, independently of its
stock sample playback machine. **YES** opens the original filename editor;
**NO** goes back. Cancel or failure preserves the take and recording block.
Successful saving restores the normal recorder for that take. Other tracks
remain available, and shared aliases inherit the same take's saved status.

All six stock sample playback machines (IDs 0–4 and 6) work with the lookup and
USE assignment. SLICE is identity 6; display position 4 is not machine ID 4.
MIDI, synthesis and ordinary samples retain stock sampling entry. The block
follows the selected track's base sample assignment, not sequencer sample locks.
Existing project-save exports count as saved. Changing unrelated persistence
policy, reclaiming abandoned takes and increasing the 32-identity limit are
outside this change.

Manual and armed starts are guarded, and USE cannot overwrite an unsaved
destination after a track switch. New USE follows the selected track instead
of the recorder's last destination. Dialog actions occur on button release so
the opening YES gesture cannot also confirm the filename.

## Actual screenshots

The [complete flow gallery](../out/runs/flex-save-screen-packaged-flow-20261019-01/flow.html)
contains 16 unedited guest-framebuffer captures, including two pending tracks,
STRETCH/SLICE selection, cancellation, injected storage-open failure, named
save and restored recording. Raw framebuffer bytes and image hashes are kept
beside the PNGs. These screenshots come from the packaged candidate's actual
CPU image, not a host-drawn UI.

- [Return to T1: save screen](../out/runs/flex-save-screen-packaged-flow-20261019-01/05-return-to-track1-save.png)
- [Filename editor](../out/runs/flex-save-screen-packaged-flow-20261019-01/11-named-take.png)
- [Successful +Drive save](../out/runs/flex-save-screen-packaged-flow-20261019-01/12-saved-to-plusdrive.png)
- [T2 remains unsaved](../out/runs/flex-save-screen-packaged-flow-20261019-01/13-track2-still-unsaved.png)
- [T1 recorder unlocked](../out/runs/flex-save-screen-packaged-flow-20261019-01/14-track1-recorder-unlocked.png)

## Checks

- 255 source tests pass, including eight native save-screen tests covering all
  tracks/sample engines, shared aliases, captured destinations, recording and
  overwrite guards, key edges and ordinary-track fallback. Scoped lint passes.
- The packaged native panel session records two separate takes, switches T1 to
  STRETCH and T2 to SLICE through the stock menu, and returns to T1's save screen.
  Cancel writes nothing. A failed filesystem open leaves the exact take intact
  and the guard active. Saving `/recorded/GLEX` preserves both machines and all
  track controls, retires the saved CPU source normally, leaves T2 unsaved and
  permits another record/trim/USE cycle on STRETCH. An independent stock CPU
  reloads the saved sample with exact PCM. No fault pages are touched.
- Native reset/ready, segment initialization, BSS and boundary canaries pass.
  The CPU-only boot checker does not establish a coupled CPU/DSP startup.
- The actual MAIN DSP depacker decodes the candidate's 626,560 bytes with its
  one-byte command inside the original 1 MiB allocation; the canary survives.
  The withdrawn overflowing DSP stream reproduces a 265,885-byte overflow on
  the same candidate CPU as a causal negative. The existing zero-fill-repair
  script requires the entire CPU to equal that withdrawn build, so its direct
  invocation is inapplicable to this UI change. The preserved verification
  runner reuses its unchanged `execute` function with the candidate CPU.
- Source-frozen SINE replay passes. The DSP image is byte-identical to the
  accepted any-track R2 image. Omitting the new flag reproduces the accepted
  any-track MAIN exactly; the standalone managed Flex MAIN also retains its
  original hash.

Reports and frozen sources:
`out/runs/flex-save-screen-verification-20261019-01/`,
`out/runs/flex-save-screen-packaged-flow-20261019-01/report.json`,
`out/runs/flex-save-screen-boot-20261019-01/report.json`,
`out/runs/flex-save-screen-staging-20261019-02/report.json`, and
`out/runs/20261019T090338Z-test-344d0c5b/manifest.json`.

## Candidate and reproduction

The opt-in candidate is
`out/runs/flex-save-screen-package-20261019-01/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_FLEX_SAVE_SCREEN_R1_OS1.16.syx`.

| Component | SHA-256 |
| --- | --- |
| SYX | `7809f0d24859bcc0938b46fffd8bd36b3eb23552d151c1e13a6b54f4f4f20c12` |
| MAIN | `2c1a30a11a78450435808ce67c2cb44f5b59d904b1a2e43c7f5831b0e2e0a505` |
| DSP, unchanged | `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2` |

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/FRESH-PACKAGE \
  --all-features --any-track --flex-save-screen \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-flex-save-screen.py out/runs/FRESH-FLOW \
  --package out/runs/FRESH-PACKAGE \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
```

Recorder input and sector I/O remain external models. Physical controls,
internal audio capture, storage latency, audio continuity and hardware operation
are unverified. No hardware transfer, Git staging, commit, push or publication
was performed. Exploratory runs are retained, including the early YES-edge
auto-confirm bug, a wrong SLICE identity assertion, and premature dialog captures.
