# Optional native Flex source ownership — 2026-10-08

Historical source-ownership milestone. The later [capacity continuation](FLEX-CAPACITY-RESULTS.md)
replaces whole-take Save As scratch with 32 KiB streaming and records newer final
candidate hashes. The evidence and remaining identity/lifecycle limits below remain
preserved as the original stage results.

The bounded CPU-source reclamation stage is implemented behind `--managed-sources`.
The broader memory redesign is **not complete**. Default builds retain the exact
legacy behavior and bytes. This is a local OS 1.16 experiment, not hardware readiness.
No firmware was sent, committed or published.

## Implemented behavior

Accepted takes have an immutable 64-byte descriptor and a separate native sample
allocation. Active RAM reads and saves pin that allocation. Successful named save
or project persistence may detach/free the source only after exact backing
validation and a second check of the cached reference and active reader count.
Descriptors stay allocated; old synthetic handles keep their take identity and
position and open/read/close the backing file when RAM is absent. A repeated Save
As uses a bounded temporary allocation, then the existing exclusive writer and
hash/length checks. Unsaved takes stay in RAM, including inactive-pattern material.

Failed published candidates become tombstones. Their source is freed immediately
or after the last active reader drains; only the matching loader slot is cleared.
Assignment failure preserves the previous kit and project pool. Pre-publication
allocation/copy failure releases allocations without spending an identity.

The named-save dialog reports requested Flex CPU bytes and issued identities, for
example `FLEX SAVED / RAM 64 B / TAKES 1/32`. It excludes allocator overhead,
recorder/playback RAM and other firmware consumers. It is not a free-memory meter.
20-second mono/stereo, ONESHOT, explicit naming, automatic persistence on project
save, and the Plaits-before-MIDI display order remain intact.

## Corrected durable-reference gate

Actual OS 1.16 resolver `0x4015b178` returns 1 only on the exact ID, nonzero serial,
hash and length match. Statuses 2–4 are recovery matches, not exact identity proof.
Reference-open `0x4015b2d0` propagates that status and opens a handle for positive
results. The previous implementation incorrectly treated every positive status
as sufficient. The deliberate hash-corruption test exposed this error.

Retirement and cached-project reuse now require status 1. Backing reads close
positive nonexact handles without reading. Save As uses that same read path.
Negative tests independently corrupt each of the four words and supply a missing
reference: the remaining RAM source is retained; backed read, Save As and project
persistence reject the reference without wrong PCM, file writes or publication.
Valid restore/read/Save As/stock reload still match PCM exactly.

Original failures remain in `flex-managed-{mono,stereo}-final`; their misleading
`running` report status was corrected to `FAIL` with the observed error. The
lifetime harness now records exception failures. Early `flex-exact-backing-01`
through `-07` placement attempts failed before producing a runnable candidate.
Compact integer forms and range-constrained placement of split routines fit the
same guarded candidate gaps; no additional RAM/code region was claimed for this fix.

## Final evidence

Paths below are relative to the lab. All tests execute modeled/native CPU or
prepared DSP paths; they are not physical device tests.

| Gate | Evidence | Result |
| --- | --- | --- |
| Source suite | `out/research/flex-memory-implementation-2026-10-08/exact-source-tests-final.log` | 90 tests passed, including active-reader, retirement-owner, allocation/copy failure and recovery-status negatives |
| Strict backing and 20-second mono | `out/runs/flex-exact-mono-20s/report.json` | PASS; 1,920,144 requested bytes to 64 after retirement |
| Strict backing and 20-second stereo | `out/runs/flex-exact-stereo-20s/report.json` | PASS; 3,840,144 requested bytes to 64 after retirement |
| Project/failure transaction | `out/runs/flex-exact-project/report.json` | PASS; stock project serializer/reload, actual assignment rejection, loader failure, short-write/collision controls |
| Recorder UI | `out/runs/flex-exact-use-ui/report.json` | PASS; USE, discard, replacement, oversize retry, original job/panel path |
| Named-save UI | `out/runs/flex-exact-save-ui/report.json` | PASS; naming/cancel/collision, source retirement, independent stock PCM reload; `saved.png` inspected |
| Sequential source reuse | `out/runs/flex-exact-reuse-32/report.json` | PASS; 32 native accept/persist cycles, five source addresses reused, 0 retained PCM and 2,048 descriptor bytes, earliest take unchanged; 33rd safely rejected |
| Legacy parity | `out/runs/flex-exact-package/legacy-parity.json` | PASS; stock, R3 and R3/menu default outputs byte-exact |
| Menu | `out/runs/flex-exact-package/menu-check.json` | PASS; four display-order bytes, original machine IDs |
| Combined boot | `out/runs/flex-exact-boot/report.json` | PASS; 400M ColdFire instructions, nine tasks, all 96 native/menu writes retained; stock DSP boot peer |
| Container/repeat | `out/runs/flex-exact-package/native-patches.json` | PASS; deterministic output and container guards; Plaits DSP unchanged |
| Stable-source SINE replay | `out/runs/20261008T071935Z-test-a3a50ac4/manifest.json` | PASS; behavioral baseline, exact repeat, stock isolation and lifecycle; source snapshot stable |

