# Native arp firmware on stock OS 1.16

Status: the first package failed its user hardware trial on 2026-10-15.
The user reports T1, keyboard mode, G UP, three held keys: no arp with the
sequencer stopped or running. The G control is visible. The original emulator
checks below are historical evidence and did not predict this failure.
No firmware was sent to the device by the agent; no commit or publication.

## D1 device diagnostics

The user reports that leaving/re-entering keyboard mode, holding three keys and
pressing PLAY still produces no arp. Which of the two installed candidates was
used is not yet confirmed. The flag mismatch is a demonstrated emulator bug;
it is not an established explanation of this physical failure.

The optional `--diagnostics` build instruments the existing keyboard-fixed port.
It adds no new arp scheduling/input policy, tempo or track behavior. Without
that option, MAIN remains exactly
`5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310`.
D1 reads/counters use spare bytes in the same 8 KiB allocation. They are transient,
not saved, and do not require Python services. Journal layout is unchanged.
The screen renderer formats values only; it never clocks the arp or emits notes.

In Keyboard Settings the G cell reads, for example:

- `H3P1`: held contributions 3; the arp observed PLAY (1).
- `UPN08`: UP mode; 08 generated note-on API calls, in hexadecimal modulo 256.
  Other mode prefixes are OF, OR and RN. This counts calls, not audible voices.
- `K1C1`: stock keyboard setting active; sample tick advanced between native
  heartbeat services while the arp's PLAY flag was set. C resets at the next
  accepted PLAY press, then latches once progression is seen. C alone does not
  prove a regular hardware service cadence or correct note timing.
- `D1A03` in the upper right: D1 build; 03 T1 note-on API entries observed,
  excluding this arp's own output. A can include other stock users of that API,
  not just physical keys, and also wraps modulo 256.

Hold the chord with Keyboard Settings open and press PLAY. A useful report is
all three G lines plus the D1A and R values while the chord is held. The R value is the last observed non-arp T1 note-on caller, shown as two
stacked halves at the right (`R4005` over `C666` means 0x4005C666), so differing native
input paths can be identified without another diagnostic build. The exact split
H/P/K/C/N/A/R will choose the next investigation; no physical cause or fix is
claimed by producing this diagnostic package.

The native formatting test executes the original OS formatter and intercepts
only its final renderer. It verifies all displayed strings and checks drawing
leaves core/counter state unchanged and never enters note/clock functions.
An initial `%X` format was unsupported by the stock formatter; `%x` produces the
required uppercase hexadecimal. That failed test and earlier panel captures
are retained, not treated as final evidence.

D1 handoff: `out/runs/arp-diagnostics-d1-readout-package-01/EXPERIMENTAL_ARP_STOCK_OS1.16_DIAG_D1.syx`.
SYX SHA-256: `c96eab65ba6104699c73b9078fd3f12808af605ce5fa4f2d84573ef3a4d10175`.
MAIN SHA-256: `3c622ff76fceb3e5ea0cd9a15be532c3a0965d5ffaa18b3eae48790ed9c72c7a`.
Payload is 7522 bytes including diagnostic strings; runtime request remains
8,192 bytes. `arp-diagnostics-d1-readout-panel-02/native.json` passes under this
exact MAIN with identical source hashes at capture/package time. It captures
eight UP ons and matching offs, eight stock control trigs, collected/owned release
cleanup and STOP, no CPU fault pages, clock-progress flag 1, output counter 8,
non-arp T1 API counter 3, and original caller 0x4005C666. The visual capture may
show N07 because the stock display refresh trails the eighth call; it is not a
synchronous CPU-state snapshot. All lines, including R4005/C666 in the blank
strip right of the keys, were visually checked. An earlier top-header caller
placement was repainted by the stock draw continuation and was replaced.

The stable source suite passes. Build/container checks preserve all non-MAIN
sections and verify exact repeats. Startup and original depacker results for
this exact candidate are linked in its verification report. These remain
emulator/container evidence; neither full project save/load nor new DSP audio
was repeated for the diagnostic overlay. Physical behavior remains unresolved.

Reproduce with fresh ignored output directories:

```sh
python3 scripts/check-arp-firmware.py out/runs/arp-d1-panel \
  --diagnostics --keep-settings-open
python3 scripts/build-arp-firmware.py out/runs/arp-d1-package \
  --diagnostics --elekloader-reference out/references/elekloader-upload-audit
```

## Hardware-failure follow-up

EVIDENCE: the first port shadowed keyboard mode in a private boolean, initially
zero, toggled only by observed KEYBOARD events. It never read the original
project's keyboard setting. The OS1.16 getter at 0x4004AF88 reads its live
settings object through vtable slot +0x28 and tests data +0x38. It is also the
stock keyboard handler's own predicate. The original getter returns a byte
boolean, so callers must normalize before long tests.

