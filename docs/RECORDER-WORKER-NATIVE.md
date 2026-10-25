# Native BUF recorder worker

Continuation: [queued native FREEZE and reader-lifetime controls](RECORDER-LIFETIME-WORKER.md).
The original results below describe the preceding bounded worker increment.

Target: Digitakt II OS 1.16. Authorized emulator increment, 2026-10-21.

## Implementation contract

Use the original recorder's queued directory worker and completion callback,
as the existing native Flex implementation does. NORMAL forwards the exact
displaced stock instructions. BUF USE latches trim, destination, track, kit
and epoch in guest state. ColdFire code reserves checked empty slots, copies
stopped recorder chunks with their recursive lock, hashes and publishes using
the original sample loader, associates the stable logical slot, registers the
immutable generation with native FREEZE, and releases its transient CPU source.
No host source dictionary, host loader invocation or host registration is
allowed in that transaction.

The first implementation pins eight immutable generations and eight snapshots.
It refuses admission at capacity. It does not infer reader completion from a
track stopping, and never reuses a sample identity or old backing allocation.
The four logical slots remain stable. Failed candidates must leave the prior
logical buffer, active readers and snapshots intact; issued identities remain
consumed. Project serialization/load remains guarded while resources are volatile.

This is a separate opt-in stock-image experiment, using explicitly mapped
emulator scratch. Legacy Flex and the all-features image remain unchanged.
Their temporary identity namespace overlaps this experiment: simultaneous
installation is forbidden until a common dispatcher and target reservation
are implemented. Capicola's reservation is untouched.

Evidence required: actual queued-worker entry/completion and interrupt state,
native resource calls without source HLEs, exact chunk/page PCM and original
SHARC ONESHOT output; repeated recording, shared slots, frozen old generation,
cancel, stale context, exhausted memory and publication rollback. Tests must
distinguish modeled recorder peer, page transport and prepared DSP replay from
native CPU orchestration and physical capture/timing. Next-bar clock work is
conditional on this foundation, and must not substitute explicit test bars.

## Results

**PASS: bounded native CPU recorder workflow and modeled DSP publication.**
Final primary run:
`out/runs/recorder-worker-native-20261021-06/report.json`.
The publication gate independently passes in
`out/runs/recorder-worker-publication-20261021-05/report.json`.
Exact repeat run `recorder-worker-native-20261021-07` also passes: native
checks, context/tick traces, source retirement, heap observations, resource
calls and all audio results are identical. `repeat.json` in the audit records
both report hashes and the identical source maps.
This is not an installable or indefinitely reusable device implementation.

| Check | Observed result |
| --- | --- |
| Native queued jobs | 11 entries, all SR `0x2000`, none through a host direct transaction |
| Record/re-record | BUF 1 keeps slot 300; native allocator `start` fields are `0x2400` for A and `0x6400` for B (not CPU PCM pointers) |
| Shared selection | Original selector assigns BUF 1 to T5; T1/T5 retain slot 300 after B |
| FREEZE | Native B1-001 at slot 312 pins A; no PCM pages or duplicate source |
| Sequencing during replacement | Five original PLAY triggers, all selecting stable slot 300 |
| Four buffers | BUF 1–4 independently committed; five successful recordings total |
| CPU PCM retirement | Five native frees each restore an actual 16,384-byte buddy block; every source pointer is zero afterward |
| Failure/limits | Cancel, admission refusal, native malloc refusal, missing final header, post-alias rollback, stale completion, full generation capacity and native project/frozen-slot guards pass |
| Failed identities | Missing header, rollback and stale completion consume IDs 3–5; never reused |
| Resource callbacks | Zero host source HLE calls and zero host BUF commit transactions |
| Publication | One final logical header at the modeled packet boundary; no clear window or failed-commit logical headers |
| DSP replay | Exact ordinary-file comparison in all four phases, 88 blocks total over six reader lanes |
| Regression | 334 unit tests; SINE replay; legacy managed Flex panel flow; NORMAL mono/stereo and NORMAL after BUF |

