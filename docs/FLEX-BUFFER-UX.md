# Flex recorder destinations — emulator prototype

Target: Digitakt II OS 1.16, existing stock panel and sample-pool selector.
User authorization covers investigation through an isolated functional emulator
prototype. No hardware installation, package, or change to normal builders.

## Inspected stock controls

The actual 128×64 recorder was captured in
`out/runs/flex-buffer-ui-audit-20261020-01/stock-recorder.png`. Its draw entry is
`0x40021de0`; ready-state cell text is drawn by `0x40113ae8`. Coordinates below
are the native raster coordinates, whose y increases upwards on this view.

| Encoder | Stock control | Native text anchor | Prototype |
| --- | --- | --- | --- |
| A | SRC | (16,27) | stock |
| B | CHAN | (48,27) | stock |
| C | unused rotation; REC NOW / YES graphic | prompt (75,29) | DEST label (80,27), value (80,39) |
| D | THRES | (112,27) | stock |
| E | MON | label (16,0), values (15,9)/(15,15) | stock |
| F | R.LEN | (48,0) | stock |
| G | R.STRT | (81,0) | stock |
| H | ARM | (112,0) | stock |

These are dedicated recorder controls, not the machine's 44-byte parameter
descriptors. Rotation dispatch is `0x40020960`; encoder identity is event+12,
C=3, E=5. The stock ready/armed dispatch has no C branch; its encoder-match
helper uses zero-based indices, so C is index 2. The REC NOW / YES graphic
occupies C's display cell but is a YES-button prompt, not a C assignment.
Stock `0x40111b62` scales input before MON setter `0x40020334`.
MON reads ProjectSettings data+0x1b6 through `0x4004cd02`; its setter is
`0x4004d0d2`. MON draw starts at `0x40022316` and joins at `0x400223c8`.
Recorded event and draw evidence is in the two `flex-buffer-ui-audit-20261020-*`
runs. The stock selector opens with SRC then encoder D push.

## Selected interaction

C chooses TAKE, BUF 1, BUF 2, BUF 3, BUF 4. E retains the original MON cell
and handler, with no additional modifier gesture. DEST remains remembered
across recorder visits in volatile emulator session state. Destination is latched
when recording starts; changing it during recording/trim must not redirect the
candidate. Other ready controls, YES start/stop, preview and E/H trim stay stock.

YES starts/stops recording, the original trim interface edits the candidate,
and YES/USE accepts. FUNC+NO discards a candidate without changing the committed
buffer. TAKE preserves the existing independent-take emulator path. Buffer USE
autoassigns the selected ONESHOT track. The alternative for later comparison is
commit without autoassignment: useful when a performance template already has
several tracks pointing at the destination, but less discoverable initially.

The sample selector shows BUF 1–4 alongside ordinary samples, including
EMPTY/READY/RECORDING states where space permits. A reference to BUF 1 stays the
same across commits; older voice pointers retain the previous generation.
SAVE/DISK is not exposed. Native DSP readback remains a separate dependency.

The initial E/FUNC+E proposal confused C's on-screen YES prompt with an encoder
assignment. The corrected layout uses C and keeps monitoring visible. A new page
adds navigation; moving R.LEN/R.STRT changes timing controls; moving MON is
unnecessary. DEST replaces the REC NOW / YES graphic, while the original YES
button still starts/stops recording. The emulator window retains its YES hint.

## Acceptance contract

Working artifact: opt-in `scripts/try-flex-buffers.py`, stock recorder/selector
screens plus explicitly host-managed generation publication and buffered stock
SHARC ONESHOT replay. Evidence must distinguish emitted ColdFire UI, original
CPU/SHARC execution, host orchestration and unimplemented target lifetime logic.
Use deterministic stereo PCM; exact ordinary-loading voice output is the oracle.
Cover shared references, old readers, empty selection, discard, incomplete load,
capacity, project epochs, monitoring, return to TAKE, and guarded project save.
Keep generated images/audio/state in fresh ignored runs. Never recycle issued
sample identities or reclaim a generation based on track inactivity.

## Implemented controls and practical limits

