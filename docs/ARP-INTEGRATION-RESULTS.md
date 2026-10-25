# Four-mode arp prototype, OS 1.16

EVIDENCE: DigiKit now has an original native OFF / UP / ORDER / RANDOM core,
a G selector in keyboard settings, stock live recording, and checked native
project save/recall with a mode companion. This is an emulator prototype for
track 1, one octave, 102 BPM sixteenths and 50% gate. It is not a hardware
firmware package. The first UP implementation and its evidence remain intact.

The approved scope is [ARP-INTEGRATION.md](ARP-INTEGRATION.md). Results are
from 2026-10-14–15. No original firmware/card bytes, pinned dependencies or
unrelated inherited changes were edited. Nothing was committed or flashed.

## Controls and recording

G clamps through OFF, UP, ORDER and RANDOM. Compact native labels are OFF,
UP, ORD and RND. Its push retains stock behavior and does not change the arp
mode; this does not promise that the stock view remains open after a push.
Native menu screenshots and the strict pixel comparison were taken while the
keyboard settings view was active, before the push. `menu-after-push.png` is
an observation of the stock transition, not evidence of reopened settings.

The G overlay changes only pixels inside its 32×32 cell. Scale E, Root F and
Fold H were turned through native panel events, changed their native values
and rendered values, and left the arp mode unchanged. The stock encoders
accumulate/accelerate movement. Root includes its octave, so the test restores
its full MIDI value through the same native setter used by F; it does not
assume opposite accelerated detents cancel exactly. Tested values were Scale
CHRO (-1) to 4, Root 60 to 62, and Fold 0 to 1, followed by restored values.

For held G–E–C, the first eight generated notes were:

| Mode | MIDI notes |
|---|---|
| UP | 60,64,67,60,64,67,60,64 |
| ORDER | 67,64,60,67,64,60,67,64 |
| RANDOM | 64,64,60,60,60,64,67,60 |

RANDOM uses the frozen seed and original LCG from the proposal. It permits
repeats; no exact MicroFreak algorithm is claimed. Live recording sends the
realized notes through the original keyboard note APIs. Native sequencer
playback reproduces those eight pitches without re-collecting them, including
RANDOM. OFF emits no arp edges and passes physical G–E–C on/off calls through.
Track 2's C press/release also stays on the stock path.

EVIDENCE: recording retains the stock timing behavior. The first seven gates
were 3,552 samples both live and on playback. Early release shortened the last
live gate to 256 samples for UP/ORDER and 928 for RANDOM; native playback used
896 samples for that final recorded note. Playback onsets also follow stock
recording timing. This is not sample-exact preservation of every performed
edge. No patch to the recorder's duration encoding/quantization is claimed.

## Persistence and lifecycle

Recorded notes and duration bytes use the unmodified native project format.
Modes live in a separate 210-byte, versioned, two-bank companion record on the
same modeled card, bound to the native project slot and SHA-256 of the complete
serialized project. It stores 128 pattern modes for track 1, and no held keys,
RNG/cursor position, gate or running clock. Missing/corrupt/mismatched records
load OFF. Unknown existing files are preserved; injected inactive-bank partial
writes retain the previous valid bank.

The tested save uses the original Project save routine (`0x40043A30`), whose
successful return hook writes the companion. The checked diagnostic recall
reads the saved slot afresh (`0x4012F1D8`) and calls the original Project loader
(`0x40043F74`). Three independently restored firmware instances recovered
all 121,740 bytes of the recorded runtime pattern exactly, as well as the mode
vector. They do not read the stale snapshot project cache or old boot record.
The serializer cache accessor used after save is non-mutating `0x400F4A74`;
`0x400F4D08` is a builder accessor that clears the buffer's first word.

UNRESOLVED: the normal GUI project-load gesture is not associated with a
checked companion slot yet. A load outside the diagnostic transaction turns
the arp OFF and retains suppressed release ownership instead of carrying the
previous project's modes across. Source/native-core adapter tests cover that
guard, menu releases, track changes and FUNC release in the menu. The actual
GUI load gesture, automatic mode restoration through it, export/import,
Transfer, pattern copy/undo and companion cleanup need separate work. Save is
verified by the original native API and return hook, not by a GUI save gesture.

