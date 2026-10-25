# Bounded native live-buffer slot reuse

2026-10-22, Digitakt II OS 1.16. Continuation of
[the eight-seat plan](RECORDER-SEAT-REUSE-PLAN.md) and
[native DSP allocation reuse](RECORDER-DSP-REUSE-RESULTS.md).

**EVIDENCE:** two independent emulator runs each complete 100 native
record/trim/USE transactions with one immutable queued FREEZE snapshot retained.
Eight physical registry/private slots are reused with unique generation tokens;
the former eight-issued-generation limit no longer ends this experiment.
Complete reports and 216 captured/built artifacts repeat byte for byte.

## What changed

`lab/recorder_seat_reuse.py` supplies an opt-in ColdFire overlay, installed by
`lab/recorder_seat_native.py`. A bounded eight-entry lookup matches the exact
token and project epoch. Registration uses a vacant physical entry, separately
from the monotonically issued token. Tokens occupy `0x7ffb0001..0x7ffbffff`,
outside the existing Flex, logical BUF and FREEZE namespaces; exhaustion refuses
without wrapping. Reset requires a fresh isolated session.

The existing reclamation command still requires its exclusive paused-test
certificate and an actual native SHARC diagnostic. After the last stock owner
is unloaded, native code unlinks/frees the dead 64-byte CPU source descriptor
and vacates its registry entry. Frozen/current entries stay pinned. An
allocation failure returns an unexposed reservation; an exposed failed candidate
keeps a quarantined entry and its consumed token. Quarantined entries can still
fill the finite registry: this is not indefinite recording under arbitrary
failure conditions.

The diagnostic is rebuilt with only FIRST_ID/LAST_ID changed. Its reader and
descriptor scans, pending-selection checks, zero allocator permission and
unknown-ownership mask remain unchanged. All 821 inherited source, test,
contract and documentation files captured at startup remain byte-identical.
Normal builders and pinned dependencies were not edited.

## Executed results

Primary runs: `out/runs/recorder-seat-reuse-20261022-03` and `-04`.
Aggregate checks: `out/runs/recorder-seat-continuation-audit-20261022-01/verification.json`.

| Check | Result in each run |
| --- | --- |
| Native record/trim/USE | 100 successes, 100 distinct tokens and distinct captured PCM |
| Logical selection | BUF 1 remains stock slot 300 |
| Native stock allocator release | 98 obsolete generations released; physical slots and extents reused |
| Frozen C | Slot 312 remains pinned; late voice PCM equals original C exactly |
| Recording DSP allocations | Peak 48 KiB; 32 KiB at cycle 100 for current + frozen C |
| Unrelated fixture allocation | Separate 8 KiB, preserved |
| Linked CPU source descriptors | Peak 3; 2 at cycle 100 |
| Temporary CPU PCM | 100 successful native source frees; no accepted source PCM retained |
| CPU free bytes at publication, cycles 16–100 | 28,108,016–28,108,032, a 16-byte variation |
| CPU free bytes after cycle-100 reclamation | 28,108,128 |
| Stock-file voice oracle | Exact non-silent 48-block comparisons for B, C, 5, 8, 9, 16, 32, 64, 100 and late frozen C |
| Refusals | Active/pending reader, frozen root, missing exclusive certificate, stale token after address/entry reuse, real allocation failure, unpublished candidate and token exhaustion |

These are short stereo takes of 3,056–3,200 frames, approximately 64–67 ms.
The memory measurements above describe the successful replacement workload
before deliberately failed-candidate controls. A failed published candidate
may retain quarantined DSP storage. The test does not measure twenty-second
throughput, total device headroom or physical capture timing.

All 370 unit tests pass, including seven new native-instruction tests covering
full entries, stale tokens, epoch checks, exact registration, dead-node unlink,
unexposed failure cleanup and token exhaustion. Ruff and SINE replay pass.
The final unit log is `out/recorder-seat-units-20261022-02.log`; SINE report:
`out/runs/20261022T001245Z-test-42f3c2f5/manifest.json`.

## Provenance and reproduction

Base branch `codex/plaits-macro-controls`, HEAD `77b1c2a`, plus preserved
inherited work. Each successful run retains `sources.json`, executed sources,
native allocator traces, source frees, all candidate PCM/page histories and
independent oracle renders. The portable experiment contract is
`machines/recorder-seat-reuse/contract.json`.

* MAIN OS 1.16 SHA-256: `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
* Diagnostic blob: `5e4ea873e61f45cf404795b5a1244c8df77f996051b3d13195049bae488e0cd1`.
* Reclamation command: `3d3c3e9b85f8cc38149c58e5e79e4da0201e0cfecd593557b9f9a78334b70a79`.
* Explicit isolated conditional-MODIFY runtime: `9d2374a3fd6f4123e6cd2356f4e2c110b022282ddb8e0b788636be08b285c24d`.

Use fresh output names:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-seat-reuse.py out/runs/YOUR-UNIQUE-SEAT-RUN
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

The first smoke run passed. Full attempts `-01/-02` were deliberately interrupted
after 42/29 successes when a separate short control exposed a driver mistake:
expected recorder errors needed dismissal before the next recording. The driver
was corrected; `recorder-seat-tail-controls-20261022-02` passes all three final
failure controls before the full `-03/-04` repeats. A shorter panel-cadence probe
lost its initial pad trigger and was rejected; the original cadence is retained.
Failed/interrupted runs and executed probe text remain available. No baseline
expectation was rewritten.

## Remaining boundary

Capture production, LP0 delivery, diagnostic-result delivery and the exclusive
pause certificate remain explicit models. Native CPU allocator operations and
prepared original-SHARC ONESHOT execution are separate observations. Voice PCM
is not final DAC output, listening, coupled real-time operation or device proof.

The next increment is a native stopped-state ownership transaction: seal new
acquisitions, order a consumer fence, receive a matching completion, then perform
the proven final-owner unload. Arbitrary project/pattern/lock/undo roots, other
playback machines, DMA/cache visibility, native SAVE/readback, target code/state
placement and hardware timing remain open. This experiment produces no
installation image and does not establish a general live-retirement fence.