Run from this repository:

```sh
python3 scripts/try-flex-buffers.py
```

The launcher selects the configured Python 3.12, verifies pinned inputs, and
opens the existing emulator panel for fifteen minutes. `--input /path/file.wav`
selects a 48 kHz PCM16 mono/stereo source; the window also has an Input WAV
chooser. This is a modeled recorder input, with buffered audition through
original SHARC code. It is not live microphone/internal-mix capture or real-time
audio. Use **Render / listen to take** for an accepted track's buffered audition.

1. Open SAMPLING. Turn C to BUF 1. Turn E to change monitoring normally.
2. YES records, YES stops, E/H trim, and YES/USE publishes and assigns to the
   track selected when recording began. FUNC+NO discards. The existing preview
   screen and waveform remain stock; their audible monitor path is not verified.
3. On another ONESHOT track, open SRC, press encoder D, and select BUF 1 in the
   original sample-pool selector. Both tracks keep the same logical sample number.
4. Re-record BUF 1 and USE. Subsequent triggers on either track acquire the new
   generation. BUF 2–4 are independent. Turn DEST back to TAKE for an independent
   temporary sample through the existing host Flex adapter.

In the guarded fixture the four rows occupy **bank C, 044–047** (numeric
slots 300–303). They are chosen from verified empty project/loader entries,
not hard-coded over existing samples. Private generation rows have empty names
and zero displayed length. The four named rows do not multiply on re-recording;
the underlying private allocations still consume finite sample slots and RAM.
EMPTY and READY are shown in the selector; RECORDING is maintained as metadata
while capture is active, without a demonstrated selector visit during capture.
The original selector can briefly retain a previous viewport while opening;
normal cursor/bank navigation refreshes the rows.

BUF captures are bounded to **two seconds**, **eight retained generations**
and **4 MiB** of sample allocations per emulator session. Earlier generations
remain pinned. Further USE fails with a reason in the emulator window and keeps
the previous buffer. This is not indefinite reclamation. The older host TAKE
adapter retains its ten-second bound; production native Flex's twenty-second
implementation is unchanged. Buffer transaction/status/error handling and
selector names are host callbacks. The emitted ColdFire
draw/setter runs in emulator-only scratch and is not an installable firmware
feature.

SAVE, DISK and FREEZE are absent. Project save is conservatively refused when
volatile resources are present. The tested public project-load API is refused
after the first retained buffer generation; start a fresh emulator session to
load a different project. No new confirmation dialog is inserted in ordinary
record/trim/USE. The warning text currently appears in the host window; a native
OLED error screen and complete project-menu integration remain future work.

## Display comparison

These are actual 128×64 OLED rasters, rendered by original OS 1.16 routines;
PNG captures use the existing emulator's integer scaling. No conceptual UI
mockup substitutes for these captures. See [results](FLEX-BUFFER-RESULTS.md) for
the final source-frozen run, selector screenshot and limitations.

| Stock recorder | Buffer recorder |
| --- | --- |
| ![Stock recorder](../out/runs/flex-buffer-ui-audit-20261020-01/stock-recorder.png) | ![DEST BUF 1](../out/runs/flex-buffer-c-workflow-20261020-02/02-dest-buf1.png) |

The C graphic block at `0x400221a0..0x400222b4` is replaced with stock-style
value/label draws centered at (80,39)/(80,27), using the original templates
`0x402a96a0`/`0x402a6c30` and text routine `0x40113ae8`. A C-only branch is
inserted at ready/armed rotation entry `0x400209ae`; other encoders continue
through the original dispatcher. The added setter uses stock scaling.
MON setter `0x40020334`, draw/label `0x40022316..0x40022402` and settings setter
`0x4004d0d2` remain byte-identical to stock; the workflow verifies those ranges.
No FUNC-state observer or MON trampoline remains. The cell is cleared before
drawing DEST. All other ready-page cells and trim controls retain their
original draw/event paths. Stock input scaling still has an acceleration
deadband; in automated tests several small encoder deltas can produce no step.
This is preserved behavior, not a direct mapping of each host wheel event to
one destination.