The earlier SINE run `20261008T070109Z-test-dbdef97b` has behavioral `result.json`
`ok=true`, including exact-repeat/baseline, stock isolation and lifecycle checks.
Its outer manifest failed because source changed during the run. It remains a
failed provenance run, not a behavioral regression or a passing final gate.

Older positive reports remain historical supporting traces. Final firmware
placement changed, so the final runs above supersede old placement/UI/boot checks.
The baseline code/output hashes establish applicability of existing legacy
behavioral checks; the final managed path was rerun independently.

## Exact artifacts

Final local candidate: `out/runs/flex-exact-package/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`.

- SYX SHA-256: `1ccb39e9686115a8122c1bcf2383fbef3b6e75e0edf97d0ccbab814d97a09f88`
- Combined MAIN with menu: `243a87d5e47934e31729d34a839a96d71637791f9014ad3f4f0e5adfee2f7933`
- Managed stock MAIN exercised by loader tests: `358c521cc80339d222591f1b2ba6fe9ee5d3deaf17b9f188bce838b454fb4912`
- Pre-menu R3 MAIN: `a6b078ee34b6b3ca0679fb4ba06901626cfccc762fc2f775013c2d1c3b84b241`
- Plaits DSP: `b52b60c208cd3a9a9b88dd4db6ee0895754970cb34b48efccc2646f134159b3f`

Complete final source hashes are in
`out/research/flex-memory-implementation-2026-10-08/final-source-manifest.json`.
Exact stock resolver/allocator disassembly is alongside it in
`exact-resolver-and-allocator.asm`. Pinned DigiKit remains
`277760aad51b036a4756db051409d4d3b1eeccbc`; no dependency or Plaits DSP changes.

Reproduce from the lab with its configured Python and pinned snapshot:

```sh
python3 scripts/check-flex-lifetime.py out/runs/UNIQUE --managed-sources --frames 960000 --stereo
python3 scripts/probe-flex-native.py out/runs/UNIQUE --managed-sources --snapshot /absolute/path/to/dt2-1.16/running.snap
python3 scripts/build-flex-native.py out/runs/UNIQUE --plaits-r3 --plaits-before-midi --managed-sources --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

Use a distinct nonexistent output directory for each command. The source suite
requires the configured patched Unicorn Python, not an arbitrary system runtime.

## Remaining capabilities and exact missing invariants

**More than 32 sequential published takes is unsupported.** Source bytes return,
but identity capacity does not. Published failed candidates also spend identities.
The observed late synthetic handle remains valid after the loader closes its own
handle and after stock slot clear. Handles carry an ID/position, not a validated
generation lease. No complete enumeration of inactive patterns, locks, undo,
clipboard, queued callbacks or other retained references is established. Recycling
an ID/descriptor would let an old handle resolve a different take. The guard is
therefore retained. Next experiment: instrument all synthetic opens/closes and
reference copies through pattern/undo/project teardown; establish epoch boundaries
and drain acknowledgments, then test a generation-aware handle/descriptor design
with stale handles across >32 jobs and generation wrap. Merely increasing the
range is not this experiment.

**Independent safe byte admission is not implemented.** Current bounds are
960,000 frames, 32 issued identities and checked original malloc failure. The largest
source file is 3,840,080 bytes plus its 64-byte descriptor. Saved-source Save As
needs at most one extra source-sized allocation. The counters expose these requests;
they do not reserve stock headroom or prove a capacity guarantee. Allocator wrappers
were traced to `0x4011e674` / `0x4011e87a`, but a worst-case live-demand envelope and
largest-contiguous-free-block invariant for all stock consumers remain missing.
Next experiment: trace original allocation/free sizes, arena bounds and high-water
marks during maximum supported stock project/recording/UI/save workloads, including
fragmentation and failed allocation. Derive protected headroom before introducing
an admission budget. No speculative 16 MiB reservation or capacity reduction was
introduced.

**Full project lifecycle and unsaved-root reclamation remain unproved.** Existing
pointer checks reject observed stale assignment/project contexts, but are not epoch
proof against address reuse. Unsaved sources and tiny descriptors stay pinned until
reboot; inactive-pattern audio is not reclaimed based on current-track reachability.
Next experiment: trace project load/new/reload/discard teardown and queued callbacks
with deliberately delayed jobs and same-address reuse, then establish a project
epoch and all-root scan before adding GC.

**Physical concurrency and durability remain separate.** Tests model peripheral
I/O and selected interleavings. They do not establish hardware memory ordering,
real-time audio continuity, flash flush/power-loss semantics, simultaneous external
backing-file mutation, or exhaustive asset use of padding. A backing file removed
or modified after retirement causes reads/saves to fail; RAM is not resurrected.
Cold boot validates the exercised paths, not universal code-padding ownership.
No hardware-ready label is warranted by this report.
