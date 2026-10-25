# Native stopped-state buffer retirement

2026-10-22, Digitakt II OS 1.16. Continuation of the
[eight-seat experiment](RECORDER-SEAT-REUSE-RESULTS.md). This is an isolated
emulator implementation, with target CPU/DSP instructions and modeled capture,
LP0 delivery, cadence and SEC reset contents. No installation image is produced.

This belongs to the separate BUF 1–4 experiment. The packaged
[Flex R5 workflow](FLEX-BANK-SAVE-RESULTS.md), including Save/Discard, bank
selection and persistence, is preserved. This experiment does not replace it
or add native BUF readback/SAVE. The normal firmware builder does not install
this adapter. Combining the implementations requires a common resource/hook
dispatcher and target code/state reservation; they must not simply be installed
together. The latest generation tokens use a separate namespace, but that alone
does not establish integration compatibility.

## Native transaction

`lab/recorder_native_retirement.py` adds two jobs to the original background
worker: prepare and commit. The test command supplies only a generation token
and request serial. Native code derives the live epoch, kit, exact registry key,
private stock owner and allocation extent. The prepare job holds a lease that
blocks native recorder/FREEZE admission, new metadata acquisition of that token,
and foreign stock sample load/unload/clear operations. A permanent guard at the
original DSPI2 driver rejects private slots 304–311 in all sixteen outgoing
track selections. Both authenticated driver callers pass through this guard. Mutation authority
also requires an active native unload flag; another job on the shared worker
cannot borrow permission from the queued commit phase. The operation counter
is acquired before permission is checked and held through the stock body. An
entry preempted before counter acquisition must recheck the live lease.

The original LP0 path sends the derived tuple and extent. The unchanged native
SHARC observer/gate checks all 32 readers, 1,025 descriptors, cached/incoming
selections and a fresh control pass. `machines/recorder-native-retirement/seal.c`
then clears the single internal private descriptor only when no other observed
root exists. It never clears reader pointers or frees PCM. An eight-entry native
sealed-tuple table allows an exact retry after a lost reply, including when the
private descriptor is already empty. The general diagnostic still grants no
permission and retains its unknown-ownership mask of 127.

A separate 64-fragment completion carries epoch, unique token, sequence and an
RTOK domain word. A receipt echo cannot satisfy it. The original CPU frame ISR
matches the actual DSP reply and posts one original timer notification to the
original GUI queue, checking capacity first. The GUI poll queues commit on the
original worker; there is no host GUI poll after the command wake. Commit
revalidates roots and the matching tuple. Immediately before tombstoning the
registry entry, it briefly masks interrupts and rechecks live context, lease,
operation counts and all sixteen machine choices, closing the context-switch
interval after the longer ownership scan. It restores SR before the original
stock unload and native dead-node cleanup.

Timeout, cancellation and refused context retain the CPU allocation and token.
The previous paused-certificate command is disabled in this adapter. No host
writes a certificate, diagnostic result, completed tuple or allocator commit;
no host retirement direct call or diagnostic pump is used. The scalar and
batched read-only voice taps are cross-checked periodically.

## Executed results

The final paired runs `recorder-native-retirement-20261022-05` and `-06`
were deliberately stopped at 28 accepted recordings each. The extra 100-cycle
qualification was stopped after the user questioned the repeated testing.
Both raw reports retain `status: failed` / `KeyboardInterrupt`; neither is a
completed 100-cycle result. A separate [bounded-prefix audit](../out/runs/recorder-native-retirement-audit-20261022-01/prefix-verification.json)
checks the captured evidence without rewriting those reports. The full
qualification script remains separate and has not passed.

| Captured result, per run | Observation |
| --- | --- |
| Accepted distinct recordings | 28, with identical candidate PCM and page histories |
| Native releases | 26; current take and frozen C remain allocated |
| Native attempts | 32, including root refusals and three reply-fault timeouts |
| Common complete wire frames | 32,942, exact requests, replies, instruction counts and diagnostics |
| Voice comparisons | All 32 raw voice buffers matched stock before every captured trace row |
| Independent stock-file renders | Four exact, finite, nonzero 48-block milestones: 5, 8, 9, 16 |
| Recording DSP storage | 48 KiB peak; 32 KiB after last release, plus unrelated 8 KiB stock allocation |
| CPU source metadata | At most three linked entries at publication; completed loop iterations assert two after retirement |
| Heap free bytes at publications 16–28 | 28,099,024–28,107,984; returned to upper value at 28 |
| Worker/GUI evidence | 26 original unload calls, active flag only in unload, SR below IPL 7, distinct GUI/worker tasks |

The two stop points differ by 141 trailing frames. Each full captured trace
contains 33,465 / 33,324 successful per-frame voice comparisons; the common
32,942-frame prefix is compared exactly. Interruption prevented the normal
final whole-run PCM digest and late-frozen render from being emitted. The
heap range fluctuates by 8,960 bytes; this prefix does not qualify long-run heap
stability. The previously completed paused-certificate 100-record experiments
remain separate evidence.

