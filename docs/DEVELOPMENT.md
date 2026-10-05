# Development roadmap

## Present foundation

The lab owns the SINE sources, CPU patch construction, DSP assembly/linking,
replay, checks and reports. Dependencies are pinned and checked; generated
outputs and fixture bytes are private. `labctl` provides actual build, render,
test and profiling commands. See [README](../README.md) for their exact scope.

Maintain one lab for multiple machines. Keep version-specific patch details
in firmware profiles and generic engine behavior separate from the adapter.
General emulator fixes belong in a focused DigiKit branch; adopt them by
changing the dependency pin after regression checks. Never depend on hidden
edits inside `.deps/`.

## Next: complete fixture generation

Replace imported prepared state with a builder that starts from the owned,
hash-checked `.syx`, builds dependencies, generates the sample/card fixture,
initializes patched CPU and DSP images, drives panel events and captures the
control stream. A second-directory test must recreate the same expectations.

The current test replays a real CPU capture into a patched DSP starting from
stock-initialized state. CPU cold boot and patched DSP initialization were
tested separately in the original experiment. The lab must join those stages
before claiming a clean, complete boot-to-audio result.

Key caches by firmware, source, build configuration, sample/card inputs,
emulator options and state-format version. Schedule panel events at defined
execution boundaries rather than host sleeps. Keep CPU instruction positions
and DSP frame positions separate until their timing relationship is validated.

## Then: one real parameter

Define pitch once: identity, label, default, range, units, encoding, update
timing, and each step through CPU storage, control frame, DSP decode and the
engine. Measure 220, 440 and 880 Hz from actual panel/sequencer input. Then
exercise extremes, rapid changes, retriggering, parameter locks and recall.
Direct DSP fixtures remain useful but do not replace control-path tests.

The present `machine.json` describes a fixed oscillator; it is not yet a
parameter-code generator or a general machine registration API. Initially
build one custom type at a time. Additional simultaneous machine types need
central ID/table/dispatch allocation and independent per-track state.

## Broader audio and resource tests

Establish sample-free startup, stock AMP/filter/FX behavior and final output
capture. Expand to multiple tracks/voices, sustained notes, dense retriggers,
transport changes, silent-but-enabled machines and mixed stock/custom work.
Retain stock isolation, explicit disabled-hook controls and lifecycle tests.

For larger engines, first validate a small compiled C kernel and its register,
stack, numeric and memory behavior. Selache contains a C99 compiler; the
current working path validates assembly/linking, not a C++ synth port.
Keep host algorithm tests and compare executed SHARC results against them.

## Load measurements

Current reports separate whole-handler **emulated instructions** from **host
microseconds** and include p50/p95/p99/observed maximum. These are not isolated
SINE kernel cost. Next add paired stock/custom reports and bounded region
measurements; include memory/table/state/stack use and profiling overhead.

DigiKit's instruction clock is diagnostic, not cycle accurate. For actual
DSP load, establish configured clock and callback cadence, then measure all
work that must finish within `clock_hz * samples / sample_rate` cycles. This
general method is described by
[Analog Devices](https://wiki.analog.com/resources/tools-software/sharc-audio-module/baremetal/processing-audio).
It does not supply DTII's configured clock or spare capacity.

For CPU work, start with instructions per event/interrupt and control latency.
A physical utilization percentage needs a validated timer and real idle-time
measurement. Account for interrupt activity, storage, UI, MIDI and the full
stock audio workload. Report workload/duration and observed maximum; a finite
test does not prove an absolute worst case. Host speed determines emulator
usability, separately from device capacity.

## Everyday process

Use ordinary branches, code review, a known reference run, and focused tests.
Keep one machine definition, a small integration note, and generated run
reports. There is no investigation registry or claim-approval process.
Source-only tests need no firmware; firmware CI, if added, uses private local
inputs. Hardware work and publication remain separate user requests.
