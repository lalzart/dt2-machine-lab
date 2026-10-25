# BUF architecture alignment

The [canonical contract](../BUF-WORKFLOW-CONTRACT.md) records the intended
product and source audit. This note records the correction results, not a new
product specification.

Baseline sources, default native-emitter hashes and the initial dirty-tree
inventory are preserved in `out/runs/buf-alignment-20261022-01/`.

## Corrections

- `buf_next_bar.initialize` reserves/names four empty logical slots through
  the existing native setup; it creates no take, PCM, loader success or generation.
- `arm/check` use global recorder DEST. Track selection is diagnostic only;
  ordinary kit parameter edits and unrelated machines do not gate capture.
  Project epoch, live kit replacement, destination, transport, clock and the
  relevant recorder settings still guard the transaction. Monitor edits do not
  cancel it. STOP/NO remain provisional frontend cancellation actions.
- The current `NextBarUI` installs publication-only worker/completion variants.
  Both manual BUF USE and automatic publication omit `assign_recording`; NORMAL
  still forwards to its original worker/completion paths. Historical/default
  worker and performance payloads remain byte-identical.
- Native recorder R.LEN raw 4 represents 16 steps (`1 << raw` in the original
  draw code); raw 8 is MAX. Only raw 4 is admitted in the current slice. Other
  values refuse with result -6. Source/channel settings remain native. The
  first apparent display mismatch was an older latched OLED frame; the actual
  CHAN getter's settings pointer and the project-pool prefix were identical.
- Empty logical slots are selectable through the ordinary selector. Their
  native empty-row naming still needs a presentation solution; a tentative
  display-length override was not visually established and was removed.
  No sample renumbering or bank architecture was introduced.

## Executed CPU workflow

`out/runs/buf-alignment-panel-20261022-04/report.json` passes the native panel
flow: reserve empty BUF 1, select its existing slot 300 on T1/T5, start a pattern,
record A while sending T6 filter/pitch and T2 amp gestures, FREEZE A, then record
B. This earlier run proves that gestures/selection do not cancel; it did not
assert actual parameter changes. Neither publication changes track assignment. An
explicit final selector action assigns the frozen snapshot to T6. Both captures
use native controller/queued worker/stock loader/publication instructions; input
audio and service transport remain emulator models. This run retains the
inherited unrelated machine choices. It precedes the empty-row label correction
and the additional latency/reader instrumentation.

The follow-up `out/runs/buf-alignment-panel-20261022-07/report.json` passes the
same flow with full-rate modeled input and actual parameter-byte assertions:
T6 filter offset `0x98` changes while armed, T6 pitch `0x7b` and T2 amp `0xac`
change while recording. Both captures complete with zero cancellations and
unchanged assignments. Their 112,960/112,928 audio frames equal their native
start-to-completion sample-tick intervals. No host resource commit/assignment
was used. The private probe changes the input count model to one tick/frame;
the final `NextBarUI` selects that same model only for its owned next-bar
capture. NORMAL and historical Flex keep the legacy default. Final source
removes the unverified row-label override and invalid SEC clone described below;
these final harness changes have not had another full coupled run.

Seventeen focused next-bar native instruction cases and the shared input-clock
case are included in the passing 192-test `./labctl unit buf flex` run
(`unit-buf-flex-final.log` in the audit directory). BUF alone selects 115 cases;
the combined run deduplicates shared recorder tests and excludes Capicola/Arp.
The tests distinguish prepared native service boundaries from full firmware flow.
The cases include actual publication instructions with all track bytes
unchanged, empty-destination admission, performance edits, explicit length
refusal and stock ARM forwarding.

## DSP and memory evidence

The first mixed-machine coupled run and an all-ONESHOT control both trap before
capture at native DSP PC `0xb88e8b` (`sharc_core.compute._compute:339`), retained
as `buf-alignment-coupled-20261022-01` and `-02`. Static decoding confirms the
same stock/test bytes `a401d40d`: the known register-FEXT gap documented in
[PATTERN-LAB](PATTERN-LAB.md). It is not evidence that recording requires
all tracks to be ONESHOT.

