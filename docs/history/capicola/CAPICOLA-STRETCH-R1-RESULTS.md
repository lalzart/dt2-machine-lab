# Capicola STRETCH R1 results

2026-10-08. OS1.16 local prototype. Capicola now runs behind the **existing
STRETCH machine, ID 2**, using its native renderer destination and controls.
The original CPU interface remains intact. No separate CAPICOLA machine,
RATE overlay or preparation-caption overlay is included in this candidate.

The [frozen R1 proposal](../../CAPICOLA-STRETCH-R1.md) and
[implementation bundle](../../../machines/capicola/stretch-contract) describe the
equations, allowed adaptations and acceptance thresholds. This extends the
existing Capicola-derived finite sample reader; it does not claim the source
module's complete live circular-buffer/transient behavior or better sound.

## What runs

TUNE follows the native positive pitch, including 1/32..32. BARS and tempo
drive the independent timing cursor. All four PLAY modes work: reverse,
reverse loop, forward loop and forward. Native integer STRT/LEN bounds select
the region; mode and region changes take effect at the next trigger in R1.
Pitch and timing changes update a playing reader without resetting its cursor
or splice. One-shots can last up to 128 seconds of output, while the **input
sample remains limited to 12 seconds**. Loop cursors/counters stay bounded.

Preparation is automatic, in two bounded passes after stock audio blocks.
The adapter resolves eligible mono 48 kHz samples directly from the native
slot table. It retains one referenced source, otherwise admits the lowest
eligible track. Thirty-two independent readers cover the sixteen tracks' two
native lanes, sharing that source's immutable bank. Other distinct samples,
stereo, unsupported regions/rates and unready triggers use stock STRETCH.
Preparation completing during a stock note does not replace that note.

LP0 page/header hooks invalidate publication before PCM rewrites. An invalidated
custom note becomes silent until a new trigger; reloading prepares a new
generation. Native envelope, level and effects code remains in the surrounding
stock path. Full final-mix and native voice-position/UI reconciliation remain
separate integration work.

## Checks and artifacts

- [Host report](../../../out/runs/capicola-stretch-host-03/report.json): **2,160**
  independent numerical comparisons across six signals, four PLAY modes,
  five pitches, six timing rates and three regions. Maximum error
  `1.79e-6`, worst RMS `1.61e-7`, against frozen limits `1e-4` / `1e-5`.
  Twenty-five old forward-reader cases retain exactly identical PCM.
  Block partitions, tiny loops, lagging negative cursors, live changes,
  exact duration, generation invalidation, storage guards and wrong-pitch /
  one-frame-shift negative comparators pass.
- [Final native report](../../../out/runs/capicola-stretch-frozen-01/source/out/runs/native/report.json):
  **240** original-STRETCH control cases, four additional 2,048-sample PLAY
  comparisons, 32 continuous-control blocks and all sixteen tracks / thirty-two
  readers pass. Matrix maximum error is `2.92e-7`; the longer reverse-loop
  case reaches `4.22e-7`, within the same frozen tolerances. Stock fallback,
  no mid-note takeover, reload invalidation, independent shared-track controls,
  uncached/stereo fallback and switch-away clearing pass. Sixty enclosing-block
  stock/Plaits comparisons and four prior image hashes remain exact.
- The configured Python 3.12 source suite passes **117 tests**, without skips.
  Ruff checks/formatting and `git diff --check` pass for the modified sources.
  [SINE replay passes](../../../out/runs/capicola-stretch-frozen-01/source/out/runs/20261008T101516Z-test-2890c200/manifest.json),
  including its final source-freshness check.

The native signal is captured **at the actual STRETCH renderer destination**,
before native envelopes/effects reuse that buffer. A 4 KiB diagnostic copy
retains its 32 samples per lane. Reading that buffer only after the full block
gave a deliberately retained failed comparison; the generic voice-buffer tap
is also unsuitable for STRETCH. This is pre-mix DSP signal evidence, not a
listening test, final-output measurement or physical real-time proof.

The control fixtures are explicit adaptations of prior captured panel wire;
they are not new physical-panel captures. The final run retains
`adapted-stretch.dtfr`, direct-destination `.f32`, per-case errors, prepared-bank
state, exact MAIN/BLOB and linked listings. Fixture hashes and all source hashes
are in its report. Candidate identities:

- MAIN: `7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3`
- BLOB: `2e40f16aca0243cf44732703be0e18817669ddb2ae5653c945de352ca4b3334a`

## Resources

The total reservation remains **8 MiB**. A maximum bank requires 6,912,048
bytes (6.59 MiB), with actual arrays sized to measured key count. The source
PCM stays in the existing sample pool. Thirty-two readers consume 4,224 bytes;
their bank is shared. The candidate has 78,766 instruction bytes, 12,496 bytes
of constants, and uses the established 200 KiB reserved working arena for
constants, stacks, worker, readers and diagnostics. No allocation or analysis
occurs in the renderer. The CPU reservation still requires fresh allocator
state; instruction-code ownership and other runtime writers need further proof.

Cached key brackets avoid repeating a binary search when an exact Q24 check
shows that the cursor remains in the same interval. Neighbor movement is bounded,
with the original binary search as fallback. Audio and splice decisions remain
unchanged. In the same all-sixteen-track sharing fixture, retired instructions
per 32-sample block drop from **3.79–3.93 million to 2.25–2.33 million**, roughly
**40.5% fewer**. This remains substantial work. These are emulated instruction
counts, not hardware cycles or a DSP-load percentage, and the fixture uses a
2,400-frame source rather than maximum-length/density banks.

At 32 analyzed positions per normal 32-sample block, the two passes schedule
approximately twice the input duration in audio-block time: around 24 seconds
for a full 12-second source. This is a schedule estimate, not measured hardware
wall time. Stock STRETCH remains available during preparation, with Capicola
selected on a subsequent eligible trigger.

## Reproduction and remaining work

From the lab checkout, with its configured Python 3.12 runtime and unchanged
private fixtures:

```sh
python3 scripts/check-capicola-stretch.py out/runs/<fresh-host-name>
python3 scripts/check-capicola-stretch-native.py out/runs/<fresh-native-name>
./labctl test sine --replay
```

The native runner selects the configured runtime automatically. Source tests
must use Python 3.12; the Mac's unrelated Python 3.10 cannot load the resource
diagnostics module. Final checks use a frozen source copy under
`out/runs/capicola-stretch-frozen-01/source`, with unchanged dependencies and
fixtures. Its snapshot manifest records the copied source hashes. Two earlier
SINE runs passed their audio checks but failed the broad freshness gate when
unrelated resource-profiling files changed in the shared checkout; those failed
manifests are retained. The old controls image hash also belongs to its legacy
layout, while the later selection/feedback hashes belong to reserved-state
builds; the final checker compares the correct recorded placements.
The [checkout comparison](../../../out/runs/capicola-stretch-frozen-01/checkout-comparison.json)
also confirms the current Capicola and shared build inputs remain byte-identical
to the successfully tested snapshot. Unrelated profiling work is preserved.

Next work is live mode/trim semantics and native position bookkeeping,
multiple-source bank admission/lifetime, final-mix/level/release checks,
project/recall behavior, further playback optimization and actual DSP timing.
Stereo, the video's GAP semantics, listening comparisons, complete code-memory
ownership and an installable package remain open. No device upload or firmware
package is produced by this run.
