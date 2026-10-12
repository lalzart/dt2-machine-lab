# Capicola final twelve-second limit

2026-10-07. The user-selected prototype cap is **12 seconds of mono input at 48 kHz**: 576,000 frames. At advance 0.5, output duration is at most 1,152,000 frames (24 seconds). The shared-bank architecture, Q24 precision and audio tolerances are unchanged from the [ten-second experiment](CAPICOLA-TEN-SECONDS-RESULTS.md).

The maximum bank capacity is 576,004 keyframes: 6,912,048 bytes (6.59 MiB) per distinct sample. Count-before-load still allocates only the measured requirement. Temporary float input uses up to 2,304,000 bytes (2.20 MiB). Shared target readers remain 76 bytes each. The three-limb duration product stays below 2^29 throughout the expanded domain; no wider integer arithmetic is needed.

Host report: [capicola-12-host-01](../out/runs/capicola-12-host-01/report.json). Thirty long signal comparisons, 10,000 duration checks, wrong-pitch negative control, repeat/partition and one-second compatibility pass. Dense noise uses 258,451 keyframes / 3,101,412 bytes. The maximum valid input is tested at 576,000 frames and 576,001 is rejected. The configured full suite passes 59 tests, no skips.

All five target comparisons pass; worst sample error is 1.69874e-6, below the unchanged 1e-4 threshold. Repeat, bank guards, duration/cursor and invalidation checks pass.

Target report: [capicola-12-target-01](../out/runs/capicola-12-target-01/report.json). It exercises full twelve-second source playback at advance 2, repeated exactly, large dense-noise windows, and seeded endpoint windows approaching 24 seconds of output. Seeded windows are not continuous target playback histories. The target analyzer discrepancy and existing sparse end-of-sample behavior remain as documented previously.

The full SINE replay regression passes, including exact baseline/repeat, stock isolation and negative controls.

SINE regression: [20261007T130558Z-test-2cdd5240](../out/runs/20261007T130558Z-test-2cdd5240/manifest.json).

Reproduce with unique output directories:

```sh
python3 scripts/check-capicola-capacity.py out/runs/capicola-12-host-<unique>
python3 scripts/check-capicola-capacity-target.py out/runs/capicola-12-target-<unique>
# Use the configured Python for the complete source/native CPU suite:
python3 -B -m unittest discover -s tests -v
./labctl test sine --replay
```

The original ten-second proposal and reports remain historical evidence; its contract is archived in `machines/capicola/capacity-10-contract`. The active contract binds [revision 2](CAPICOLA-TWELVE-SECONDS.md). Its inherited phrase “up-to-20-second” in the target test paragraph is superseded by the explicit 1,152,000-frame limit and the actual 24-second endpoint tests.

Firmware memory ownership, hardware timing and sound-quality validation remain unverified. No firmware upload, commit or publication occurred.
