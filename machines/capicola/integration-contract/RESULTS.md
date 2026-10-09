# Integration results

## Evidence ladder

Combined OS 1.16 voice-hook checks pass in `out/runs/capicola-integration-02/report.json`. Three prepared-bank control cases match the host reader (maximum output error 2.24e-8); 100 actual stock voice-entry blocks match direct compiled calls exactly. All six Plaits models match the previous integration on both lanes. Eight audible stock fallback blocks match, eleven malformed handoffs silence safely, and the injected type-8 frame replay completes 23 frames with no bank and no interpreter faults. MAIN is byte-identical to the existing Plaits R3/Flex/menu package; DSP rebuilds exactly.

The actual-entry harness uses caller stack 0x200dc000, separate from the wrapper private stack 0x200dff00. The earlier integration-01 mismatch was caused by overlapping test stacks; no DSP core change or relaxed tolerance was needed.

See docs/CAPICOLA-INTEGRATION-R1-RESULTS.md for final regression results and reproduction. Prepared banks are host analyzed. No native loader, CPU selector, installable package, physical timing or final-output claim.