Eight private allocations remain pinned: **128 KiB** for these short test
recordings, including three quarantined candidates. Eight generation IDs are
issued. The source-owner nodes request 64 bytes each; those are metadata,
not PCM. The source samples here contain roughly 3,120–3,184 stereo frames.
The inherited native copy primitive retains its 20-second bound, but this run
is not a 20-second throughput or hardware-headroom measurement. Ordinary GUI
heap churn is visible and is not attributed to retained recording PCM.

The original SHARC output hashes match the ordinary-file oracle:

| Phase | Blocks | SHA-256 |
| --- | --- | --- |
| A plus frozen A | 12 | `655ca1fecf548431f21964e7f7dc7bb528e2e8a8197127f9c59b068f7c197fbc` |
| Active A during B publication | 12 | `d3090e584d94b23dbec40e3abe5857f3e8913cdbe336537eb410e9e63a3e2fdd` |
| New B on T1/T5, frozen A on T6 | 40 | `f3066ab5e61416ef6eec429a0584dd1e3442ca1c45d6bdd7ce7e3873d98dde72` |
| Late frozen A after eight issued generations | 24 | `82785f2809238d040e3b07d8075800c711b660632d47948ba48ab80b27a746ed` |

These are voice work-buffer taps, not final DAC/mixer recordings. The live CPU
PLAY check and prepared DSP replay are separate observations, not a coupled
real-time CPU/DSP deadline proof.

## Implemented path and ownership

The separate `NativeWorkerUI` installs `recorder_worker_code` over the
**authenticated stock 1.16 checkpoint**. It does not patch the normal build,
legacy Flex source, dependencies, Plaits, Capicola or shortcut prototypes.

| Boundary | Executed code / ownership |
| --- | --- |
| Original manual record / stop / discard | `0x40015fda` / `0x400161fe` / `0x40015ff8`; original controller code |
| Completed-trim YES | `0x40022fbe`, destination dispatcher; NORMAL displaced stock continuation |
| Queued worker | `0x4001fc48` redirected only while a BUF job is pending |
| Worker completion | `0x4002196c`, original progress/recorder completion convention |
| Recorder chunks | `0x4001282e`; outer recursive lock `0x40012542`, unlock `0x40012552`; shared response copied before unlock |
| Native heap | `0x4011e8f0` / `0x4011e8fc`; independent 64-byte descriptor and transient native-file source |
| Hash and playback load | Original hash `0x4015aa20` / `0x4015a6dc`, loader `0x40154540` |
| Immutable generation registration | Existing native `0x10403200`; full key/reference and epoch |
| Native FREEZE | Existing `0x10403800`; cache-hit metadata alias, no PCM copy |
| Stable buffers | Four checked-empty project/sample slots, reserved once; project IDs `0x7ffd0001..4` |
| Private backing | Eight distinct checked-empty stock sample slots, pinned for the session |
| Generation IDs | `0x7ffe0001..8`, consumed once visible to the loader; failed candidates do not recycle them |
| Snapshot IDs | Existing `0x7ffc0001..8`; separately issued, pinned metadata aliases |

New worker code/state uses **emulator scratch `0x10600000..0x1060afff`**.
It is not a discovered hardware reservation or a directly shared SHARC pointer.
The prior destination UI (`0x10300000`) and FREEZE metadata/code
(`0x10400000`) remain separate. DSP allocation comes from the original pool;
no code touches or resizes Capicola's reserved 8 MiB.

ColdFire owns the transient source until the original synchronous loader
returns. The worker fills a new private allocation. The completion callback
rechecks kit/epoch/machine, associates the logical slot only with completed
backing, registers its immutable metadata, assigns the selected ONESHOT track,
publishes a stable volatile project reference and frees the source. Other
tracks continue referencing the same logical slot. Native resource dispatch
then resolves the committed metadata/cache key and rejects PCM OPEN/read/size.
A native filter at `0x10604a00`, hooked at `0x400cd638`, defers every logical-slot header while the
transaction runs. It drops intermediate clear headers and retains the completed
header in a fixed 4 KiB staging page at `0x10609000`. After validation, metadata,
assignment and source retirement succeed, the native flush at `0x10604b00`
sends the single final header through the original transport. Rollback discards the staged header, so
the old DSP descriptor remains visible. Private PCM pages are never deferred.
No Python `fw.source`, `fw.load`, `fw.assign`, `n.REGISTER` call, or host BUF
`process()` transaction participates. The latter raises if invoked.

