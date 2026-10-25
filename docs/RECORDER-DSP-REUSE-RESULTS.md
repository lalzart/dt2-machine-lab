# Restricted native DSP allocation reuse

This implements the user's four-task experimental request of 2026-10-22.
Normal builds and the existing recorder, Flex, Plaits and Capicola sources are
unchanged. No hardware or installable firmware image is involved.

**EVIDENCE:** the first smoke run with corrected transport freed A's 16 KiB
sample allocation through stock OS 1.16 instructions. C consumed that free gap
with a different issued identity and produced exact stock-file ONESHOT audio.
The allocator release is real guest execution; it is not a host-written empty
slot, a synthetic allocation result, or a ColdFire PCM free.

## Mechanism and evidence boundary

`lab/recorder_dsp_reuse.py` adds a 778-byte ColdFire command at emulator scratch
`0x10b01000`. It is only installed by the new experiment script. It checks the
generation/epoch/kit, recorder/FREEZE/sample-operation inactivity, frozen
canonical keys, the stock allocation record's exact extent and one remaining
alias, and current cache/project references. The existing native SHARC gate
supplies active/retained readers, descriptor roots and cached/incoming selections.
Its code, zero permission and unknown-ownership mask remain unchanged.

For this restricted experiment both processors are paused, stock STOP actions
are sent, and the harness asserts an exclusive, closed-world test certificate.
The actual native diagnostic is copied to a CPU mailbox by **modeled transport**.
The certificate is required because pattern/undo/clipboard/save-job roots and
future producer admission are not comprehensively proven. It is not a native
general retirement fence. Missing certificate or observed unknown descriptors
refuses. Do not connect this command to live device recording.

After all refusal checks, the command tombstones the old registry entry,
consumes the certificate, clears its obsolete private project reference, then
calls stock unload `0x401540c6`. The trace observes:

| Native instruction/path | Effect |
| --- | --- |
| `0x4015415e` → `0x401e40b6` | Remove private slot from the allocation's alias tree |
| `0x4015416c` | Decrement allocation alias count at record `+0x30` |
| `0x40154174` | Final-owner test |
| `0x401541cc` / `0x4015419e` | Shift/remove the empty allocation record |
| `0x401541fc` → `0x4015366e` | Rebuild slot-to-allocation indices |
| `0x40154202` → `0x40153bea` | Stock CPU slot cleanup and empty DSP header publication |

The allocation vector is at CPU `0x405a0f64`, stride `0x34`; extent is record
`+0x10/+0x14`, free gap `+0x18`, alias count `+0x30`. These describe SHARC sample
storage, not retained CPU audio. PCM storage starts at SHARC byte base
`0x8422b9c8 + logical_start - 0x400`. Freeing returns ownership to the stock
allocator; it need not zero the DDR bytes. The later native loader writes new
PCM to the returned extent through the original sample-page path.

Native execution covers recorder USE worker/copy/hash, loader, registration,
assignment, temporary CPU source frees, queued FREEZE, reclamation command,
stock unload, SHARC LP0 callback and ONESHOT rendering. The audio capture
producer remains the deterministic modeled recorder peer. CPU/DSP cadence,
LP0 delivery/callback entry, diagnostic-result delivery and the exclusive pause
are modeled. Paused unload calls use the existing page-publisher peripheral
HLE; normal recorder publication is the running native path. Host audio and
memory reads are correctness oracles. Native SAVE/readback and hardware timing
are not implemented or established here.

## Initial release/reuse

From `out/runs/recorder-dsp-reuse-20261022-02/report.json`:

| State | A/C allocation | B allocation |
| --- | --- | --- |
| After A → B | A: start `0x2400`, size `0x4000`, one private alias | start `0x6400`, size `0x4000`, two aliases |
| After native A release | A record absent; B has preceding free gap `0x4000` | unchanged PCM/identity |
| After C | C: start `0x2400`, size `0x4000`, ID `0x7ffe0003` | unchanged |

A had ID `0x7ffe0001`. Logical BUF 1 remains stock slot 300. The stock allocation
record count falls from three to two, including one unrelated 8 KiB baseline
allocation, then grows when C consumes the free gap. Both A's lookup and a
stock-loader acquisition through its full old reference fail after tombstoning.
An independent original CPU file load and original SHARC ONESHOT renderer give
exact, non-silent PCM for C over 48 blocks. Host WAV files are reference oracles;
they do not save or supply the accepted native recording.

## Refusals and retained failed run

The active-A case refuses before any ownership mutation. The zero-reader
pending-A case also refuses: the first stock control block has no active A
reader yet, but cached/incoming selection still names A's private descriptor.
The test does not clear that descriptor to manufacture quiescence. Missing
exclusive ownership refuses with the allocation and playback state intact.

Run `recorder-dsp-reuse-20261022-01` is retained as a failure. Native A release
worked, but the harness omitted forwarding the direct-call publisher capture
to SHARC and therefore correctly failed its empty-DSP-header assertion. The
fix forwards the captured native unload arguments through the existing LP0
model; it does not synthesize a clear header or alter the allocator result.

## Repeated reuse and FREEZE

Final runs `recorder-dsp-reuse-20261022-06` and `-07` pass. Eight native recorder USE
transactions issue eight distinct IDs; six obsolete generations are released.
C is frozen through the existing queued native FREEZE worker, then replaced.
Reclaiming C refuses, and its frozen slot 312 still renders the exact original
C PCM after all later recording/reclamation cycles.

