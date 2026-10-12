# Capicola automatic preparation results

OS1.16, local emulator prototype, 2026-10-08. Automatic preparation and the selector/control overlay now build together as `capicola-controls`. The earlier `capicola-owned` image still reproduces exactly.

The DSP automatically identifies the track1 mono sample, counts and writes its bank in 32-frame slices after normal audio blocks, and publishes only the finished bank. Page transfers, slot resets (including the stock negative-offset sentinel), and the sample-end guard copy invalidate overlapping source lifetimes. The interrupt handlers change publication/epoch flags; analysis and bank mutation remain serialized with rendering in the audio task. The guard-copy hook conservatively protects16 bytes; direct native inspection observed10 bytes copied by the stock routine.

`out/runs/capicola-controls-dsp-02/report.json` passed exact repeated builds, exact host/native keys for two-tone and dense PCM, same-address reload, reset, overlapping page/guard writes, unrelated-page preservation, invalid metadata, mono rejection, stale epochs, native frame-driven publication, six control mapping cases, and46 stock/Plaits frame comparisons. The1024-frame fixture publishes after67 frames, entirely through the native block-completion hook. Its prepared audio differs from the host oracle by at most1.49e-8. A separate captured CPU sample-transfer replay passed all1620 LP0 callbacks; the [completed panel-to-voice result](CAPICOLA-CONTROLS-RESULTS.md) is recorded separately.

Observed preparation calls cost at most7940 emulator instructions for two-tone and25500 for seeded dense noise at32 input frames per slice. These are instruction counts, not DSP cycle or physical deadline measurements. The full candidate frame maximum in that fixture was239906 instructions; the302398-instruction stock/Plaits comparison maximum uses different machine conditions and must not be presented as a measured speedup or incremental load percentage.

The current schedule takes approximately twice the sample duration to prepare: about24 seconds for the maximum12-second input if every audio block runs. Playback is silent while preparing and starts on a later trigger. No trigger is queued. This is a deliberate measurable prototype schedule, not a final loading-time target. Hardware deadline measurements are required before increasing the per-block budget.

The bank uses the earlier8MiB reservation carved from the400MiB sample pool, leaving392MiB. Input capacity remains576000 mono frames at48kHz. One bank serves the two track1 lanes. Other tracks, stereo, tempo-synchronized stretching, looping/start/end controls, readiness feedback, project persistence and physical listening are not complete.

The compiled combined BLOB hash for this check is `ce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f`. Code/state placement outside the reserved bank remains the experimental L2 arena; disjoint stock loader segments are not proof of runtime firmware ownership. No hardware-ready package or upload follows from this test.

Reproduce with fresh output names:

```sh
python3 scripts/check-capicola-automatic.py out/runs/capicola-dsp-check --controls
python3 scripts/check-capicola-controls.py out/runs/capicola-cpu-check
python3 scripts/capture-capicola.py out/runs/capicola-panel-check
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The configured-runtime unit suite passed60 tests. SINE regression passed at `out/runs/20261008T021717Z-test-d047a388/manifest.json`. Later changes to the capture script concern checkpoint preparation and panel test gestures; they do not alter the compiled DSP or SINE implementation.