The source list retains small identity tombstones. Its native transient-source
lookup explicitly rejects a zero source pointer, including while a later job
is busy. This prevents a failed generation from reopening through the legacy
source API. Metadata for successfully registered generations takes precedence.
Legacy Flex itself is not installed alongside this registry.

A failed private publication leaves the current logical slot untouched. A
failure after aliasing clears the candidate logical association and reloads
its old complete cache key in CPU metadata; the old DSP descriptor has never
been invalidated. CPU source storage is freed; the new private
allocation/identity remains quarantined. Restoration status is observable;
restoration failure must not be mistaken for a healthy committed buffer.
Existing reader and snapshot pins are never released by rollback.

NORMAL bypasses both the BUF worker and completion. The free-slot filter skips
the checked reservations, including snapshot slots. Original error rendering
is preserved for NORMAL; BUF failures have a separate error-text dispatch.
Original FUNC+NO discards a completed candidate. Plain NO can leave a candidate
available on returning to the recorder, so it is not used as a discard oracle.

## What is native and what is modeled

**Native CPU instructions:** recorder control, stopped/trim chunk retrieval,
locked copy, heap allocation/free, content hash, stock sample allocation and
page/header production, logical replacement/rollback, generation registration,
slot/project guards and selected-track assignment. The worker is entered by
the original queued operation, not `fw.call()` with a fabricated commit.

**Existing native diagnostic:** FREEZE registration/key/name/cache association
and rollback still execute ColdFire instructions, but its entry is the prior
paused, IPL-7 diagnostic call. The worker adapter relocates the unchanged
command body to `0x1060a000` and adds a native busy guard at `0x10604c00` behind its public entry
to refuse FREEZE during any pending recorder transaction. This increment integrates the recorder worker's
generations with that implementation; it does not add a performance-safe
queued FREEZE entry or bind a shortcut.

**Emulator models:** deterministic external recorder peer and frame count,
DSPI response peripheral boundary, SSI timing/interrupt delivery, eMMC sectors,
page delivery and prepared SHARC replay. The Python input fixture retaining
its original WAV bytes is test input, not retained ColdFire heap PCM. Native
MAIN mix capture, physical input DMA, actual DMA/cache completion, coupled
CPU+DSP deadlines, listening and hardware behavior remain unverified.

**Host diagnostics/oracles:** heap/metadata inspection, failure-fixture setup,
page capture, snapshot command invocation and ordinary-file reference creation.
They do not commit or register BUF recordings. Host readback is not native
+Drive saving. No native readback/save facility is supplied here.

## Sequencer-clock investigation

The pinned ready snapshot's VBR is `0x40000000`. Authenticated vector inspection
identifies software source 44 / vector 108 at **`0x400d5a50`**, source 57 /
vector 121 at **`0x400d7a2e`**, and scheduler source 13 / vector 205 at
`0x40000410`. These agree with `pattern_clock.py`'s delivered guest-requested
interrupts. The first handler explicitly raises IPL and clears bit 12 of
`0xfc048010`; the second clears bit 25.

The first handler reads the pattern-state pointer at `0x4316501c`, advances a
word derived from `0x431650ec`, stores it at `0x43164f98`, and compares with a
pattern field at `+0x1db74`. **The post-store boundary `0x400d5aec` is rejected
as the normal PLAY clock:** the dedicated positive run executes each interrupt
entry 612 times and emits seven real track triggers, but never reaches this
store. Its guard at `0x43158f88` stays zero and the observed counter stays one.
It appears to be a conditional transition path (inference), not the normal
master bar counter. Disabling only sequencer software-IRQ delivery preserves
SSI but produces one initial PLAY trigger, zero observed sequencer ISR entries
and no continuing sequence. Both diagnostic expectations pass.

