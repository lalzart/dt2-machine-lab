# Native request and DSP reader observer

Digitakt II OS 1.16; isolated emulator experiment, 2026-10-21.

Follow-on: [RECORDER-ACK-RESULTS.md](RECORDER-ACK-RESULTS.md) now proves a
diagnostic native request echo through guest DMA descriptors and the original
CF receive driver, using one padding byte. Completion callback entry remains
modeled; queued-control/root closure and production integration remain open.
No allocation or identity reuse is enabled. The observer results below are
preserved as the preceding experiment.

This increment implements a ColdFire request serializer, a guarded SHARC LP0
request handler and an advisory observer running after each audio block. It
does **not** implement a native DSP-to-CPU acknowledgement or permit allocation
or identity reuse. The existing eight-generation recorder limit stays intact.
The observer exposes why a reader mask alone cannot grant retirement: a stock
trigger can acquire a generation one block after the observer reports no active
reader for it.

## Scope and ownership

New opt-in source:

- `lab/recorder_retirement.py`: guarded build, native ColdFire serializer and
  independently encoded packet oracle.
- `machines/recorder-observer/observer.c`: native request validation and reader
  observation; no allocator, slot mutation or PCM processing.
- `machines/recorder-observer/contract.json`: frozen protocol constants and
  experiment conditions; generates the C header and serializer constants.
- `scripts/check-recorder-retirement-observer.py`: executes both processors'
  instructions with named modeled transport boundaries and an unchanged stock
  SHARC comparator.
- `tests/test_recorder_retirement.py`: native ColdFire ABI and refusal tests.

The frozen proposal is `RECORDER-RETIREMENT-OBSERVER-PROPOSAL.md`, SHA-256
`b1c799972b209114ff3643bf3739e3c2af6a842f52502c8ce9fcc492240e40ee`.
Contract SHA-256:
`4fe70232dd6955d6b2fe36e30676ae46e1ef219c819a2aebfdfe445406b73134`.
Readiness was recorded before the DSP edits. Neither the normal firmware
builder nor the native recorder/FREEZE implementation is modified.

The standalone overlay appends 5,340 bytes of code in the explicitly guarded
`0x20080000..0x200bffff` experiment arena and zeroes 16 KiB of experiment state,
contexts and separate frame/event stacks at `0x200f4000..0x200f7fff`. The build
rejects loaded stock-memory overlap, wrong stock BLOB, changed patch-site bytes
and instruction-width disagreement. These are isolated emulator placements,
not approved hardware reservations or a layout composed with Plaits/Capicola.
Capicola's DDR3L reservation and status field are untouched.

## Request carrier and native observer

The original CPU page publisher is `0x400cd638(tag, data, word_order)`. It sends
a fixed 4 KiB payload. A third argument of one selects long-word metadata order;
zero uses the sample PCM halfword order. The original body contains its mutex
and a delay call; the new diagnostic captures the call at its existing harness
boundary, so physical publisher latency and completion are not measured here.

The experimental positive tag `0x46585231` (`FXR1`) lies outside the stock page
range below `0x19200`. Unpatched stock ignores it. The guarded handler replaces
the tag load at SHARC `0x1c7e35`, latches only valid requests, then returns through
the original rearm path at `0x1c7e43`. Ordinary tags replay the displaced load and
continue at `0x1c7e38`. LP0's descriptor remains `0x268220`, input tag `0x268240`,
payload `0x268244`, and length `0x401` words. Original sample page copy remains
`0x1c403c`, addressing the sample window `0x8422b9c8 + (page << 12)`.

ColdFire instructions construct the packet, clear its padding, validate bounds
and call the stock publisher address. They do not dereference a SHARC pointer.
The 64-byte metadata contains version, project epoch, generation, sequence,
logical allocation start/size, complemented sequence and final marker. Only
nonzero epochs/sequences, worker identities `0x7ffe0001..0x7ffe0008`, 8 KiB
alignment and spans within `[0x400, 0x18800400)` are accepted. That is the normal
392 MiB pool boundary, excluding Capicola. This diagnostic does not allocate or
reserve another PCM workspace.

The LP0 handler commits a local request revision last and invalidates the old
observation. Exact duplicates are idempotent; malformed, stale and conflicting
duplicate requests preserve the prior request. A larger epoch permits sequence
restart, while a separate revision prevents request ABA. Revision exhaustion
refuses new requests. These epoch tests exercise the protocol, not project
transition cleanup.

The post-block hook at `0x1c75c5` runs after the original timing-word write and
replays displaced `I2`/`I3` reloads before `0x1c75c9`. Native code scans:

