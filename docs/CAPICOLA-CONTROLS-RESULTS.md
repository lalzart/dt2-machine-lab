# Capicola panel-to-voice integration

OS 1.16, 2026-10-08. **EVIDENCE:** the local combined Plaits/Flex/Capicola prototype now selects CAPICOLA through the emulator panel, transports RATE edits, loads the captured sample through stock DSP callbacks, automatically prepares its bank and renders the whole triggered sample. The 12-second mono input limit remains unchanged. This is native instruction execution in the Mac emulator, not a hardware-tested OS package.

The selector exposes TUNE, RATE, SAMP and LEV on track 1. CPU checks cover 13 descriptor dispatch cases, 170 permission cases and 1,024 restore-field cases. The nine-entry selector needed both allocation and capacity raised to 36 bytes; merely enlarging its tables left the original 28-byte allocation too small. The patch guards and changes both instructions. Prepared eight-entry widgets cannot validate this extension: the capture resumes an early checkpoint and runs the stock initialization before exercising the panel.

`out/runs/capicola-panel-08/capture.json` passes panel selection, real encoder RATE endpoints and outgoing type-8 trigger checks, with no faulted pages. It reuses the exact initialized checkpoint in `capicola-panel-05`; that earlier run completed initialization but its panel check failed on a startup notification. The passing script dismisses that notification before opening the selector. This is not a full reset boot, project persistence or bidirectional CPU/DSP integration test; CPU capture uses the existing clock model and zero DSP replies.

`out/runs/capicola-wire-01/report.json` rebuilds the exact CPU/DSP images and replays 1,620 captured LP0 transfers through stock SHARC callbacks. Stock voice assignment picks slot 7, pointer `0x8422ba08`, 2,400 mono PCM frames at 48 kHz. No sample pointers, bank keys, voice trigger flags or sample metadata are injected. The only test-side memory mapping is zero external RAM; its sample contents come from the captured transfers. The LP0 callback/resubmission and SSI completion are modeled by the harness.

Automatic preparation publishes the exact 2,760-byte host-reference bank after 151 further audio blocks. A later captured trigger produces 1,280 output frames, including the completed silent tail. Both mono lanes match exactly; maximum host/native error is `1.4901161e-8`, RMS `1.0851376e-9`. The captured settings produce pitch `0.8405170`, advance `1.9999380` and gain `0.1085587`.

The initial full-path probe inspected the source too early and compared playback one block early. Stock firmware applies the trigger on the following block. The regression now explicitly asserts that fixed 32-sample silent delay before comparing the entire output; it does not search for an alignment. A deliberately uncorrected comparison fails by maximum `0.06667`, RMS `0.02110`. This resolved the apparent sample-pointer failure without changing production DSP code or loosening tolerances.

The full-wire run observed at most 405,503 emulator instructions per block and 1,378 per LP0 callback. These are not physical cycle counts, deadline margins or measurements of incremental Capicola load. For preparation costs, source-lifetime guards and stock/Plaits comparisons, see [automatic preparation results](CAPICOLA-AUTOMATIC-PREP-RESULTS.md).

**Remaining limitations:** one mono bank on track 1, with approximately twice the sample duration needed for preparation (about 24 seconds for the maximum 12-second input). The first trigger establishes the source; playback remains silent while preparing and requires another trigger after readiness. Readiness UI, project persistence, stereo, other tracks, tempo matching and loop/start/end controls remain incomplete. TUNE saturates at the supported +/-12-semitone range despite its wider stock display. The bank has an explicit 8 MiB pool reservation, but full runtime ownership of the experimental L2 code/state arena, final-mix playback and physical timing still need validation. No hardware image was sent or installed.

Exact candidate hashes:

- MAIN: `82b17a4f9068f47bef1b272205e3dc153e057fdb67a52db6a9726e5f09ceb8da`
- BLOB: `ce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f`

Reproduce using fresh output names and the configured private fixtures:

```sh
python3 scripts/check-capicola-controls.py out/runs/capicola-cpu-check
python3 scripts/check-capicola-automatic.py out/runs/capicola-dsp-check --controls
python3 scripts/capture-capicola.py out/runs/capicola-panel-check
python3 scripts/check-capicola-wire.py out/runs/capicola-wire-check \
  --capture out/runs/capicola-panel-check --sample-load out/runs/capicola-panel-check
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The configured-runtime suite passes 60 tests. SINE replay passed at `out/runs/20261008T021717Z-test-d047a388/manifest.json`; subsequent harness and documentation changes do not change that DSP build. Failed diagnostic runs are retained. Source fingerprints in each report describe the files at that run; later result/contract documentation updates change those fingerprints without changing the verified image hashes.
