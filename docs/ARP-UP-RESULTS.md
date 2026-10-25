# UP arp emulator result, 2026-10-14

The first UP prototype passed in DigiKit. An original ColdFire core collects
mapped keyboard pitches and sends generated notes through the stock OS 1.16
note routines. Pressing G–E–C produced C–E–G; releasing E left C–G. Last-key
release and Stop ended the generated note. This is an emulator experiment with
temporary memory and diagnostic calls, not an installable firmware package.

The selected scope is [ARP-UP.md](ARP-UP.md): one audio track, one octave,
sixteenths at 102 BPM, 50% gate, no latch. Eventual modes are OFF / UP / ORDER /
RANDOM. Only OFF and UP are implemented in the native core. G's menu selector,
recording, saved settings and hardware integration remain separate work.

## What changed

- `lab/arp_native.py`: six integer-only ColdFire routines, 1,324 bytes of core
  code and 1,600 bytes of caller-owned state. Sixteen held contributions,
  duplicate-pitch reference counts, retained release ownership, rational phase,
  bounded missed-clock behavior and reset/panic handling.
- `lab/arp_emulation.py`: bounded CFV4E execution with stack and nonvolatile
  register checks. `tests/test_arp_native.py` covers ten musical/lifecycle cases.
- `lab/arp_ui.py`: real keyboard note-call interception on track 1, stock
  generated-note calls and actual guest sample ticks. Two native collection
  wrappers add 102 bytes. All 1,426 emitted bytes passed the ColdFire auditor.
- `scripts/check-arp-core.py`, `scripts/capture-arp-up.py` and
  `scripts/render-arp-up.py`: source audit, deterministic panel capture and
  existing stock SHARC voice-buffer replay. No dependency or sound engine edit.

The adapter runs between emulator worker chunks in borrowed CPU contexts.
PLAY/STOP comes from observed KeyboardView button events; it is not yet a
traced native transport-state integration. Temporary code, state and stack
occupy a checked emulator-only region at `0x60000000`. Neither placement nor
scheduler/interrupt safety has been established for a device.

## Observed results

| Check | Retained artifact | Result |
|---|---|---|
| Native instruction audit | `out/runs/arp-up-core-02/core.json` | 1,426 bytes accepted; 1,600 state bytes |
| Source suite | `out/runs/arp-up-summary-01/source-tests.log` | All 154 tests passed, including ten arp tests |
| UP repeat | `out/runs/arp-up-panel-02/arp.json`, `arp-up-panel-03/arp.json` | Same 12 note-ons and 12 note-offs, physical inputs, stock calls, ticks, interrupts and complete control bytes |
| DSP control delivery | `arp-up-panel-03/arp.json` | All twelve pitch words equal generated MIDI note × 256; each arrived 32 modeled samples later; capture ticks remain consecutive 32-sample blocks |
| Held-gate Stop | `out/runs/arp-up-stop-panel-01/arp.json` | Restarted C on at tick 185536; Stop off at 185824; retained one suppressed input owner until release, then zero; no later generated or leaked stock event |
| OFF comparator | `out/runs/arp-off-panel-01/arp.json` | Zero arp edges; physical G–E–C reaches the native stock note API in that order |
| Unsupported track | All passing panel captures | Track 2's C press and release remained ordinary stock calls |
| Stock voice PCM | `out/runs/arp-up-audio-01/replay/render.json` | 2.24 seconds, 12 note intervals, finite/nonzero/nonclipping, peak 0.3230743408; two native replays byte-identical |
| SINE regression | `out/runs/20261014T121201Z-test-0349e6e0/manifest.json` | `./labctl test sine --replay` passed |

The twelve UP notes were `60,64,67,60,64,67,60,64,67,60,67,60`.
Their intervals were 7,040 or 7,072 output samples, as the rational sixteenth
deadline crosses 32-sample service blocks. This measures modeled capture
delivery, not physical-device jitter or an actual real-time workload.

The OFF comparator proves the native keyboard input path. Its raw control
capture had an additional track-1 trigger after PLAY; full control-byte parity
against a separate adapter-free stock run was not tested.

Audio: `out/runs/arp-up-audio-01/replay/pattern.wav`. This is actual stock SHARC
voice-buffer replay using the existing sample-state fixture and isolating track
1. Final mixer/DAC output and subjective listening were not verified.

## Reproduce

Run in `dt2-machine-lab`, using new output names. The scripts use the configured
runtime; the explicit interpreter below also covers the audit and source tests.

```sh
arp_python='/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python'
./labctl doctor
"$arp_python" scripts/check-arp-core.py out/runs/arp-up-core-new
"$arp_python" -B -m unittest discover -s tests -v
"$arp_python" scripts/capture-arp-up.py out/runs/arp-up-new
"$arp_python" scripts/capture-arp-up.py out/runs/arp-up-repeat-new
"$arp_python" scripts/capture-arp-up.py out/runs/arp-off-new --off
"$arp_python" scripts/capture-arp-up.py out/runs/arp-stop-new --stop-held
"$arp_python" scripts/render-arp-up.py out/runs/arp-up-new out/runs/arp-audio-new
./labctl test sine --replay
```

Each capture is bounded by 600M CPU instructions and 600 seconds. The ordinary
UP run used 506,903,375 instructions/4,196 control frames; the extended Stop
case used 555,590,750/4,749. All passing captures had no worker errors or touched
fault pages. Preserve an unsuccessful run and choose a new directory to retry.

## Inputs and provenance

Uses the inherited prepared SINE CPU fixture, with track 1 switched to the
stock sampler through the panel. This is not a clean-stock cold-boot comparison.
The CPU MAIN image remains `344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830`.
The original OS 1.16 SYX is
`278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec`;
the replay's stock DSP blob is
`0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
The pinned DigiKit dependency remains clean at
`277760aad51b036a4756db051409d4d3b1eeccbc`; the research checkout remains clean
at `fd899a1d7f3188f99e5b21ed83e62fa5d54bf550`.

The repeated control capture SHA-256 is
`58754321e4903a4373b94c3ed23e18c34673489c3b961c8a99aa584099837156`;
WAV SHA-256 is
`63a8fef3795be1b85e77dde564855f6ce33b5d84535de0f8ebd78ce56a719bf1`.
`out/runs/arp-up-summary-01/summary.json` authenticates sources, comparisons,
reports and unchanged firmware/snapshot/card inputs. Each run retained its
own source freeze. Later capture assertions and results backfill do not change
the core, adapter or renderer source fingerprints used for the signal result.

The first integrated capture, `arp-up-panel-01`, failed because the physical
input assertion included a preparation key press before arming. The assertion
was scoped to the armed gesture sequence and rerun; no native behavior or timing
tolerance changed. An initial unit assertion also expected an off beyond its
capture endpoint; it was corrected to the declared deadline. Failed evidence is
retained. No firmware was packaged, flashed, committed, pushed or published.
