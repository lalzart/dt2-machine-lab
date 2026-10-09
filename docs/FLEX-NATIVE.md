# Native Flex recorder workflow — OS 1.16

The requested feature changes the recorder's completed-take workflow. It does
not add a playback machine or a DSP engine. The existing Python Flex prototype
is a behavioral reference; its callbacks are not part of a flashable OS.

Implementation must execute on the device's ColdFire CPU: preserve a completed
recording in owned memory, pass it through the stock sample loader, and assign
the resulting sample to an existing ONESHOT track. Discard or a failed accept
must retain the previous sample. The recorder response is shared memory: copy
each chunk while holding the stock outer recursive lock, before releasing it.

The current bound is 141–960000 frames of 48 kHz PCM16, mono or stereo. The
native sample representation has a 64-byte header and 16-byte zero trailer.
Temporary sources need bounded ownership and cleanup. The user selected
automatic persistence on project save: save the accepted recordings used by
the project, replace their temporary references with durable sample references,
and only then complete project saving. A storage failure must not report a
successful project save or discard the in-memory take. Project reload must
recover the same audio. This path must be resolved before calling the feature
ready.

Keep Plaits R2 and R3 builds independently reproducible. All patches must guard
the exact 1.16 input and displaced bytes, avoid Plaits allocations, and remain
below the reset-clear boundary. Static unused-space scans are candidates, not
proof that a location is safe. Audit emitted ColdFire instructions independently
of Unicorn: the previous R1 failure demonstrated that emulation alone is not
an instruction-legality check.

Validation must distinguish native CPU execution, peripheral models, original
sample-loader/DSP behavior, UI integration, project persistence, and hardware.
No hardware upload is authorized by this task.

## Explicit named save (2026-10-07)

The native recorder now has a deliberate save action for the selected track's
accepted Flex sample:

1. Record and trim, then press **YES / USE** as before.
2. Select the track containing the Flex sample and open **SAMPLING** again.
3. While the recorder is idle, hold **FUNC** and press **RECORD** (the sequencer
   Record button). The original filename editor opens as **SAVE FLEX SAMPLE**.
4. Edit the name and press **YES**. **FLEX: SAMPLE SAVED** confirms completion.
   **NO** cancels without writing. The file is stored in `/recorded/<name>`.

This saves the accepted trimmed PCM from its owned buffer, without another
recording or a project save. Track processing such as filters/pitch is not
rendered into this file. It leaves track controls, slot assignment and RAM audio
unchanged. It promotes only project-pool references belonging to that take,
including aliases, and caches the durable reference. Subsequent project saving
keeps the chosen filename and still persists other temporary takes normally.
Saving a sample does not save pattern/project edits.

The shortcut is intercepted only in the recorder view. Unmodified RECORD and
other keys retain their stock dispatch. Recording/arming does not invoke it;
the completed-trim screen says **FLEX: USE TAKE FIRST** so an older accepted take
cannot be mistaken for the new unaccepted recording. A track without an owned
Flex sample says **FLEX: NO FLEX SAMPLE**. After reboot, normally loaded +Drive
samples are outside this temporary-sample action.

The filename limit is 60 printable ASCII characters, with no leading space/dot
or path separators. Existing files are never overwritten. A collision or write
failure shows **FLEX: SAVE FAILED** and retains the original sample/reference;
retry with a different name for a collision. This is Save As: an earlier file,
including an automatic project-save copy, remains on +Drive. Project save does
not create another automatic copy of a take saved with this action.

Implementation: `lab/flex_native_save.py`, a guarded recorder-handler hook at
`0x40022c6e`, the stock filename/message dialog constructors, native exclusive
file creation and selective reference promotion. The inline dialog callback
borrows an immutable owned node and captures the project-pool identity. The
writer rejects a changed project before filesystem writes. No Python callback
performs naming, file creation, reference promotion or confirmation in the OS.
File writes execute synchronously during confirmation using the stock filesystem;
hardware UI latency and audio continuity during the write remain unmeasured.

Checks:

