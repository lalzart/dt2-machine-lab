# Capicola behind the existing STRETCH machine

2026-10-08. Authorized direction: the user corrected the prototype to
“replace the current, or the existing stretch with capicola,” referencing the
[Alternative STRETCH demonstration](https://www.reddit.com/r/Elektron/comments/1wyg27f/alternative_stretch_for_digitakt_2/).
The product remains **STRETCH, machine ID 2**. Keep its existing selector,
parameters, parameter locks and serialized machine identity. Replace its DSP
backend. No separate CAPICOLA selector or RATE parameter is wanted.

The separate type-8 experiments remain reproducible engineering baselines.
Their analyzer, immutable banks, independent readers, bounded preparation,
sample-transfer invalidation and memory tests can be reused. Their CPU menu,
four-control interface and status-title roadmap are superseded. Automatic
title-refresh development has stopped; its incomplete UI results are recorded
in [the continuation results](history/capicola/CAPICOLA-LIVE-FEEDBACK-RESULTS.md).

## Verified existing interface

The new interface checker builds Plaits R3 + legacy Flex + the eight-MiB bank
reservation **without** `capicola_controls` or either feedback CPU overlay.
Its MAIN SHA-256 is
`7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3`.
This is a checked CPU base for replacement work, not a completed replacement.
The newer managed Flex candidate is not silently composed into this baseline.

Native OS1.16 descriptor initialization and getter execution confirm:

| SRC encoder | Parameter ID | Mirror | Track-one wire offset | Meaning |
| --- | ---: | ---: | --- | --- |
| A | 221 | 25 | `0xda` | TUNE, raw 1024..31744; default 16384 |
| B | 222 | 26 | `0xdc` | PLAY, raw 0/256/512/768 |
| C | 0 | — | — | Unexposed in original STRETCH |
| D | 223 | 28 | `0xe0` | SAMP, raw 0..1023 |
| E | 224 | 31 | `0xe6` | STRT, raw 0..30720 |
| F | 225 | 32 | `0xe8` | LEN, raw 0..30720 |
| G | 226 | 33 | `0xea` | BARS, raw 0/256/512/768 = 1/2/4/8 bars |
| H | 227 | 34 | `0xec` | LEV, raw 0..32512 |

The descriptor trailer remains Track Level, parameter 10. Names remain
`Stretch`/`STRE`; the stock hint is empty. Native permissions admit all sixteen
tracks. The native restore check covers all 256 serialized values with four
neighbor values: STRETCH retains stock restoration; the existing Plaits
type-7 restoration is the sole permitted difference.

The supplied demonstration shows **GAP** in encoder C. The original OS1.16
descriptor has zero in that slot. GAP is therefore an addition in that
demonstration, not an existing stock parameter to preserve. Do not assume
it is the prototype's RATE or invent its relation to Capicola's leash. The
existing interface is the integration base; the demonstrated GAP binding needs
its own verified semantics before it is added.

## Correct DSP seam and control authority

The OS1.16 voice loop sends selector 2 to `0x1c5576` via the call at
`0x1c6af1`. Other sample machines use `0x1c4ecf`. The earlier combined
Capicola hook at `0x1c4f15` is inside that generic renderer, so changing the
prototype's guard from type 8 to type 2 would not intercept STRETCH.
Keep the native selector-2 setup and intercept its renderer separately.
Retain the generic Plaits hook and original fallback for other machines.

Native setup already resolves the sample, start/end, direction, looping,
pitch and tempo/BARS conversion. Prefer those computed fields as the adapter
authority, rather than assigning a new RATE control or duplicating CPU math:

- `voice + 0x1cc`: positive pitch ratio. At note 60, TUNE yields
  `2 ** ((raw / 256 - 64) / 12)`, ranging from 1/32 to 32.
- `voice + 0x1c8`: positive timing advance computed from the selected region,
  tempo and BARS. Increasing BARS from 1 to 2/4/8 divides advance by 2/4/8.
- `voice + 0x198` / `+0x1a0`: native start/end Q31 pairs, low word first;
  preserve the native trimming/clamping result.
- Bytes `voice + 0x1bb` / `+0x1bc`: reverse/loop flags. PLAY 0 is reverse,
  1 reverse loop, 2 forward loop, 3 forward.
- The STRETCH call passes voice in R4, destination in R8 and frame count in
  R12. It produces the destination buffer directly. The current generic
  `Dsp.frame()` observation of decimated voice work buffers does **not**
  establish STRETCH output. Add a capture at the STRETCH destination before
  claiming replacement audio or final mixer behavior.

Two hundred forty native stock cases exercise PLAY × BARS × five TUNE values
× three start/length regions. They use an explicitly transformed captured wire
fixture and the original 1620 sample-transfer callbacks. These are control
computation checks, not new panel capture or Capicola playback. The short
2400-frame source requires advances from approximately 0.001328 to 0.02125.
The current finite Capicola reader only accepts pitch and advance 0.5..2, so
its bounds cannot be silently clamped to satisfy the existing interface.

## Implementation order

1. Keep the checked type-2 CPU base and freeze a replacement transport
   contract. Extend the finite reader for native timing, the full pitch range,
   start/end, forward/reverse and both loop modes. Preserve the original
   analyzer and standalone reference experiments. Give extreme rates explicit
   duration and numeric bounds instead of reusing the old 24-second output
   assumption.
2. Add the STRETCH-specific renderer adapter. Validate the passed destination,
   output block size, trigger/release behavior and downstream stock processing.
   Compare its prepared-bank output with a host oracle and retain a stock
   STRETCH comparator. An unready/unsupported bank must continue through stock
   STRETCH; select a backend at a trigger, avoiding a mid-note restart when
   preparation completes. Invalidated playback must not read a retired bank.
3. Generalize the source and reader ownership beyond the two track-one lanes.
   Keep banks keyed by source identity and load generation; matching tracks
   share immutable analysis, while each voice owns its cursor/splice state.
   The eight-MiB reservation is a **total bank budget**, not eight MiB per track.
   Multiple distinct banks need bounded admission, pinning and eviction;
   sixteen dense twelve-second banks do not fit it. Preserve stock fallback
   when a source cannot be admitted. Do not reduce STRETCH's CPU permissions
   to hide incomplete DSP support.
4. Verify original project/pattern recall, parameter locks, sample locks and
   source reload under type 2. Build/package, timing, final output and physical
   listening remain separate gates.

Preparation remains outside the reader: two bounded analysis passes when a
source changes, then prepared-bank playback. Replacing the UI does not improve
that cost. The current worst-case twelve-second bank occupies 6,912,048 bytes
inside the existing eight-MiB reservation; sample capacity stays twelve seconds.
No hardware headroom or sound-quality improvement has been demonstrated.

## Reproduction and current evidence

```sh
./labctl doctor
python3 scripts/check-capicola-stretch-contract.py out/runs/<unique-cpu>
python3 scripts/probe-capicola-stretch-path.py out/runs/<unique-dsp> \
  --capture out/runs/capicola-panel-08 \
  --sample-load out/runs/capicola-panel-05
```

First passing native CPU report: `out/runs/capicola-stretch-contract-04/report.json`.
First passing native control report: `out/runs/capicola-stretch-path-01/report.json`.
Final formatted-source reruns also pass:
`out/runs/capicola-stretch-contract-05/report.json` and
`out/runs/capicola-stretch-path-02/report.json`. The configured Python's
`-B -m unittest discover -s tests -v` passes all 95 tests without skips;
focused Ruff checks and `git diff --check` pass. No DSP implementation or
shared runtime adapter was changed in this correction step.
The static stock listings and preliminary field probe are retained under
`out/runs/capicola-stretch-probe-01/` and
`out/runs/capicola-stretch-voice-probe-01/`.

**Current state:** replacement architecture and native control authority are
verified; the replacement renderer and expanded Capicola transport are not yet
implemented. Prior type-8 audio results are useful engine evidence, not evidence
that the original STRETCH machine has been replaced. No image was flashed,
committed or published.
