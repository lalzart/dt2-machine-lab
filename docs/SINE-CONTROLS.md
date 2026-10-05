# SINE controls and parameter locks

2026-10-05. The `sine-controls` experiment connects three inherited SRC controls
to the new oscillator on track 1. The original fixed SINE remains the baseline.
Both use the existing SINE CPU image; the controls variant changes SHARC code.

| Control | CPU frame word | Oscillator behavior |
| --- | --- | --- |
| A / TUNE | `0xda` | Pitch, combined with TRIG note at `0x02`. Note 60 and TUNE wire value 16384 give 440 Hz. |
| F / LEN | `0xe8` | Duration in source samples: `clamp(FIX(raw * 25/32), 960, 48000)`, at 96 kHz. |
| H / LEV | `0xec` | Linear gain: `min(raw, 32768) / 262144`, maximum 0.125. |

These values latch at each trigger. Sustained knob sweeps, LFO destinations,
velocity response and slide behavior are not implemented. LEN still has the
borrowed slice display; its displayed units are not milliseconds. CPU smoothing
means a freshly turned knob need not have reached its final transmitted value.
Pitch uses a 129-entry interpolated increment table; code is 876 bytes.

## What was observed

Real panel inputs selected SINE, entered grid recording and stored locks on
step 1. Step previews used held TRIG + YES. The base sound remained unchanged.
Previewing steps **1, 5, 1** transmitted these values:

| Step | TUNE | LEN | LEV | Rendered pitch | Duration setting | Source gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1, locked | 9576 | 15616 | 5418 | 94.733 Hz | 127.083 ms | 0.020668 |
| 5, unlocked | 15614 | 30720 | 28458 | 369.832 Hz | 250 ms | 0.108558 |
| 1, recalled | 9576 | 15616 | 5418 | 94.733 Hz | 127.083 ms | 0.020668 |

The capture is in `out/runs/controls-cpu-preview-fast/`; its three-control
checkpoint is `out/runs/controls-cpu-lock-fast/locked-ready.snap`. The renderer
reads those CPU control words directly. No synthetic parameter values are used.
The cleaned capture script reproduced the same frame bytes in
`out/runs/controls-final-capture/`. Audio and the measurement report are in
[`out/runs/controls-render-preview/`](../out/runs/controls-render-preview/).
The two locked notes matched sample for sample over their shared 3,328-sample
window; the final note completed its 12,200-sample envelope.
PLAY startup also emitted the locked values and rendered the complete short
tone (`out/runs/controls-render-play/`). The bounded PLAY run emitted only the
first track-1 note: continuous pattern traversal and restoration during normal
playback remain unverified. The three-step comparison above is a preview test.

Audio is taken from the two track-1 voice work buffers and decimated to 48 kHz.
Other tracks' event bits are masked during replay: letting the factory pattern
trigger them encountered an unsupported native Type7a predicate at `0x1cbc93`.
The raw CPU capture is preserved, and track-1 controls are unchanged. This is
prepared-state emulator evidence, not final-mix, hardware or CPU-load proof.

## Repeat the experiment

The scripts select the configured patched Python automatically. Use fresh
output names; existing directories are refused.

```sh
./labctl doctor
python3 scripts/capture-sine-controls.py out/runs/my-lock-capture \
  --locked-snapshot out/runs/controls-cpu-lock-fast/locked-ready.snap
python3 scripts/render-sine-controls.py out/runs/my-lock-capture \
  out/runs/my-lock-render
```

The renderer writes `controls.wav`, raw source/stereo PCM, `render.json`, and
the candidate `SINE_BLOB.bin`. Reports include control values, actual latched
state, measured frequency, hashes and scope. Short preview intervals retrigger
the oscillator before every note finishes; duration settings are not all full
audible note durations in the combined clip.

`.local/cpu-inputs.json` references the existing private `syx`, `sections`,
`main`, `snapshot` and `card` inputs from the preserved workspace. Omitting
`--locked-snapshot` performs the panel preparation again from that original
ready state. The final recapture uses the saved full-state checkpoint; clean
fixture generation from original firmware remains a separate milestone.

Two practical findings matter for further work:

- The GUI dwell gate throttles encoder messages too. Isolated slow messages
  were ineffective for this experiment. The script retains button dwell but
  delivers twelve encoder messages at separate, shorter chunk boundaries.
  Exact delivered input clocks are printed in the log.
- Save CPU checkpoints with `save_longrun`, including timers and peripherals.
  A bare RAM/register snapshot lost timer state in a discarded diagnostic run.

Verification stays local to the experiment. The existing eight harness tests
and full fixed-SINE replay suite passed; no new broad test framework or new
golden PCM expectation was added. The unchanged baseline suite report is
`out/runs/20261005T044235Z-test-d9a483b9/manifest.json`.