- `out/runs/flex-save-ui-03/report.json`: panel FUNC+RECORD, missing-sample and
  unaccepted-take messages, cancellation with zero writes, native name editing
  (FLEX → GLEX), actual guest filesystem save, success dialog, collision
  rejection, unchanged playback state and a later pad trigger pass. A separate
  unmodified stock CPU reads `/recorded/GLEX` and reloads exact PCM. Dialog,
  edited-name and result screenshots were visually checked. The recorder and
  sector read/write services are external peripheral models; filesystem,
  naming, ownership and reference operations execute in the guest. The first
  discovery run using the prepared snapshot's full eSDHC interrupt path did
  not finish the write within its bounded window; this result does not establish
  a complete peripheral/interrupt simulation or physical save behavior.
- `out/runs/flex-save-loader-02/report.json`: native mono and stereo named save,
  preservation of unrelated temporary takes, name collision protection,
  automatic project save after named save, independent stock project reload,
  the chosen path and exact PCM pass. The test also covers Save As after the
  take already has an automatic durable reference.
- `out/runs/flex-save-mono-use-01/report.json`: mono USE, rejection/retry, pad,
  discard and replacement still pass with the expanded overlay.
- All 40 configured-runtime source tests pass, including invalid/long names,
  changed-project and write-failure rollback, alias promotion, preserved ABI
  registers, shortcut press/release/repeat handling and stock dispatch controls.
  Scoped Ruff and independent ColdFire instruction audits pass. Shared DSP and
  adapter sources are unchanged by this addition.
- The combined package repeats exactly, preserves every Plaits R3 CPU change
  and the R3 DSP blob, and passes container/depacker checks.
  `out/runs/flex-save-package-01/boot-payload-check.json` confirms all 76
  overlay writes survive 400 million cold-boot instructions with nine tasks.

Current local package:
`out/runs/flex-save-package-01/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`.
SHA-256: `264f1355ff60fff8ef9561b4c380d2177ac85e95b0a6a3f70857d46a86f4e63c`.
MAIN SHA-256: `22205e8116af10907c79e5b98b0b4d75becbb4f3014772e27ab300e7ecedfc55`.
The native payload totals 5621 bytes. It includes the mono conversion correction
below. Previous packages remain untouched. This replacement has not been sent
to hardware by the agent and its physical behavior is unverified.

## Mono USE correction (2026-10-07)

The user's follow-up photos show **FLEX: INPUT FORMAT** and recorder settings
**MAIN / MONO R / 4 STEPS / 00:71**, with the previously reported ONESHOT
destination. The ten-second bound does not explain this format rejection.

The native USE entry mishandled the stock recorder's byte-boolean ABI. OS 1.16
helper `0x40020388` runs `SNE.B D0; NEG.L D0`: a mono channel returns
`D0 = 0xffffff01`, whose low byte is true. The original stock caller zero-extends
that byte. Flex instead copied all 32 bits before calculating `!mono`, producing
`stereo = 0x100`. Its format guard correctly rejected that invalid value.

`recorder_use_entry` now clears D1 and copies only D0's low byte before the
subtraction. Stereo remains 1 and every mono enum produces 0. This adds two
bytes to the native payload; the rejection guard and Plaits R3 behavior are
unchanged. A regression executes the exact stock helper instructions and
recreates the old caller as a negative control: the old code yields 256 for
mono, while the corrected caller yields 0. The earlier UI checks used stereo;
the lower-level mono tests bypassed this entry conversion and missed the bug.

The replacement local package is
`out/runs/flex-mono-fix-01/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`.
SHA-256: `eb2754d276de58b5123c0f904f688457fbe90223708d9b7fb7e82393a579690c`.
MAIN SHA-256: `6db3ccfc012fe838c30fc74addd5e683c15c9771839b93260e32ff70d91712ee`.
The emitted native payload is 4100 bytes. Previous packages remain untouched.

Validation for this correction:

- All 33 configured-runtime source tests pass, including the stock byte-boolean
  regression and the old-code negative control. Scoped Ruff checks pass.
- `out/runs/flex-mono-ui-02/report.json` and
  `out/runs/flex-stereo-ui-01/report.json`: native queued USE, error/retry,
  preservation of other controls, pad slot dispatch, discard and replacement
  pass in both formats. The mono fixture seeds ProjectSettings channel enum 2
  before recording; the stock screen displays **MONO R** (visually checked).
  The setup hook is removed before recording, so the original getters, byte
  boolean and native USE execute normally. Encoder changes did not take effect
  in this prepared snapshot; `flex-mono-ui-01` retains that failed setup attempt.
  These runs use an external recorder peer and IN source, not actual MAIN
  resampling or rendered audio.
