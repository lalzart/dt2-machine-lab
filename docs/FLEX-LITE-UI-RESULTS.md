# Flex Lite sampling in the emulator

**EVIDENCE — 2026-10-06, OS 1.16:** local emulator prototype. Implements the approved
[remembered-track flow](FLEX-LITE-UI.md) using the original recorder panel and
stock ONESHOT playback. This builds on the [RAM loader experiment](FLEX-LITE-RESULTS.md).

## Try it

From the machine-lab directory:

```sh
python3 scripts/try-flex-lite.py
# Or supply simulated input:
python3 scripts/try-flex-lite.py --input /absolute/path/input.wav
```

The launcher checks pinned dependencies and fixture hashes, warms up the
stock checkpoint, and opens a bounded window with the real emulator panel.
Startup takes several seconds. Every launch gets a fresh ignored run directory.
The default window closes after 15 minutes; `--window-seconds` accepts 10–1800.

1. Leave the destination on ONESHOT. The default is track 1.
2. Press **SAMPLING**, then **YES** to start recording.
3. Press **YES** to stop. E/H adjust the trim boundaries through the original
   firmware; its encoder deadband can require several knob movements.
4. The trim screen reads **Y:USE**. Press **YES** to assign the temporary take
   and return to SRC. There is no naming or sample-save dialog in this path.
5. Return to **SAMPLING** and repeat. The destination stays remembered even
   if another track is selected. The current sample changes only on USE.
6. **FUNC + NO** discards the candidate and leaves the accepted take assigned.
   The recorder is then ready for YES to start another take.

The surrounding window shows the remembered track and `TEMP001`, `TEMP002`,
etc. These host labels supplement the native SRC sample-slot display; this
prototype does not add a native TEMP badge. **Remember selected track next**
lets the next recording choose a new destination. **Input WAV…** changes the
simulated source when no recording/candidate is pending.

**Render / listen to take** captures a real pad trigger, renders original
SHARC voice audio twice, verifies exact repeat, and plays the completed WAV.
It previews approximately the first second at most, with a short tail for
short takes. It is buffered and may take time to finish. Long samples, slowed
playback and loops may continue beyond this preview. Native recorder
FUNC + YES preview is outside the implemented audio path.

## What is implemented

- An opt-in lab adapter; no edits to dependency checkouts or firmware files.
- Original panel dispatch, recorder states, trim processing, chunk wrapper,
  loader, allocation, channel packing and track refresh execute in the CPU
  emulator. Version-specific hook/string sites are guarded.
- The save action is intercepted before the stock save-progress view. USE is
  serviced between worker chunks with the interrupted CPU context restored.
- A completed take is copied while the recorder lock is held. Each response
  is deliberately poisoned after unlock; accepted PCM must still match exactly.
- A fresh normal sample slot is published before assignment. The rest of the
  destination's 0x450-byte track record must remain byte-identical.
- Old allocations remain available throughout this bounded session. Up to 32
  temporary source identities are allowed; rejected candidates remain retryable.
- Incompatible machines are rejected before allocation. Capacity failure
  preserves the previous assignment and completed candidate.

The recorder input is a **WAV service model**: 48 kHz PCM16 mono/stereo,
141–480000 frames (up to 10 seconds). Every recording starts at the beginning
of the selected WAV and advances on emulated sample-clock ticks. While the
window is recording, its worker advances between gestures; this is slower
than real time. EOF caps the take. The normalization command is acknowledged
without changing PCM; automatic normalization is not implemented. Waveform
responses use signed integer extrema, scaled by the native display code.

## Retained verification

