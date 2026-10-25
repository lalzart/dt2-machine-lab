# Pending Sketch capture — OS 1.16

Sketch has an opt-in `--startup-capture` profile over fixed H124–H127. It
separates ownership of one recorder take from the shared sample-publication
lease. It changes no PCM allocator, playback engine, DSP image, FREEZE backend,
ordinary project slot, NORMAL default or physical memory budget.

The current local stage includes the [engineering review corrections](#engineering-review-corrections).
The earlier `6ca1ded5` image and its review remain preserved in the preceding
`buf-startup-integration-20261024-01` stage. Results below explicitly distinguish
that reviewed image from the corrected candidate.

## Behavior

- FUNC+SONG admits the selected BUF with the existing BAR/default or NOW timing.
  Recording can start during a witnessed native project-load batch without
  allocating/name-writing the BUF playback slots first.
- Native START, STOP, count and normalization remain authoritative. After STOP,
  a complete take waits in the stock recorder. `BUF n: WAIT LOAD` distinguishes
  this candidate from a newly playable BUF. An older committed take remains
  the playable generation until publication succeeds.
- Publication waits for the complete native project-worker batch to return and
  for the existing sample-operation/loader/mutation guards to be quiet. A zero
  count between two samples is insufficient. Setup then applies the existing
  H-slot conflict checks and the original queued BUF worker publishes the take.
- One pending transaction latches BUF, project, kit, recorder-pool pointer,
  generation epoch, batch serial, capture settings and recorder DEST. Track
  selection does not redirect it. A second ARM, stock recorder START/USE or
  conflicting FREEZE cannot consume/replace its take. Automatic retirement
  yields while capture owns it.
- NO/STOP invalidate pending publication. Cancellation during normalization
  retains ownership until native normalization completes, then calls the stock
  discard routine. Project-load intent or changed project/kit/epoch/batch
  invalidates the candidate; a foreign recorder/worker lease is not released.
  A queued job finishes or aborts through its existing completion path.

Capture admission may overlap the stock sample-operation guards only inside
an observed project batch. Existing BUF/FREEZE/shared-worker exclusions remain.
Before the first witnessed batch, or with unknown/nested batch ownership,
admission refuses conservatively. Unsupported pattern clocks/lengths still
refuse. This does not generalize the current normal-16-step clock contract.

## Implementation

`lab/buf_startup.py` contains the small admission/publication gates and native
batch observers. `buf_next_bar.py` retains one authoritative recorder state
machine with opt-in branches. `sketch_device.py` composes the profile; ordinary
profiles still emit their previous bytes. Sketch feedback reads the actual
recorder pool before playback-slot setup exists.

The new code uses vacant space in the existing disabled-diagnostic reservation,
leaving its disabled entry intact. State uses an audited gap in next-bar state.
The total reservation remains 360,448 bytes. This is logical ownership over
existing recorder/playback storage, not a separate physical BUF pool.

The current native input adapter observes the authenticated original START
body after the new guard, rather than treating a refused START entry as a
successful recording. This changes only a copied adapter's observation PC;
PCM, count, STOP, normalization model and lock semantics remain unchanged.
It attaches after extension initialization so its target bytes can be checked.
The original peer, pinned dependencies and upstream remain untouched.

## Validation and limits

Initial implementation results are recorded in the preceding stage's results and
`out/runs/startup-*` reports. Source/instruction tests, native CPU/DSP execution,
modeled audio, physical timing and hardware are separate observations.

Fifteen focused ColdFire ownership tests cover early setup absence, BAR/NOW,
inter-load idle gaps, one later publication, second requests, cancelled
normalization/waiting takes, project/kit/epoch/batch changes, queued callbacks,
foreign lease preservation, batch-task return ownership, pending feedback, NO
before view closure and selector setup deferral.
Adjacent recorder/UI/device composition and test-catalog checks run separately.
The old R4 MAIN is reproduced exactly with the option disabled.

The native startup probe uses only panel input to prepare a normal 16-step test
pattern, select LEN 16/NOW, start playback and issue FUNC+SONG during actual
loading. Its card is the previous experiment's verified native-write fixture;
physical cold boot and capture through a filesystem-verification modal remain
unqualified. Recorder input/peripheral cadence and normalization remain modeled.
No new final-output, listening or physical timing claim is made.

A controlled LP0-receiver stall was rejected as a slow-loader fixture: this
emulator queues transfers and the CPU batch can return despite the held link.
It did not qualify completed-take WAIT LOAD in the coupled startup flow. Its
failed run and frozen probe are preserved, and the control was removed from
current code. Completed-wait cancellation/retention is currently native
instruction-fixture evidence; real slow-startup timing still needs hardware
or an independently qualified slow-loader fixture.

Earlier failed attempts are retained. They include START observer authentication
before extension initialization, an in-flight trace checked as if quiescent,
a missing probe helper, a 128-step fixture rejected by the existing clock guard,
and a capture that started after the batch. These are not successful early
captures. Legacy Unicorn UI tests could not execute in this host session; the
Rust instruction bridge lacks their hook API. They are not counted as passing.

The first native cancellation run exposed NO closing Sketch before the global
recorder bridge received it. The opt-in Sketch input handler now latches
cancellation before closing, while allowing the key to propagate normally.
Native cancellation is rechecked on the corrected image. The selector/poll
initializer also has one central batch/capture gate; only the qualified
publication path can initialize slots while it owns a completed candidate.

## Reviewed-stage local results

| Check | Result |
| --- | --- |
| Focused recorder/Sketch/device/catalogue checks | 74 passed, zero failures/errors |
| Native early recording and automatic publication (`startup-sketch-native-10`) | START inside actual load 9 of 297, before playback setup; 114,016 stereo frames published to H124 |
| Owned CPU source and modeled input | Exact PCM; 223 contiguous native readbacks; live DSP descriptor length/rate/flags match |
| Native early cancellation (`startup-sketch-cancel-03`) | START during actual loading, then native DISCARD; zero PCM readbacks and zero publications after the full batch |
| Final images | Publication/cancellation use the identical final container; code/canaries, all 16 assignments and DEST=NORMAL preserved |
| Stock/default comparison | Disabled profile reproduces R4 exactly; original R4 package and 953 previous-stage files preserved |
| SINE compatibility | Passed exact-repeat, stock-isolation, clone/negative and lifecycle replay; unchanged relevant emitters and matching SINE build bytes |
| Completed-take WAIT LOAD | Native instruction-fixture checks pass; coupled slow-loader/hardware gate remains open |

Final MAIN SHA-256: `6ca1ded579dd391888a608909eb0141b7ee52bdd48638409712e96ef06b0cbd0`. DSP remains
`2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a`. Reservation: 360,448 bytes.
No new distributable OS, commit, dependency update or hardware transfer.

[Full preservation and results audit](../out/runs/startup-final-audit-02/report.json).
[Final native publication](../out/runs/startup-sketch-native-10/report.json).
[Final native cancellation](../out/runs/startup-sketch-cancel-03/report.json).

Actual native-emulator views (modeled input, not hardware):

![Recording during startup](../out/runs/startup-sketch-native-10/startup-Sketch-recording.png)

![Published BUF ready](../out/runs/startup-sketch-native-10/startup-Sketch-final.png)

## Reproduction

Use the configured Python 3.12, unchanged pinned inputs and fresh output paths:

```sh
./labctl doctor
"$LAB_PYTHON" -B scripts/check-buf-startup.py out/runs/UNIQUE-publish
"$LAB_PYTHON" -B scripts/check-buf-startup.py out/runs/UNIQUE-cancel --mode cancel
```

Each native command builds a private test container and copies the opt-in native
boot adapter. Neither produces a distributable OS package or accesses hardware.
For CPU/DSP outputs only, add `--startup-capture` to the existing
`build-sketch-device.py` fixed-H recipe (all inherited profile prerequisites
remain required). The prior R4 package and source snapshots stay preserved.

## Engineering review corrections

The `buf-review-fixes-20261024-01` stage fixes the three confirmed review issues:

- Completed pending capture (phase 6) displays `BUF:WAIT` alongside its existing
  `BUF n: WAIT LOAD` action, instead of incorrectly displaying `REFUSED`.
- Fixed-H build metadata always includes the public H124–H127 mapping, whether
  or not startup capture is enabled. The existing fixed-slot regression passes.
- The startup profile throttles failed setup to one attempt per 48,000 native
  sample-clock frames. A newly admitted ARM or witnessed batch clears the delay;
  a refused second ARM does not. All existing loader/mutation guards run before
  the attempt, and successful initialization retains its inexpensive fast path.

Throttling uses eight bytes of previously vacant next-bar state. It adds no
allocator, slot cache, PCM storage, DSP work or reservation growth. Layout changes
can recover automatically on the next one-second retry. Earlier non-startup
profiles keep their emitted firmware bytes; fixed-H metadata is corrected there.

154 focused checks pass, including retry boundaries/wrap, capacity recovery,
foreign ownership, both metadata profiles and executed draw arguments. In the
prepared full-project fixture, repeated failed-setup polls fall from 36,695 to
46 interpreted instructions (99.87% less work); the full first scan remains
necessary. These are instruction counts, not measured hardware CPU load.

[Focused checks](../out/runs/review-fixes-units-01/report.json).
[Cost and recovery reproduction](../out/runs/review-fixes-cost-01/report.json).

The corrected image also passes native startup capture and automatic H124
publication, with 114,016 modeled stereo frames and exact CPU-owned PCM readback.
All track assignments, NORMAL DEST, code and canaries remain intact. Fresh SINE
compatibility replay passes exact-repeat, stock isolation, clone/negative and
lifecycle checks. This is native emulator execution with modeled input, rather
than physical input or CPU timing evidence.

[Corrected native publication](../out/runs/review-fixes-native-01/report.json).
[SINE compatibility](../out/runs/20261024T103345Z-test-22b1be63/manifest.json).

Fresh native NO cancellation also passes on the identical corrected container:
recording starts during loading, DISCARD executes, and the 297-load startup
batch completes with zero PCM readbacks or BUF publication.
[Corrected cancellation](../out/runs/review-fixes-cancel-01/report.json).
[Final preservation and results audit](../out/runs/review-fixes-audit-01/report.json).

Corrected MAIN SHA-256:
`eea6d8bb70c0a91ea26a34b50232a4cedb80b436fafdc4be35fa53f132e6ba7c`.
The DSP and 360,448-byte reservation remain unchanged. Actual project/kit cleanup
and a completed take surviving a coupled slow-loader wait remain open validation
items. These corrections do not claim to resolve those separate questions.
