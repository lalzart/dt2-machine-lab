# Flex discard and save screen — OS 1.16

User-authorized CPU/UI change on 2026-10-19. Keep the existing managed Flex
save path and all playback engines. No DSP edits, hardware transfer or Git staging.

The native 128x64 screen gets an original sample/waveform icon, track heading,
clear Save to +Drive / Discard take rows, selection marker and navigation hint.
R3 cleanup, explicitly requested by the user on 2026-10-19: Save is the default.
Selecting Discard and pressing YES deletes immediately, with no confirmation
screen. The UP/DN navigation hint is removed; YES/NO hints remain. This supersedes
R2's confirmation requirement. Discard still removes the take throughout the
current project. NO goes back without changing audio. Selection resets on
take/project changes so an old selection cannot discard a different take.

Explicit discard invalidates the immutable take identity before releasing its
CPU source, clears exact matching project-pool and loaded aliases through stock
slot unload, and retains the descriptor as a tombstone. New reads of discarded
identities fail; issued IDs are not recycled and the 32-take limit is unchanged.
Active source readers/savers, a retirement owner or queued USE reject discard
without mutation, with a visible busy result. No save or disk write is needed.
Other takes and track controls remain unchanged. Future project persistence
normalizes restored tombstone references to empty rather than saving missing PCM.
This intentionally invalidates the discarded audio, including undo/clipboard
references; it is not automatic reclamation of apparently unused recordings.

Acceptance: native instructions for cancel/context/busy/alias/tombstone cases;
actual guest UI on T9 with icon, back, immediate discard and busy rejection; original
allocator frees source, stale handle cannot read freed/reused PCM, project save
continues, another track survives, recorder reopens and accepts a new take.
Full source suite, existing save flow, reproducible OS build and reset check.
Screenshots must be unedited guest framebuffers. Peripheral peers remain modeled;
physical timing and general project-epoch/identity recycling remain unverified.