| Generation | Logical allocation start | Outcome |
| --- | --- | --- |
| A / 1 | `0x2400` | freed after B |
| B / 2 | `0x6400` | freed after C |
| C / 3 | `0x2400` | frozen; remains pinned |
| D / 4 | `0x6400` | freed after E |
| E / 5 | `0xa400` | freed after F |
| F / 6 | `0x6400` | freed after G |
| G / 7 | `0xa400` | freed after H |
| H / 8 | `0x6400` | current BUF 1 |

These short stereo takes contain 3,120–3,136 frames (about 65 ms); each
recording allocation is 16 KiB. Recording DSP storage peaks at 48 KiB
during replacement and finishes at 32 KiB: current H plus frozen C. The prepared
fixture also has one unrelated 8 KiB allocation. The test does not claim these
are whole-device capacity measurements. Empty private slots remain reserved;
they are not recycled into ordinary sample identities. Final live private
owners are C and H.

All eight temporary CPU PCM source allocations are freed: 131,072 allocator
bytes cumulatively, separately from 100,800 requested source bytes reported by
the existing worker's counter. Observed CPU heap free space changes from
28,108,512 after A to 28,107,712 after H (800 bytes); metadata/UI allocations
remain. This is not a hundreds-cycle CPU plateau claim.

B, C, E–H and late frozen C each match an independent stock-file ONESHOT oracle
exactly over 48 blocks. The late frozen C hash equals C's original audio hash.
The ninth real recorder/USE attempt is refused with the issued count still
eight and sample ownership/publication unchanged. Available DSP space does not
remove that admission limit.

The existing deliberately unsafe reader-lifetime control was rerun at
`recorder-dsp-reuse-unsafe-20261022-01`. Stock unload/reuse without the reader
barrier still changes old A's audio. That failure mode remains excluded from
the restricted path.

## Validation and reproduction

The final probe additionally reads actual emulated DSP PCM diagnostically,
checks A→C extent contents change, records stock cache lookup/index rebuild
entries, and retries stale A acquisition **after** C reuses its address. This host readback
is an assertion only; it is not native SAVE or a source used for recording.

363 unit tests pass (`out/recorder-dsp-reuse-units-20261022-02.log`), including
five new native-instruction refusal tests. SINE replay passes at
`out/runs/20261021T224652Z-test-5d5716e4/manifest.json`. The final pair has exact
equality for 25 artifacts (native command, panel capture, all eight PCM
candidates, all eight page histories and seven audio renders), plus all native
allocation/unload traces, diagnostic tuples, source-free records and allocation
states. The tightened pending control first publishes B's logical descriptor,
so A has only a private descriptor and a queued selection; its next stock
block actually acquires A after refusal.

The 609 inherited source/contract files and 59 inherited unit files remain
byte-identical. Original fixture/dependency checks pass. No baseline
expectations were changed. Compact aggregate verification is retained at
`out/runs/recorder-reuse-audit-20261022-01/verification.json`; its `verify.py`
rechecks the exact pair, source preservation, fixture hashes and regressions.
Earlier successful exploratory runs remain available; the final pair supplies
the tightened-control repeat claim.

From the repository root, using the already accepted isolated conditional
MODIFY runtime and retirement-gate fixture:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-dsp-reuse.py out/runs/YOUR-UNIQUE-REUSE-RUN
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

Input gate blob:
`out/runs/recorder-barrier-probe-20261022-02/dsp/GATE_BLOB.bin`, SHA-256
`d4e9a786dc74fb26b174f5f591a2b1de6e68af202778c870f09eb65bf555b153`.
The script rejects drift. If absent, reproduce it with the preceding
`check-recorder-retirement-gate.py` experiment. Native PCM/page captures,
allocator states, diagnostic tuples, unload traces and per-generation oracle
audio are retained in each run. Baseline source/dependency/firmware identities
are recorded by `doctor` in `report.json`; HEAD is
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5` with inherited dirty work preserved.

## Smallest identity follow-up

PCM reuse and identity reuse are separate. Current worker admission uses the
issued count both to select one of eight private slots and to derive the next
identity. Registry lookup indexes directly by `id - FIRST_ID`; registration
requires an unused entry. Source metadata nodes also remain linked after their
PCM pointer is cleared. None of those mechanisms is reset here.

The smallest promising follow-up is to separate reusable physical/private
slots and bounded registry seats from a monotonically issued generation token.
Resolve old tokens to no entry after retirement, reuse a seat only after its
ownership barrier, and keep frozen generations pinned. Initially keep tokens
unique and refuse wrap. This avoids ABA while exploring a bounded metadata pool.
Merely resetting the count would also reuse cache keys, slots and lookup indices.
The stock `key(id, out)` interface receives only an ID, so reusing an ID with a
new serial is not sufficient without an acquisition lease carrying that serial.
Audit legacy Flex's overlapping ID namespace before choosing a larger token
range; changing its limit is not this experiment's solution.

The next practical experiment is to implement bounded registry/private-seat
reuse with unique generation tokens under the same stopped, exclusive harness,
then attempt 100 replacements while one snapshot stays pinned. Keep the current
cap until that replacement protocol is implemented and stale keys are rejected;
do not just raise it. Separately, replace the pause certificate/mailbox copy
with a stopped-state native worker transaction: seal acquisitions, send an
ordered consumer fence, receive a matching completion, then execute this
proven final-owner unload. Live recording,
arbitrary projects, sample locks/undo, other playback machines, DMA/cache timing,
native BUF SAVE/readback and hardware behavior remain unresolved.
