# Continuous BUF recording

**13 consecutive recordings published successfully while a native pattern
played.** The whole run remains failed because a test assertion stopped the
fourteenth capture. All 15 allowed attempts were consumed across two runs;
no further recordings were performed.

| Deliverable | Observed result |
| --- | --- |
| Successful recordings | 13, beginning with empty BUF 1 shared by T1/T5; frozen A independently selected on T6 |
| Release/reuse | 11 native stock-allocator releases and 10 subsequent physical extent reuses |
| Settled DSP storage | 925,696 bytes (904 KiB) at every checkpoint 2–13: frozen A + current take, each 448 KiB, plus unrelated 8 KiB stock allocation |
| CPU staging | Source PCM pointers zero after completed transactions; two metadata entries; exactly 28,106,992 heap bytes free at checkpoints 2–13 |
| Playback | Shared assignments and frozen descriptor preserved; initial stock-file oracle and post-run ONESHOT/REPITCH comparisons pass |
| Identity limit | 13 distinct tokens `0x7ffb0001..0x7ffb000d`; eight fixed seats, only private slots 304–306 used, with no ID recycling or limit change |

A remains at extent `0x2400`. Later takes alternate between `0x72400` and
`0xe2400`, reusing storage only after native retirement completes. Eight physical
seats stay fixed; the existing nonwrapping 65,535-token ceiling remains. The policy
records 11 refusals followed by successful cleanup, with zero queue denials.
Completion-to-publication remains 189.333–194.667 ms in the 48 kHz model.

The native malloc-boundary sampler observes at least 27,529,312 heap bytes free
and a largest owned-capture request of 452,048 bytes. These are guest heap
measurements; host input/capture fixtures are separate. Completed takes retain
metadata and pinned DSP PCM, rather than growing CPU source PCM.

## Scope

User-authorized OS 1.16 emulator integration, 2026-10-22. Preserve the
[BUF contract](../BUF-WORKFLOW-CONTRACT.md) and existing Flex/NORMAL paths.

The experiment starts with empty BUF 1 on two ONESHOT tracks, freezes A on a
third track, and attempts at most **15 recordings in this work**. Native GUI
bar receipts, recording, publication, automatic retirement, DSP acknowledgement
and stock unload remain authoritative. No host retirement, new allocator,
generation-limit increase or identity recycling is authorized by this experiment.

Use the existing conditional-MODIFY/FEXT private emulator runtime. One live DSP
executes the complete control stream; bookend stock-file oracles check PCM
independently. Do not clone live SEC state. Keep all 16 machines ONESHOT for the
existing retirement policy. Compatibility expansion follows sustained reuse.

Check actual allocation extents, occupied PCM bytes, CPU staging heap and
metadata, fresh take IDs/private seats, active readers, shared assignments and
frozen playback at every completed cycle. Wait for the native cleanup policy
between recordings without granting it authority. Record refused/delayed
retirements. A stalled session stops with its largest completed sequence; do
not add stress recordings beyond the 15-cycle cap.

The accepted publication delay is measured, not optimized in this milestone.
Results here are modeled-peripheral/native CPU-DSP evidence, not physical timing
or device behavior. No firmware publication or hardware transfer.

The first attempt, `out/runs/buf-continuous-20261022-01`, completed capture but
stopped before publication in the inherited `HeapTrace` free-size assertion.
Its native heap bitmap remains decodable; that pointer-size ledger does not
observe every GUI allocation/reallocation path. It is not used by the current
driver. A smaller sampler reads heap occupancy at completed native malloc
boundaries and settled transaction boundaries without inferring ownership.

That attempted capture consumed one of the 15 allowed attempts. The second
session was capped at 14, enforced before runtime initialization. The following
historical command has finished; it must not restart the exhausted budget:

```sh
"$LAB_PYTHON" -B out/runs/buf-alignment-20261022-01/with-fext.py \
  scripts/check-buf-next-bar.py out/runs/buf-continuous-20261022-02 \
  --continuous --prior-attempts 1 --continuous-recordings 14
```

The wrapper reuses the already validated local conditional-MODIFY/FEXT runtime;
it does not modify pinned dependencies. A request exceeding 15 total attempts
refuses before creating a run or starting firmware. Preserve the failed first
attempt; do not silently restart a 15-recording budget.

## Incomplete live-run qualification and final checks

`buf-continuous-20261022-02` started 14 captures and published 13. On the last
attempt it stopped at `No native AMP edit during capture`: the encoder gesture
changed no tracked kit bytes. The exact parameter/page state was not saved, so
a clamp is plausible rather than established. The recorder was still in phase 2,
with zero cancellations and 13 stops/publications. This is not evidence of an
allocator or identity-limit failure. Both raw reports retain **failed** status
and stable source inventories.

The final driver tries reversing the encoder direction and reports remaining
UI no-ops without aborting capture. Actual parameter-change evidence is checked
separately. Prepared-boundary clamp/no-op checks pass; no new coupled recording
run followed these harness corrections because the attempt budget was exhausted.
The final playback assertion also checks rendered intervals after triggers;
an envelope's silent first control frame is not evidence of a silent track.
Saved traces have nonzero T1/T5/T6 output in every completed take's interval.

The live run executes 148,191 native DSP blocks with modeled capture, LP0,
cadence and SEC reset. It checks reader pointers across publication, finite
active PCM, and no active reader in an extent at native unload. There is no
per-frame paired-stock comparison claim.

Initial A passes a 48-block stock-file comparison during the run. Post-run
ONESHOT and REPITCH (raw machine 3) comparisons each pass 88 blocks: 12 initial,
12 old-A during final publication, 40 current-13/frozen-A and 24 late frozen-A.
They replay saved native pages with controlled triggers and independent original
CPU file loads, adding zero recordings. They do not turn the failed live run
into a completed whole-run qualification, or establish final mix, listening,
real-time or hardware behavior.

The next functional step is to qualify another machine's complete reader and
retirement lifetime, then narrow the all-16-ONESHOT requirement to proven relevant
readers. REPITCH playback is promising; native UI packing and retirement remain
unqualified. The global guard is unchanged. No allocator, ID limit, CPU/DSP
emitter or normal builder changed. Flex R5, Plaits, Capicola and NORMAL are
preserved; no firmware was committed, published or sent to hardware.

Evidence: [summary](../out/runs/buf-continuous-audit-20261022-01/summary.json),
[preservation/evidence audit](../out/runs/buf-continuous-audit-20261022-01/verification.json),
[raw report](../out/runs/buf-continuous-20261022-02/report.json),
[ONESHOT replay](../out/runs/buf-continuous-prefix-0-20261022-01/report.json),
[REPITCH replay](../out/runs/buf-continuous-prefix-3-20261022-01/report.json).
The 115 focused BUF tests, SINE replay and Ruff pass; final harness-only fixes
have prepared-boundary checks and do not change the firmware payloads.
