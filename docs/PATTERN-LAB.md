# Pattern editing, capture and buffered playback

OS 1.16, prepared track 1, local emulator only. This work uses the pinned
DigiKit checkout without modifying it. Machine engines are unchanged.

The acceptance example is a 16-step, 102 BPM, 1x pattern. Panel gestures clear
the selected track, add steps 1/5/9/13, add and remove step 3, and store two
different locks. Normal PLAY must traverse two complete loops, restore base
values on unlocked notes, and stop. Removing step 5, adding step 7 and changing
the base sound must survive a transport restart while retaining step 13's lock.
The stock sampler is checked before the Plaits macro machine.

## Why PLAY previously stalled

The pinned GUI's live path forces DSPI control frames but does not connect
the existing SSI DMA clock model or deliver the firmware's sequencer software
interrupts. The new opt-in `lab/pattern_clock.py` adapter connects the existing
SSI model and delivers guest-requested vectors 108, 121 and 205 at instruction
boundaries, respecting their programmed priority and the CPU interrupt mask.
The firmware acknowledges the requests and schedules its own steps. No host
code chooses which note to play or injects a sequence of preview gestures.

The SSI model uses the existing explicit 96,000 requests/second assumption,
producing 1,500 blocks/second. Captures retain the actual control frames and
the firmware's sample ticks; the checker rejects missing or duplicate ticks.
Timing comparisons use 32 samples/block at 48 kHz, with one block of allowed
quantization. This is emulator musical timing, not a physical clock measurement.

The negative control disables only the new sequencer interrupt delivery,
leaving the SSI clock running. It must fail to complete the pattern.

Scripted advances also pause inside the CPU worker at a chunk boundary.
Polling from the host to request a pause could run one extra chunk; an initial
repeat exposed a two-increment TIMB difference. The final worker-side boundary
removes that scheduling dependence. Input gestures still use the panel path.

## Panel preparation

The workflow starts from the original ready checkpoint in `.local/cpu-inputs.json`,
not the later macro/lock checkpoint. It lets the firmware's initial 1500-block
transmit countdown finish naturally. The script selects the stock sampler or
applies the guarded Plaits CPU image, auditions track 1 to refresh its active
parameters, enters grid recording, clears track 1 with FUNC+PLAY, opens FUNC+PAGE,
and uses PAGE to select 16 steps from the initial 128-step pattern.
These gestures follow Elektron's [page setup instructions, section 10.7](https://www.elektron.se/wp-content/uploads/2025/07/Digitakt-2-User-Manual_ENG_OS1.15A_250708.pdf).
The manual is OS 1.15A; the local execution is specifically OS 1.16.

Stock means the original sampler engine selected inside the inherited SINE
CPU fixture. It is not a new cold boot of an entirely stock OS. Trying to
revert the CPU image beneath already-created objects was discarded after a
firmware halt; the passing path must preserve that fixture's CPU integration.

## Scope

Prepared CPU state, panel gestures, normal transport, CPU-to-DSP frames and
buffered SHARC voice PCM are separate checks. Other tracks' event bits are
masked only in the derived audio replay; raw captures are retained. The audio
is a voice-buffer tap, not the final mixer/DAC output. Real-time sound, project
save/reload, clean startup and hardware remain outside this milestone.

## Repeat the pattern check and listen

From the machine-lab repository, choose a new directory for each invocation:

```sh
./labctl doctor
RUN="out/runs/pattern-$(date +%Y%m%d-%H%M%S)"
python3 scripts/capture-pattern.py "$RUN" --machine plaits
python3 scripts/render-pattern.py "$RUN" "${RUN}-audio" --play
```

Use `--machine stock` for the sampler control. The capture command prepares and
edits the example, checks two loops, then checks a changed pattern after STOP
and PLAY. The renderer uses the first two complete loops, adds 100 ms of
preroll, renders through the SHARC firmware twice, requires exact PCM equality,
checks finite/nonclipping samples and every note interval, and writes
`pattern.wav`, `pattern.f32` and `render.json`. `--play` sends the completed WAV
to macOS `afplay`. Capture and rendering run slower than real time.

The raw `.dtfr` file retains other-track events and all captured parameter
bytes. Replay masks only other tracks' event bits, keeping track 1's original
control stream and timing. CPU reports record input/source hashes, sample
ticks, panel gestures, expected note values and screen captures. Reports and
firmware-derived files remain in ignored `out/` directories.

The clock's negative control is separate:

```sh
python3 scripts/capture-pattern.py out/runs/pattern-negative-new \
  --machine stock --no-sequencer-irqs
```

That command must report `negative-control-passed`: the same panel preparation
and SSI clock cannot complete two loops without the added software interrupts.

## DSP emulator gap encountered

The long Plaits replay reached stock firmware's register-form `FEXT` at
`0xb88e8b`, which the pinned native core does not implement. The lab-owned
`pattern_dsp.py` checks the exact PC and instruction bytes and lowers the
current register operand into the core's existing immediate-FEXT operation.
It preserves the original instruction width and requires non-SIMD, concrete
operands. Any other trap fails the render. The instruction is executed; no
firmware instruction is skipped or overwritten.

