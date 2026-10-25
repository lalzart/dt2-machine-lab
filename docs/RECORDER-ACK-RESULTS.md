# Native recorder request echo results

Digitakt II OS 1.16, 2026-10-21; isolated emulator prototype.

**The diagnostic request/receipt round trip works through target instructions
and descriptor-driven peripheral models.** SHARC constructs the echo; the
original ColdFire driver receives it and native ColdFire code matches the
generation, project epoch and sequence. No host code sets a successful receipt.
Memory reuse remains disabled, and the recorder's eight-generation limit is
unchanged. This is a request receipt, not proof that old readers have retired.

## Implemented path and evidence boundaries

```
CF native request + expected-fragment construction
  -> existing publisher call captured at 0x400cd638
  -> modeled LP0 delivery, original SHARC callback and validated FXR1 latch
  -> native post-block echo construction in the selected reply bank
  -> original SPI2 DMA descriptors / pinned native DMA model
  -> pinned ColdFire DSPI2/eDMA model, receive staging at 0x80001000
  -> original CF driver copies the previous staging buffer to 0x8000488c
  -> native CF matcher confirms only its outstanding tuple
```

The original CF driver body at `0x400cd2bc`, its receive copy and DMA setup
execute; no driver HLE replaces them. Original setter `0x400cd2b0(0xabc)`
initializes its frame-length variable. The frame remains `0xabc` bytes with
`0x802` real TX bytes. The stock driver copies the **previous** receive staging
buffer before starting the next exchange. An independent preflight observed
receive histories zero → `0x5b` → `0x5c` while new staging advanced
`0x5b` → `0x5c` → `0x5d`.

Original SHARC initializer `0x1c7bd4(0xabc)` builds these circular descriptors:

| Direction | Descriptor | Next | Buffer byte alias | CFG / count / modify |
| --- | --- | --- | --- | --- |
| RX | `0x2641b0` | `0x282641cc` | `0x28265220` | `0x144117`, `0x55e`, 2 |
| RX | `0x2641cc` | `0x282641b0` | `0x28264220` | same |
| TX | `0x2641e8` | `0x28264204` | `0x28267220` | `0x144115`, `0x55e`, 2 |
| TX | `0x264204` | `0x282641e8` | `0x28266220` | same |

The native peripheral model fetches those guest descriptors, transfers bytes,
advances the lists and marks DMA completion. Its TX bytes are passed to the
existing ColdFire eDMA model; the peer does not synthesize a positive reply.
SHARC byte aliases and CPU addresses are separate address spaces.

**Still modeled:** LP0 publisher body/completion, wire and DMA events, block
cadence and entry to original completion callback `0x1c77b4` with event `0x20`.
The prepared checkpoint lacks SEC source-register reset contents; the harness
explicitly supplies a zero SEC source control/status bank, consistent with the
pinned peripheral model's absent-register default. It does not supply descriptors
or echo bytes. Actual SEC acceptance/ACK/END, preemption, SPI pin configuration,
coupled real-time scheduling and hardware timing are not established.

The CF matcher is invoked through a native diagnostic pump, not installed in
the running production GUI/interrupt path or native recorder worker. A host
harness invokes the pump and inspects its result. A/B/FREEZE page histories are
authenticated outputs of the preceding native worker experiment. This probe
does not newly capture recorder input or implement SAVE/readback.

## Carrier audit and protocol

The selected carrier is **DSP reply byte `+25`**, arriving at **CF wire byte
`+24`** after the existing 16-bit word byte swap. The rest of the frame retains
its stock meaning.

Original SHARC `0x1c3241..0x1c324b` combines a byte from `0x2528e8`, shifted
16 bits, with a masked 16-bit value and stores it at reply `+22`. Consequently:

- DSP `+22/+23` carry the low 16-bit stock value.
- DSP `+24` carries a stock flag. The whole halfword `+24/+25` cannot be borrowed.
- DSP `+25` is zero padding in that producer.
- DSP `+26/+27` remain Capicola's field.

