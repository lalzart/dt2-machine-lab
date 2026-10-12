# Native worker results

## Evidence ladder

Host preparation passed 70 exact-bank comparisons including twelve-second inputs in out/runs/capicola-prep-host-01. Native target-02 reproduced two-Q24-unit noise timestamp drift from approximate division. Target-03, with explicit nearest-even ratio rounding for int16 derivatives, passes all ten cases with exact keys and maximum audio error 1.20e-7. The preserved general float analyzer is unchanged; this closes the tested int16 worker path only.

Final lifecycle, canary, repeat, combined-hook and regression reports are recorded in docs/CAPICOLA-NATIVE-PREP-RESULTS.md after source freezes. The combined entry is harness scheduled; native scheduler/allocator ownership is not established. No device or production claim.

Final reports: capicola-prep-host-02, capicola-prep-target-04 and capicola-native-hook-02 all pass. All 59 unit tests and SINE replay 20261008T000344Z-test-053cfd0f pass. Detailed results are in the linked document. After the runs, experiment recipe text was corrected to match the executed worker fixtures, and result notes were completed; executable source and tolerances did not change.