Field placement and extraction follow Analog Devices' [SHARC+ reference,
section 3, bit-field instructions](https://www.analog.com/media/en/dsp-documentation/processor-manuals/SC58x-2158x-prm.pdf).
The renderer checks 28 operand/corner cases against a Python instruction
execution, comparing results, flags, unrelated state and the next PC.

`pattern_native.py` builds an ignored copy of the pinned native sources with
one additional C entry point to resume after a successful replacement
instruction. Generated instruction semantics are unchanged. This avoids a
full sample-RAM export/import for every fallback. Cargo and the configured
Python toolchain are needed on the first run; subsequent runs hash-check and
reuse the cached library. The stock library, prepared state, firmware inputs,
and `.deps/` checkouts remain unchanged. The pattern renderer records the
additional library's hash and fallback count. Ordinary lab commands retain
the original pinned library.

## Optional panel window

```sh
python3 scripts/capture-pattern.py out/runs/pattern-window-new \
  --machine plaits --window --window-seconds 900
```

This opens the prepared 16-step example with the firmware panel and a small
capture bar. Edit track 1, choose 1–8 seconds, then use **Capture & render**.
The intended flow stops and restarts transport, saves a take, pauses the CPU
during the two DSP renders, plays the completed WAV, and resumes editing.
**Listen again** replays the last successful WAV. Takes remain under the
window's run directory. The window closes at the supplied lifetime bound.

This interface is experimental: window startup/idle/shutdown were checked,
but the interactive capture button has not been independently exercised via
the desktop UI. Use the scripted commands above for the qualified repeatable
path. Quick encoder gestures and arbitrary pattern configurations are not
covered by the acceptance example; the checked lock gestures deliberately
allow the slow firmware enough time and read back each result.

## Local evidence, 2026-10-06

CPU runs `pattern-stock-09` and `pattern-plaits-01` pass: steps 1/5/9/13 traverse
two loops with intervals `[882, 882, 883, 882, 882, 883, 882, 882]` audio blocks.
The edited 1/7/9/13 pattern restarts with `[1323, 441, 883, 882]` block intervals.
Every captured tick advances exactly 32 samples; both runs report no worker
error and no faulted pages. The Plaits example uses MODEL 1 (FM), with two
different three-macro locks; stock uses two TUNE locks. This milestone does
not requalify every Plaits model or every control corner.

`pattern-negative-01` retains the SSI clock but emits only the first PLAY
note within the same bounded check. `pattern-window-01` opens, idles for
300 seconds and shuts down with no worker error or faulted pages.

The original native library rendered `pattern-stock-audio-01` twice exactly:
4.805333 seconds, eight note events, peak 0.333099, PCM SHA-256
`7e55f825f9001cbdfa54e96dae89eb686235b6221e06ce9266bc1c9567faa9ce`.
`pattern-stock-audio-02`, using the additional native ABI, produces that same
PCM hash and exact repeated output, with no FEXT fallbacks. This checks stock
audio parity across the native-library change.

`pattern-plaits-audio-02` passes two complete renders of the eight-note,
4.805333-second captured performance. Peak is 0.1085575, with no nonfinite or
clipping samples and nonzero output in every note interval. PCM SHA-256 is
`e0599072bf6f5c21b495d8895a97324c72e64b77b83cba822bc9e900dbca7a78`.
Each render uses 1,765 guarded FEXT fallbacks. All four corresponding note
prefixes (128 blocks each) match across loops, and both locked-sound prefixes
differ from the base sound. `audio-review.json` records these comparisons.
macOS `afplay` completed successfully; no subjective listening judgement is
claimed. Both renders together took about 478 seconds on this Mac.

The ten source-only harness tests pass. The SINE regression in
`20261006T053346Z-test-431183ed` passes with the original pinned native library.
`doctor`, formatting/lint and dependency-cleanliness checks also pass.

Final CPU verification after the pause fix:

- `pattern-plaits-final-a` and `pattern-plaits-final-b` both pass, with identical
  gestures, expected values, note events, ticks and all 17,941 raw control
  frames. Capture SHA-256:
  `5216ca551bd446a3d1cb5c9a2ec270dfa8efc9526aaedba1194d24fae98c2dde`.
- `pattern-stock-final` passes (16,082 frames, 9 initial and 5 restarted notes).
  Its entire isolated two-loop replay input, including preroll, is byte-identical
  to the input already rendered in `pattern-stock-audio-01/02`.
- `pattern-negative-final` passes its negative check: 13,372 frames and just
  one PLAY note. All final CPU runs report no worker error or faulted pages.
- The final Plaits captures are also byte-identical to `pattern-fixed-01`, the
  validated pause prototype used as input to `pattern-plaits-final-audio`.
  Its firmware candidate, render range and ticks match, establishing that
  this audio replay uses the final workflow's exact control stream.

`pattern-plaits-final-audio` passes both complete renders of that final stream:
4.805333 seconds, peak 0.1085575, 1,765 FEXT fallbacks per render, and PCM SHA-256
`e19818b26cd2854af4d5aae083d0ddf74528a1d320057ff97b7df6f0f2569488`.
Corresponding 128-block note prefixes match across loops; both locks differ
from the base sound. `final-equivalence.json` connects the replay input to both
final CPU runs. Render and exact repeat together took 470.7 seconds.
The final SINE regression also passes in `20261006T054454Z-test-dee6abbd`.

[Listen to the final Plaits pattern](../out/runs/pattern-plaits-final-audio/pattern.wav).