The initial whole-word sentinel control failed because the stock producer
rewrites that halfword. This led to the one-byte choice. The final native probe
uses a nonzero stock flag `0x7b` and a separate Capicola sentinel `0x8abc`;
both survive every comparison. A read-only stock CPU panel/PLAY/recorder run
finished at 1,109 total frames and observed 1,001 header reads at `0x4002f10e`,
reply `+22`, size two. Instrumentation starts after warmup: the total-frame
figure in the proposal must not be read as 1,109 instrumented frames. No
observed access overlapped the proposed carrier. The other known reply
areas remain occupied signal payload or tail data, as recorded in the previous
observer audit. This is bounded OS 1.16 evidence, not exhaustive approval for
every stock/composed mode.

The existing FXR1 request is unchanged. Each echo cycles through 48 fragments,
two payload bits per fragment, from `[epoch, generation, sequence]`. A fragment
byte is `(index << 2) | two_bits`, with indexes 0–47. CF constructs its expected
48-byte table using native instructions and accepts only a complete ordered
match of all 96 bits. Index zero restarts assembly; bad indexes or data reset
progress. No request and stock-zero replies cannot confirm. After 192 native
polls the outstanding request times out without releasing storage.

Newer requests supersede old state; lower epoch/sequence and conflicting
duplicates refuse before publication. Exact same tuple/extent submissions and
already confirmed receipts are idempotent. The epoch checks are protocol tests,
not a complete project transition or restart protocol. Reconnect/reset needs
its own fresh session/drain policy before this could authorize anything.

The emitter uses the stock block's selected reply pointer and writes no other
bank. The pinned C compiler implements the byte update as an aligned 32-bit
read/modify/write, preserving the neighboring flag and Capicola bytes. The
emulator tests prove those preserved values under serial execution. They do
**not** prove atomicity against a concurrent hardware writer or DMA/cache
behavior; production integration requires that audit or a proven byte-store
implementation.

## Executable results

The first complete run, `out/runs/recorder-ack-native-20261021-03`, passed all
17 frozen contract conditions. The final source adds full request, TX and
native/delivered reply captures for independent inspection. Final runs
`recorder-ack-native-20261021-05` and `-06` both pass. Their entire reports,
per-block instruction counts, CPU/fragment traces and all four binary captures
are byte-identical. Each binary frame stream is 2,811,204 bytes; twelve native
request packets occupy 49,248 bytes. Audit `exact-repeat.json` records the
hashes and verifies both complete source snapshots.

Both final reports have SHA-256
`ec8a338d20221bf4944400c381bcb3d34d7e6dc4489685eed29b5b91fc33a992`.

| Test | Observed result |
| --- | --- |
| Native A receipt | 51 polls; generation A, epoch 1, sequence 1 |
| Native B receipt | 51 polls; independent B, sequence 2 |
| Delayed fragments | Four-frame carrier delay; receipt at 55 polls |
| One dropped fragment | Recovery on a later complete cycle; 99 polls |
| One duplicated fragment | Recovery; 99 polls |
| Reordered fragments | A held fragment arrives after its successor, with a bubble/drop in this fault fixture; recovery at 99 polls |
| Corrupt fragment | One payload bit changed; recovery at 99 polls |
| Stale A echo during newer request | No receipt; timeout at 192 polls |
| Pending request superseded after 20 polls | Only the new complete tuple confirms, 51 polls after supersession |
| Zero carrier replies | No receipt; timeout at 192 polls |
| Busy CF transport | 192 polls, zero new exchanges, no receipt |
| Native CF units | ABI/callee-saved registers, all tuple bit positions, epoch/sequence/extent ordering, conflicting/exact duplicates, corrupt/out-of-order fragments, timeout and immutable expected tuple |
| Native full-width control | Epoch/sequence `0x80000001/0xa5f0cc33`, then `0xffffffff/0xffffffff`, confirm in 51 polls each; includes last allowed generation/span |
| Shared tracks and frozen A | B triggers on T1/T5; snapshot 312 remains A and its original reader remains valid |

