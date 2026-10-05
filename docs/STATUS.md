# Current status

2026-10-05: the local machine lab is initialized with source, repeat commands
and engineering notes. No remote is configured; generated artifacts stay local.

Implemented: pinned dependency checks, guarded CPU/DSP image construction,
private-fixture import, offline SINE replay, regression checks, per-block
instruction/host-time reporting, and separate run manifests/logs.

Validation passed on 2026-10-05:

- Eight source-only harness tests, plus lint and formatting checks.
- CPU and DSP builds match the original SINE image hashes exactly.
- The migrated one-second render matches the original PCM SHA-256 exactly:
  `2a38b64c83b1636b9f1a3793f6e78c71275d0a64ca2473c2e6b20bc183673eae`.
- Measured 440.000005 Hz, peak 0.125, maximum analytic error `9.45e-6`.
- Exact repeat, stock-machine isolation, controlled clone parity, disabled-hook
  negative control, retrigger, switch-away clearing and silent return all pass.
- A separate fresh-directory import and CPU/DSP build reproduce both image
  hashes. This relocation check did not repeat the audio suite.

The full replay report is retained in
[`out/runs/20261005T040725Z-test-108cd765/manifest.json`](../out/runs/20261005T040725Z-test-108cd765/manifest.json),
with its audio, raw PCM, profiles and logs. The independent path check is
recorded in [`out/relocation-check.json`](../out/relocation-check.json).
These are local, ignored artifacts; the portable expected hashes are in
[`tests/fixtures/sine-1.16.json`](../tests/fixtures/sine-1.16.json).

The successful run resolved firmware symbols through a newly generated lab
database. The first migration attempt exposed an old default database path;
that failure report remains in `out/runs/` and the adapter now uses a cache
keyed by firmware hash and DigiKit revision.

The [SINE controls experiment](SINE-CONTROLS.md) now connects pitch, duration
and level. Stored locks reach the DSP in step previews, and an unlocked step
restores the base values. PLAY startup emits the locked values; continuous
pattern traversal remains unverified.

The [Plaits VA experiment](PLAITS-VA.md) now runs a C99 translation of the
original VA2 engine on the host and as compiled SHARC instructions. Host audio
matches upstream exactly; short target comparisons pass, with a documented
long-render numeric difference. Prepared firmware replay produces the new
audio and recovers the existing pitch/length/level locks. Repeat, stock-hook
compatibility and disabled-hook checks pass. New macro panel controls and
locks are unverified. A named `P-VA` CPU candidate is built but not UI-tested;
the actual replay reuses the SINE type-7 CPU capture.

The optional [Plaits resource optimization](PLAITS-OPTIMIZATION.md) now skips
unused AUX and shares renders only for matching complete lane states. MAIN
audio remains bit-identical in the host and SHARC comparisons. MAIN-only
uses 50.82% fewer standalone emulator instructions; both changes reduce the
whole 801-frame firmware replay by 10.73%, adding a 1,036-byte cache. These
are instruction counts, not hardware load percentages. The reference remains
the default. Divergent-lane state tests, exact repeat, stock-hook compatibility,
negative controls and the SINE regression pass.

The [three-model Plaits prototype](PLAITS-TRIO.md) now selects VA, two-operator
FM and analog bass drum. All three host ports match upstream exactly in the
bounded vectors/corners; the short compiled SHARC comparisons pass. Real CPU
MODEL locks recall VA/FM/BD/VA, with a track-1/type-7 CPU shim bypassing stock
smoothing for the discrete selector. The prepared firmware replay passes exact
repeat, VA recall, stock-hook parity and disabled-hook checks. Direct adapter
checks cover latching, independent lanes, retrigger and silent return. The old
VA image remains byte-identical. Dedicated macro labels/ranges and full Plaits
voice behavior remain unfinished; this is not all 24 models. The final report
is `out/runs/trio-final-01/report.json`; the refreshed SINE regression
`out/runs/20261005T082651Z-test-a0ec5c52/manifest.json` also passes.

Buffered GUI audition is now available through `scripts/listen-plaits-trio.py`;
see [the listening instructions](PLAITS-TRIO.md#buffered-listening-in-the-emulator-window).
VA/FM/BD previews render real SHARC voice PCM and play completed WAVs on the
Mac. The native live source matches the checked replay, but renders around 2%
of real time, so uninterrupted real-time streaming remains open.

Clean fixture generation, sample-free startup, final output, real-time audio, and
physical CPU/DSP timing remain open.

The [six-voice Plaits bank](PLAITS-BANK.md) adds waveshaping/wavefolding,
harmonic additive synthesis and granular formants as MODEL 3/4/5. All six host
engines match their upstream MAIN references exactly in the bounded vectors
and corners; compiled SHARC comparisons pass. Old trio host/target PCM and its
rebuilt image remain exact. Real CPU locks recall VA/WS/ADD/GRAIN/WS/VA, and the
811-frame replay passes exact repeat, recall, stock parity and disabled-hook
checks. The capture now verifies each actual trigger selector while setting
locks, after catching a range-dependent encoder scaling mismatch. The complete
report is `out/runs/bank-final-01/report.json`, and the SINE regression in
`out/runs/20261005T095057Z-test-5569b436/manifest.json` passes. This adds engine
choices; the existing interactive-emulator and macro-interface limits remain.

Read [INTEGRATION](INTEGRATION.md) before changing the firmware hook and
[DEVELOPMENT](DEVELOPMENT.md) for the next steps. Elekloader is recorded in
[ECOSYSTEM](ECOSYSTEM.md) as an optional future integration.
