# Digitakt II BUF workflow contract

Canonical product direction, OS 1.16. User architecture alignment, 2026-10-22.
Read this before extending BUF. Earlier experiment reports describe their
historical slices; they do not override these invariants.

## Product and invariants

Build a reusable live recording-buffer system for musical performance. Keep
the original recorder with DEST = NORMAL | BUF 1 | BUF 2 | BUF 3 | BUF 4.
NORMAL retains Elektron's record/trim/name/save/assignment behavior.

- BUF 1-4 are global, stable logical sample identities. Any compatible track
  can select them through the ordinary sample selector; tracks may share a BUF.
- A committed recording generation is immutable. Recording into a BUF stages
  new PCM, then publishes it to that logical BUF only after successful loading.
  A failed or canceled candidate preserves the previous committed generation.
- Publication does not assign any track. Selected-track changes neither redirect
  the latched recorder destination nor cancel an otherwise valid recording.
  Existing BUF track assignments remain stable across replacement.
- New triggers after publication see the new generation. Existing voices retain
  their original allocation until their readers are proven clear.
- FREEZE creates a separately selectable immutable snapshot, preferably by
  sharing the pinned allocation. It does not assign a track or save a file.
- Empty BUFs must be selectable and directly recordable. No accepted manual
  seed take is part of the product workflow.
- Ordinary pitch, filter, amp and other performance edits must remain usable
  while armed/recording. Project/kit replacement, destination change, transport
  stop or incompatible capture settings may invalidate the pending transaction.
- Source/channel and R.LEN must be respected. The normal-16-step slice supports
  16/32/64 steps (one/two/four bars), bounded by the existing ten-second take
  limit. Other lengths/MAX refuse explicitly. Overlong capture preserves the
  prior committed take and reports the capacity limit.
- Sketch may offer START BAR (default) or START NOW as one volatile menu
  setting. NOW begins on the native GUI recorder service without a bar wait
  and captures the full selected length from that start. Its first slice is
  during playback; native tempo changes cancel it. Recorder DEST=NORMAL stays
  independent. TRIG/SRC/FLTR/AMP/FX/MOD presses leave Sketch for the native page.
  TRK press leaves Sketch as native track selection starts; bare
  performance/step trigs retain their existing behavior.
- Recorder admission does not depend on unrelated track machines. ONESHOT is
  the initially validated reader path; broader playback compatibility and the
  more restrictive retirement proof remain separate engineering work.
- Record/FREEZE gestures are provisional frontend choices. Keep them separate
  from backend publication, ownership and snapshot operations.
- Keep existing project slots/sample numbering intact. The user's 2026-10-23
  selector direction is BUF 1–4 immediately before A00 OFF, using UI aliases of
  the existing logical buffers. The selector profile implements that presentation; ordinary bank browsing
  must remain on its bank when traversing a BUF backing row. The backing slots
  remain guarded reservations. See docs/BUF-BANK-TRACK-REVIEW.md. Native +Drive saving/project persistence
  are later work.
- Reclaim DSP PCM only through proven ownership/reader fences and stock memory
  management. Physical metadata seats may be reused with fresh generation
  tokens; do not confuse this with recycling an immutable generation identity.

## Current work and acceptance

Authorized implementation: correct the current native next-bar adapter using
existing recorder, queued worker, stock loader, slot associations and DSP paths.
No new playback engine, host-successful commit, dependency edits, bank redesign,
hardware flash or firmware publication. Preserve Flex R5, Plaits and Capicola.

The immediate acceptance flow starts with empty BUF 1, assigns it to T1 and T5
through the sample selector, plays a pattern, arms SAMPLING+YES, edits unrelated
performance parameters/track selection, and publishes from the configured source.
Both BUF assignments remain unchanged. FREEZE A, record B into BUF 1, then
compare current B, frozen A and any retained reader of A. Measure stop-to-publish
latency and whether the following bar's first trigger precedes publication.

Use short native instruction tests while exploring. Run the realistic coupled
workflow and broader compatibility checks at integration milestones. Preserve
known-good sources and failed candidates; do not repeat 100-cycle experiments
to substitute for a missing architectural behavior.

## Alignment audit before corrections

| Finding | Classification | Responsible paths / first correction |
| --- | --- | --- |
| Stable logical slots, immutable generation registry, shared allocation FREEZE, native loader and deferred header publication exist | Matches foundation | `recorder_worker_code.py:setup/assign/page_filter/flush`, `recorder_freeze_code.py:freeze`, `recorder_seat_reuse.py` |
| Completion publishes and then writes a track's sample slot | Genuine mismatch | `buf_next_bar.py:done` -> `recorder_worker_code.py:assign` -> `flex_native.py:assign_recording`; split publication from assignment |
| Next-bar DEST comes from selected track's committed BUF; accepted-take count is required | Genuine mismatch / prototype dependency | `buf_next_bar.py:arm`, `buf_performance.py:eligible`; use recorder DEST and native empty setup |
| Selected-track changes cancel; whole 36-byte recorder region is compared | Genuine mismatch for selection; overbroad capture guard | `buf_next_bar.py:check`; retain structural/capture guards and allow performance edits |
| All 16 track machines are checked during recorder admission | Temporary proof restriction leaking into architecture | `buf_next_bar.py:check`, `buf_performance.py:eligible`; isolate from recording, preserve retirement restrictions |
| One bar is used regardless of R.LEN | Incomplete prototype with misleading behavior | Authenticate the native R.LEN encoding; explicitly refuse unsupported values |
| SAMPLING+C and exact buffer-bank layout | Provisional UI | Preserve shortcut; do not refine or renumber samples |
| Native retirement lease, DSP seal, distinct acknowledgement, stock unload and dead-node cleanup exist | Implemented isolated mechanisms, not device-ready ownership | `recorder_native_retirement.py`, `machines/recorder-native-retirement/seal.c`; existing restricted releases are evidence, not a general fence |

The older paused reuse proof freed six allocations, and the later native
transaction has captured successful stock unloads/reuse; the interrupted
100-cycle qualification is not a completed result. Current/frozen/retained
reader protection stays mandatory. Follow the publication fixes with one short
current-source release/reuse integration, not another long qualification loop.

## Evidence and current source entry

`lab/buf_next_bar.py` and `lab/buf_next_bar_ui.py` are the current native flow.
Keep the optional publication emitter variants isolated from historical adapters
and packaged Flex. Native CPU/DSP execution, modeled recorder/LP0/cadence and
hardware-unverified behavior must be stated separately. Current results and
remaining gaps belong in the short [alignment note](docs/BUF-WORKFLOW-ALIGNMENT.md).