The executable source manifests match both final runs. All 828 inherited files
were checked against the pre-work snapshot; only the intentional README
pointer changes afterward. No previous artifacts were replaced.

The stress driver uses original native pad retriggers of the new current BUF
to replace retained old ONESHOT pointers. It never clears those pointers itself.
A pointer that remains retained blocks sealing and leads to a safe timeout;
quiet recording without a stock reader transition can still exhaust the finite
seats. Automatic product-level retirement policy is not implemented here.

The focused suite executes twenty-four native ColdFire controls, covering exact
extent/key admission, all CPU alias pools, current/frozen/stale context,
foreign/in-flight operations, all private slots at multiple track positions,
sealed lookup, receipt-domain rejection, tuple mismatch, cancellation, native
512-frame timeout, duplicate admission, prepare callbacks and IRQ wakeup/full
queue retry. Forced changes after the root scan cannot cross the atomic
retirement point. The original stock unload executes below IPL 7.

Fifteen native DSP controls independently verify a fresh control fence,
private-only sealing, exact retry, wrong-token refusal after an empty descriptor,
active/inactive retained readers, pending private selections, logical/snapshot/
preview/other roots, unknown extents and disabled SEC. The explicit destructive
pending-descriptor comparator changes PCM. These are prepared native ABI
fixtures, separate from the coupled CPU/SEC/worker stress run.

All 394 unit tests pass; Ruff and stable-source SINE replay pass. SINE:
`out/runs/20261022T051609Z-test-fe1c40df/manifest.json`.
Unit log: `out/recorder-native-retirement-unit-20261022-05.log`.
Native DSP controls: `out/runs/recorder-native-seal-controls-20261022-08/report.json`.

The first coupled attempt correctly refused its inherited T3 STRETCH context.
The driver now selects ONESHOT through original panel events before creating
buffer identities. A three-record smoke test then passed 5,347 exact all-voice
comparisons, two native releases and an independent late-frozen stock-file
oracle. A subsequent code audit added the final atomic context recheck and its
forced-switch tests. Two stress runs were deliberately interrupted after a code audit exposed the
shared-worker admission edge. The mutation guard now requires the native active
unload interval, and its regression tests reject same-task queued jobs.
Another paired run was stopped after a native forced-preemption test exposed
the entry-before-counter race. Its red control is preserved, and the corrected
guard passes that test, counted-body admission and existing FREEZE checks.
One SINE run was retained as a source-drift failure and
rerun successfully after the sources were held stable. Early standalone DSP
control attempts corrected direct-call stack/SEC fixture setup and an inherited
request sequence; none changed the production diagnostic or seal conditions.

## Reproduction

The pinned runtime and all normal firmware builders remain unchanged. Use the
configured Python 3.12 and the explicit isolated conditional-MODIFY runtime;
choose fresh ignored output directories. Full runs use short stereo takes with
the sequencer stopped and all sixteen live kit tracks on ONESHOT.

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-native-retirement.py out/runs/YOUR-UNIQUE-NATIVE-RUN \
  --cycles 12 --faults
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  tests/native_recorder_seal.py out/runs/YOUR-UNIQUE-SEAL-CONTROLS \
  --fixture out/runs/recorder-native-retirement-smoke-20261022-02 \
  --build out/runs/YOUR-UNIQUE-NATIVE-RUN/dsp
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

The standalone controls authenticate their captured smoke fixture by hash.
Each coupled run freezes its executable source set, build/listings, native
request/reply streams, worker/ISR traces, allocation snapshots, candidate
PCM/page histories and available stock-file oracle renders. The interrupted
runs omit normal final-only fields. Use `--cycles 100 --faults` only for the
still-open full qualification; it is not necessary to repeat that to inspect
the implementation. The captured prefix can be checked without running the
emulator:

```sh
PYTHONPATH=. "$LAB_PYTHON" out/runs/recorder-native-retirement-audit-20261022-01/checkpoint.py 28
"$LAB_PYTHON" out/runs/recorder-native-retirement-audit-20261022-01/verify-prefix.py
```

## Next development step

Integrate automatic stopped-state retirement into the BUF experiment's lifecycle:
select obsolete unreferenced takes, request this transaction, handle retained
reader refusal, and preserve recording, FREEZE and saved references. The current
driver explicitly issues commands and uses native retriggers to advance old
reader pointers; that is not yet a normal-use policy. Start with a focused
record/replace/freeze/refusal flow before choosing another long qualification.
Native readback/SAVE and shipping memory placement remain separate work.
This step does not merge BUF behavior into the existing packaged Flex workflow.

## Remaining boundary

The protocol closes acquisition only in this guarded volatile private namespace.
It is not a general proof for arbitrary projects, every playback machine,
external producers, full RTOS startup or actual DMA/cache coherency. Capture
production, LP0 callback delivery, CPU/DSP cadence and SEC reset contents remain
explicit models. Voice PCM is not final DAC output, listening or physical timing.
Native readback/SAVE, shipping code/state reservation, automatic product-level
retirement policy and device operation remain separate integration work.

No hardware transfer, commit, push or publication occurred.
