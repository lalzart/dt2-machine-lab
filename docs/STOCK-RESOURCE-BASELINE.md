# Stock OS 1.16 resource baseline

2026-10-08. Local emulator workload sweep requested by the user. No device
upload, firmware package publication or hardware resource percentages.

## Earlier coverage

The prepared SINE regression already measured an original stock DSP image and
matched installed-hook overhead. It was a narrow saved trace. Pattern-lab
“stock” cases exercised the stock sampler from a SINE CPU-ready fixture;
`docs/PATTERN-LAB.md` explicitly records that the CPU checkpoint is modified.
Those were useful compatibility checks, but not a systematic stock-CPU baseline.

## Method

`scripts/profile-resource-baseline.py` captures six bounded pad auditions from
an independently verified original OS 1.16 CPU-ready checkpoint. It checks the
exact snapshot hash, saved stock MAIN identity, unchanged static executable
prefix and the +Drive card sidecar. Runtime-initialized data after the executable
prefix is allowed to differ from the file. The CPU is not overlaid or patched.
The emulator retains its existing boot/peripheral accommodations, modeled
96 kHz SSI clock and zero DSP replies. The CPU capture and DSP replay are
separate stages, not a coupled device simulation.

Stock MAIN SHA-256:
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
Original DSP BLOB SHA-256:
`0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
Stock ready snapshot SHA-256:
`3852f53c7e45c358702ed9cefb8bb3ef2af194f4f501e70b6cfbcba333494867`.
Full package, card, fixture, dependency and source provenance is saved locally
in the run manifest and `stock-capture.json`.

Scenarios, sequentially in the same prepared project:

1. Idle after stopping transport.
2. Track 1 pad (ONESHOT).
3. Tracks 1 and 2 pads (ONESHOT).
4. Tracks 1–4 pads with the inherited track-3 STRETCH setting.
5. Tracks 1–4 pads after selecting ONESHOT on track 3.
6. Track 1 pad after selecting GRID on track 1.

The CPU delivers batched pad gestures serially. These are short auditions of
the prepared sample, not sustained simultaneous-voice stress tests. The run
records track types and trigger masks and rejects faults, missed captures and
unknown machine selection. Paused heap snapshots decode the 32 MiB stock buddy
arena; they exclude sample-pool storage and other memory arenas. The CPU runs
for a fixed instruction budget, so its instruction count is not a load metric.

Each capture is replayed for 192 DSP blocks from the same pinned prepared DSP
state. All one-shot events must fit within the replay; only an event-free final
frame may be repeated. This gives 0.128 seconds of tapped 48 kHz stereo output
(32 samples/channel/block). Three independent DSP images receive identical
bytes: original stock, installed SINE hook and installed Plaits R3 hook.
The entire DSP block handler is counted, excluding DMA callback and the Python
tap. Voice-0/1 tap PCM must be byte-identical across installed-hook variants.
This does not verify the final mixed output or other voice PCM independently.

Two additional active cases use historical genuine custom-CPU captures:
SINE and Plaits FM. Each has 32 blocks of event-free preroll and explicit
track-one event-mask isolation, retaining every parameter byte. These inputs
are saved and hashed as derived clips. Their costs have no identical stock
reference and must not be used as matched stock-to-custom deltas.

All replays use `PatternDsp` and record its actual native-library hash. The
existing guarded register-FEXT lowering is checked against 28 state cases;
per-case fallback counts are retained. Emulated retired instructions are not
physical DSP cycles. Host microseconds are descriptive and include uncontrolled
host contention. Active lane flags are state observations, not a polyphony
or headroom guarantee.

## Reproduce

From the sibling machine lab, using the configured Python 3.12+ interpreter
from `.local/config.json` and a new output directory:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  -B scripts/profile-resource-baseline.py \
  out/runs/stock-resource-baseline-01 --extended-stock --custom-engines

./labctl diagnostics \
  --run out/runs/stock-resource-baseline-01 --paired-stock \
  --stock-report out/runs/stock-resource-baseline-01/stock-capture.json \
  --output out/diagnostics/stock-resource-baseline-01
```

