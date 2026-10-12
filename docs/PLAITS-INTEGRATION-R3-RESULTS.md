# Plaits R3 integration results

R3 is a separate local `integration` build for Digitakt II OS 1.16. The existing `controls` build still reproduces R2 exactly. These are emulator and compiled voice-buffer results; R3 has not been flashed or heard on the physical Digitakt II.

## What changed

- LEN is a dedicated duration parameter, displayed as **100–12,800 ms**. Its metadata default is 1,000 ms. The DSP uses that duration as a gate; it does not extend an engine's intrinsic drum decay. Duration and MODEL are read on a new trigger.
- MODEL displays **V-ANALOG, 2-OP FM, BASSDRUM, WAVESHAP, HARMONIC, GRANULAR**. These abbreviate the existing Virtual Analog, two-operator FM, Analog Bass Drum, Waveshaping, Harmonic and Granular Formant engines.
- The modulation destination list exposes **Harmonics, Timbre, Morph, Duration**. HARM/TIMB/MORP modulate continuously; Duration changes take effect on the next trigger. TUNE/MODEL/LEV are not added as continuous LFO targets in this revision.
- The original permission mechanism restricts new Plaits selection to **track 1**. Choosing another host track is deferred. This does not migrate old R2 projects that already contain Plaits on unsupported tracks.

The CPU required a physical-mirror-to-parameter reverse map: the stock cache has only seven machine rows. Simply extending metadata or changing the owner check did not populate the LFO menu. The exploratory owner-check patch was removed once the actual path was identified. Timbre also inherited a non-modulatable sample-slot flag, and its late raw-value repair erased LFO modulation. R3 gives it the modulation flag and bypasses the late sampler repack only for track 1/type 7. All other types/tracks follow the stock path.

Added code and data occupy guarded padding below the reset-clear boundary. The CPU builder first reproduces and audits exact R2, then checks every R3 delta and decodes added code with the explicit ColdFire subset audit. Dependencies and synthesis cores are unchanged. Flex Lite is not included.

## Verification

- CPU: 3,384 sparse-resolver/register cases, existing metadata/range/default/restore checks, 48 early transport cases, 640 repack cases, 4,536 reverse-map cases, and 153 track-permission cases. Stock rows remain unchanged except the existing dedicated MODEL row's formatter. Real stock `sprintf` produces all six names, invalid-model fallback, and duration endpoints.
- Panel: duration minimum/maximum and named MODEL extremes; actual LFO 1 selection for each macro. HARM produced 907 distinct values, TIMB 779, MORP 913, with the other macros constant. Selecting None stops modulation. Attempting Plaits on track 16 is rejected and track 1 remains Plaits. Zero faulted pages.
- Compiled SHARC: all six engines preserve baseline PCM over the comparison window. Both lanes pass duration limits, terminal fades, expiry and retrigger. A contiguous 100 ms render repeats exactly. Long-duration expiry checks place state near the endpoint; they are not a 12.8-second real-time performance measurement.
- Pattern: stored HARM/TIMB/MORP/LEN locks, two playback loops, stop/edit/restart and base-value restoration pass with zero faulted pages. The separate SINE regression passes exact-repeat, stock compatibility and negative controls.
- Source harness: 22 unit tests pass; changed Python files pass Ruff and the diff whitespace check.

CPU report: `out/runs/integration-r3-cpu-final-02/report.json`.
Panel report and images: `out/runs/integration-r3-controls-final-01/capture.json`.
DSP report: `out/runs/integration-r3-dsp-final-02/report.json`.
Pattern report: `out/runs/integration-r3-pattern-final-02/capture.json`.
SINE report: `out/runs/20261006T124547Z-test-c3ea11d1/manifest.json`.

MAIN SHA-256: `6f5a9df5f1bf17c002c7755e1682051aff9e2d990238ec62722c5a459e8e9543`.
BLOB SHA-256: `b52b60c208cd3a9a9b88dd4db6ee0895754970cb34b48efccc2646f134159b3f`.

## Reproduce

Use fresh output directory names:

```sh
./labctl doctor
python3 scripts/check-plaits-integration.py out/runs/r3-cpu-check
python3 scripts/check-plaits-duration.py out/runs/r3-duration-check
python3 scripts/capture-pattern.py out/runs/r3-controls --machine integration --integration-controls
python3 scripts/capture-pattern.py out/runs/r3-pattern --machine integration
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The two check scripts also build the MAIN and BLOB images respectively. No SysEx upload file is released by this workflow. The existing R2 upload preparation retains its exact-image gates; it must not silently package an R3 image. A hardware handoff needs R3-specific container, firmware-depacker and startup checks, followed by a separate user-controlled hardware trial.