EVIDENCE: injecting private keyboard flag zero while leaving the stock keyboard
active reproduces no collection and no arp output with PLAY, without CPU fault
pages. The stock notes still pass through. This is an explicit mismatch fixture,
not a claim that the same state was observed on the physical device. Leaving
Keyboard Settings open alone does not prevent collection/output in the emulator.

HYPOTHESIS: restored keyboard mode or an unobserved mode transition could explain
the physical failure. The exact device cause remains unconfirmed.

The follow-up source reads the stock predicate during native sync and immediately
before physical-keyboard note collection. It removes the private event-toggle
logic and panics on a true-to-false stock setting transition. Core ordering,
timing, track limit, journal layout and stock DSP are unchanged. A focused native
test executes the actual stock getter with restored active settings, then exits
keyboard mode and checks panic plus retained release ownership.

Replacement package:
`out/runs/arp-stock-keyboard-fix-package-01/EXPERIMENTAL_ARP_STOCK_OS1.16_KEYBOARD_FIX.syx`.
SYX SHA-256: `c4f508f72039f6d33ae7781ddae193c3e936ed6de7c20c78e72d98a2b6749e41`.
MAIN SHA-256: `5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310`.
Payload is 6,946 bytes; the existing 8 KiB runtime allocation is unchanged.
The filename was changed after packaging; the verified bytes are unchanged.

`arp-stock-keyboard-fix-01/native.json` passes with that exact MAIN. It deliberately
resets only the arp's keyboard flag while the stock keyboard stays active,
keeps Keyboard Settings open, then captures eight UP ons/offs, eight stock
control trigs and clean release/STOP. RECORD + PLAY is used; this run does not
repeat project persistence or verify recorded pattern contents. It retires
428,925,750 emulator instructions with zero fault pages. The independent native
stock-getter regression fails against the preserved original source and passes
against this source. The current source suite passes; the same focused suite
also executes the relocated journal's codec and failure checks.

`arp-stock-keyboard-fix-boot-01/boot.json` passes the bounded 400M startup and
static-write preservation check; state is still uninitialized at that checkpoint.
`arp-stock-keyboard-fix-package-01/device-depacker.json` passes the original
bootstrap depacker for all three packed sections. Exact build/container and
protected-section checks pass; DSP and all non-MAIN sections remain stock.
No new physical operation, listening, final-output or timing success is claimed.
The earlier full recorded-project save/load/replay result below belongs to the
first MAIN, and was not repeated for this keyboard-only correction.

Reproduce the new failure-recovery fixture:

```sh
python3 scripts/check-arp-firmware.py out/runs/arp-keyboard-recovery \
  --record --stale-keyboard --keep-settings-open
```

The normal builder reproduces the replacement bytes under its default generic
filename; rename that file to the keyboard-fix name when comparing this handoff.
Private baseline copies, expected failing controls and command logs are retained
in `out/runs/arp-hardware-failure-01/`. Reporting-only edits after the panel
capture do not change its exact MAIN equality with the packaged file.


This continuation replaces the Python arp services with native ColdFire code:
G menu edit/draw, keyboard ownership, task-paced clock, stock note input and
project mode journal. MAIN changes only; DSP, bootstrap, updater and all other
sections stay byte-identical to the supplied stock Digitakt II 1.16 container.

## Use

On audio track 1, enter keyboard mode, open its settings with FUNC + KEYBOARD,
and turn G to UP, ORD or RND. Close settings, hold a chord and press PLAY. Release keys and stop before project saves/loads in this
first build. RECORD + PLAY records the generated phrase as ordinary stock notes. STOP,
mode changes and project load close the arp gate. FUNC + PLAY retains its stock
clear action. G push and the other settings controls keep their stock handlers.

This first build is fixed at 102 BPM, sixteenths, half-length gate, one octave,
no latch and track 1. It does not follow tempo edits or external clock; MIDI I/O is unsupported. Mode settings are 128 per-pattern values in separate AR16 companion
files on +Drive. Recorded notes stay in the ordinary project format. Missing,
invalid, wrong-project or conflicting companions recall OFF. Runtime keys,
gate, clock and RNG progression are never restored. The normal load's working
project autosave to slot 128 also passes through the native save wrapper.

Companion write failure keeps the original project's save result and marks
ARP! in keyboard settings; the previously active journal bank is preserved.
Mode configuration is separate from the stock project format and Transfer
exports do not automatically include its companion files.

## Implementation and checks

Native state is an 8 KiB lifetime allocation from the original OS heap. Failure
keeps the arp disabled and leaves stock input available. Guarded instructions,
strings and two small mutable globals use reviewed stock-image padding before
reset-copy data. No diagnostic 0x60000000 placement or Python arp callbacks are
required by the package. Image generation rejects unknown stock hashes and
unexpected patch-site/padding bytes. All generated instructions are audited.