The disassembly is in
`out/runs/recorder-worker-audit-20261021-01/clock-vectors.json`; its older decoder
explicitly leaves an unsupported instruction as `.word`, not invented C.
The reproducible positive/negative trace is
`scripts/trace-recorder-worker-clock.py`. No native bar-based recording is bound.

Do not call the loader, copy loop or recorder worker from either ISR. A future
hook should only latch an epoch-bound request and enqueue work into a known
safe task. Before enabling next-bar recording, establish the authoritative
master boundary under tempo changes, non-16-step lengths, per-track scale,
external clock, STOP/restart and pattern transitions. Neither the arp's private
tempo phase nor explicit TEST-bar events satisfy that requirement. The shortcut
trials remain dry; SAMPLING+YES is the provisional preference.

## Remaining implementation gates

- **Reclamation:** reader completion, queued packets, locks, pattern/undo roots
  and all playback-machine caches are not closed. Eight generations is a hard
  session bound, not indefinite buffer reuse or a memory plateau. Aborted
  publications can consume capacity. Never raise the bound to hide this.
- **Machine coverage:** this native worker admits ONESHOT. SLICE, GRID, WERP,
  REPITCH, stock STRETCH and Capicola need their own loading/reader tests before
  admission is broadened. Existing machines and builds remain unchanged.
- **Projects:** volatile save/load menu entry guards block transitions once
  reservations are owned. This is deliberately restrictive. All possible
  project-reset entry points are not proven covered; this is not a project
  persistence implementation.
- **FREEZE scheduling:** retain the proven metadata ABI; move its command into
  a serialized task and prove preemption/context/rollback before performance
  shortcut binding. Do not merely remove the diagnostic IPL assertion.
- **Device integration:** allocate target-owned code/state, resolve the legacy
  Flex namespace conflict through one registry/dispatcher, compose with the
  existing CPU extension/all-features patch plan, then revalidate exact combined
  image bytes and ownership. Emulator scratch is not an installable solution.
- **Saving:** native DSP readback or another bounded verified persistence path
  remains required for SAVE. Volatile data is not silently serialized as a file.


## Reproduction and provenance

Working branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, inherited dirty tree.
OS 1.16 MAIN SHA-256
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
Pinned DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`, Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`. Doctor passes.

The final core run freezes **581 source files**; source-map JSON SHA-256
`0462208938fb1b81222194a88dbba568edea7a0eb25369986741a68a901d47fc`.
The audit contains original status, before/final maps, test-file hashes and
per-address emitted-payload hashes:
`out/runs/recorder-worker-audit-20261021-01/`.
575 of 576 inherited source files are byte-preserved. The sole changed
inherited source is the NORMAL checker, adding an opt-in `--native-worker`
adapter switch. All 52 inherited unit-test files are preserved; six native
worker tests are added in one file. There is no commit, push, dependency update
or hardware transfer. Emitted worker/relocated FREEZE/trampoline payload totals
6,672 bytes, plus explicitly initialized scratch/data/header workspace.

From the repository root, using the configured Python 3.12 (choose fresh
output names when repeating):

```sh
LAB_PY="/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python"
./labctl doctor
"$LAB_PY" scripts/check-recorder-worker-native.py out/runs/recorder-worker-native-20261021-06
"$LAB_PY" scripts/check-recorder-worker-publication.py out/runs/recorder-worker-native-20261021-06 out/runs/recorder-worker-publication-20261021-05 --require-atomic
"$LAB_PY" scripts/check-recorder-normal.py out/runs/recorder-worker-normal-prebuffer-final-20261021-01 --native-worker --prebuffer
"$LAB_PY" scripts/check-recorder-normal.py out/runs/recorder-worker-normal-mono-20261021-01 --native-worker --mono
"$LAB_PY" scripts/check-flex-native-ui.py out/runs/recorder-worker-legacy-flex-20261021-01 --managed-sources
"$LAB_PY" scripts/trace-recorder-worker-clock.py out/runs/recorder-worker-clock-20261021-01
"$LAB_PY" scripts/trace-recorder-worker-clock.py out/runs/recorder-worker-clock-negative-20261021-01 --no-sequencer-irqs
"$LAB_PY" -m unittest discover -s tests -v
./labctl test sine --replay
```

