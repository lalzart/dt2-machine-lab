# Capicola source playback — OS1.16

Built a new source-oriented sample reader and grain-handoff implementation, with fidelity before instruction savings. The local experimental all-feature package includes Plaits R3, CAPI OFF/ON, native Arp and managed Flex. Hardware sound and deadline margin are unverified; nothing was flashed, committed, pushed or published.

Candidate: `out/runs/capicola-source-package-20261017-03/EXPERIMENTAL_ALL_FEATURES_CAPI_SOURCE_OS1.16.syx`

SYX SHA256: `397e2288ab8f972487e980c44705e372674213147b1289dac005a8c267dd64ec`
DSP SHA256: `5c48264d391070718b1f1120fc170cb9d3aafd997824d77c30bfab3ff5319945`
MAIN SHA256: `0b962b8925fbcc68559bd3d23ac45467c531cd8b19399dfdaa918a9142019f98` — byte-identical to the preceding all-feature OS.

## What changed

The adaptive reader follows original Granule splice equations, separate pitch/time cursors and sparse Hermite reconstruction, with no 20 ms ceiling or one-region fade ceiling. The selected sample becomes a virtual periodic keyframe medium. Both pitch heads can cross its boundaries without disappearing into zero or receiving independent 48-sample gain dips. Finite transport stops by the ideal grid; native envelopes own note gain.

Two grains hand off over the source module's 960-output-sample default fade. Retiring grains keep their previous rates and continue until their handoff finishes. Fast geometry changes queue rather than overwriting an audible retiring grain. Init, invalid controls and generation invalidation stop stale readers. CAPI remains trigger-latched; no mid-note switch back to stock.

Native planar stereo now works.32 channel banks support 16 distinct stereo samples inside the same 8 MiB reservation. Mono channels still share one bank. Both stereo banks must be ready before either channel enters CAPI; READY also requires both. A real stereo source reset silences both CAPI channels. Descriptor cache grows 1,436 to 2,844 bytes within unused reserved state; 276-byte lane ABI and sample arena stay unchanged. DSP code is101,780bytes,8,276bytes above the previous quality candidate. No performance shortcut was added.

The C99 source port is attributed to Matthew Nielsen / Heavylight Industries, Capicola120b0b843c18bda373d96eb79d49805545f61556, AGPL-3.0-only. Original sources, old default and previous quality experiments are preserved. The C99 target needs Q24 positions because its double is binary32. The virtual file medium and queued sample-host edits are explicit adaptations in the approved [proposal](CAPICOLA-SOURCE-PLAYBACK.md); this is not a claim that the Alchemy CV/live-input/feedback module or the unavailable Reddit Digitakt port was reproduced. The source detector punches in LIVE_EFFECT, not ordinary sample PLAYBACK, so transient auto-punching is not inserted into this file machine.

## Accepted final checks

All final runs bind the same 443-file freeze and 37 separately hashed test files. Ready source contract was validated before DSP edits and stereo addendum edits; final results live here to preserve that fingerprint.

- 504 complete-start comparisons against actual unmodified upstream Analyzer/SparseLine/Granule over the materialized periodic medium: max error1.19e-07. Forward/reverse, trims, loop/finite, pitch 0.5/1/2, advance 0.425/1/2, seven signals, exact repeats and block partitions 1/7/32/127. Extreme controls, silence, impulses, NaN, generation changes, queued edits and stop pass.
- Actual KeyframeRecorder::Punch/ReadPair handoff comparison: max1.63e-06, RMS1.77e-07. Immutable sample Spawn placement is the explicit host seam.
- 36 packaged SHARC full-start/wrap comparisons at pitch 0.5/1/2: max2.38e-07; three complete reverse/trim/retrigger handoffs match host, with exact target repeat and state/output guards. Bank and initial state are host fixtures; the separate native frame tests exercise actual trigger/start/control calls.
- Actual LP0 stereo file loading, deinterleaving and native headers pass; 16 tracks/32 distinct channel banks ready in 1,118 blocks. Every first native channel render matches its host reader using actual voice pointers/controls: max8.94e-08. One-bank-ready stereo triggers remain stock; real LP0 reset silences both without mid-note stock takeover.
- Native OFF/ON/routing passes 16 tracks, mixed selection, latching/status, exact stock OFF, unsupported metadata and 56 other-machine parity blocks. Source comparator history is matched explicitly on OFF→ON triggers because an always-ON comparator otherwise retains grains absent from the bypassed track. Audio tolerances were not relaxed.
- Four 96-block final-master/DAC-ring cases pass. OFF/ON native controls match, outputs differ, muting CAPI bank values alone gives exact silence, ring conversion error 0. This is routing evidence, not a listening verdict.
- Repeated build/container authentication, actual device bootstrap depacker, protected sections, independent DSP reset twice at 500 million instructions and default-package exact reproduction pass. CPU reset is inherited through exact MAIN identity, not rerun or presented as coupled startup.
- 230 source tests, focused Ruff, whitespace and stable-source SINE replay pass. Source freeze: `out/runs/capicola-source-freeze-20261017-02`. [Machine-readable results](CAPICOLA-SOURCE-VERIFICATION.json) bind every report/hash.

