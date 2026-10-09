# STRETCH R3 results

Final source/emulator gates pass. See [R3 results](../../../docs/CAPICOLA-STRETCH-R3-RESULTS.md) for reproductions and retained artifacts.

Host: 576 live-control comparisons, max 1.92e-7 and RMS 5.66e-8; rapid queues, exact partitioning, invalid-state guards and the latched-control negative comparator pass. Unchanged-control PCM is exact against the preserved C reader.

Native: sixteen banks/thirty-two lanes, forty-eight mode/region cases, simultaneous sixteen-track edits, continuous rates, completion/retrigger, selective reload, pressure fallback and stock/Plaits parity pass. Live error max 1.38e-7, RMS 5.70e-8. Sixteen nonzero modeled master/ring blocks match the independently audited native conversion at zero LSB error. Exact R1/R2/MAIN images remain preserved. Final source freshness passes.

All 138 units and the source-equivalent SINE regression pass. Stress instruction counts reach 4,459,587/block; they do not establish real-time hardware load. Hardware, listening and production evidence are deferred.

## Evidence ladder

Source, host structural/signal and compiled native emulator gates pass. Modeled master/ring output is observed separately. Real-time, connected-device, listening and production-integration gates remain deferred.
