# STRETCH R3 gap register

- Full native phase/elapsed/stretch-progress and UI/playhead reconciliation. Only native active completion is now written by the replacement renderer; +0x190 is loop start, +0x1b0 is phase, and +0x1c0 is elapsed output count.
- Physical DSP/DDR timing and effect headroom. Simultaneous live edits peak at 4.46 million emulated instructions/block; the stress-only harness cap is eight million, not a hardware budget.
- Dense/full twelve-second native workload coverage, complete L2 runtime ownership, project lifecycle and installable packaging.
- Stereo, subjective comparison and physical output. Modeled master/ring conversion is checked; it is not a full effects/mix oracle or hardware proof. Pinned native execution negates both ring channels; separate stock/pre-negation audits establish this local convention only.

The transition policy is explicit Capicola behavior, not stock grain parity. Reservation remains 8 MiB; sixteen banks are supported when the measured storage fits. Original reader, analyzer and R2 cache remain unchanged.
