# Native BUF recording lengths — OS 1.16

The native next-bar recorder accepts LEN 16, 32 and 64 with the existing normal
16-step pattern clock. Sketch and SAMPLING+YES use the same guarded ARM service.
Recorder DEST and Sketch's remembered BUF remain independent. Publication never
assigns a track.

| Recorder length | Native value | Capture bars |
| --- | ---: | ---: |
| 16 steps | 4 | 1 |
| 32 steps | 5 | 2 |
| 64 steps | 6 | 4 |

ARM latches the bar count once. The existing interrupt still publishes receipts
only after consecutive `15 -> 0 -> 1` first-step transitions. The GUI starts at
the next receipt, services each following receipt once, and stops after the
latched number of bars. Duplicate polls cannot advance duration. Missed receipts,
a late final edge, changed capture settings or stale context cancel through the
existing recorder owner. Ordinary track/performance selection remains usable.

The existing next-bar BUF limit is **480,000 frames / ten seconds at 48 kHz**. It is
separate from the older Flex recorder's limits. No allocator or capacity grows.
During recording the native sample counter bounds elapsed capture, including
counter wrap, even if the modeled input count has saturated. An overlong take is
discarded through the original cancellation path; Sketch reports TOO LONG and
the committed BUF remains available. Slower tempos can exceed this limit before
LEN 64 finishes. Shorter lengths, LEN 128 and MAX still refuse explicitly.

Completed takes still use the original STOP/normalization, queued worker, stock
loader and publication. Existing readers retain their allocation; FREEZE remains
an immutable snapshot. Publication latency is measured, not optimized here.
The separate native-emulator reply investigation, physical timing, final mixed
output, device packaging and hardware validation remain open.

## Focused validation

`./labctl unit buf` passes 156 cases. Five additional cases cover exact native
bar counts through both ARM frontends, missed/late receipts, cancellation and
setting changes, sample-clock capacity/wrap, and dry UI recognition of all three
lengths. These are bounded native instruction checks with explicit service
boundaries; they do not substitute for a coupled workflow.

The coupled acceptance run is limited to two committed takes plus one cancelled
candidate: two-bar A, FREEZE A, four-bar B, and a LEN 64 candidate cancelled after
one complete bar. It checks exact bar counts, full captured PCM, stable shared
assignments, old-reader pointers and frozen A. A saved-page stock-file comparison
then checks A/retained-A/B/frozen-A voice PCM without more recordings.

Reproduce with the configured Python from `.local/config.json`, in fresh ignored
run directories:

Use native instruction tests for ordinary iterations. The coupled command is
an integration milestone and is substantially slower than real time; do not
repeat it without a relevant source change, failure or unresolved question.

```sh
./labctl doctor
./labctl unit buf
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/YOUR-FRESH-RUN \
  --lengths 32 64 --cancel-capture
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/YOUR-FRESH-REPLAY \
  --replay out/runs/YOUR-FRESH-RUN
./labctl test sine --replay
```

Recorder input, SSI cadence, LP0 delivery and SEC reset remain modeled. The
coupled run executes native CPU/DSP instructions; voice PCM and modeled timing
are distinct from final output, listening or physical-device behavior. Older
sealed device builds omit this extension and must retain their original source
and evidence scope.

## Measured captures — 2026-10-23 JST

Evidence is retained at `out/runs/buf-multibar-20261023-01/`. The coupled run
publishes these two takes through the original native recorder/worker/loader:

| Take | LEN | Native bars | Stereo frames | Capture completion to publication |
| --- | ---: | ---: | ---: | ---: |
| A | 32 | 2 | 225,888 | 384 ms |
| B | 64 | 4 | 451,776 | 772 ms |

Full captured PCM matches the modeled source and the native LP0 payload. Shared
BUF selectors, frozen A and active old-reader pointers survive B publication;
subsequent native triggers produce current B and frozen A. These delays come
from the 48 kHz emulator sample-clock model. They do not establish hardware
latency or promise that the immediately following bar's first trigger uses the
new take. Larger takes increase the measured publication delay in this model.

The coupled run passes 26 checks over 57,888 native DSP blocks with zero CPU
fault pages. Four active old-reader lanes (0, 1, 8, 9) retain their pointers
across B publication. A third LEN 64 candidate is cancelled after one native
bar; current B, frozen A, their complete registry/cache associations and all
assignments remain exact, with no additional LP0 publication. Final counts are
three STARTs, two successful STOP/publications and one FREEZE. SINE compatibility
replay also passes using the same source inventory.

The saved-page oracle passes 96 blocks repeated twice, comparing A/frozen A,
retained A during B publication, current B/frozen A and late frozen A against
fresh stock-file CPU loads and stock SHARC voice PCM. Its wrong-frozen-source
control differs as required. No additional recording is performed. The capacity
and missed/late receipt refusals have bounded native instruction evidence;
the coupled run does not add an overlong or deliberately broken-clock take.

The source inventory matches the coupled run, replay and SINE result at
`out/runs/20261023T041827Z-test-c9ed1743/manifest.json`. Native clock, queue,
worker, publication and cancellation emitters are byte-exact against the saved
pre-change implementation. Only native duration admission/stop logic, Sketch
feedback/labels and the validation driver change. DSP, FREEZE, Flex, dependencies
and existing sealed binaries remain unchanged.

See the [verification index](../out/runs/buf-multibar-20261023-01/verification.json)
and [native panel screenshots](../out/runs/buf-multibar-20261023-01/screenshots.html).
