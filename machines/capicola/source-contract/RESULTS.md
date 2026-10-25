# Source playback results

## Commands and checks

Final accepted commands, reports and artifact identities are backfilled in docs/CAPICOLA-SOURCE-RESULTS.md and docs/CAPICOLA-SOURCE-VERIFICATION.json. This pointer is frozen before the final source validation so bookkeeping cannot change the validated source set.

## Metrics and artifacts

Host complete-start source oracle, actual KeyframeRecorder pair, packaged native full playback and grain handoffs, actual stereo LP0 loading and32-channel voices, frame routing, final-ring causal mute, package/reset/depacker, source suite and SINE are separate checks. The final verification record determines pass/fail.

## Deviations and corrections

Virtual immutable source medium and Q24 timing are explicit host adaptations. Stereo uses original independent channel grains. Previous failed runs retained:4M emulator block allowance insufficient; always-ON comparator had previous grains absent from OFF-to-ON track. Comparator initial history is now matched explicitly before native trigger, without changing tolerances or firmware.

## Evidence ladder

Source, host signal and target evidence require their named reports. No physical listening, coupled startup, cache ownership, or real-time deadline claim. Source algorithm has priority over instruction savings.