`--capture-only` omits DSP replay. `--frames` permits 128–512 blocks and refuses
truncation that loses any event. `--extended-stock` adds the ONESHOT/GRID setting
changes. `--custom-engines` adds installed Plaits and the active custom clips.
The stock checkpoint and card remain private local prerequisites; their paths
are explicit in the harness. Firmware, snapshots, captures and derived binaries
stay in ignored directories. A run succeeds only after all requested cases,
PCM parity checks and source stability checks pass.

## Results

Run: `out/runs/stock-resource-baseline-01`, completed successfully at
2026-10-08T10:06:45Z. Twenty independent DSP profiles (192 blocks each), six
paused stock CPU heap stages, zero fault pages and successful stock voice-tap
PCM parity for every installed-hook case. `source-audit.json` additionally
checks 44 compiler-input files against the initial manifest; future harness
runs include these files directly in the source-stability gate.

All instruction figures below count the whole emulated DSP block handler.
Hook percentages are the mean instruction increase over the identical stock
replay, with the custom engine not selected.

| Stock workload | Stock mean instructions/block | Stock observed peak | SINE hook | Plaits R3 hook |
| --- | ---: | ---: | ---: | ---: |
| Idle | 212,978.76 | 216,199 | +1.59% | +4.40% |
| 1 pad: ONESHOT | 216,336.48 | 221,054 | +1.56% | +4.33% |
| 2 pads: ONESHOT | 222,568.37 | 228,676 | +1.52% | +4.21% |
| 4 pads: STRETCH mix | 225,865.29 | 240,297 | +1.50% | +4.15% |
| 4 pads: ONESHOT | 229,659.05 | 243,158 | +1.51% | +4.28% |
| 1 pad: GRID | 213,105.57 | 220,778 | +1.64% | +4.69% |

| Separate active custom clip | Mean instructions/block | Observed peak |
| --- | ---: | ---: |
| SINE | 222,110.82 | 224,238 |
| Plaits FM | 325,871.00 | 367,097 |

The active clips have different controls/source captures from the stock cases;
they are intentionally unpaired. The Plaits mean also includes 32 preroll blocks;
its median is 360,556 instructions/block. Peak active lane flags are 0/2/4/8 for
idle/one/two/four pad workloads, and 2 for each active custom clip. This records
the stock two-lane-per-track representation without claiming hardware polyphony.
No register-FEXT fallback was needed in any of these short cases.

The 32 MiB CPU heap contains about **5.194 MiB occupied** and **26.806 MiB free**
in every observed stage. Free bytes range from 28,107,760 to 28,108,480; the
largest free block stays at 16,777,216 bytes. This is a snapshot of the stock
buddy arena after each audition, not total installed RAM consumption, the
sample pool, or a watermark during playback. Tiny differences include ordinary
UI/stock allocations and must not be attributed to individual machines.

These captures do not rank ONESHOT versus STRETCH or GRID in general. Their
controls differ, and the prepared sample is short. More overlapping tracks do
raise total block work in these auditions, but longer samples, sustained
sequenced overlaps, effects and recording need new workload cases before
judging capacity. Actual CPU/DSP utilization and deadline margins remain
unmeasured and require hardware timing.

## Validation

`./labctl doctor` passes. The full configured-runtime unit suite passes 117
tests, including 16 resource-diagnostic/workload tests. These reject truncation
of triggers/releases, repetition of one-shot tail events, invalid clip bounds,
modified-library comparisons, ambiguous stock references and unhealthy or
inconsistent stock heap records. Focused Ruff checks and `git diff --check`
pass. Browser review verifies the saved twenty-profile overview and six-stage
stock memory table. The unchanged SINE replay regression passes from the frozen
source copy at `out/runs/resource-baseline-regression-frozen-01/source/out/runs/20261008T101639Z-test-55c31740/`.
Its exact repeat/baseline, stock isolation, clone parity, lifecycle and signal
checks all pass, along with the complete global source-stability gate.

The shared checkout changed during two normal SINE replay checks: first the
diagnostic files were still being edited, then concurrent Capicola work changed
unrelated source files. Their DSP result records report `ok: true`, but their
overall manifests correctly remain failed because the global source-stability
gate was not satisfied. A verified frozen source copy under
`out/runs/resource-baseline-regression-frozen-01/source/` reruns the unchanged
`labctl test sine --replay` command with the same hash-verified dependency and
fixture paths. This preserves the gate and lets the live checkout continue.
