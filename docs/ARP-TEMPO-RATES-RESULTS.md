# Native arp tempo and note rates — 2026-10-16

Later continuation: the user reports the arp is almost perfect on hardware.
The focused [R2 G sensitivity fix](ARP-G-SENSITIVITY.md) replaces raw-pulse
selection with the stock enum response. The R1 artifact below is preserved.

Status: native tempo/rate/UI, recording/menu save, checkpoint-resumed menu
load/replay, source regression and target-package checks pass. New-candidate
hardware and physical timing remain unverified.

The user reports that the previously installed arp now works as expected. The
installed hash and reason for the delayed start are unknown. This report covers
a separate stock OS1.16 tempo/rates candidate, not a confirmed device fix.

## Controls and implementation

Track 1, keyboard mode, PLAY, held keys. Turn G in Keyboard Settings to choose
OFF, UP, ORD or RND. Push G to switch to RATE; turn G to choose 1/4,1/8,1/16 or
1/32. Push again to return to mode. Both values stay visible. Defaults remain
OFF and 1/16. Rate edits close the current gate and restart phase while retaining
held notes and order. Mode changes retain the earlier flush behavior: release
and play the chord again. Tempo edits preserve beat phase. Gate remains 50%; no latch
or MIDI input was added. E/F/H and modified G keep their stock handlers.

The native clock reads the original OS1.16 BPM*120 getter at 0x4002D744.
Integer beat phase supports fractional BPM without whole-BPM rounding. The
same 8192-byte allocation is retained; the arp core adds no per-note
allocations, DSP patches or Python arp services. The UI thread and original note APIs still own
output. Emulator service latency is explicitly measured, not physical timing.

The discovery run catalogued 3052 initialized static bitmap objects, including
animation frames, and 17 font resources. The old dotted G box was the stock
empty-slot bitmap. A named-text selector matches the existing scale/root-note
controls better than a decorative icon. Implementation refinement from the
proposal: the original bitmap drawing call is retained, with an equivalent
17x17 blank bitmap substituted, preserving native call side effects. G push
also continues through the stock key handler after changing focus.

AR16 v2 saves packed mode/rate bytes per pattern in the existing authenticated
two-bank, 210-byte companion format. V1 records import at 1/16. Unknown files
are protected; corrupt/missing/conflicting companions default to OFF/1/16.
Different wire versions with the same sequence are treated as a conflict,
even when their raw bytes match: v1 mode1 means UP/1/16, whereas v2 byte1
means UP/1/4. The ordinary stock project payload is unchanged. Old firmware may use a retained
v1 bank or OFF; project exports do not automatically include these companions.

## Verified observations

- Native instruction timing agrees with independent rational onset/half-gate
  deadlines at 30,60,90,102,120,127.5,180,240 and300 BPM, all four rates and
  UP/ORDER/RANDOM. Long fractional phase, live tempo/rate changes, late-service
  bounds, sample wrap, OFF, allocation bounds and input guards pass.
- Native v1 import, v2 output, mixed banks, corruption, wrong project, conflicts,
  failed writes, unknown-file protection and 64-bit sequence carry agree with
  an independent host codec. Pattern/track rate recall and runtime defaults pass.
- Earlier iteration, before the equal-sequence version safety addition:
  `arp-tempo-r1-panel-probe-11`: actual stock Tempo-menu gestures select127.5
  BPM; G push/rotation traverse all four rates. UP at1/8 emits the expected eight
  note-ons and eight offs into the stock API, with eight captured stock trigs.
  Exact period11294.117647 samples; onset lateness11..105 samples; maximum
  observed service gap1632 samples. Half-gate lateness592..912 samples.
- Final compiled MAIN, `arp-tempo-r1-fast-panel-03`: actual stock Tempo-menu
  gestures reach300 BPM. UP at1/32 emits the expected eight notes and eight
  offs with no fault pages. Exact period1200 samples; onset lateness32..848
  samples; maximum service gap1536 samples. Two of seven measured gates are
  shortened exactly at the following note's onset. Relative to the earlier of
  nominal half-gate expiry and next onset, off lateness is0..1000 samples.
  The monophonic preemption is checked explicitly. These are bounded emulator
  observations, not long-run jitter/headroom or physical timing guarantees.
- Final MAIN, `arp-tempo-r1-storage-record-05`: actual Tempo-menu edits select
  120 BPM. Enter REC+PLAY before playing the chord. ORDER/1/16 generates and
  records67,64,60,67,64,60,67,64. Normal Save Project writes slot0 and the stock
  working autosave128; native AR16 v2 save and independent readback pass.
- `arp-tempo-r1-storage-recall-03` starts normal menu slot0 loading after an
  explicit RAM fixture sets all settings to zero, modeOFF and the wrong rate.
  `arp-tempo-r1-storage-recall-05` resumes the native load checkpoint, finishes
  hashing/recall and the stock follow-up autosave, then verifies modeORDER,
  rate1/16 and all121740 pattern bytes. PLAY replays the exact eight recorded
  pitches with zero generated arp calls. The final report is passed, with no
  fault pages and a passing live-stack check. This save/load observation spans
  retained emulator checkpoints; it is not one uninterrupted cold-boot run.
