# Managed Sketch buffers

Implementation proposal, 2026-10-26. User authorization: implement the presented
Sketch redesign as one uninterrupted task. Baseline: committed `34284b5`, OS1.16.

The instrument keeps its existing track pages, sample slots, sequencer, effects,
four live BUF identities, eight immutable FREEZE identities and one recorder.
This is an opt-in successor profile, with the accepted profiles byte-preserved.

## Behavior and control contract

Each BUF owns source, channel, length, monitor and start mode. Selecting another
BUF changes the displayed settings. Editing an idle BUF does not edit another
BUF or the normal sampling settings. Capture latches the selected BUF's settings;
changing selection during capture does not retarget the take. The original
recorder owns capture and the original loader owns sample allocation/playback.

The panel reports EMPTY, READY, WAIT, REC, BUSY, FULL or ERROR from native state.
Capacity means available generation seats, not an invented number of free PCM
bytes. Occupied, playing, frozen, leased or quarantined storage is never freed
merely to make a counter look empty. The accepted publication/retirement protocol
remains authoritative. A failed replacement retains the accepted take.

Buffers and their settings are volatile. Powering off may discard every
unsaved take. FREEZE keeps an immutable take within the running session; only
explicit +Drive export makes a durable sample. No project persistence, automatic
saving, project restoration or project-format changes are part of this profile.
The existing project guards and native Sketchbook save/preview path remain.

## Source and authority

Reuse the user's local Sketch, recorder worker/retirement, Sketchbook export,
native filesystem adapters. No external DSP
algorithm or firmware source is redistributed. Firmware and generated binaries
remain ignored. Dependencies stay pinned. Original instruction emitters are the
baseline oracle; deviations are per-BUF controls, status/admission, explicit save compatibility and their explicit UI feedback. The DSP signal processing
and sample formats remain unchanged.

## Experiment and validation

Use deterministic native ColdFire instruction cases for independent settings,
normal-settings isolation, latched capture, busy/refused transitions, lifecycle,
allocation capacity, save failure and stale recorder settings. Run scoped buf, core
and integration suites; add explicit affected retirement cases. Rebuild the
baseline profile and compare its exact hash. Run a fresh native coupled
CPU/SHARC capture, replacement, FREEZE, save and independent reload where the
available harness supports the changed path. Test rejected readback and failed or disabled export as negative controls. No host callback may manufacture
target success. Replay SINE if DSP/adapter behavior changes. Retain failed runs.

Acceptance is evidence-specific: source/static, isolated native instructions,
coupled modeled peripherals, voice/final-output PCM, real time/listening and
physical hardware are separate. No flash, commit, push or publication is
authorized. Result notes must identify implemented behavior and remaining
unverified or incomplete paths, with exact reproducible commands and hashes.
