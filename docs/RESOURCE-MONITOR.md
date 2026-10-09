# Digitakt II resource monitor

2026-10-08: first working local screen and reusable JSON snapshot importer.
This implements the first stage of the user's approved resource diagnostic.
Source: `lab/diagnostics.py`; command: `./labctl diagnostics`.

The screen reads saved experiment records. Each row describes its own run or
candidate; importing Flex and Capicola together does not measure a combined
device workload. Importing does not execute the emulator or alter firmware.

## Use

From this repository, import the latest successful lab run:

```sh
./labctl diagnostics
```

The command prints the absolute paths of `index.html` and `snapshot.json` in a
fresh `out/diagnostics/<timestamp>-<id>/` directory. Open the HTML in a browser;
it works locally without a server, JavaScript, network access or dependencies.
The screen has links to DSP/memory/provenance and expandable measurement details.
`--output` selects a destination; existing directories are refused.

To reproduce the first complete example, choose a new output directory:

```sh
./labctl diagnostics \
  --run out/runs/20261008T083716Z-test-b8be7e0b \
  --baseline out/runs/20261008T083716Z-test-b8be7e0b/stock-profile.json \
  --flex-report out/runs/flex-heap-stereo-20s/report.json \
  --flex-report out/runs/flex-heap-reuse-32/report.json \
  --layout out/runs/capicola-selection-wire-02/candidate/memory-layout.json \
  --reservation out/runs/capicola-owned-cpu-02/report.json \
  --output out/diagnostics/resource-monitor-v1
```

`--run`, `--flex-report`, `--layout` and `--reservation` can be repeated. The
standalone entry point is `scripts/diagnose-resources.py` using Python 3.12+;
`labctl` selects the already configured interpreter automatically.

For a workload sweep, `--paired-stock` automatically compares each DSP image
with an imported original stock BLOB replay having exactly the same workload
identity. An unmatched or ambiguous reference is refused; active custom-engine
clips remain separate observations. `--stock-report` imports verified paused
stock CPU heap stages. The overview table keeps the whole sweep visible before
the detailed per-profile traces.

```sh
./labctl diagnostics \
  --run out/runs/stock-resource-baseline-01 \
  --paired-stock \
  --stock-report out/runs/stock-resource-baseline-01/stock-capture.json \
  --output out/diagnostics/stock-resource-baseline-01
```

See [STOCK-RESOURCE-BASELINE.md](STOCK-RESOURCE-BASELINE.md) for the workload
capture, firmware verification, results and reproduction command.

The [Capicola STRETCH comparison](CAPICOLA-RESOURCE-COMPARISON.md) measures
preparation, unready stock fallback and one/four/sixteen-track playback with
identical sample-loading and warmup metadata. Its bank arrays and reader
records are shown inside the declared total reservation, separately from CPU
heap consumption. The importer refuses comparisons with different replay
initialization, even when the measured control capture is identical.

## Measurements and boundaries

- DSP: mean, p50, p95, p99 and observed maximum retired instructions per block;
  host microseconds separately. Peak-preserving plot bins keep brief spikes
  visible. The current adapter covers the whole DSP block handler, excluding
  DMA callbacks/output taps; its exact recorded boundary is retained.
- Baseline: instruction deltas are calculated only when capture hash, frame
  count, preroll, rates, initial DSP state, native library, dependency revisions,
  stock firmware hashes and measurement boundary all agree. Different DSP
  candidate images are intentional. Host timing remains descriptive because
  host contention and measurement overhead were not controlled.
- Flex: retained takes, cached save references, source PCM bytes and requested
  source/descriptor heap bytes after USE, clear/reload and save handover. Cached
  save references are not an independent validation of durable files.
- CPU heap: where the source experiment recorded allocator events, show arena
  size, initial/final/minimum free bytes, observed peak occupied bytes,
  final/minimum observed largest free block and allocation failures. This is
  the whole traced heap, including stock allocations. It is not attribution
  of every occupied byte to Flex. Requested Flex bytes exclude allocator
  rounding, recorder storage and stock playback copies.
- Capicola: working-state span and instruction bytes from the candidate layout;
  reservation and remaining pool capacity from an explicit CPU reservation
  record. These are placement/capacity figures, not live consumption. Working
  state lies inside a reservation and must not be counted again on top of it.

Physical CPU/DSP percentages, audio deadline misses and live device free memory
remain `null` in the JSON and are shown as unmeasured. DSP instruction deltas
are cost differences, never remaining hardware headroom.

The importer rejects failed runs, unsupported stock firmware, malformed or
nonfinite samples, array/statistic disagreements, overlapping layout regions,
invalid memory counters and unfinished allocator traces. It recomputes DSP
statistics from raw arrays. Input JSON SHA-256 values are recorded and checked
again before export. These identify the imported records; the importer does
not rerun or independently certify their original experiments.

## First observed baseline

Example artifact: `out/diagnostics/resource-monitor-v1/`.

- Stock sampler fixture: mean 213,598.99 instructions/block; observed maximum
  221,054 over 450 blocks. The same stock control trace with the SINE hook
  installed uses 3,381 more instructions/block (+1.58% mean). This is hook
  overhead for the stock workload, not the cost of playing SINE.
- The separate SINE workload: mean 219,138.00 instructions/block, maximum
  224,302 over 1,500 blocks. Comparison to the stock trace is refused because
  its capture, length and preroll differ.
- The native 20-second stereo Flex experiment requests 3,840,144 source-owner
  heap bytes after USE and retains 64 descriptor bytes after verified save
  handover. Its traced 32 MiB CPU arena reaches 9,677,968 occupied bytes;
  largest observed free block stays at 16 MiB. This covers that bounded
  emulator experiment and does not establish recording capacity on hardware.
- The separate 32-cycle short-take experiment retains zero source PCM and
  2,048 descriptor bytes after the final save. The CPU reservation record
  declares 8 MiB for Capicola and 392 MiB remaining sample-pool capacity.

## Next stage: native screen and timing

The existing native Flex snapshot is a suitable first source for an on-device
memory page. It must be called at its documented idle/UI boundary and show an
unavailable state when the owner is busy. Allocator free/largest-block reads
need a coherent snapshot under the stock allocator's synchronization rules.
Avoid walking allocation lists from an audio interrupt.

Use a small fixed telemetry record with consistent-read sequencing, counters
and peaks. Refresh the screen slowly; measure its own CPU and RAM overhead.
Resetting peaks changes only diagnostics state. No sample lifetime or allocator
policy changes are needed for this screen.

CPU load still needs validated busy/idle timing including interrupts. DSP load
needs a verified counter, configured clock, block deadline, full processing
boundary and overrun detection. Before reporting percentages, establish counter
wrap/preemption behavior and compare instrumented/uninstrumented workloads.
The on-device page, live emulator attachment and hardware timing hooks are
future stages; this version has no native UI or new firmware instrumentation.

## Validation

`./labctl doctor` passes. The configured Python 3.12.11 runtime passes the full
104-test unit suite, including nine diagnostic tests covering comparison
eligibility, source changes, invalid data, accounting separation, HTML escaping
and output preservation. Focused Ruff checks and `git diff --check` pass.
The complete example imports seven DSP profiles, two Flex experiments, a layout
and a reservation; browser review verifies the DSP tables, memory section and
source disclosure. No DSP execution or adapter behavior was changed, so this
reporting-only addition did not rerun the prepared SINE audio regression.
