# Selection preparation results

Status: validated native emulator slice, 2026-10-08.

See docs/CAPICOLA-SELECTION-PREP-RESULTS.md for reproduction, exact images, native status ABI and limitations. Positive wire evidence is out/runs/capicola-selection-wire-03/report.json; compatibility and startup evidence is out/runs/capicola-selection-resident-01/report.json. SINE replay passes in out/runs/20261008T054746Z-test-5fe6f828/manifest.json. Sixty-three source tests pass. These result notes were updated after the frozen-source checks; DSP and harness code remain as tested.

## Evidence ladder

Source: optional adapter and guarded layout exist; prior builds are byte-identical. Host structural: bounds and layout checks pass. Host signal: existing reference used without tolerance changes. Target build and native execution: exact repeated candidate, trigger-free preparation with unchanged previous voice pointers, exact keys, first-trigger full audio, progress, twelve rejection cases, active and mid-prep cancellation, page invalidation and reload pass. Maximum audio error 1.4901161193847656e-8, RMS 1.0851376394619265e-9. Stock/Plaits parity passes 184 frame comparisons and fresh startup repeats exactly twice. Real-time, physical device, listening and production integration remain deferred. Native status is not yet an on-device display.
