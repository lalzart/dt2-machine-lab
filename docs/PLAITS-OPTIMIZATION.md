# Plaits VA resource experiment

Approved scope: the user's “Let's do that” following the proposal to skip
unused AUX and conditionally share matching lane renders. Baseline is commit
`69650c3`; source authority, MIT notices, dependency pins, controls and numeric
quirks remain those in [PLAITS-VA.md](PLAITS-VA.md) and
`machines/plaits-va/source-lock.json`. No dependency edits or device writes.

## Frozen implementation contract

Working artifact: an optional optimized SHARC image plus a repeatable comparison
report under `out/runs/`. Evidence level: host signal and prepared emulator
voice PCM, not physical DSP timing or final output. The default reference
build remains available and continues to compute both outputs.

- Preserve MAIN equations, float32 operation order, pitch calibration,
  12-sample engine blocks, FIFO, envelope, parameter transforms and trigger
  latching. AUX-only oscillator updates/output are intentionally excluded in
  the main-only variant; switching variants requires a fresh image/state.
- Keep the existing 384-byte lane ABI and two independent lane states.
  Share only deterministic transitions with bit-identical complete incoming
  lane state **after** trigger/control handling. A one-entry cache stores
  input state, output state and the 64-sample source buffer. On a hit copy
  the output state and buffer. On a miss render independently and replace
  the cache. Compare integer bit patterns, including unused fields; conservative
  misses are acceptable. No inferred firmware epoch or lane ordering.
- Inactive voices bypass the cache and use the original zero-fill loop: copying
  cached state for silence was more expensive in the first measured variant.
- All external controls must be read before cache lookup. Cache storage is
  separate from firmware buffers, which downstream code may overwrite.
  Fresh loader state zeros the cache; trigger resets, type changes, tail
  completion and unequal lanes follow the original wrapper. A type change
  disables that lane and returns to stock. Other voices remain stock.
  Resetting an engine does not imply zeroing all scratch bytes; the complete
  key includes them. No dynamic allocation, random input, panic/freeze protocol,
  UI or new controller mappings are introduced.

## Fixed comparison and acceptance

Use a small dedicated comparison script, not a new test framework. Retain all
successful and failed reports, builds, source/input/tool hashes and raw PCM
under ignored unique run directories. Fingerprint sources before/after runs.

1. Compare main-only C against unchanged full C: 16,000 blocks with the
   existing four parameter settings at blocks 0/4000/8000/12000, then all
   16 note/macro corners for 120 blocks each. MAIN must be bit-exact and
   finite; AUX sentinel must stay unchanged. Confirm full C against the pinned
   original C++ oracle. No random seed is needed.
2. Build reference and main-only standalone SHARC images, drive those same
   vectors and resets, require MAIN bytes identical. Retired instructions
   per 12-sample block measure emulator work, not cycles/utilization.
3. Replay the identical 801-frame real-control preview in reference,
   main-only, and main-only/shared images. Require exact PCM, repeat equality,
   locked/unlocked/locked recall, stock type-6 hook parity, and a nonzero
   disabled-hook negative comparison. Preserve the raw capture and record
   event masking. Compare whole block-handler instruction totals on this
   same workload; report cache hits/misses and memory/code tradeoffs.
4. Direct compiled-machine calls compare independent and shared variants
   under matching lanes, reversed/skipped/repeated lane calls, unequal
   retriggers and controls, switch-away/back and tail completion. Require
   exact buffers and lane state after every call. Require both hits and misses;
   corrupt cached output in a deliberate negative control and detect it.
5. Run the repository's eight harness tests and SINE replay regression.

No tolerance will be silently relaxed to accept an optimization. If MAIN
equivalence or divergent-lane behavior fails, diagnose or leave that variant
disabled. Existing host/SHARC long-render drift is a separate unresolved
question. Configured physical clocks, safe runtime memory ownership, stack
high-water mark, final mix and device CPU/DSP load remain unmeasured.

## Results

EVIDENCE, 2026-10-05: all comparisons pass in
[`out/runs/plaits-optimization-final/report.json`](../out/runs/plaits-optimization-final/report.json).
The pre-results contract is retained there as `frozen-contract.md`, SHA-256
`243032604188918e2fd70deb45e2c635ffca69b8f54f5a9c93ecf4cd0e02f44d`.
Both reference images are byte-identical to the previous standalone and
firmware builds. Default builds still produce those reference images.

| Same workload | Reference | MAIN only | MAIN + sharing |
| --- | ---: | ---: | ---: |
| Mean retired instructions / standalone 12-sample block | 21,886.34 | 10,763.94 | N/A: one engine |
| Whole firmware block-handler instructions, 801 frames | 215,892,739 | 199,056,173 | 192,728,477 |
| Reduction in that whole replay | — | 7.80% | 10.73% |
| Largest observed handler block | 362,326 | 297,889 | 272,464 |
| Integrated code bytes | 13,928 | 13,278 | 14,210 |
| Persistent lane + cache bytes, excluding stack/context | 768 | 768 | 1,804 |