The fault peer replays, delays, erases or corrupts **native-produced carrier
bytes**. It never sets CF receipt state. Faults affect only the diagnostic byte;
they are transport test fixtures, not a claim to model all physical bus failures.
The reordered fixture combines reordering and loss; native CF unit inputs also
exercise out-of-order indexes directly.

The additional full-width control executes the same frozen DSP image and CF
code through both DMA models. It is a protocol-only fixture: its requested
last-pool span and generation do not allocate a sample. Executed source and
hashes are retained in audit `full-width-echo.py` / `full-width-echo.json`.

There are 1,023 actual SPI exchanges/audio blocks and 1,215 native CF pump calls
including the 192 busy polls. All 32 voice work buffers, each 64 words, match
the original engine exactly. Both complete reply banks and transmitted wire
replies match stock except for the designated carrier byte. Descriptors 300,
304, 305 and 312 remain exact. Frozen A's descriptor is
`[8224, 16416, 6240, 48000, 1]`.

| Observable | SHA-256 |
| --- | --- |
| Complete compared voice history | `1750e8ebfafc2f34bb6910cb98a66dde56f8c2b92faf95584cbebdbed78996a8` |
| Non-carrier reply-bank history | `3412c845b7c58e50c4f871c1b95c648d4f8f738cda9528aec9d330aabf2c784b` |
| Generated isolated DSP BLOB | `6cd12c9191647fe1d71a1832e3715c5b72966dc7cf1ca0a6e7a8b828031189b6` |

Resource observations: 2,104 additional SHARC code bytes and 16 KiB of
experiment state/context/stack, alongside the previous observer's 5,340 code
bytes and 16 KiB. CF emits 2,010 request bytes, 236 matcher bytes and 40 pump
bytes into a 16 KiB diagnostic mapping; expected-fragment storage is 48 bytes.
It reuses the preceding sender's single 4 KiB packet. No new PCM allocation,
sample identity, stock slot alias or file is created by an echo request.
The retained host capture arrays/files are test artifacts, not ColdFire PCM
allocations.

The combined observer plus echo adds 656–51,755 emulator instructions per
block in these fixtures, mean 51,359.56. The original driver-range counter sees
9,588,327 CF instructions and new-code ranges see 64,484. These counts are
not physical cycles or utilization. The previous observer's 1,025-descriptor
scan dominates; it remains diagnostic work outside an approved production
audio budget. Stock timing-word preservation excludes this post-timing work;
that word must not be used to claim zero overhead.

## Source, reproduction and failed attempts

Base: branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5` plus inherited uncommitted work.
HEAD alone does not reproduce this state; retain the source snapshots.
New source is `lab/recorder_ack.py`, `machines/recorder-ack/{echo.c,contract.json}`,
`scripts/check-recorder-ack.py` and `tests/test_recorder_ack.py`. The normal
builders, native worker/FREEZE, legacy Flex, Plaits, Capicola, shortcuts and
pinned dependencies are preserved.

All 588 inherited source files and 55 inherited unit-test files are byte-exact.
Four source/contract files and one unit-test file are added. Final 592-source
manifest SHA-256:
`37c01da75528a099b08c735896cdc8afc74eb1cab003e314679f7e41ab1a2fe8`.
Final 56-file unit manifest SHA-256:
`79efa75d1e364420ce120dfc9973e687c5fc66e56be9a34c0a7ff0cc1b0e20e2`.
Audit: `out/runs/recorder-ack-audit-20261021-01/preservation.json`.

Final regression results:

- 352 unit tests pass: `out/recorder-ack-unittest-20261021-02.log`.
- SINE replay passes: `20261021T125238Z-test-ca676fb1/manifest.json`.
- Atomic publication passes with `--require-atomic`:
  `recorder-ack-publication-20261021-02/report.json`.
- Focused Ruff checks, formatting checks and final doctor pass. No expected
  baseline or pinned dependency was changed.

The proposal is frozen at `RECORDER-ACK-PROPOSAL.md`, SHA-256
`c155855b6be45f72b88ccb0bacd7c91de2f40d3c061fbe29971a49b5254851e1`;
contract SHA-256
`44924c0a2c6d5e81d67d38320bd47eb079004a6a70b33a181a726837a1e5d147`.
Readiness preceded DSP edits. The selected SHARC code arena
`0x200c0000..0x200c3fff` and data/context/stack arena
`0x200f8000..0x200fbfff` are guarded against stock/observer loaded-memory
overlap. They are isolated emulator scratch, not a production reservation or
an approved Plaits/Capicola composed layout.

Firmware: MAIN SHA-256
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`;
BLOB SHA-256
`0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`. Dependencies were not edited.