The final SINE replay is
`out/runs/20261021T045032Z-test-31a84e74/manifest.json`; the unit log is
`out/recorder-worker-unittest-20261021-03.log`. NORMAL's nine OLED states,
saved PCM and disk overlay match the retained untouched-stock mono/stereo
oracles. The post-header-gate NORMAL-after-BUF check passes independently.
The earlier NORMAL comparisons are saved in `normal-parity.json` in the audit.
Legacy Flex passes native replacement, discard, control preservation and
oversize-error/retry checks without installing this new worker.

Useful captures:
`recorder-worker-native-20261021-06/01-native-buffer-ready.png` and
`02-native-four-buffers-and-frozen-a.png` under `out/runs/`.
`pages-a.bin`, `pages-af.bin`, `pages-b.bin`, `pages-all.bin` retain packet order;
the phase WAV/F32 files retain the rendered voice comparisons.

## Failed controls and corrections retained

- Native run 01 reached actual copy/registration/retirement but the test wrongly
  compared the captured prefix with the entire 12,000-frame input fixture.
  The oracle now uses the actual native accepted trim range.
- Run 03 stopped in the old all-GUI heap tracer. Its paused-call allocation
  assertion was inappropriate for the live GUI. Scoped native source-free
  observations now verify the exact buddy-block release.
- Run 04 exposed a fixture navigation mistake: plain NO retained the candidate.
  Tests now use stock FUNC+NO to discard and dismiss error dialogs separately.
- Run 05 passed batch stock-audio comparison but failed the stronger atomicity
  requirement: publication diagnostic 04 proves two logical clear headers,
  an empty DSP descriptor and a silent new trigger between packets. Old active
  reader pointers remain valid. This **architectural negative is retained**;
  final native header deferral fixes it without changing the reference oracle.
- Publication diagnostics 01–03 rejected their silent initial oracle. The final
  diagnostic uses the same voice work-buffer layer as the audio oracle, selects
  the logical sample explicitly and allows startup blocks before claiming sound.
- The real-clock candidate store receives zero hits despite continuing native
  sequencing. Both ISR entries fire; the candidate guard stays false. Next-bar
  arming remains blocked on identifying an actual master-bar contract.

## Concrete next increment

1. Preserve this bounded worker and its single-final-header invariant as the
   oracle. Add explicit reader/generation acknowledgement or close the stock
   lifetime protocol before recycling any private allocation or identity.
   The known ONESHOT reader pointers/active flags at DSP
   `0x2412cc + lane*0x1d8` (active `+0x1b8`) are not ColdFire-readable pointers
   or a proven native acknowledgement channel. Current modeled DSP replies do
   not establish reader retirement.
2. Put FREEZE behind a serialized native task request, retaining its metadata
   ABI and the new recorder-busy refusal. Validate preemption and task ownership;
   the global busy marker plus modal USE test is not proof against every
   background loader/project-reset path.
3. Resolve target code/state placement and the legacy Flex resource namespace,
   then test combined Plaits/Capicola/Flex images. Verify the header staging
   allocation, alignment, cache visibility and transport acknowledgement on
   the target; no target reservation is inferred from emulator mappings.
4. Trace the normal source-57 sequencer continuation and test master-boundary
   behavior under scale/tempo/transport/project changes. Only then connect the
   provisional SAMPLING+YES request to the recorder backend.
5. Expand playback-machine and native persistence coverage separately. Keep
   project saves guarded and do not describe host readback as native SAVE.