| Run | Observed result |
| --- | --- |
| [`flex-ui-stereo-01`](../out/runs/flex-ui-stereo-01/report.json) | PASS: real track-1 record/stop/trim/use; 3120 recorded frames trimmed to [86, 3034); discard, destination retention, fresh replacement, injected capacity failure and successful retry. |
| [`flex-ui-mono-t3-02`](../out/runs/flex-ui-mono-t3-02/report.json) | PASS: mono on track 3, both trim boundaries, the same replacement/cancel/retry checks, unsupported-machine preservation, actual pad-slot transport and exact-repeat original DSP voice audio. |
| [`flex-ui-preservation-01`](../out/runs/flex-ui-preservation-01/report.json) | PASS: all 17664 bytes of the 16 native track records remain identical while a replacement is a candidate and after it is discarded. The standalone check is retained beside its report. |
| [`flex-ui-stock-save-02`](../out/runs/flex-ui-stock-save-02/report.json) | PASS: disabling USE reaches the original Y:SAVE / PLEASE WAIT stage and assigns no temporary sample. Naming/completed storage are not claimed. |
| [`flex-ui-window-01`](../out/runs/flex-ui-window-01/report.json) | The native Tk window initialized, ran for its 10-second bound and closed without CPU faults. Mac was locked, so desktop mouse click-through and visual layout inspection were unavailable. |
| [`source tests`](../out/flex-ui-source-tests.log) | 17 tests pass, including chunk boundaries, immutable accepted PCM, invalid requests, clock wrap, EOF, WAV format and signed channel extrema. |
| [`SINE regression`](../out/runs/20261006T081256Z-test-92b0a30b/manifest.json) | PASS: required prepared-fixture replay, including stock isolation, exact repeat and negative controls. |

The stereo run retains zero CPU fault pages, zero storage reads/writes in the
bounded temporary handoff, closed loader source handles, and 20 poisoned
recorder responses. It accepts slots 300/301/302 without recycling earlier
allocations. Actual pad-trigger control captures are 350 frames each, with
one trigger using the expected assigned slot. Original DSP voice output is
finite, nonzero and byte-identical on repeat; the replacement changes its hash.
The earlier take is replayed with all later pages present, exercising retained
sample data after replacement.

Native OLED evidence: [trim / USE](../out/runs/flex-ui-stereo-01/01-trim-use.png),
[accepted SRC](../out/runs/flex-ui-stereo-01/02-temp-assigned.png),
[discard](../out/runs/flex-ui-stereo-01/04-discarded.png),
[capacity retry](../out/runs/flex-ui-stereo-01/07-capacity-retry.png).

Run reports include exact dependency, firmware, snapshot, card, sample-feed,
native-library and source fingerprints. Each run retains frozen adapter source,
action events, PCM chunk requests, accepted pages and relevant audio/captures.
The prepared stock checkpoint needs its original startup frame countdown to
expire; a responsive OLED alone does not prove that control frames are flowing.

The initial save-control run mislabeled its instrumentation as “naming”; OLED
inspection and the original PLEASE WAIT string established that it was the
save-progress stage. The corrected negative control above preserves that
narrower observation. Earlier failed and diagnostic runs remain in `out/runs/`.

## Boundaries

**UNRESOLVED beyond the observed layer:** this is a working emulator sampling-flow prototype with modeled input.
Microphone/physical input, internal resampling, simultaneous recording and
playback timing, project save/reload, power-loss recovery, final mixer/DAC
output, real-time audio and physical-device behavior remain unverified or
unimplemented. Temporary takes disappear with the process. The original card
image is read-only; emulated storage overlays are session-local. No firmware
was sent to hardware, committed or published.

Reproduce the checks in fresh directories:

```sh
python3 scripts/try-flex-lite.py out/runs/my-flex-stereo --check
python3 scripts/try-flex-lite.py out/runs/my-flex-mono --check --mono --track 3
python3 scripts/try-flex-lite.py out/runs/my-flex-stock --check --stock-save-control
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The mono/track-3 check first verifies rejection of that checkpoint's STRETCH
track, then deliberately selects ONESHOT through the native machine chooser.
The interactive launcher never silently changes an incompatible machine.
