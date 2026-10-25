# Mod reuse and resource implementation

2026-10-16, Digitakt II OS 1.16. Implements the approved local resource audit.
The source and inherited uncommitted work were frozen before changes in
`out/runs/reuse-baseline-20261016-01`; dependencies remain pinned. Nothing was
committed, published or transferred to a device.

## Shared implementation

- CPU emission, version-specific placement rules and deterministic guarded
  allocation now live in `lab/emit.py`, `lab/dt2_116.py` and `lab/resources.py`.
  Arp and Flex use these helpers. Existing import names remain compatible.
- `lab/context.py` supplies explicit build paths. The Plaits compatibility
  facade delegates to separate CPU and DSP builders and named family features.
  Public builders can be imported outside an active CLI run.
- `lab/sharc_hooks.py` records hook address spaces, rates, continuations and
  preemption constraints. Active source, STRETCH, maintenance and sample-event
  wrappers consume those typed definitions. Event and voice scratch/stacks remain separate.
  Assembly and loader helpers live in `lab/sharc_tools.py`; five native replay
  validators share LP0 loading through `lab/replay_io.py` and keep independent
  numerical checks.
- `lab/project_save.py` provides native prepare/stock/commit/cleanup sequencing,
  register and argument preservation, and one owner of the stock save call.
  Arp snapshots before saving and writes its journal after stock success; Flex
  persists before stock. Cleanup runs on failures. Standalone Arp and Flex can
  select this entry with `--shared-save`; default builds retain their old bytes.
- `lab/mods.py` exposes active builds, actual CPU-write conflict preflight and
  per-owner resource declarations. Diagnostics can import those declarations.
  Nested capacities are not summed; hardware utilization and protected heap
  headroom remain unset.

## Optional STRETCH work reduction

The reference build remains the default. `cached` snapshots selected sources
once per maintenance pass and uses a range/alignment/generation checked pin
lookup. All selected banks are marked before admission; current and outgoing
readers retain pins. `trace-off` removes diagnostic copies of 32 floats per
lane. `cached-trace-off` combines them. No persistent state layout, bank budget,
sample identity limit or recording capacity changed.

Paired compiled SHARC runs used identical captured controls and sample input,
16 distinct sources and 32 lanes. Every block compared cache, reader and
handoff state, finite modeled master PCM and DAC-facing ring values exactly.
Trace arrays are intentionally excluded when tracing is disabled.

| Workload | Cached | Trace off | Both |
| --- | ---: | ---: | ---: |
| Bank preparation | 1.98% | 0.00% | 1.98% |
| Steady playback | 0.55% | 0.78% | 1.33% |
| Rapid live edits | 0.45% | 0.51% | 0.95% |
| Settled playback | 0.50% | 0.67% | 1.18% |

These are reductions in mean retired emulator instructions for the whole DSP
block handler, excluding callbacks. They are not physical CPU/DSP utilization,
wall-clock timing, listening results or a quality improvement claim. Block
counts, totals, maxima, means and exact fixture/build hashes are retained in
`out/runs/reuse-runtime-freeze-01/source/out/runs/paired/runtime-comparison.json`.
The broader cached native suite also passed its 48 mode/region cases, finite
completion, live edits, reload/invalidation, pressure fallback, stock/Plaits
parity and modeled downstream checks:
`out/runs/reuse-runtime-freeze-01/source/out/runs/cached-native/report.json`.
The copied source and dependencies identify exactly what those runs exercised.

## Reproduction

Use the configured Python through `labctl`; the system Python is not supported.

```sh
./labctl doctor
./labctl build plaits
./labctl build flex --shared-save
./labctl build arp --shared-save
./labctl build capicola --runtime-variant cached-trace-off
./labctl test sine --replay
./labctl test flex --replay --shared-save
./labctl test arp --replay --shared-save
./labctl test capicola --replay --runtime-variant cached
./labctl compare-runtime
./labctl resources
./labctl plan --mods plaits flex
./labctl plan --mods arp flex
```

The last command intentionally fails: it records the actual conflicting
writes. Every CLI invocation creates a fresh run and provenance manifest.
The build commands produce local image overrides, not installable containers.
See `REUSE-VERIFICATION.json` for final artifacts and checks.

The native Arp runner retains its default 8.5-billion-instruction bound and now
accepts an explicit `--instruction-limit` up to 16 billion. The CLI's longer
ORDER/120 BPM/record/save/recall scenario selects 12.5 billion. Its first attempt
hit the old ceiling during a stock follow-up autosave; that failed run is kept
at `out/runs/20261016T143312Z-test-f94d458c`. The existing save, recalled state,
complete-pattern and replay-note assertions are unchanged. Earlier tempo/rate
validation also needed checkpoint continuations for the storage sequence.
The uninterrupted rerun passed at 10,219,163,625 instructions, preserving all
121,740 pattern bytes and replaying 67,64,60,67,64,60,67,64 without generated
arp calls or fault pages. The final source suite passes 217 tests, including
an active-wrapper negative that rejects a word address supplied as byte scratch.

## Composition limit

Arp plus managed Flex currently has 86 overlapping write pairs, covering 6,026
unique bytes. Their raw helper payloads total 14,803 bytes against 9,182 bytes
in the union of the presently admitted gaps; part of that union also belongs
to Plaits. Sharing a save hook does not resolve the other code collisions.
The complete combined image therefore remains refused until an owned code
region or sufficient proven code reduction is available. No spare-looking
RAM was silently claimed and no combined firmware is presented as working.

The existing 8 KiB Arp allocation, Flex source lifetimes/32 identities/32 KiB
save scratch, Capicola 8 MiB reservation and twelve-second source limit remain.
Project lifetime reclamation, permanent DSP code ownership, physical timing
and device validation remain separate work. The implementation contract is
in `REUSE-IMPLEMENTATION.md` and `profiles/dt2-1.16/reuse-contract.json`.
