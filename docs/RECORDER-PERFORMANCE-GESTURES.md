# SAMPLING performance gestures — OS 1.16 investigation

2026-10-20. Shortcut selection remains open. This work adds a read-only emulator
observer; it installs no gesture, changes no normal firmware build and leaves
the previous Flex, BUF, native FREEZE, Plaits and Capicola sources intact.

## Recommendation for a trial

**Double-tap to arm, hold to FREEZE is a stronger one-handed candidate than
SAMPLING + C push.** Restrict a first trial to an explicitly selected BUF 1–4
and the tested SRC performance context. Audit the other performance pages
before widening that scope. Keep NORMAL's stock interactions intact.
Neither action should navigate, assign a track or open a file dialog.

There are two material qualifications:

1. A double-tap needs arbitration with the existing single-tap navigation.
   Stock opens the recorder on the first release and closes it on the second.
   Avoiding that flash means delaying a BUF single tap until the native double
   window expires. SAMPLING + C alone and a hold alone do not need this extra
   single-tap delay: their intent is known before release.
2. A hold takes time to recognize. It can FREEZE at its threshold, without
   waiting for release, but it cannot be instantaneous at initial contact.
   Native input already supplies a distinct hold milestone. Compare its feel
   on a device later; emulator instruction timing cannot choose a physical
   hold duration for us.

This is a recommendation to compare in a later opt-in prototype, not approval
or installation of either shortcut. A physical ergonomics/listening trial has
not occurred.

## Scope and provenance