Input: retained `recorder-freeze-queue-native-20261021-02` report and A/FREEZE/B
page files, with the same strict hashes as the preceding observer probe.
`stock_inputs()` authenticates the stock checkpoint, +Drive card and baseline
LP0 feed. Missing/changed fixtures refuse execution. Each final run retains
its 592-file source map/text, generated listings, emitted CF code, full wire
captures, request packets, receipt-state trace and instruction counts.

Retained failed/diagnostic attempts under `recorder-ack-audit-20261021-01`:

- Unseeded native SPI init trapped on a missing SEC register in the prepared
  checkpoint. The explicit model reset fixture resolves that gap; full boot
  or hardware reset is not inferred.
- The first reply-header stepping script attempted to resume a halted native
  core without clearing its stop state. Independent fresh runs at each PC
  supplied the corrected diagnostic; no emulator semantics were changed.
- A stock panel trace used an unavailable `FILTER` button name; the retry uses
  existing controls and completes without fault pages.
- The initial CF emitter used shift forms outside the existing auditor's
  reviewed subset. The final native encoder uses reviewed immediate shifts;
  the auditor is unchanged.
- Build smoke `-01` and full probe `-01` had dependency import-order mistakes.
  Probe `-02` misinterpreted native `poke`'s element count as a byte count.
  These are harness failures; the old directories/logs remain.
- Full run `-03` passes. Run `-04` was intentionally interrupted before final
  validation to fix an import-order annotation. It is not counted as a pass.
  Final runs retain complete captures and exact source guards.

From the repository root, use fresh output names:

```sh
PYTHON=$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')
./labctl doctor
"$PYTHON" scripts/check-recorder-ack.py out/runs/recorder-ack-repro-01
"$PYTHON" scripts/check-recorder-ack.py out/runs/recorder-ack-repro-02
"$PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
"$PYTHON" scripts/check-recorder-worker-publication.py out/runs/recorder-freeze-queue-native-20261021-02 out/runs/recorder-ack-publication-repro --require-atomic
"$PYTHON" -m ruff check lab/recorder_ack.py scripts/check-recorder-ack.py tests/test_recorder_ack.py
```

## Next gate

First integrate/validate completion and receipt polling in the real running
control path, close the carrier's composed-mode and interrupt/write-order
audit, and establish the generation-specific queued-control barrier. Combine
that with logical slots, CPU aliases, frozen snapshots, preview, sample locks,
project and save-job roots. The known zero-reader → later-trigger transition
still forbids treating this echo as permission to reuse backing.

Only after those gates may a native retirement acknowledgement release a
private stock slot. Identity recycling needs its own lifetime proof. Then
measure hundreds of successful re-recordings with fixed snapshots and bounded
memory. Native SAVE/readback, actual capture producer and real sequencer bar
arming remain separate dependencies. No hardware was flashed, uploaded,
committed, pushed or published.