- All 32 standard voice records at `0x2412cc + lane*0x1d8`, comparing pointer
  `+0` with the complete requested allocation and checking active byte `+0x1b8`.
  It reports active and retained-but-inactive pointer masks separately.
- All 1,025 stock slot descriptors at `0x257810 + slot*20`, including preview
  slot 1024. Both channel extents count as roots when they overlap the allocation.
  Malformed/out-of-pool descriptors produce an unknown-root count.

The observer snapshots revision/identity, checks revision after the scan, then
commits its result revision last. A cooperative native mid-scan replacement
invalidates the result. This test seam does not prove interrupt preemption,
SIMD/context behavior at arbitrary instructions, cache coherency or DMA ordering.
States are `IDLE_UNSEALED`, `SLOT_ROOTED`, `ACTIVE` and `UNKNOWN`; none grants
permission to retire. Only the current prepared scalar callback/frame boundary
is exercised.

## Why the return path remains blocked

The CPU DSPI2 receive buffer starts at `0x8000488c`, has `0xabc` bytes and ends
at TX start `0x80005348`. The bounded audit found concrete conflicts:

| Reply area | Evidence / ownership |
| --- | --- |
| `+0x1a` | Existing Capicola feedback: CPU `0x800048a6`, DSP reply banks `0x266220/0x267220 + 0x1a` |
| `[+0x1c, +0xa9c)` | 32 records of `0x54` bytes. Original CF `0x40139fca` conditionally rewrites these records, with stride `0x54`, fourteen six-byte writes or a whole-record clear. Original `0x4002d36c` also reads packed 24-bit samples using receive `+0x1c`, row stride `0x2a` and three-byte channel offsets for selectors above 13. This is used signal payload. |
| `[+0xa9c, +0xabc)` | Original CF `0x4002f0e6` reads banked halfwords, covering the final 32 bytes. This is not a spare tail. |

Disassembly is retained under
`out/runs/recorder-retirement-audit-20261021-01/`, including the packed-sample
reader, reply consumers and reply-record writer. This establishes conflicts at
these candidate locations; it is not an exhaustive proof that every possible
return mechanism is unavailable.

The pinned DigiKit `LiveFramePeer.exchange()` returns zeros after submitting a
CPU frame. It does not execute native SPI transmission and deliver a matching
reply completion. Reading observer state from the host cannot fill this gap.
No reply field or frame size is changed, and no CPU acknowledgement consumer is
installed. Native transport loss/reorder/timeout and acknowledgement matching
remain untested because there is no native return carrier in this increment.

## Evidence boundaries

**Target instructions executed:** ColdFire packet construction, validation and
publisher call ABI; patched and original SHARC LP0 dispatch; native latch,
observer and original ONESHOT processing.

**Host-assisted/model boundaries:** the stock CPU publisher call is captured
before its body executes; the harness delivers the resulting bytes and enters
the original LP0 callback with modeled DMA/interrupt entry/exit. Recorder
A/B/FREEZE page histories come from the authenticated preceding native worker
experiment. The host drives audio-block calls, inspects scratch results and
compares original voice buffers. It does not simulate the observer's masks or
construct a successful BUF commit in this probe. Direct synthetic lane/root
fixtures and a cooperative race seam are explicitly separate from audible stock
voice playback.

**Not established:** native duplex transport or acknowledgement, retirement,
identity recycling, native capture producer/readback/SAVE, queued-control and
project/root closure, other-machine lifetimes, final DAC output, listening,
coupled real-time execution, physical timing or hardware behavior. Snapshot
alias ownership remains the preceding native FREEZE implementation; this code
observes those roots without changing them.

## Failed controls retained

- Initial build omitted the local upper-bound spill in the pinned compiler's
  inlined overlap calculation. The native root count was zero while the
  independent oracle found slots 300, 304 and 312. Requiring a concrete volatile
  local spill fixed the generated code. The old binary, generated assembly and
  independent expected-failure recheck remain in the audit; compiler/dependencies
  and comparison expectations were not altered.
- Probe `-01`: an added zero-trigger priming frame did not reproduce the prepared
  stock trigger history. The corrected fixture uses the previously proven first
  frame trigger.
- Probe `-02`: expected B to become active in the trigger block. It actually
  becomes active the following block. This became the queued-control negative
  test, rather than being hidden by a changed retirement expectation.
- Probe `-03`: 256 blocks were insufficient for the frozen reader's retained
  low pitch. The final wait bound is derived from its native Q31 reader step.