Focused native checks compare the existing AR16 codec byte-for-byte, exercise
inactive-bank failure, missing/corrupt/wrong-project/conflicting records,
64-bit sequence carry, root filename handling, heap failure, relocated mode
vectors, releases during storage, and FUNC + PLAY versus RECORD + PLAY.
The normal panel checks produce the registered UP, ORDER and RANDOM phrases,
with matching offs, and OFF preserves ordinary note input. Full source and
baseline SINE results are retained separately from feature-specific evidence.

The native stock formatter uppercases hexadecimal digits; the port explicitly
converts the digest characters to match the existing AR16 filename convention.
A lookup pointer initially skipped four pathname bytes instead of just the
slash; the real filesystem readback exposed this and a focused native argument
check now guards it. Failed attempts remain in the discovery/run directories.
The first GUI storage test exhausted its audio capture on silent save/load
frames. Capture is now paused for storage, and the runner waits for the actual
discard dialog after the stock working-project autosave completes.

## Reproduce

Use fresh output directories under `out/runs`:

```sh
./labctl doctor
python3 scripts/check-arp-firmware.py out/runs/arp-check --record --storage
python3 scripts/build-arp-firmware.py out/runs/arp-package \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-arp-firmware-boot.py out/runs/arp-package out/runs/arp-boot
python3 scripts/check-upload-depacker.py out/runs/arp-package \
  --elekloader-reference out/references/elekloader-upload-audit
```

Scripts select the configured Python automatically. Storage uses a private
card overlay with modeled eMMC transfers. During long native crypto/file jobs,
the runner raises instructions per emulated second to reduce interrupt overhead,
then restores the normal clock model for button gestures and musical checks.
This is a test speed adjustment, not evidence of physical storage latency or
CPU headroom. The firmware itself has no such test switch.

## Remaining limits

Hardware upload/boot, real-time scheduling, physical CPU load, coupled final
DAC output and listening are open. The bounded cold-start check preserves
all static patches but stops before the prepared panel state; it does not
prove a complete card-backed cold boot or automatic power-on mode recall.
Broader held-key/view transitions, new-project reset/creation, pause/external transport, more tracks,
tempo following, pattern copy/undo/export and companion cleanup need further
integration. Stock recording quantization is unchanged. A new voice-PCM render
is not claimed for this port; the DSP remains exact stock.

## First artifact and historical evidence

Package: `out/runs/arp-native-stock-package-01/EXPERIMENTAL_ARP_STOCK_OS1.16.syx`.
SHA-256: `f3a84cac28aed347b35c351944e634b2ba546c67b77b2e5028521396b6b4389b`.
MAIN SHA-256: `fde3770d1f51eeafc3f55ff0858e2e7b183b53658f1852917b882bae299b807f`.
Native payload is 6,918 bytes including strings/data; runtime heap request is
8,192 bytes. The existing 2,254-byte core is reused with relocation.

`arp-native-record-project-01/native.json` passes under the exact final MAIN.
It verifies eight live UP notes and offs, the native stock save routine and
AR16 write/readback, normal project-menu recall, all 121,740 pattern bytes,
and ordinary sequencer replay of 60,64,67,60,64,67,60,64. Playback produces no
new collected arp events. The GUI's native working-project autosave to slot
128 also succeeds. No CPU fault pages are touched. The initial save is invoked
through the original routine in a paused transaction; menu loading and its
autosave run in the original scheduled task context. eMMC uses a private model.

`arp-native-order-01`, `arp-native-random-01`, and `arp-native-off-01` retain
earlier native panel vectors. Final relocated instruction tests cover every
mode against the frozen vectors and the journal's complete four-mode byte map.
The late changes concern filename handling, held-release/transport guards and
slot-0 binding; no selector algorithm was changed.

`arp-native-discovery-01/source-stock-final.log` is the passing full source
suite. `20261015T094316Z-test-f056bcd2/manifest.json` is the passing SINE replay.
The package, complete UP project capture and SINE use identical frozen source
hashes. `arp-native-stock-package-01/freeze-final.json` records that freeze and
the native test/log fingerprints. Subsequent result backfill changes reporting
Markdown only.

`arp-native-stock-boot-01/boot.json` checks bounded startup and preserved static
writes; no-card startup has not initialized arp state at the 400M checkpoint.
`arp-native-stock-package-01/device-depacker.json` runs the original bootstrap
depacker for the actual package's packed sections. The build manifest checks
both independent decoders, transport checksums, HMAC, section identity,
protected bytes and staging bounds. Results are also indexed by
`arp-native-stock-package-01/verification.json`.

Retained failures include a wrong native filename pointer, native formatter
case, selecting CREATE NEW from a stale slot catalog during a test, premature
confirmation input, silent audio capture exhaustion and an erroneous slot-0
decoder guard. The latter tested a scratch D3 instead of the explicit load flag;
a focused native test now proves slot 0, unarmed rejection and destination
mismatch. The successful menu test uses the existing registered slot 0.