- `out/runs/flex-mono-loader-01/report.json`: native mono/stereo loading,
  assignment, original project serialization, independent stock reload,
  persistence failure handling, and preservation checks pass.
- `out/runs/flex-mono-fix-01/native-patches.json`: independent ColdFire audit,
  deterministic overlay rebuild, Plaits byte preservation and container
  roundtrip checks pass. The Plaits DSP blob is byte-identical to the previous
  R3 package.
- `out/runs/flex-mono-fix-01/boot-payload-check.json`: all overlay bytes survive
  400 million emulated cold-boot instructions; nine tasks are created.

This fixes a reproduced native code defect matching the photographed error.
Physical MAIN resampling, audio and the corrected hardware USE result still
need confirmation. Retest the same short MAIN / MONO R take and press YES on
the completed-take screen. The agent has not uploaded this replacement.

## Hardware report and diagnostic follow-up (2026-10-07)

The user reports uploading the combined firmware, recording a take, and seeing
**FLEX: CANNOT USE** after YES. The destination was ONESHOT. At that point,
source, take length and the precise rejection stage were unknown; the
subsequent photos and mono correction are recorded above.
This is a failed physical USE result, not a confirmed recorder-source issue.
The exact installed bytes have not been read back from the device.

The first build uses the same generic message for multiple rejections. The
follow-up distinguishes track changes, unsupported machine, missing project,
no free slot, short/over-ten-second take, input format, 32-take limit, allocation,
copying, sample loading and assignment. It also records the native loader return
value and checks the absolute trim end before allocating. This is diagnostic
work, not a claim to have corrected the reported hardware failure. Existing
firmware files and original test reports are retained.

The diagnostic build is in
`out/runs/flex-error-package-01/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`,
SHA-256 `a1c042d0102762a5da40d7b322cbb55ddaef3c160907f26fef9285a4f1ab6adf`.
MAIN SHA-256: `3e2ecb8c53ea76dd138d9e3f086a3b97112894d709ccc6fbdb1fc2ae086e7889`.
It retains Plaits R3 and the same recording limits. No replacement firmware
has been sent to hardware by the agent.

Checks for this revision:

- `out/runs/flex-error-ui-01/report.json`: original queued UI shows **FLEX:
  OVER 10 SEC** for an oversized trim, preserves the previous track, dismisses
  the message, and accepts a valid retry. Pad, discard and replacement also pass.
  `over-limit-error.png` was visually inspected.
- `out/runs/flex-error-loader-01/report.json`: native mono/stereo acceptance,
  stock fallback, slot protection, original project save and stock reload pass.
  An injected loader failure retains its distinct error and raw return value.
- 31 configured-runtime source tests, scoped Ruff, and independent emitted
  ColdFire instruction audits pass. This revision changes native CPU/error
  reporting and checks only; the shared DSP/adapter sources are unchanged.
- Container roundtrip, exact rebuild, and preservation of the Plaits CPU
  changes pass. `out/runs/flex-error-package-01/boot-payload-check.json`
  confirms every patch byte survives 400 million cold-boot instructions
  with nine created tasks. Package remains diagnostic and hardware-unverified.

The state allocation grows from 48 to 56 bytes: +48 is an error index (zero
means generic/no current error), +52 holds the most recent loader result.
The original error PEA is replaced by an audited trampoline that pushes the
selected static message and rejoins the stock error-dialog code with the same
stack effect. A successful accept/assignment clears the error index.

## Implemented native path (2026-10-07)

`lab/flex_native.py` emits ColdFire instructions for the recorder's queued USE
job, owned sample buffers, temporary resource lookup, normal sample loading,
track assignment, file persistence, and the project-save guard. The original
recorder service, heap, filesystem, sample loader, UI scheduler and ONESHOT
playback engine remain responsible for their existing operations. Python builds
and tests the patch; it does not perform USE or manage samples in the OS image.

The completed-take screen displays **Y:USE**. YES copies the trimmed recording,
loads it into a slot empty in both the CPU loader and project pool, and assigns
it to the selected ONESHOT track. Subsequent recordings remember that track.
The native completion callback closes the progress dialog and recorder. FUNC+NO
discards an unaccepted take without replacing the previous assignment.

