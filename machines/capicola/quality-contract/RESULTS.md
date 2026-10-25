# Quality profile results

Status: prototype; source, host and direct packaged SHARC checks passed in the
preliminary immutable runs. Final accepted runs and exact hashes are recorded
in `docs/CAPICOLA-QUALITY-RESULTS.md` and `docs/CAPICOLA-QUALITY-VERIFICATION.json`.
Those result documents are outside compiled source so later result backfill
cannot invalidate a frozen DSP build.

Approved proposal fingerprint and user approval are in implementation-contract.json.
Readiness validation passed before DSP edits. Sources are preserved; a guarded
source overlay changes admission/duration/phase policy only. No other control,
voice state or storage capacity changes.

Preliminary measurements: nine original-Granule host cases at max1.8e-7;
600 host boundary/control cases across partitions1/7/32/127; ten phase-progress
cases; 228 source tests. Direct packaged SHARC checks pass nine original-source
comparisons, exact repeat, 120 boundary cases and ten phase-progress cases.
Sixteen-bank routing, stock OFF exactness and 56 other-machine parity blocks
pass. These are modeled source/host/target observations, not listening or
physical timing. The first target invocation failed due import ordering in the
new observer; the DSP image was unchanged, and the observer is corrected.

Reproduce using the commands and paths in the final result documents. Every
preliminary/failing run remains under ignored out/runs. No flash, commit, push
or publication is authorized or performed.

## Evidence ladder

Source, host structural/signal and target build: preliminary checks passed; final
records linked above. Real-time, connected device, listening and production
integration: deferred. Numeric parity is not an audible-quality observation.
