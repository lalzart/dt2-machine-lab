# Flex Lite: recorder boundary on OS 1.16

2026-10-06. Result: an existing chunk-reading interface is a plausible source
for a temporary sample. The original CPU save consumer passes isolated tests
with synthetic peers. Recording directly into a playable temporary slot is
not implemented or demonstrated.

The desired workflow remains **record, use on a track, optionally save later**.
See [the feature assessment](FLEX-LITE-FEASIBILITY.md).
The subsequent [RAM playback prototype](FLEX-LITE-RESULTS.md) now validates
the allocation/publication/playback half with synthetic PCM; this recorder
note retains the earlier probe's narrower evidence.

## Finding and design consequence

The CPU save routine does not receive an owned pointer to an entire recording.
It requests PCM chunks through a synchronous service, copies each response
while retaining a lock, then writes the copied bytes to storage. The response
address is shared scratch space. Keeping that address as a sample would not
provide a safe lifetime.

The candidate design is therefore:

`completed recording -> locked chunk reads -> independently owned temporary sample -> track`

`temporary sample -> optional persistent save`

This can avoid a persistent sample file while still requiring copying,
formatting and publication to sample memory. Stop-to-play latency has not been
measured. Once another recording can replace the recorder contents, optional
save must use the retained temporary audio or another deliberately retained
source; it cannot blindly read the current recorder again.

This is principally recorder/resource/assignment work. A new playback DSP
engine is not indicated by this evidence.

## Version and source

- Digitakt II **OS 1.16 MAIN**, 3,275,616 bytes, SHA-256
  `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
  Rehashed the lab fixture and original workspace copy.
- Machine lab: `codex/plaits-macro-controls`, HEAD
  `c1a0ad675741339c5e154dcb5a58caa7b65b21c2`; inherited changes preserved.
- Clean pinned DigiKit: `277760aad51b036a4756db051409d4d3b1eeccbc`.
  `./labctl doctor` passed the dependency, tool and private-fixture checks.
- Earlier OS 1.15C recorder, assignment, RAM-backing and format notes under
  the original workspace's `outputs/elektron-firmware-research/analysis-results/`
  supplied search anchors. The addresses below were recovered and inspected
  against **1.16 bytes**, not assumed from an address delta. Those historical
  notes do not govern this work.

## Recovered CPU path

These are disassembly findings unless specifically marked as executed below.
Addresses are private analysis references, not a stable firmware API.

| OS 1.16 location | Observed responsibility |
| --- | --- |
| `0x40015fda` recorder transitions; `0x40020ede` post-normalize | Completion retrieves recorded frame count; the view retains trim bounds. |
| `0x4002302e` | Captures trim start, end-minus-start and the format flag for save work. |
| `0x4001f8b0` | Save worker calls the writer at `0x40153994`. |
| `0x4001282e` | Command 4 PCM request: 12-byte descriptor containing command, selector, starting frame and frame count; response extent `0x800`. Executed with a synthetic service. |
| `0x400124a0` | Synchronous request service. Intercepted in the probe; its peripheral completion was not executed. |
| `0x400cd482` | Returns shared response address `0x4fe79340`. Executed. |
| `0x400cd48a` | DMA setup uses TX `0x4fe7a340`, RX `0x4fe79340`, and DSPI1 registers `0xfc03c034`/`0xfc03c03a`. |
| `0x40153994` | Save consumer copies responses to staging at `0x405a50b0`, then writes the native sample representation. Executed with the substitutions described below. |

The save consumer uses selector 1 with two bytes per frame for mono and
selector 0 with four bytes per frame for stereo. Its inner response limit is
`0x800` bytes and outer staging limit is `0x8000` bytes. The native sample
representation has a `0x40`-byte header and a 16-byte trailer; observed header
fields include payload byte count, 48,000 Hz and the stereo flag. These are
not RIFF/WAV headers.

The outer lock helper at `0x40012542` remains held across the request wrapper's
own lock and the caller's copy. The matching outer unlock at `0x40012552`
precedes the file write. The recursive mutex object is `0x40965b74`.

Command 5 at `0x4001288a` is the neighboring normalization request. This work
does not establish where the entire recording resides, identify the recorder
peer physically, or prove how long completed audio survives cancel, a new
capture, or a project change.

## Isolated execution result

[Probe source](../../../scripts/probe-flex-recorder.py) loads the entire authenticated
MAIN unchanged into patched Unicorn's ColdFire model. The stock save loop,
PCM request wrapper, response getter and lock-helper glue execute. RTOS mutex
primitives, the request service, memory helpers and filesystem calls are
substituted. File output is an in-memory byte sink, not a disk operation.
One unsupported FF1 instruction at `0x401539e2` receives the same semantic
accommodation used by DigiKit's harness; the probe records it explicitly.

The [final local report](../../../out/runs/flex-recorder-116-final-01/report.json)
passes 16 mono/stereo vectors, each run twice with exact result comparison,
plus an open-failure control: **33 executions**. Frame counts are 0, 1, 511,
512, 513, 1024, 1025 and 20,000, starting at frame 7. They cover both response
and staging boundaries with distinguishable synthetic channel words.

The probe verifies contiguous frame requests, exact saved payload bytes,
header fields, staging bounds, balanced locks and unchanged MAIN bytes. It
poisons the shared response on every outer unlock; saved output still matches,
demonstrating that this consumer copies before relinquishing the response.
Open failure performs no PCM request or file write. This validates the CPU
consumer under the specified peers, not those peers or genuine recorder PCM.

Reproduce from the machine-lab root, choosing a fresh output directory:

```sh
./labctl doctor
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
"$LAB_PYTHON" scripts/probe-flex-recorder.py out/runs/flex-recorder-116-my-run
```

The probe rejects unknown MAIN hashes, existing output directories and paths
outside ignored `out/`. Reports and disassembly slices stay local. Initial
failed runs are retained; they exposed the unsupported FF1 instruction before
the compatibility accommodation was added. Scoped Ruff checks/formatting and
all eight source harness unit tests pass. No DSP adapter changed.

## Connection to playback and next experiment

Existing DigiKit findings `04-coldfire-dsp-link.md` and
`15-sharc-sample-path.md` establish the other half: sample-memory allocation,
4 KiB page transfer through `0x400cd638`, and mono/stereo slot headers through
`0x40153b90`/`0x40153b28`. The stock loader `0x40154540` also resolves a
persistent file identity and updates CPU metadata; bypassing its file read
does not supply the rest of that contract. Those playback findings were read,
not rerun in this investigation. This probe also saves fresh disassembly of
the two header builders, without executing them.

The next bounded experiment should construct **one owned temporary resource
from deterministic PCM**, publish it using the existing sample format, assign
it to one track and compare stock-renderer output with the same file-loaded
PCM. It must include allocation bounds, an unpublished-slot negative, storage
tracing, detachment/replacement and CPU metadata. Do not borrow the preview
slot `0x400` or reserved bank-zero slots without establishing their ownership.

The recorder source inspected here uses **DSPI1**, separate from DigiKit's
existing DSPI2 control exchange. Inspection of the current Python emulator
setup found DSPI2 and SSI peers but no completed recorder DSPI1 service peer.
That is an emulation gap to resolve or bound before testing real panel capture;
the synthetic request hook used here is not a replacement for that evidence.

Remaining unknowns include recorder retention/cancellation, temporary-resource
allocation and release, sample identity and project reload, failed-save
recovery, slice/stretch metadata, real input/resampling, downstream audio,
memory headroom and device timing. No firmware image was patched, hardware
accessed, or changes committed or published.