Project saving persists temporary references in the project sample pool under
`/recorded/FLEX-<content-hash>-<collision-number>`. Files are created exclusively;
existing files are never overwritten. The original content hash distinguishes
different recordings of the same length. Only after every required file has
been saved does the guard promote project references and enter the original
project writer. A failed recording save leaves the temporary pool unchanged
and returns failure before project serialization. Successful files are cached
per owned buffer so retries do not duplicate those recordings. Already written
files can remain if another recording or the later project write fails.

This saves all temporary samples retained in the project pool, including an
older take still present there after replacement. It does not garbage-collect
unused pool entries or promise that only the currently selected track sample
will be stored.

## Checks and current bounds

- Prepared GUI: `out/runs/flex-native-ui-03/report.json` passes native queued
  USE, preservation of other track controls, a real pad trigger carrying the
  accepted sample slot, discard, and a second USE. The recorder input is an
  external WAV/peer model; the guest performs copying, allocation, loading,
  assignment and UI completion itself. That run captures control frames, not
  newly rendered SHARC audio or physical inputs.
- Native loader/project probe: `out/runs/flex-native-loader-21/report.json`
  passes. The original project serializer and storage
  writer save a mono/stereo take. An independent unmodified stock CPU instance
  refreshes its project directory from the resulting sector overlay, decodes
  the saved project, recovers its track assignment/reference and reloads exact
  PCM through the stock sample loader. The test also injects persistence failure
  to verify that the original project writer is not entered, preserves an
  unloaded-but-referenced project slot, and distinguishes same-sized takes.
  Peripheral/mutex
  models and bounded direct calls are distinct from a hardware save test.
- All 31 source tests and scoped Ruff checks pass in the configured runtime.
  Independent ColdFire audit checks every newly emitted instruction. Raw CPU
  tests cover copy bounds, chunk boundaries, mono/stereo, nonvolatile registers,
  recorder-lock lifetime, resource validation, EOF and stock fallback.
- The shared SINE replay regression passes in
  `out/runs/20261006T152914Z-test-1a95b623/manifest.json`, including exact
  repeat, stock compatibility and negative controls. An earlier run was
  invalidated by source edits during execution; the final run held source fixed.
- Combined-image build repeats exactly and preserves every Plaits R3 CPU
  change. Container checks depack both changed sections back to the intended
  bytes, verify checksums and retain other stored sections byte for byte.
- `out/runs/flex-native-build-02/boot-payload-check.json`: the combined MAIN
  image completes 400 million cold-boot instructions, creates nine tasks, and
  retains every native overlay byte. This is bounded boot/placement evidence,
  not exhaustive proof that all asset paths leave the padding unused.

Current limits: ONESHOT destinations; 141–960000 frames per take (up to twenty
seconds at 48 kHz), mono or stereo; at most 32 accepted buffers per boot, subject
to heap availability. Accepted buffers remain allocated until reboot, including
replaced or persisted takes. A full pool, unsupported destination, oversized
recording or failed allocation returns the stock error flow with a Flex message.
Reclaiming buffers across project changes needs further work. Power loss before saving the project loses its temporary recordings.

The original combined package is **experimental; hardware USE has failed as
reported above**. The agent has not uploaded firmware. Concurrent device activity, storage exhaustion,
power interruption, final audio and real-time timing remain unverified. Plaits
R2's user hardware result does not establish R3 or Flex hardware behavior.

## Reproduce

From the lab repository (all outputs must be new ignored directories):

