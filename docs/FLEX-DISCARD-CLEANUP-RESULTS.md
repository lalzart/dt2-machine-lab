# Flex save / discard cleanup — OS 1.16 R3

The user requested removal of the discard confirmation and UP/DN hint on
2026-10-19. Selecting **Discard take** and pressing **YES** now executes discard
on that first button release. **NO** goes back. Save stays the default, and the
footer reads **YES:OK  NO:BACK**. The waveform icon, action spacing and selection
outline remain. The unused confirmation renderer, strings and state word are
removed. The existing completion/busy result dialogs remain.

The take-wide deletion worker, reader guards, source freeing and persistence
cleanup are unchanged. The 32 issued-identity limit is unchanged. R2's explicit
confirmation requirement is superseded by this user request; prior artifacts
and [R2 results](FLEX-DISCARD-RESULTS.md) remain preserved.

The package is `out/runs/flex-discard-cleanup-package-20261019-01/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_FLEX_SAVE_SCREEN_R3_DISCARD_OS1.16.syx`.

SYX SHA-256: `53d6ca6ee1a84cc5eed587f7baa44470e79a852a8ea8d811d58f7f31c136d0c9`

MAIN SHA-256: `20b7f144d801504a2eabe0bd05846802e742a95f2119faca4c38f72382325088`

DSP SHA-256: `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2`

Build with the same `--all-features --any-track --flex-save-screen` flags.
Reports and frozen sources are in
`out/runs/flex-discard-cleanup-verification-20261019-01/`. The actual packaged
[flow gallery](../out/runs/flex-discard-cleanup-flow-20261019-01/flow.html)
shows the simpler menu and first-YES discard. Screenshots are unedited guest
framebuffers. Recorder, storage and DSP peers remain modeled; this revision has
not been transferred to or tested on hardware by the agent.

Validation: **262 tests pass**, scoped lint passes, and the exact packaged native
UI confirms first-YES discard, busy-reader rejection, no discard file writes,
exactly-once native source freeing, unrelated take preservation, recording again
and successful named save. Native reset/ready and original project save plus
independent stock reload pass. The DSP matches R2 exactly; build repeats match.
See [verification](FLEX-DISCARD-CLEANUP-VERIFICATION.json).
