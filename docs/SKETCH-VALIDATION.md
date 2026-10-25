# Sketch combined DSP validation — OS 1.16

Validate the existing opt-in ARM/FREEZE profile, without changing firmware
emitters, DSP implementation, memory policy or hardware. The
[BUF contract](../BUF-WORKFLOW-CONTRACT.md) and
[Sketch FREEZE implementation](SKETCH-FREEZE.md) remain authoritative.

## Bounded check

`scripts/check-sketch-dsp.py` has three modes:

```sh
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/sketch-preflight-FRESH --preflight
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/sketch-coupled-FRESH
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/sketch-audio-FRESH --replay out/runs/sketch-coupled-FRESH
```

Set `LAB_PYTHON` to the interpreter in `.local/config.json`. Output directories
must be new and under ignored `out/runs`. Preflight uses preserved native BUF
pages and performs zero recordings. Replay also performs zero recordings.

The coupled mode permits two captures. It initializes empty BUF 1 through real
Sketch ARM, cancels before START, then selects the empty BUF on T1/T5 using the
stock browser. A native pattern plays; FUNC+SONG records A into BUF 1 while
recorder DEST remains NORMAL. Held SONG freezes A. The ordinary selector assigns
the snapshot to T6, and FUNC+SONG records distinct B into the shared BUF.
Publication and FREEZE must preserve every existing assignment. No host commit,
recording seed, diagnostic retirement or retirement certificate is supplied.

The live DSP receives actual CPU control packets and native LP0 publications.
The existing prepared SPI/SEC engine executes native blocks and returns its real
replies. The harness checks finite/nonzero active ONESHOT voices, shared/frozen
selectors, old-reader pointers across publication, fresh generation IDs and
native completion. It saves both page histories, input PCM, the last complete
wire frame, native traces, screenshots and completion-to-publication latency.

The independent playback mode loads A/B WAV references through the original
stock CPU file loader into fresh stock DSPs. It compares voice PCM exactly for
A/current+frozen, retained A during B publication, current B+frozen A and late
frozen A. It repeats from fresh state, and requires a deliberately incorrect
frozen-B reference to differ. No live SEC state is cloned and no new recording
is needed to rerun the comparator.

## Runtime and evidence boundary

Reuse fingerprinted local conditional-MODIFY and exact-site register-FEXT
support with the existing resume ABI; pinned dependencies stay unchanged.
The 28-case FEXT comparator runs before each mode. The live DSP blob is built
from the existing retirement implementation, without source changes.

Recorder input, SSI cadence, LP0 callback delivery and SEC reset contents are
explicit emulator models. Live native DSP voice buffers and fresh-state
stock-file playback are separate evidence. Neither establishes final mixed/DAC
output, real time, listening, physical input, target memory placement, startup
or hardware readiness. Preview, persistence, other capture lengths and broader
machine/retirement compatibility remain outside this validation.

## Results — 2026-10-23 JST

Artifacts: `out/runs/sketch-validation-20261023-01/`.

- Preflight and final page replay each perform zero recordings. The coupled run
  performs exactly two captures and one FREEZE, with 21 native checks, 34,249
  native DSP blocks and zero CPU fault pages. An initialization ARM is canceled
  before START; both empty BUF assignments are made through the native browser.
- A contains 112,960 stereo frames (`0x7ffb0001`); B contains 112,928 frames
  (`0x7ffb0002`). Both native LP0 payloads exactly match modeled recorder input.
  Recorder DEST stays NORMAL throughout, with no destination writes.
- FREEZE returns slot 312. T1/T5 remain on logical slot 300 and T6 is deliberately
  selected onto the snapshot using the native browser. Capture/FREEZE preserve
  all existing assignments. After B publication, both shared tracks have
  nonzero finite voice PCM pointing into B's allocation; T6 has nonzero finite
  PCM pointing into frozen A. Four active old voice lanes (0, 1, 8, 9) retain
  their pointers across publication. This does not qualify general retirement
  without a frozen root or other playback machines.
- Fresh stock CPU file loads and stock DSP voice comparisons pass exactly for
  all four phases: 12 A/frozen-A blocks, 12 retained-A blocks across B publication,
  48 B/frozen-A blocks and 24 late-frozen-A blocks. All 96 blocks repeat exactly
  from fresh state. Deliberately routing frozen B instead of frozen A changes
  the output, confirming that the comparator distinguishes the two sources.
- The existing DSP blob is byte-identical to the previous accepted BUF build.
  All inherited firmware emitters, DSP code, tests, dependencies and other source
  files are preserved. Only validation helpers and documentation are added.
  138 scoped BUF tests and Ruff pass. SINE passes at
  `out/runs/20261023T002258Z-test-0c68afe3/manifest.json`, with source hashes equal
  to the completed coupled and audio replay runs.

| Take | Capture completion to publication, modeled | Following bar's first T1 trigger | Publication frame |
| --- | ---: | ---: | ---: |
| A | 197.333 ms | 18,450 | 18,710 |
| B | 196.000 ms | 32,475 | 32,732 |

Automatic publication works, but the first following-bar trigger still occurs
before the new take is available. Existing A readers continue during B's
publication; later triggers use B. This is the measured prepared-emulator
schedule, not physical-device latency or a seamless downbeat-switch guarantee.

The native playback check and controlled stock-file comparison are separate
observations. No final mixed/DAC output, real-time, listening or hardware result
is claimed. Target memory placement and startup/package validation are next;
no installable firmware, hardware transfer, commit, push or publication is made.

An initial launch omitted the preflight option and was stopped during setup
with zero STARTs. The first saved-page preflight then correctly rejected an
incomplete zero-length snapshot header. Selecting the complete positive-length
header fixes that fixture boundary; `preflight-03` passes. Earlier outputs stay
failed, and neither case consumed a recording. No stress/reuse loop was run.

See the [verification index](../out/runs/sketch-validation-20261023-01/verification.json),
[native screenshot gallery](../out/runs/sketch-validation-20261023-01/screenshots.html),
[coupled report](../out/runs/sketch-validation-20261023-01/coupled-01/report.json)
and [stock-file PCM report](../out/runs/sketch-validation-20261023-01/audio-01/audio/report.json).