- Probe `-04`: the cooperative injection wrote raw CPU metadata directly into
  DSP RAM without LP0's word conversion. Native validation correctly rejected
  it. A separate replay retains both the rejection and the valid converted
  injection. The request decoder was not relaxed.

All failed directories, their source snapshots and reports remain in ignored
output. Exact successful results, resource costs and reproduction follow below.

## Executable results

Primary passing probe:
`out/runs/recorder-retirement-observer-20261021-05/report.json`.
Exact repeat: `recorder-retirement-observer-20261021-06/report.json`. All sixteen
contract conditions, queued-trigger observations, natural-end fixture, compiled
image, per-block instruction counts, sampled state and PCM history match
exactly. Both complete 588-file frozen-source snapshots are verified against
their manifests. Comparison: audit `exact-repeat.json`.

| Case | Native observation / result |
| --- | --- |
| No request | Request state remains zero; original PCM/replies remain exact |
| Ignored stock tag | Original unpatched callback ignores FXR1; later original playback remains exact |
| Request without audio block | Request revision is committed; result revision stays zero |
| A playing on shared T1/T5 and frozen T6 | Active mask `0x0f03`, three slot roots (300, 304, 312) |
| B prepared and published while A plays | Old readers remain exact; no observer mutation of PCM or descriptors |
| B trigger block | B mask zero, two slot roots; this is `SLOT_ROOTED`, not permission |
| Following block | B mask `0x0303` for T1/T5; the same outstanding request now sees active readers |
| Frozen A after replacement | A mask `0x0c00`, two roots (private 304 and snapshot 312) |
| Natural A completion | At total block 2,827: active zero, retained-pointer mask `0x0c00`, two roots remain |
| Late frozen A trigger | Native playback reacquires A: mask `0x0c00`; exact stock PCM |
| Malformed metadata | Fourteen cases rejected without replacing the committed request |
| Duplicate/stale requests | Exact duplicate counted once; old epoch/sequence and conflicting duplicate rejected; larger epoch accepted with restarted sequence |
| Native synthetic ABI fixtures | All 32 individual lane bits, all-active `0xffffffff`, all-inactive retained pointers, overlapping-start/preview roots, unknown descriptor status and rootless `IDLE_UNSEALED` pass |
| Cooperative supersede | Native mid-scan latch advances revision; old result stays invalid; following scan reports new identity/sequence |
| Revision exhaustion | `0xffffffff` refuses a new native LP0 request without changing the request fields |

The native Q31 step for frozen T6 is `37,350,456 / 2^31` frames per internal
sample; its length is 3,120 frames. The bounded wait is
`ceil(length / (step * 64)) + 128 = 2,931` blocks. Original record duration
alone cannot bound a reader's lifetime when pitch and looping are independent.

All 2,830 compared blocks match the unchanged stock engine byte-for-byte in
all 32 voice work buffers (64 words per lane), both complete `0xabc` reply
banks, and exercised descriptors 300, 304, 305 and 312. The voice-history hash is
`3a7858f162bd8a90ed51feabef5f5c3614a31ce1b0f186c5cb4e67447f465905`.
This includes unused lane work buffers; the 32 simultaneous active-lane case is
a separate synthetic state fixture, not a claim of 32 audible voices.

The trigger-block mask changing from zero to active is the unsafe-comparator
failure: accepting an idle **reader mask alone** could release storage before
the queued trigger acquires it. These examples still have descriptor roots,
which correctly pin them independently. This experiment does not claim that
clearing all roots also drains native queued controls.

Resource observations:

| Resource / cost | Result |
| --- | --- |
| Native CF serializer | 288 emitted bytes; 8 KiB experiment mapping includes one reusable 4 KiB request packet; no PCM allocation |
| SHARC additions | 5,340 code bytes; 16 KiB zeroed state/context/stack mapping; no sample allocation or identity consumption |
| No-request block | 337 additional emulator instructions |
| Requested blocks | 51,168–51,330 additional emulator instructions, mean 51,234.30 over 2,829 blocks |
| Total requested block count | Stock 219,370–237,918 instructions; patched 270,602–289,182 instructions |
| Storage policy | No DSP free/reuse, no native CPU acknowledgement, no new long-lived CPU PCM copy; existing recorder cap remains eight issued generations |

The fixed 1,025-descriptor scan is diagnostic work, not a shipping performance
budget. It should not be added unconditionally to production rendering. The
hook deliberately follows the stock timing-word write, preserving reply bytes;
that stock field therefore excludes observer overhead. The table uses total
native instruction counts measured separately. They are not SHARC cycle counts,
DDR bandwidth measurements or evidence of meeting the hardware deadline.

