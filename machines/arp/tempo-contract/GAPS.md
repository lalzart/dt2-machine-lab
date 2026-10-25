# Tempo/rates gap register

Closed within the bounded emulator scope: native tempo/rate arithmetic, G text selector/focus, v1 import/v2 save, mixed-version conflict safety, native recording/menu save, checkpoint-resumed menu recall/replay, source/SINE regressions, repeat package, original depacker and bounded startup.

Open/deferred:
- New-candidate hardware, listening, physical jitter/headroom and full playable cold boot.
- External clock/swing, other tracks, latch/MIDI input and broader copy/undo/export/companion cleanup lifecycle.
- Dense32nd recording and retaining a pre-held chord through REC+PLAY. Verified workflow starts live recording before the chord.
- Some incomplete stock redraw frames also occur in the earlier D1 baseline; this is not a proven device display fault or a completed display-pipeline repair.
- Save/load/replay evidence spans retained emulator checkpoints. The corrected fresh-run harness path was not rerun uninterrupted end to end.
- No new arp PCM/listening validation; SINE voice-buffer replay is a separate regression.

At300 BPM1/32, native UI delivery in the bounded run preempts two measured half gates at the following onset. The engine preserves monophony and does not emit catch-up bursts; physical timing remains unmeasured.