## Retained verification

| Check | Artifact under `out/runs/` | Result |
|---|---|---|
| Native instruction audit | `arp-integration-core-01/core.json` | 2,254 bytes audited; 2,120 state bytes |
| Source suite | `arp-integration-summary-01/source-tests-guard.log` | All 171 tests pass |
| Complete UP / ORDER / RANDOM | `arp-integration-{up,order,random}-final-01/arp.json` | G controls, neighbors, live recording, checked recall, replay, other-track checks; no worker errors/fault pages |
| Independent native reloads | `arp-integration-{up,order,random}-final-reload-01/storage.json` | Exact full runtime pattern and companion mode vector |
| OFF comparator | `arp-integration-off-01/arp.json` | Zero arp edges; stock keyboard calls preserved |
| UP repeat | `arp-integration-up-19`, `arp-integration-up-repeat-01` | Events, ticks, interrupts, gestures, menu events, all control bytes, native state, recorded pattern and card overlay exactly equal |
| Final guard parity | `arp-integration-summary-01/summary-final.json` | Final three mode captures have unchanged control/state/pattern/overlay bytes relative to passing pre-guard captures |
| Stock voice PCM | `arp-integration-audio-01/replay/render.json` | Eight intervals, 1.484 seconds, finite/nonzero/nonclipping, peak 0.3230743408, two renders byte-identical |
| SINE regression | `20261014T155648Z-test-5ebdd803/manifest.json` | `./labctl test sine --replay` passes |

The final captures used 805,838,000 worker instructions and 7,593 control
frames each; the OFF comparator used 572,939,125 and 4,946. Capture ticks stay
consecutive 32-sample blocks. Every generated recording pitch reaches the
actual DSP control frames as note × 256, within two modeled blocks. The UP
control SHA-256 is `6b5979b5ca7b9b6e5357d68dbba27dd6650dcfac1baae690f93fe03064fcfff7`.
The WAV SHA-256 is `b00be5f7b282ba780ba13fcb4416c38a6e96a8ffad30bc244e0d2942882c0e02`.

Failed bounded probes remain retained. They exposed the wrong boot/cache reload
oracle, missing-file status assumptions, paint-versus-layout invalidation,
stock encoder accumulation and an incorrect Root getter. One SINE run was
retained as a provenance failure because the capture harness changed during
it; subsequent frozen runs pass. Expected musical vectors were not rewritten.
The final source review retained unrelated changes and clean pinned checkouts.

## Reproduce

Run from `dt2-machine-lab`, with fresh output names:

```sh
arp_python='/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python'
./labctl doctor
"$arp_python" scripts/check-arp-modes.py out/runs/arp-core-new
"$arp_python" -B -m unittest discover -s tests -v
"$arp_python" scripts/capture-arp-modes.py out/runs/arp-up-new --record
"$arp_python" scripts/capture-arp-modes.py out/runs/arp-order-new --mode order --record
"$arp_python" scripts/capture-arp-modes.py out/runs/arp-random-new --mode random --record
"$arp_python" scripts/capture-arp-modes.py out/runs/arp-off-new --mode off
"$arp_python" scripts/check-arp-record-save.py out/runs/arp-up-new out/runs/arp-reload-new
"$arp_python" scripts/render-arp-up.py out/runs/arp-up-new out/runs/arp-audio-new
./labctl test sine --replay
```

Each panel run is bounded by 950M worker instructions and 600 seconds; native
file/project calls have separate explicit instruction limits. Private card
writes use overlays and the original card is opened read-only. Prepared CPU
MAIN SHA-256 remains `344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830`;
stock SHARC blob remains `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
DigiKit stays clean at `277760aad51b036a4756db051409d4d3b1eeccbc`.

Voice PCM comes from the existing native stock renderer, with track 1 isolated.
Final mixer/DAC output, subjective listening, real-time fitness, permanent RAM
placement and physical-device behavior have not been verified. Documentation
backfill after the frozen captures does not change their recorded code hashes.
