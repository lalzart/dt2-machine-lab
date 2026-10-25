# Shared mod integration implementation

Authorized by the user on 2026-10-16: implement the resource and reuse audit.
Approved proposal: the preserved `work/mod-resource-audit-20261016-01/REPORT.md`
in the sibling emulator workspace. The source-reimplementation lane preserves
the current OS 1.16 musical algorithms and resource lifetimes.

The working artifact is a reusable build/resource layer, explicitly typed hooks,
separate optional optimized STRETCH builds, shared replay setup, and supported
CLI commands with passing source, guarded-build and prepared-replay checks.
Device behavior and physical timing are separate evidence levels. No publication,
dependency migration, machine-ID reassignment or device transfer is authorized.

The immutable starting source is under ignored
`out/runs/reuse-baseline-20261016-01/source`, with hashes and initial dirty state
in the adjacent baseline manifest. It includes all inherited untracked work.
Compiler/runtime dependencies and existing source licenses remain unchanged.

Implementation contract:

- Existing default CPU and DSP builds reproduce their initial bytes. Compiler
  adaptations, alignment and reference checks remain mandatory.
- Shared helpers do not alter musical state. CPU emitters preserve register/CCR
  and argument conventions. DSP hook types retain distinct rates, destinations,
  continuations, preemption classes and independent event/voice scratch/stacks.
- Composition rejects unknown firmware, overlapping writes, duplicate exclusive
  resources, unowned regions and insufficient space. Arbitrary spare-looking
  memory is not an admitted code region.
- Project saving has one stock-call owner: Arp quiesce/snapshot, Flex persistence,
  stock save once, Arp companion after stock success, cleanup on every path.
  A Flex failure skips stock; stock failure skips companion; companion failure
  preserves the stock result and is reported separately. Preserve exact backing
  identity checks, pins, allocation failure cleanup and two-pass publication.
- Optional STRETCH optimization preserves reader state and exact PCM. Diagnostic
  trace output may intentionally differ only when explicitly disabled. Bank
  selection/mark/pin/admit/prepare order, epoch invalidation and current/outgoing
  crossfade readers remain unchanged. Defaults retain tracing and old lookups.
- Reset/init/retrigger and machine switch behavior match the reference. Stop,
  finite completion, invalid controls, bank invalidation and pressure fallback
  retain their existing semantics. No new freeze, reconnect or physical controls.
- Resource records distinguish CPU requested/rounded bytes, source PCM, DSP
  sample pool, bank occupancy, stacks/code placement and reserved capacities.
  Placement is not runtime ownership or hardware utilization.

Validation registered before implementation:

1. Entire existing source/native-helper suite, with new rejection and lifecycle
   tests; exact CPU/BLOB compatibility against the frozen source.
2. Typed-wrapper text/linked-code parity; negative address/overlap/capacity tests.
3. Paired optimized/reference host and compiled SHARC tests: finite signal,
   exact state and audio, repeated runs, active current/outgoing reader pinning,
   reload and generation invalidation, all selected banks marked before eviction.
   Use the same stock fixtures and control streams. Preserve independent oracles.
4. Paired instruction counts on identical control/loading/state/library inputs;
   no claimed speedup without matched results. Retain failed runs.
5. `./labctl doctor` and `./labctl test sine --replay`; targeted native checks
   for CPU hooks and each changed DSP/adapter path. Physical timing stays unset.

Results, reproduction commands and the remaining Arp/Flex placement limit are
recorded in [REUSE-RESULTS.md](REUSE-RESULTS.md). Exact final artifact hashes and
verification paths are in [REUSE-VERIFICATION.json](REUSE-VERIFICATION.json).