Audited `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, with the inherited dirty tree.
The audit directory is
`out/runs/recorder-performance-gestures-20261020-audit-01/`. It contains the
initial Git status, pre-existing source/test hashes, version-scoped disassembly
and executable matrix driver. Reports retain their own frozen sources.

Pinned DigiKit is `277760aad51b036a4756db051409d4d3b1eeccbc` and Selache is
`2b26d3b75c53063575bc5c820fa0d38879335187`. `./labctl doctor` passes.
Stock MAIN SHA-256 is
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
`lab.flex_session.stock_inputs()` also authenticates the original ready checkpoint,
card and LP0 feed. No dependencies, baseline expectations or target binaries
are changed.

The new observer is `scripts/trace-recorder-performance-gestures.py`. Its input
goes through UART8/eDMA and the original key-event constructor, rather than
injecting preclassified double/hold events. Its five observed key-code sites
are checked against authenticated stock MAIN before and after each final run.
Recording input remains the existing external peer; this is not SHARC audio
capture or physical panel emulation qualification.

## What stock input actually supplies

EVIDENCE from original ColdFire instructions and executed event traces:

| Function/data | Confirmed role |
| --- | --- |
| `0x4011e038` | Panel byte/held-state edge processing; compares the previous key and native panel tick for double presses |
| `0x4011e0d4–0x4011e10e` | Second matching press within the window becomes flags `0x5`; normal press is `0x1` |
| `0x4011dc68` | Native panel timer; increments counter `0x47ddec1c`, emits held repeats and milestones |
| `0x402b405c` | Double window: **32 native panel ticks**, measured press-to-press, not release-to-press |
| `0x402b4058`, `0x402b4054` | First repeat delay 24 ticks, subsequent interval 8 ticks in the tested image |
| `0x40114624` | Stock key-event constructor; key and flags become object fields `+0x0c`, `+0x10` |
| `0x401146a4`, `0x401146ae` | Key and flags getters |
| `0x40114728` | Tests bit 2, the second-press flag demonstrated by fast/slow controls |
| `0x40114708` | Tests bit 3, held-repeat indication; it is **not** the demonstrated double-press bit |
| `0x401146dc`, `0x401146ec` | Tests hold milestone bits 5 and 6 |
| `0x4011de70` | Physical held-key query through the stock mapping table |
| `0x40114654`, `0x4011df84`, `0x4011dfc4`, `0x4011e026` | Stock event-consumption helpers mark a held cycle and clear repeat/double tracking; potential release-suppression mechanism, not installed here |

Observed SAMPLING flags:

| Input | Flags | Interpretation in this bounded trace |
| --- | --- | --- |
| First press | `0x1` | Press edge |
| Fast second press | `0x5` | Press plus double flag |
| Slow second press | `0x1` | Two ordinary taps; negative double control |
| Ordinary release | `0x10` | Stock single-tap/navigation event |
| Held repeats | `0x9` | Press/repeat; begins at +24 panel ticks, then every 8 |
| Hold milestone | `0x29` | One milestone at **+64 panel ticks** in the executed holds |
| Release after a consumed stock chord | `0x0` | Does not perform the ordinary SAMPLING tap |

Static code also emits a later bit-6 milestone; the 1.2-second nominal hold
probe does not reach it. A FREEZE recognizer must latch once per physical
press and ignore every later repeat/milestone until release. Testing bit 3 as
“long press” would trigger much earlier and repeatedly.

The driver schedules nominal dwell from the emulator's configured 132 million
instructions/second and logs actual native panel ticks and SSI sample ticks.
Its frontend dwell is explicitly disabled; each edge is still delivered in a
separate paused advance. This bypasses queued-input pacing, not firmware key
processing. The stock DTIM timestamp source at `0xfc07000c` reads zero here;
it is unsuitable as a measured gesture clock. Native panel ticks are the
comparison evidence. Approximately 250/500 ms for the double/hold milestones
are **emulator clock estimates**, not measured physical-device latency.

## Stock behavior and recorder states

The final matrix has **21 successful observation runs**: double and hold in
eight contexts, plus five comparison/negative controls. An artifact-local
validator passes **125 assertions**, including recorder state, event ordering,
native flag distinctions, PCM preservation and source integrity. These are
tests of stock handling, not tests of an installed replacement binding.

| Starting context | Double-tap result | Hold result | Recorder state |
| --- | --- | --- | --- |
| SRC, stopped | RECORDER opens on first release, SRC returns on second | SRC remains visible while held; release opens RECORDER | 0→0 |
| SRC after PLAY input | Same navigation | Same hold behavior; CPU control frames keep advancing | 0→0 |
| Recorder ready | First release closes it, second reopens it | Remains visible while held; release closes it | 0→0 |
| Stock armed, waiting input explicitly modeled | Visits armed RECORDER, returns to SRC; does not start/cancel | Remains on SRC while held, opens armed RECORDER on release | 1→1 |
| Recorder capturing | Visits SRC and returns; capture frame count advances | Continues capture while held; release leaves the recorder | 2→2 |
| Capturing in background on SRC | Visits RECORDER and returns; capture advances | SRC remains while held; release opens the running recorder | 2→2 |
| Completed trim candidate | Visits SRC and returns to the same candidate | Release leaves trim; candidate remains intact | 4→4 |
| Stock filename editor | Editor remains visible | Editor remains visible, despite the generic hold milestone | 4→4 |

Both trim and name tests preserve all **5,152 captured stereo frames** and the
exact completed PCM hash. No gesture invokes ARM/manual start/stop/discard in
the core sixteen cases. All twenty-one runs retain advancing CPU control
frames. The PLAY-input cases do not seed sequencer notes or assert transport
position, musical bars, active voice continuity or real-time audio performance.

Five controls:

| Control | Observed result |
| --- | --- |
| Slow second tap | Second press has `0x1`, versus `0x5` for the fast tap; native interval exceeds the 32-tick window |
| Turn C while holding SAMPLING | Turn input is delivered, no C-push event occurs; the single +64-tick hold milestone remains |
| SAMPLING + C push | C press/release `0x1/0x10`; SAMPLING release `0x0`; SRC stays visible |
| Existing shortcuts | Global SAMPLING + YES arms 0→1, SAMPLING + NO cancels 1→0 with waiting input; FUNC + SAMPLING reaches SAMPLES with `0x3/0x12`; double STOP emits `0x1/0x10/0x5/0x10` |
| YES after holding SAMPLING | Hold milestone arrives at panel tick 588, YES at 620; original ARM follows. A hypothetical hold-FREEZE would already have fired before the later chord |

The double-STOP control verifies original event classification/dispatch, not
the audible killing of active voices. The encoder-turn case does not establish
physical knob response or a parameter-output/audio comparison. No new gesture
recognizer is installed for any of these tests.

Earlier exploratory captures remain separate, with their own source revisions.

Confirmed initial controls:

- On SRC, pressing SAMPLING leaves SRC visible. Release opens RECORDER.
  A fast second press carries the native double bit; its release returns to
  SRC. A slow second tap also closes the recorder, but has no double bit.
- Holding SAMPLING leaves SRC visible through the hold milestones. Releasing
  it still opens RECORDER. No stock FREEZE action was observed.
- Turning C while holding SAMPLING does not cancel the held repeats or the
  +64-tick milestone. This supports continuing to turn an encoder while the
  other hand holds SAMPLING. Release still opens RECORDER in stock.
- SAMPLING + C push suppresses SAMPLING's ordinary release action in the
  previous trace. The final matrix repeats that comparison. C push is a
  separate event from rotation; an unused recorder C cell does not establish
  global push availability.
- Double-tap and hold on the recorder's trim page leave its completed PCM
  hash and frame count intact. They do not implicitly USE or discard it.
- Foreground and background manual recording continue through the tested
  gestures. They do not demonstrate an automatic next-bar capture action.

The actual 128×64 display captures are saved as enlarged PNGs by DigiKit.
Some very short transitions during active recording capture a cleared/partial
stock redraw; those images are retained, not corrected or made new baselines.
They limit frame-by-frame visual claims. Stable SRC, recorder, trim and naming
captures were inspected directly. Useful local examples:

- `out/runs/recorder-gesture-performance-double-20261020-10/02-first-release.png`
  and `04-second-release.png`: the stock recorder flash that arbitration must avoid.
- `out/runs/recorder-gesture-performance-hold-20261020-10/04-held-1200ms.png`
  and `05-release.png`: hold versus release navigation.
- `out/runs/recorder-gesture-name-hold-20261020-10/99-settled.png`: unchanged modal.
- `out/runs/recorder-gesture-performance-shortcuts-20261020-10/03-stock-browser.png`:
  original SAMPLES management screen.

### Armed-state failed controls and input boundary

The initial `armed-double-...-01` fixture tried SAMPLING + YES while already on
the recorder page. Its actual state was **2 (recording)**, not 1 (armed): YES
reached the recorder's manual handler first. It is retained as a failed setup,
not counted as armed-state evidence.

The next two attempts used the global shortcut from SRC. Original
`0x40016b3a` correctly called ARM `0x40015f9c`, but the generic external input
status was zero. Original `0x40016338` interpreted that as capture started,
changed state 1→2, and `0x400162d6` stopped the nonadvancing zero-frame capture.
Their armed-state assertion failed. These are retained in `...-02/` and
`...-03/`; older reports say `running` because their script version had no
exception status writer. The nonzero process exit and assertion are decisive.

The explicit `--model-armed-status` control returns a nonzero external status
at `0x400cd702` **only while the original controller is in state 1**. It does
not seed or patch controller state, change any key event or implement threshold
detection. The original global arm/cancel instructions can then be tested
while the external producer is modeled as waiting. Reports flag this boundary
and count every overridden status read. It proves key dispatch under a
controlled waiting input, not real armed capture, clock synchronization or
SHARC status transport.

Stock controller state is read through `controller+0x10`, settings offset
`+0xa4` (`0x40015f6c → 0x4004d9d6`). Tested states are 0 ready, 1 armed,
2 recording and 4 complete/trim; intermediate state 3 is not an eligible
performance-action context.

## Existing shortcut compatibility

The official [OS 1.15A manual, sampling and key combinations](https://www.elektron.se/wp-content/uploads/2025/07/Digitakt-2-User-Manual_ENG_OS1.15A_250708.pdf)
documents SAMPLING + YES/NO and FUNC + SAMPLING. It is supporting documentation;
the executed handler evidence here is **OS 1.16**.

| Existing interaction | Constraint on a future recognizer |
| --- | --- |
| Short SAMPLING | Keep stock navigation in NORMAL; a BUF double-tap trial must explicitly accept the single-tap delay |
| FUNC + SAMPLING | Preserve sample management; modifier/chord intent takes precedence over a pending unmodified tap |
| SAMPLING + YES/NO | Preserve global arm/cancel; distinguish recorder-local YES/NO handling |
| Encoder rotation | Continue controlling the current performance page; rotation alone must not count as C push |
| Double STOP | Preserve transport/audio-stop handling; cancel any queued quick-record request without replacing the stock stop action |
| Legacy Flex Save/Discard/Bank UI | Existing recorder hooks remain; bypass a new recognizer while these modal workflows own input |
| Name editor, browser, dialogs and project loading | Keep their input/navigation; clear pending gesture intent at context/project transitions |

AMP/FILTER/LFO, keyboard/mute/song pages and the combined legacy Flex R5 UI
were not executed in this matrix. Their source remains unchanged. A global
spare-shortcut claim would require those additional context audits. Project
transitions, EMPTY/BUSY/capacity feedback and recognition cancellation are
requirements for a later recognizer, not implemented controls here; the prior
native FREEZE tests cover its command-level rejection/rollback separately.

A late chord is intrinsically ambiguous: a user might hold SAMPLING past the
FREEZE threshold, then press YES or C. The hold action would already have
occurred. No classifier can infer that future intention. A BUF-only scope,
visible feedback and a deliberate hold duration reduce this risk; they do not
eliminate it. Preserve chords arriving before the threshold and test handling
of later keys in the eventual binding prototype.

## Comparison

| Candidate | Performance benefit | Cost / engineering work |
| --- | --- | --- |
| Double SAMPLING → next-bar arm | One hand, two short contacts; can stay on the sound's current page | Must defer first single navigation, intercept both presses/releases and arbitrate with holds; musical scheduling/capture remains a separate native gate |
| Hold SAMPLING → FREEZE | One hand; other hand can keep turning a control; no trim/save detour | Recognition delay and late-chord ambiguity; one snapshot per hold; suppress release navigation; native worker request/feedback required |
| SAMPLING + C push → FREEZE | Intent arrives as soon as C is pushed; uses existing stock chord suppression | Usually involves the encoder hand; may interrupt that control; push/rotation distinctions and page-specific C behavior still matter |

SAMPLING + C has the simpler intent distinction and can remain an alternative
for comparison. It is less aligned with the user's stated performance concern.
The one-button pair is feasible at the input-event layer, with a larger
arbitration/state surface. Neither option has proven target timing or an
installed performance path.

## Proposed state policy, not an installed binding

| Context | Double-tap proposal | Hold proposal |
| --- | --- | --- |
| NORMAL | Exact stock behavior | Exact stock behavior |
| BUF, ordinary performance page, running, ready | Latch destination/settings/epoch; arm for the next authoritative bar | FREEZE the committed generation once; show its immutable name |
| BUF empty | Recording may be armed | Brief EMPTY feedback, no slot/identity consumed |
| Quick arm already pending | Cancel that pending request; never start immediately | Freeze the committed version only if an independent native job can safely run |
| Transport stopped | Initial contract refuses with feedback; never starts transport implicitly | Freeze is musically meaningful while stopped, once safe GUI-worker execution exists |
| Existing stock arm, recording or publication busy | Do not take over/restart/discard it | Desired eventual behavior is freezing the last committed version; initially refuse until capture/worker coexistence is proven |
| Unsaved trim candidate / name / management modal | Keep the candidate and stock modal workflow | Do not silently accept the candidate or turn it into the current buffer; leave this context unbound initially |
| Project/context transition, new modifier/chord | Cancel pending recognition/request; preserve stock dispatch | Cancel a not-yet-fired hold; never let a deferred request affect the new project |

The recorder destination is the last explicit global DEST selection, not the
selected track number or its current sample slot. A brief `BUF 2 ARMED`,
`B2-001`, `EMPTY`, `BUSY` or capacity message should make that target/result
clear while preserving the performance page. A visible destination indication
outside the recorder is an integration requirement; it is not implemented by
this observer.

## Native work still required

EVIDENCE: the earlier [native FREEZE diagnostic](RECORDER-FREEZE-NATIVE-RESULTS.md)
executes metadata registration, stock cache aliasing, immutable names and
refusal/rollback guards without retaining source PCM. It runs from a paused
worker with masked interrupts in emulator-only scratch. BUF capture/commit is
still host-assisted. Native SAVE/readback and generation reclamation remain
unresolved; the existing snapshot capacity is deliberately finite.

Do not call that diagnostic directly inside a key ISR or keep interrupts
masked while performing a live loader operation. A performance binding needs
a bounded request, a safe original GUI/task execution point, acknowledgement,
busy handling and feedback. Latch project/kit and generation at FREEZE intent:
queueing only `BUF n` could freeze a newer version if publication wins the race.
Reject stale work or explicitly pin the intended immutable generation. Native
FREEZE's current diagnostic ABI does not itself provide that complete queue.

Next-bar arm is the larger missing piece:

- The existing `QuickRecord` is a pure supplied-bar/completion contract, not a
  native sequencer/capture hook. Tempo and SSI cadence do not identify a bar.
- Stock R.STRT supports PLAY/THRES. “Start at next bar” introduces a distinct
  start policy: it cannot also wait for an arbitrary threshold crossing.
  Preserve source, channel, monitoring and length, but explicitly define the
  start override and the role of THRES before implementing it.
- Stock R.LEN is steps 1–128 or MAX. The isolated model only accepts integer
  bars; it cannot claim to preserve all lengths, tempo/scale changes, external
  clock, polymeter or STOP behavior. The bounded two-second BUF experiment
  also cannot silently accept every stock recorder duration.
- Arm against the authoritative sequencer boundary, then commit only after
  complete publication. Next triggers use the new generation; existing voices
  retain their old generation. Never overwrite the committed PCM during capture.

Recommended next experiment: an opt-in, **dry-action** recognizer consuming the
captured native events, showing only WOULD ARM / WOULD FREEZE and preserving
the current page. Test the single/double/hold/chord ordering and late-modifier
cases before wiring either resource operation. Then add the native FREEZE
worker bridge; separately prove the sequencer-bar and recorder-status producer.
Select the actual shortcut only after comparing these interactions.

Also test tap-then-hold, triple taps, release bounce, both modifier orders,
simultaneous STOP and context/project changes in that recognizer. Define one
winning action per gesture: a recognized double must not subsequently FREEZE
when its second press is held. These combinations were not executed in this
stock matrix and must not be treated as covered by the separate hold/double
observations.

## Reproduction and verification

Use the configured Python 3.12 and fresh ignored output directories:

```sh
./labctl doctor
python3 scripts/trace-recorder-performance-gestures.py out/runs/NEW-DOUBLE --context performance --gesture double
python3 scripts/trace-recorder-performance-gestures.py out/runs/NEW-HOLD --context performance --gesture hold
python3 scripts/trace-recorder-performance-gestures.py out/runs/NEW-ARMED --context armed --gesture hold --model-armed-status
python3 scripts/trace-recorder-performance-gestures.py out/runs/NEW-CHORDS --gesture shortcuts --model-armed-status
```

Contexts: performance/SRC, playing/SRC, ready, armed, recording,
background-recording/SRC, trim and name. Additional gestures: slow-double,
encoder (turn C during hold), c-chord and late-arm (YES after the hold milestone).
Each report includes UART input intentions, constructor events, handler callers,
native controller states, completed PCM hashes, control-frame progress and
actual OLED captures. No FREEZE or next-bar action is performed.

Final artifact names:

- `out/runs/recorder-gesture-CONTEXT-GESTURE-20261020-10/`: twenty-one reports,
  frozen sources and screenshots, with the context/gesture names listed above.
- `out/runs/recorder-performance-gestures-20261020-audit-01/matrix.json`:
  exact twenty-one subprocess commands and exit codes; `run-matrix.py` reproduces
  them with three independent workers. Use fresh names for another run.
- `matrix-checks.json` and `validate-matrix.py` in that audit directory:
  125 passing assertions; `source-preservation.json`: all **567 inherited
  sources** and **50 unit-test files** unchanged. Only the new observer is added
  to the standard source manifest, now **568 files**.
- All final probes use source-manifest SHA-256
  `05531806cce3ef8842b24a96b7b16c0aceea6c36c9367414691eca42587d383c`.
  The final SINE run uses the same source map.
- `out/recorder-performance-gestures-unittest-20261020-10.log`:
  **302 tests pass**, using the configured Python 3.12 with
  `-m unittest discover -s tests -v`.
- `out/runs/20261020T143347Z-test-8c126e8a/manifest.json`:
  `./labctl test sine --replay` **passes**, including its negative replay control.
  This is the existing DSP regression, not a new live-buffer audio test.
- `ruff check` and `ruff format --check` pass for the new observer.

The only new repository files are this report and the observer script. No
shortcut was selected, no existing source or expectation was rewritten, and
no firmware was flashed, uploaded, committed or published.
