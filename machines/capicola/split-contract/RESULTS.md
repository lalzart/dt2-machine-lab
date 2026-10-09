# Split-time experiment results

## Evidence ladder

The preserved double core and original-header oracle are unchanged. The split implementation passes the host signal matrix and exact duration/cursor checks. A standalone SHARC reader passes six audio comparisons, repeat and buffer integrity checks. The target analyzer has a small two-tone arithmetic mismatch, retained as an incomplete gate. Overall target experiment remains partial.

Full results and final reproduction paths: [split-time results](../../../docs/CAPICOLA-SPLIT-TIME-RESULTS.md). Earlier diagnostic evidence: `out/runs/capicola-split-host-03/report.json` and `out/runs/capicola-split-target-04/report.json`. Final runs add boundary-rate, target duration/cursor, invalid-control and stop assertions.

No firmware integration, listening verdict or physical timing claim.
