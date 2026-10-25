# Capicola quality correction — OS 1.16

The separate quality candidate restores content-adaptive splice lengths in the
existing STRETCH CAPI backend. It includes Plaits R3, native Arp and managed
Flex. This corrects the demonstrated source mismatch; physical smoothness and
the user's exact A/B remain unverified. Nothing was flashed or published.

Candidate:
`out/runs/capicola-quality-package-20261017-05/EXPERIMENTAL_ALL_FEATURES_CAPI_QUALITY_OS1.16.syx`

SYX SHA-256:
`d534ec33fa0a4fe89698709e7cb368432db6e7f9b1ae2ff02e4e96adce1fbc95`

DSP SHA-256:
`47afbda0e86dd2f01ee26961586319cacec253ff5bc0f08af78c87d8f02f60e7`

MAIN remains exactly
`0b962b8925fbcc68559bd3d23ac45467c531cd8b19399dfdaa918a9142019f98`.
The default build still reproduces the preceding complete SYX
`f5ac5b25cff226517cfbd730a44a3c7b08e71d57e4280977c4dfc2aff16e6a8c`.
No Arp, Flex, Plaits or CPU instruction bytes changed.

## Correction and boundaries

The original finite prototype capped every adaptive splice at 960 source
samples. Its references copied that rule. Real upstream Granule instead uses
local keyframe spans, with an available-audio limit and a 48-sample minimum.
Original-source comparisons showed 291 ms and about 430 ms source spans for
the tone/chord tests, versus the port's 20 ms ceiling at pitch1.

`lab/capicola_quality.py` generates a guarded C/H source overlay. It requires
the exact preserved STRETCH source SHA and four unambiguous anchors. Original
core, references, finite reader and live wrapper stay unchanged on disk.
Only the quality overlay injects admission/duration/phase policy. Both host
and target compile the same generated reader.

The quality policy preserves the local adaptive span in interior playback.
Finite/reverse playback gets an explicit front-rescue and remaining-region
limit. Loop fades are bounded by one region, with the existing 48-sample floor.
A 2^-22 phase-step floor prevents binary32 stalls in unusually long slow fades.
These finite/loop/numeric policies are explicit adaptations, not claims of
original moving-writer equivalence. No transient detector or stereo algorithm
is added. The source/licensing lineage remains in Capicola NOTICE and LICENSE.

## Accepted evidence

- Nine deterministic interior comparisons against the actual original
  `Granule.h`, with matching keys and no original fixed-boundary rescue.
  Host maximum PCM error is below 1.8e-7; packaged SHARC maximum is below
  2.4e-7. The old capped host and SHARC readers fail all six splicing cases.
  The three no-splice cases also match, making the comparison specific to
  the splice correction rather than a gain or source change.
- 600 host boundary/control cases across all four PLAY modes, trims, extremes
  and block partitions 1/7/32/127; ten forced slow-phase completion checks,
  stop/invalidation/invalid controls and live-transition checks pass.
- The actual packaged SHARC reader passes nine source comparisons with exact
  repeat, 120 boundary comparisons and ten phase-termination checks. Its
  prepared bank and initial seek are host fixtures; native code executes
  splice admission and full fade windows. This is separate from reset.
- Native frame integration passes sixteen distinct banks, trigger latching,
  mixed routing, actual status replies, unsupported fallback, exact stock OFF
  output and 56 parity blocks for other machines.
- Four 96-block final-master/DAC-facing-ring checks use a deterministic
  4096-frame mono source. Native OFF/ON controls match, output differs, and
  zeroing only the CAPI bank produces exact silence. Ring conversion error
  is zero. This proves routing, not perceptual superiority.
- Two independent 500-million-instruction DSP resets preserve linked code,
  constants and selector state and match exactly. CPU startup is inherited
  from the previous all-feature check through exact MAIN identity, not rerun
  or presented as a coupled CPU/SHARC cold boot.
- Repeat builds, protected sections, container authentication/framing, two
  decoders and the original bootstrap depacker pass. All 228 source tests,
  focused Ruff and whitespace checks pass. Stable-source SINE replay also
  passes on the final source freeze.

The final source freeze is `out/runs/capicola-quality-source-20261017-03`.
The machine-readable [verification](CAPICOLA-QUALITY-VERIFICATION.json) binds
reports, dependency/source identities, package hashes and remaining gaps.
Every interrupted/development attempt remains under ignored `out/runs`.
The initial target observer needed its pinned imports initialized first;
that observer defect was corrected before the accepted standard CLI run.

## Resource measurements

The CPU image and lane/bank allocations are unchanged. DSP code grows by
1,620 bytes; lane state remains 9,536 bytes and the existing total reservation
remains 8 MiB. The integer guard rejection and inline phase clamp preserve all
nine host comparison WAVs exactly while removing avoidable guard-call work.

Paired direct-reader fixtures retire about 1.64% more emulator instructions
in the no-splice windows, and about 40.3–43.7% more in the windows spanning a
full long fade. The latter compares two sustained readers against the old
reader that finished its short fade much earlier. These are selected reader
windows, not whole-block averages, physical DSP cycles or utilization.
Worst-case physical sixteen-track headroom remains unmeasured.

## Reproduction

Scripts select the configured Python 3.12 runtime. Use fresh output names.

```sh
./labctl doctor
python3 scripts/check-capicola-quality.py out/runs/<host>
python3 scripts/build-cpu-extension.py out/runs/<package> --all-features \
  --capicola-quality --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-quality-native.py out/runs/<target> \
  --package out/runs/<package> \
  --baseline-package out/runs/all-features-package-20261017-03
python3 scripts/check-capicola-toggle-native.py out/runs/<routing> \
  --package out/runs/<package>
python3 scripts/check-capicola-toggle-output.py out/runs/<output> \
  --package out/runs/<package> --blocks 96 --sample-frames 4096
python3 scripts/check-combined-firmware.py out/runs/<package> out/runs/<startup> \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<package> \
  --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

Source suite: configured Python `-m unittest discover -s tests -q`.
Omitting `--capicola-quality` must reproduce the preceding all-feature package.
The proposal and approved implementation detail fingerprints remain unchanged
in `machines/capicola/quality-contract/implementation-contract.json`.

## Listening and device A/B

Equal-gain, three-second synthetic old/upstream/quality clips are in
`out/runs/capicola-quality-host-20261017-03`. They are host renders, separate
from the shorter packaged native fade-window and final-output checks.

For a separately authorized device test, use an eligible mono 48 kHz sample
of at most twelve seconds. CAPI still starts OFF. Enable encoder C on STRETCH,
wait for READY where applicable, then retrigger and confirm STRETCH CAPI.
Retrigger after switching OFF and confirm STRETCH STOCK. Changing the switch
while a note plays does not change that note's latched backend; comparing
without retrigger can compare the same engine twice. Use identical sample,
TUNE, BARS, PLAY, trim, envelope/effects, tempo and output gain for both passes.
An unsupported stereo source or an unready trigger still falls back to stock.

Listening improvement, physical input/output, physical cache/DDR ownership,
coupled startup/install and real-time deadlines remain open. Existing mono
CAPI capacity and Plaits/Arp track-one and managed-Flex limits remain.