Regression results: 348 unit tests pass; `./labctl test sine --replay` passes
(`20261021T113414Z-test-ba71e739/manifest.json`); existing atomic-publication
probe passes with `--require-atomic`
(`recorder-retirement-publication-20261021-01/report.json`). Focused Ruff checks
pass. No Plaits/Capicola composition or new device behavior is inferred from
these regressions; their implementation sources remain byte-exact.

## Provenance and reproduction

Base branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus inherited uncommitted work.
HEAD alone does not reproduce this experiment. All 584 inherited source files
and all 54 inherited unit-test files remain byte-exact. Four new source/contract
files and one new unit file are added. No dependency, normal builder, shortcut,
native recorder, legacy Flex, Plaits or Capicola source is changed.

- Final 588-source manifest SHA-256:
  `657dd23a10c937b24d6a5167aa9d179774f10f8fe615e6b06573fddc8a15f854`.
- Final 55-file unit-test manifest SHA-256:
  `fb5a41b3266db6c7f4b7cc1d5f14339427924966ca1903d7133c87de977c593e`.
- Generated isolated BLOB SHA-256:
  `1297ae4db2b155478dea0627e694631bf30f3c1a40de7860317cc6f4a87e9205`.
- Original MAIN SHA-256:
  `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
- Original BLOB SHA-256:
  `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
- DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache
  `2b26d3b75c53063575bc5c820fa0d38879335187`. Neither dependency is edited.

Each probe saves its full executed source map/text, build, linked listing,
packet checks and native instruction counts. Audit directory:
`out/runs/recorder-retirement-audit-20261021-01/`; preservation report:
`preservation.json`. Unit log: `out/recorder-retirement-unittest-20261021-01.log`.

The input is the retained, authenticated native worker/FREEZE run
`out/runs/recorder-freeze-queue-native-20261021-02/`:

| Input | SHA-256 |
| --- | --- |
| `report.json` | `5053a977dd664b473692ce3b9e9769b847d403c2440062b8af84bcdfc8a2f579` |
| `pages-af.bin` | `ef0b4314174803a6535feb326c3f29951c4b211d0f0ab6cbbe4615cac99eee29` |
| `pages-b.bin` | `e596b46a882600036d0c258eb2b66e06ccdd7e4ff52e2c85f82ac79d9218159e` |

These private local fixtures must be retained with the source snapshots. The
probe refuses a missing or changed fixture rather than synthesizing a commit.
`stock_inputs()` also authenticates the prepared stock snapshot, card and LP0
capture. To reproduce in this configured workspace, choose fresh run names:

```sh
PYTHON=$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')
./labctl doctor
"$PYTHON" scripts/check-recorder-retirement-observer.py out/runs/retirement-repro-01
"$PYTHON" scripts/check-recorder-retirement-observer.py out/runs/retirement-repro-02
"$PYTHON" scripts/check-recorder-worker-publication.py out/runs/recorder-freeze-queue-native-20261021-02 out/runs/retirement-publication-repro --require-atomic
"$PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
"$PYTHON" -m ruff check lab/recorder_retirement.py scripts/check-recorder-retirement-observer.py tests/test_recorder_retirement.py
```

## Next implementation gate

1. Trace the original SHARC reply producer and complete ColdFire receive
   processing, then select an explicit, non-conflicting return protocol and
   model its actual completion in the emulator. Preserve signal payload,
   Capicola feedback and frame size. First return an identity/epoch/sequence echo;
   demonstrate loss, duplicate, stale and reordered responses without freeing.
   A host scratch read cannot be used as the transport.
2. Establish a generation-specific queued-control barrier and stop new
   references before retiring old backing. Combine DSP readers with logical
   slots, CPU cache aliases, snapshots, sample locks, preview, queued events,
   project and save-job roots. The current scan does not close these lifetimes.
3. Bound observer cost outside unconditional per-block production work. Audit
   real context/interrupt behavior, composed placement, cache/peripheral
   completion and hardware timing before a device candidate.
4. Only after matching native acknowledgement and root closure may ColdFire
   release the private stock slot. Keep identities immutable until their own
   lifetime protocol is proven. Then test hundreds of successful re-recordings
   with frozen snapshots and a bounded DSP/CPU plateau.

The present finite native record → sequence → replace → queued FREEZE workflow
remains the fallback. Native SAVE/readback and a verified real sequencer bar
edge remain separate dependencies. No firmware was flashed, uploaded, committed
or published.