The existing `pattern_dsp.execute_fext` exact-PC/byte/operand adapter and
`pattern_native.RESUME` ABI are reused with the existing conditional-MODIFY
runtime in an ignored private build. Its 28 independent instruction comparisons
pass. No instruction is skipped and pinned dependencies stay unchanged. The
current PCM proof uses an explicitly labelled ONESHOT fixture; mixed-machine
DSP playback remains unverified. Source/ABI fingerprints are in
`out/runs/buf-alignment-fext-runtime-20261022-01/`.

The fourth coupled candidate reaches B publication and verifies unchanged reader
pointers, then fails in its extra cloned-state PCM comparator: native state
export/import does not preserve the SEC peripheral state (`SEC not drained`).
That run remains failed; it is not a completed coupled workflow.

An isolated replay of the successful CPU workflow's saved native pages passes
the existing independent stock-file/SHARC oracle:
`out/runs/buf-alignment-reader-replay-20261022-02/report.json`. The 12-block old-A
reader phase remains exact during B publication; the 40-block new-B/frozen-A
phase and 24-block late frozen-A phase also match. LP0 ordering and voice
triggers are controlled by this replay. It does not repair the continuous SEC
comparator or establish physical timing.

The pinned SSI model advances the sample counter by 32 at 1,500 blocks/s:
48,000 sample ticks/s. The earlier report's conversion using 96,000 DMA words/s
was wrong. Its preserved raw CPU ticks give 100.667 and 97.333 ms from capture
completion to publication. Both following-bar first triggers precede publication.
Corrected derivation and original error are retained in the audit directory.
Those captures also used the inherited two-ticks-per-frame input model, so they
are not evidence of a full-duration bar of audio.

The full-rate follow-up measures 9,344/9,056 ticks, or **194.667/188.667 ms**,
from completion to publication. First following-bar trigger frames 15,253/22,312
precede publication frames 15,509/22,558. These are emulator-model timings,
not physical measurements. Publication latency must be addressed before promising
the immediately following bar's first trigger will play the new take.

SINE replay passed in `out/runs/20261022T104236Z-test-49bd58ef/manifest.json`
before the final input-model/report corrections. No DSP algorithm or normal
builder changed; final preservation checks verify the historical worker and
performance payloads remain byte-identical to the initial snapshot.

Source audit confirms that the native retirement path is implemented: a worker
lease, DSP private-descriptor seal, distinct tuple acknowledgement and IRQ/GUI
wakeup precede stock unload and dead-node cleanup. The general diagnostic
observer grants no general retirement authority, and the old pause-certificate
entry is disabled in the native adapter.

The short current-source three-record check passes in
`out/runs/buf-alignment-reuse-20261022-01/report.json`: the current-root attempt
refuses; two obsolete generations are released by the native transaction. The
16 KiB extent at logical start `0x2400` is freed after generation `0x7ffb0001`
and reused by distinct generation `0x7ffb0003`. This reuses physical memory/seat,
not the generation identity. The final current/frozen generation remains pinned,
with a 48-block exact independent stock-file oracle. All 5,397 all-voice-buffer
comparisons match stock. This isolated check uses the historical manual recorder
frontend and all ONESHOT tracks; it does not qualify mixed-machine retirement
or replace the still-incomplete interrupted 100-cycle qualification.

The retirement policy still conservatively requires all live kit machines to
be ONESHOT. This restriction is separate from recorder admission. Native
project save/load also retain the existing volatile-session guards. Neither
mixed-machine reclamation nor complete project lifecycle is solved by these
publication corrections.

## Next engineering steps

First make completion-to-publication behavior explicit at the musical boundary;
the current capture completes on the requested edge, but new PCM arrives later.
Keep the memory-management work active: qualify the ownership fence for the
next compatible machine, including retained readers and pending selections,
before relaxing its conservative admission rule. Do not remove that rule merely
because recording itself no longer needs it.

Extend duration through native step/bar receipts: raw 5-7 require 2/4/8 normal
bars, while shorter lengths need step receipts. MAX needs a defined stop policy.
Do not substitute elapsed host time. Native status, saving, device placement,
listening, physical timing and hardware remain open.