```sh
./labctl doctor
python3 scripts/probe-flex-native.py out/runs/flex-native-check-new \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
python3 scripts/check-flex-native-ui.py out/runs/flex-native-ui-new
python3 scripts/check-flex-native-ui.py out/runs/flex-native-mono-ui-new --mono-right
python3 scripts/check-flex-native-save-ui.py out/runs/flex-native-save-ui-new \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
python3 scripts/build-flex-native.py out/runs/flex-native-build-new --plaits-r3 \
  --elekloader-reference out/references/elekloader-upload-audit
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The native probe and build scripts re-exec the configured runtime. Run unit tests
with that runtime too to execute the Unicorn cases rather than skip them. Keep
source unchanged during the replay suite: its final manifest checks source hashes.
The optional codec checkout must be clean at the exact revision required by
`lab/upload.py`; packaging never uploads. Existing R2 preparation gates remain
unchanged.

Local combined package:
`out/runs/flex-native-package-01/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`.
SHA-256: `2c2805e1cd052a8fc79c15ab7b3c915d4999b2858c85fda53708026230d3c775`.
MAIN SHA-256: `5d23d6cc751285767bbd202b3a6f73245c0871fbe955bda149566d4eeb716fb7`.
Its manifest records guarded sites, instruction audit, source hashes and section
identities. The firmware contains 3656 bytes of native Flex payload plus guarded
entry/label patches; there is no new DSP playback machine.


## 2026-10-07: twenty-second native limit

Raised native USE/copy bounds to 960000 frames (20 seconds at 48 kHz),
including the maximum trim end. The oversized-take message is now
`FLEX: OVER 20 SEC`. A full stereo take needs 3,840,000 PCM bytes plus
header/node overhead; accepted buffers still remain allocated until reboot.
Allocation failure retains the existing error handling. The earlier Python
prototype retains its separate ten-second input limit.

Focused validation: all ten native source tests passed, including actual
emitted-CPU copies of full twenty-second mono and stereo takes, the last valid
trim, and rejection beyond the bound. Ruff passed for the four changed Python
files. The deterministic build, ColdFire audit, Plaits preservation and SYX
container verification passed. Compared with the previous explicit-save build,
the MAIN image changes only six bound immediates and one message character.
No full UI/project regression or hardware test was repeated for this change.

Local package: `out/runs/flex-20sec-package-01/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`

SHA-256: `f0083b96c87d36bdae9c9146e2a6aacfc31d7f5f02bd3f252b5b0c2b0c2883f8`

Reproduce: `python3 scripts/build-flex-native.py out/runs/flex-20sec-package-01 --plaits-r3 --elekloader-reference out/references/elekloader-upload-audit`
(use a fresh output directory). Evidence: `focused-tests.log`,
`limit-diff.json` and the build manifests in that directory.


## 2026-10-07: Plaits before MIDI

The optional `--plaits-before-midi` build flag adds a guarded final display-only
overlay after the native Flex build. Order: Oneshot, Werp, Stretch, Repitch,
Slice, Grid, PLAITS, MIDI. Both the source list and comparator rank table
change; machine IDs remain Plaits=7 and MIDI=5. No descriptor, project format,
permission, DSP or Flex code changes. Historical base builds remain reproducible.

Reproduce with a fresh directory:

```sh
python3 scripts/build-flex-native.py out/runs/flex-20sec-menu-package-02 --plaits-r3 --plaits-before-midi --elekloader-reference out/references/elekloader-upload-audit
```

Package: `out/runs/flex-20sec-menu-package-02/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`

SYX SHA-256: `5891f98485eb5eedf0707f6f302ea56ba3fd017547a25de89752a37611efc7e9`

`menu-check.json` records the native rank-shim ABI check, exact display names,
reapplication negative control and byte comparison: only four MAIN bytes changed.
All 40 source tests, Ruff and package container checks passed. Hardware/panel
behavior was not exercised for this display-only change.


## Optional source-ownership experiment (2026-10-08)

`--managed-sources` enables separately allocated source memory, pinned native
reads/saves, exact-reference save-backed retirement, failed-candidate cleanup and
post-save counters. Default build bytes are unchanged. The bounded native tests
pass, including 20-second mono/stereo and stale/missing backing negatives; this is
not hardware readiness or a complete capacity redesign. Published identities remain
limited to 32 per boot, and safe heap headroom/project-epoch GC remain unverified.
See [the source-ownership results](FLEX-MEMORY-IMPLEMENTATION-RESULTS.md).

The [capacity continuation](FLEX-CAPACITY-RESULTS.md) measures the stock CPU heap
and streams Save As for retired sources using one 32 KiB scratch block. Native
pressure, partial-read cleanup/retry and complete 20-second stereo PCM reload pass;
it no longer requires another four-MiB block for that backed Save As. Resident
saves retain their pins. No new heap reservation or identity recycling is added.
