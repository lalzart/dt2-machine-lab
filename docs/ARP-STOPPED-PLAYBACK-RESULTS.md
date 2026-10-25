# Stopped-sequencer arp — separate all-feature candidate

The existing track-1 arp can now play held keyboard notes while PLAY is stopped,
using the current native tempo and selected 1/4, 1/8, 1/16 or 1/32 rate.
Enable UP/ORDER/RANDOM as usual, then hold a chord. No new clock setting or
transport start is required. The first note follows one selected interval.

Starting PLAY while holding a stopped arp chord retains phase and order.
STOP still silences the current chord; release and play a fresh chord to resume
while stopped. All-key release, OFF, keyboard exit and track/pattern changes
retain the existing gate cleanup and ownership handling. Latch, other tracks,
MIDI input, swing and external-sync guarantees are outside this change.

## Candidate and baseline

[Experimental OS1.16 with stopped arp](../out/runs/arp-stopped-package-20261019-02/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ARP_STOPPED_R1_OS1.16.syx)

SHA256: `621c5ba23cb3c5bc2dc52f12530f8ce676ab58a4e88ee2878dd347ea79f6c712`.
Includes the author Capicola R2 engine, Plaits, managed Flex and native Arp.
Only the CPU arp clock-enable selection changes. The emitted payload grows by
28 bytes, with no additional state, hook or allocation; arp state remains 8192
bytes. Dependent payload addresses are relocated by the existing allocator.

The R2 DSP is byte-identical, including the repaired 626,332-byte boot stream
and 422,243-byte loader headroom. Protected bootstrap/updater sections remain
stock. The original R2 artifact was preserved and a fresh default build still
produces SHA256 `764329c1324d8f666b82c40b2d3e31f4724721044ef8e0f89b070e46e973ea59`.
The new behavior requires the explicit build option `--arp-stopped`.

## Verification

- 240 source tests pass. New native tests execute the real tempo getter and
  heartbeat/clock/output instructions against an independent rational timing
  oracle: three modes, four rates, 30/102/120/127.5/300 BPM. They cover live tempo
  edits, playing parity, phase-preserving handoff, STOP/re-arm, key release,
  keyboard exit, busy state, tick wrap, late service and an old-build negative.
- The exact packaged CPU passes actual keyboard/Tempo/G panel input at 127.5
  BPM and sixteenths: PLAY stays zero, the sample counter advances and eight
  note-ons are `60,64,67,60,64,67,60,64`. Both startup and stopped cleanup have
  zero observed CPU fault pages. Timing is within observed emulator service
  intervals; these intervals do not establish physical jitter.
- The same package passes native live-recording note output at 120 BPM:
  `60,64,67,60,64,67,60,64`, followed by complete gate/key cleanup. This check
  does not claim a new durable save/reload or power-cycle test.
- Native ColdFire reset reaches ready, observes 39 DDR heartbeat calls, clears
  poisoned BSS and retains all payloads and canaries. Disabling its loader fails
  the causal negative. DSP boot is modeled, not coupled to a live SHARC peer.
- Actual bootstrap decompression, package/repeat/section checks and existing
  CAPI CPU controls pass. Focused Ruff passes for the new test and modern
  builder files; the legacy terse emitters retain their existing style issues.

The source-frozen SINE regression and full report hashes are recorded in the
[verification JSON](ARP-STOPPED-PLAYBACK-VERIFICATION.json).
Earlier exploratory runs and pre-edit source copies are retained under ignored
`out/runs/`. The working definition and frozen comparator are in
[the implementation note](ARP-STOPPED-PLAYBACK.md).

## Reproduce

Use fresh ignored run directories from dt2-machine-lab:

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/<package> --all-features --arp-stopped --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-arp-firmware.py out/runs/<stopped-panel> --package out/runs/<package> --tempo-ui --stopped-playback --stopped --mode up --tempo 127.5 --rate 1/16
python3 scripts/check-arp-firmware.py out/runs/<record> --package out/runs/<package> --tempo-ui --stopped-playback --mode up --tempo 120 --rate 1/16 --record
python3 scripts/check-cpu-extension-boot.py out/runs/<package> out/runs/<boot> --native-upstream <clean-DigiKit-ed57b475-checkout>
python3 scripts/check-upload-depacker.py out/runs/<package> --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

The scripts select configured Python 3.12. Run the source suite with that
interpreter using `-B -m unittest discover -s tests -q`.

This is a locally validated experimental candidate. It has not been uploaded or
tested on hardware, committed or published. Physical scheduling, external sync,
full coupled startup and real-device listening remain unverified for this build.
The settings resource monitor is not included; its scope clarification remains
separate from this completed arp change.
