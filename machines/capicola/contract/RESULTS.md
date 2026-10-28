# Capicola prototype results

See [the result report](../../../docs/history/capicola/CAPICOLA-PROTOTYPE-RESULTS.md) for commands, metrics and proof limits.

## Evidence ladder

- Research/proposal: source inspected, proposal and readiness contract frozen before DSP edits; readiness validator passed.
- Source: AGPL-attributed bounded mono C99 core and original-header C++ oracle implemented.
- Host structural: 46 tests pass under the configured runtime, with no skips. Lint passes.
- Host signal: 90 matrix cases and three decimal-rate cases have exact reference PCM; accepted fixtures have exact keyframes. State, peak, silence and overflow checks pass. One extreme-setting pitch criterion has no complete unspliced cycle and remains incomplete. Overall host report is partial and exits 2.
- Target: numeric ABI probe compiles, links and executes, but observes four-byte double despite the 64-bit flag. No full Capicola audio target build/execution is claimed. Target probe exits 2 for the verified blocker.
- Existing baseline: SINE replay passes in out/runs/20261007T115836Z-test-38e8761d.
- Real-time/device/listening/production: no evidence and no claim.

Final host report: out/runs/capicola-host-final-01/report.json.
Target probe: out/runs/capicola-target-final-01/report.json.
Host precision negative: out/runs/capicola-narrowing-negative-01/report.json.

Proposal fingerprint and experiment tolerances remain unchanged. Result-only documents were updated after the final source/replay checks; no DSP code changed after those checks.