- Guarded build repeat, container reconstruction, unchanged protected/DSP
  sections, exact original bootstrap depacking of sections8/3/7 and bounded
  400M-instruction CPU startup pass. The startup checkpoint preserves patches;
  its state pointer is still zero, so it is not a complete playable boot proof.
- Final source regression and the required SINE offline replay regression pass
  (`20261015T170019Z-test-826947d1`). SINE verifies its voice-buffer PCM and
  baseline isolation, not arp audio or hardware. Legacy default MAIN remains
  exactly the keyboard-fix baseline; D1 and the new tempo UI are separate choices.

## Packaged candidate

`out/runs/arp-tempo-r1-package-04/EXPERIMENTAL_ARP_STOCK_OS1.16_TEMPO_RATE_R1.syx`

- SYX SHA256: `63ed6a6812421a0c6cddbb716a96cfbe99424bade605ccd911f0b5da6a6e2f1c`
- MAIN SHA256: `fe3b6dac57ee020c26269818ef1a0fc610886800110e8d4ecd87285395521938`
- Stock BLOB SHA256: `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`

Package04 is byte-identical to package03, whose actual original bootstrap
sections8/3/7 depack and 400M startup checks passed. Final emitted MAINs in the
fast-rate, save and recall runs also match exactly. The final source/harness
freeze is `arp-tempo-r1-freeze-04`; report backfill is separate from code drift.
The package's `release-verification.json` binds these artifacts and checks.

## Reproduction and provenance

Use the Python configured in `.local/config.json`, or the scripts' interpreter
re-exec. `./labctl doctor` checks the stock fixture and pinned dependencies.

```
python3 -m unittest discover -s tests -p test_arp_tempo.py -v
python3 scripts/check-arp-firmware.py out/runs/<fresh> --tempo-ui --tempo 127.5 --rate 1/8
python3 scripts/check-arp-firmware.py out/runs/<fresh> --tempo-ui --tempo 300 --rate 1/32 --keep-settings-open
python3 scripts/check-arp-firmware.py out/runs/<fresh> --tempo-ui --tempo 120 --rate 1/16 --mode order --record --storage
python3 -m unittest discover -s tests -v
python3 scripts/build-arp-firmware.py out/runs/<fresh> --tempo-ui --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<package> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-arp-firmware-boot.py out/runs/<package> out/runs/<fresh>
```

Source and control/icon discoveries are in `arp-tempo-ui-discovery-01`.
Frozen executable sources and the private checkpoint-continuation scripts are
retained independently from report backfill.
All failed/superseded probes and previous firmware remain intact. Small raw
encoder units are not one displayed BPM: stock Tempo handling accumulates and
accelerates them. The harness uses coarse input then FINE near the target to
avoid overshoot. Early probes that assumed a one-to-one mapping are failures,
not evidence of a tempo-engine defect. Interrupted probes have retained logs
and emitted MAIN files but are not promoted to validation results.

The checkpoint continuation is reproducible with the retained private
`out/runs/arp-tempo-stack-audit-01/resume-load.py` and
`resume-busy-load-settle.py` scripts, using the parent saved/load checkpoints
listed above. The local verification shim accepts a 64-bit **host instruction
clock** in timer metadata, preserving its full value and all guest-state
validation; the pinned validator otherwise rejects clocks above2^32. SSI state
is restored without a fresh legacy arm/alignment. Fresh diagnostic memory ranges
preserve the old checkpoint's helper allocations. These are verification
adapters, not runtime firmware services or a physical-clock correction.

The filesystem helper's former whole-page guard included the UI queue. Exact
OS1.16 QueueCreate/TaskCreate at0x4003324e..0x40033280 place the main/UI stack at
[0x4096775c,0x4098f75c) and queue storage immediately after it. All changes in the
failing probes were at0x4098f868 or above, outside that stack. The guard now
protects the actual stack portion of the shared page; other task stacks keep
whole-page protection. Negative checks still reject writes to live stack bytes.

Earlier storage probes are retained: coarse Tempo input overshot the target;
pre-held REC+PLAY did not produce the full vector; whole-page stack guards
rejected legitimate queue writes; the Save menu retained its selection; prompt
waiting failed to recognize an already-started load; and playback began before
follow-up autosave finished. The final harness uses FINE near the target,
enters recording first, explicitly selects LOAD, recognizes native load entry
and waits for autosave to settle. No recorded-note golden values were changed.

## Limits

New-candidate hardware operation, listening, physical timing/headroom, external
clock, swing, other tracks, card-backed power-on recall and wider pattern
copy/undo/export lifecycle remain unverified. Native recording uses the stock
trig representation; dense32nd-note recording and retaining a pre-held chord
through REC+PLAY have not been validated. The verified recording workflow is
REC+PLAY first, then play the chord. Wait for loading/autosave to finish before
recorded playback.

Some captured redraw frames omit other stock content. The same behavior is
visible in the prior D1 baseline captures; full stock-plus-arp layouts are also
captured and inspected. This is an unresolved emulator/display observation,
not proof of physical display flicker or a completed display-pipeline fix.

Nothing was flashed, sent to hardware, committed, pushed or published.