## Performance and remaining limits

No grain/fade quality change was accepted to fit the former 4M-instruction emulator guard. That harness allowance is now explicitly 64M for this runtime; the default remains 4M. The native routing fixture peaks at5,762,844retired emulator instructions/block, and the32-channel stereo fixture at5,595,753. These are selected fixtures, not physical DSP cycles/utilization or a worst-case deadline guarantee. Hardware headroom needs a separate pass.

Input remains mono or stereo 48 kHz, at most 12 seconds/channel; finite output at most 128 seconds.32 prepared channel banks share 8 MiB, so measured key density/memory pressure can still prevent admission. Unsupported or unready sources use stock at trigger. Track-one Plaits/Arp and managed Flex limits remain. Physical A/B on the user's sample, cache/DDR ownership, coupled startup and real-time deadlines remain open. Nothing here substitutes source parity for audible success.

## Reproduce

Use configured Python 3.12 (scripts re-exec it) and fresh ignored output paths:

```sh
./labctl doctor
python3 scripts/check-capicola-source.py out/runs/<host>
python3 scripts/build-cpu-extension.py out/runs/<package> --all-features --capicola-source --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-source-native.py out/runs/<target> --package out/runs/<package>
python3 scripts/check-capicola-source-stereo.py out/runs/<stereo> --package out/runs/<package>
python3 scripts/check-capicola-toggle-native.py out/runs/<routing> --package out/runs/<package>
python3 scripts/check-capicola-toggle-output.py out/runs/<output> --package out/runs/<package> --blocks 96 --sample-frames 4096
python3 scripts/check-combined-firmware.py out/runs/<package> out/runs/<startup> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<package> --elekloader-reference out/references/elekloader-upload-audit
./labctl test sine --replay
```

Omit both CAPI runtime options to reproduce original all-feature default. `--capicola-quality` retains the previous candidate. Core files: `machines/capicola/source-playback.c`, `source-live.c`, `source-selection.h`; guarded generation in `lab/capicola_source.py`.

## Audition and activation

Three-second equal-gain host WAVs in `out/runs/capicola-source-host-20261017-03`: `audition-chord-source.wav`, `audition-chord-original.wav`, `audition-chord-previous-quality.wav`, plus percussion equivalents. Source/original max error below 2.1e-7; preceding quality differs on these fixtures. They are synthetic host comparisons, not physical recordings or an independent listening verdict.

CAPI starts OFF. Enable encoder C on STRETCH, wait for READY, retrigger and confirm STRETCH CAPI. Switching while a note plays retains its backend until another trigger. Compare OFF after retrigger with STRETCH STOCK using the same sample, trim, tuning, BARS/PLAY, envelopes/effects and gain. Device transfer needs a separate user request.

## Retained development failures

Initial diagnostic import needed the scripts path. Early source-bundle readiness caught missing required headings and ambiguous wording before DSP edits. Initial 230-test lint formatting was corrected before final freeze. The first routing run exceeded4M emulator allowance; the next exposed mismatched prior-grain history in the always-ON comparator. Explicit allowance/history fixes resolved the test without changing source DSP math or loosening PCM tolerances. All preliminary packages/runs remain under ignored out/runs; only package03 and the final report set above are canonical.