Removing unused AUX saves **50.82%** of standalone engine instructions. Lane
sharing additionally saves 6,327,696 instructions (3.18% versus MAIN-only)
on this captured workload. The shared version has 293 cache hits and 293 misses;
inactive calls bypass the cache. The whole-handler numbers exclude the DMA
callback and Python output tap, and include stock processing around the source.
They must not be compared directly with isolated engine counts or interpreted
as physical cycles/CPU/DSP utilization. The maximum above is observed in this
capture, not a proven worst case.

Initialized tables/data remain 2,076 bytes; the cache adds 1,036 bytes. The
466,944-byte experimental arena still includes holes and is unchanged. Its
size is not the engine's minimum RAM need or proof that the region is safe
on hardware. No state/stack compaction was attempted in this optimization.

MAIN is bit-identical in the host/original-C++ comparison and in the paired
SHARC comparison: four seconds plus 16 parameter corners, 215,040 samples
per variant. The optimized AUX sentinel stays untouched. All three firmware
variants retain PCM SHA-256
`48f2adba0303ee4170b8014332030bc24f8ba17b2b898f63a671aca21c5508ff`.
The three preview events remain at frames 158, 210 and 260; recalled locks
match over 3,328 shared interleaved samples. Shared repeat and stock type-6
hook parity are exact; bypassing the new source changes PCM by up to
`0.3370877867564559`.

The 92 synthetic compiled-machine calls preserve complete lane state and
source buffers across reordering, skipped/repeated calls, different retriggers,
different controls, machine switching and completed tails. They exercise 28
hits and 42 misses; one call takes the stock path and the rest bypass the
cache while inactive. Deliberately poisoning a cached output is detected.
These are adapter tests, not evidence of every firmware scheduling pattern.

Eight harness tests, Python lint/format checks, generated-source freshness,
and the full [SINE replay regression](../out/runs/20261005T070307Z-test-2384ee5e/manifest.json)
pass. Source fingerprints remain fixed throughout the final runs. The earlier
SINE run `20261005T065619Z-test-5f2e6f87` passed its signal checks but was correctly
rejected because Plaits sources changed while it was running; it is retained.

### Compiler finding and rejected measurements

EVIDENCE: the first cache used a typedef for a union. The pinned compiler
emitted `state + 0x180` for its `words` member, instead of the overlapping
union base, so the second matching lane received the right buffer without
the right state. The exact state comparator failed immediately. The retained
`plaits-sharing-probe/lane-mismatch.json` and assembly expose that error.
Using `union LaneState` explicitly gives the correct addresses and passes
the state comparison. No dependency was edited. Keep the explicit tag and
the paired state check when updating the toolchain.

The initial all-stage failure is retained in `plaits-optimization-first`.
Its host/standalone stages passed, but its faulty cache was rejected.
The subsequent `plaits-sharing-tagged` run passes with 8.81% whole-replay
savings; its silent-tail cache copying costs more than zero-filling. The
final inactive bypass improves this to 10.73%. These earlier reports are
diagnostic history, not substitutes for the final result.

UNRESOLVED: physical CPU/DSP load, configured clocks, safe runtime memory
ownership, stack high-water mark, final mix, clean startup, continuous pattern
traversal and real macro controls/locks. Existing host-versus-SHARC long-render
numeric drift is unchanged; exact optimized-versus-reference target equality
does not explain or close it.

## Repeating the experiment

```sh
python3 scripts/compare-plaits-va.py out/runs/my-plaits-comparison
python3 scripts/try-plaits-va.py out/runs/my-plaits-shared --mode firmware --variant shared
```

Each run directory must be new. The comparison supports `--stage host`,
`--stage target`, or `--stage firmware` for work affecting only one layer.
It checks the pinned upstream source, private fixture and original control
capture. That capture must still be present at
`out/runs/controls-final-capture/controls.dtfr`; the generic SINE fixture
importer does not reconstruct it.

The existing renderer accepts `reference` (default), `main-only`, or `shared`
in firmware mode. Its standalone target mode remains the full OUT/AUX oracle;
use the comparison script for standalone optimization measurements. Outputs
are image overrides, raw PCM and reports; the existing renderer also writes
`plaits-va.wav`. Neither command packages or flashes a device update.

Sharing is specific to this deterministic wrapper, with all controls latched
before lookup. Future per-block modulation or external state must become part
of the key before it is eligible. Unequal active lanes still pay lookup/copy
overhead; this experiment measures one captured workload, not every possible
pattern or worst-case device budget. The main-only variant remains independently
selectable. Inactive voices bypass caching.
