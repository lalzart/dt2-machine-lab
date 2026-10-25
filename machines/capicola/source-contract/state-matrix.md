# Source playback state-by-operation matrix

> Status: ready

Init/reset: deterministic clear, no attached source or audible grain. Exact normalized state and repeated PCM equality.
Trigger: initialize current grain on selected medium; preserve active valid prior current as outgoing over960 output samples. Invalid source falls stock at trigger.
Rate changes: current follows pitch/advance; retiring grain retains previous controls.
Trim/PLAY/reverse: preserve clamped absolute ideal position, initialize new medium, preserve old grain; queue rapid edits until existing handoff ends.
Stop/Panic: stop both, clear handoff/pending. Generation change or invalid/nonfinite input: same silence; never resume stock mid-note.
Finite completion: ideal-selected duration determines stop; physical gain remains native envelope. Loop: periodic virtual medium, no artificial per-head edge taper.
Freeze/capture: N/A - immutable sample machine, not Alchemy LIVE_EFFECT.
Recall/reconnect: native control state and later trigger rebuild reader; no serialized audio history promised.
Bypass/CAPI OFF: switch latched at native trigger, preserve existing feedback/lifecycle.

| Operation | Effect |
|---|---|
| Initialization | Clear deterministic histories |
| Reset | Clear histories and source |
| Panic | Silence both grains immediately |
| Freeze or capture | N/A - immutable file machine |
| Mode change | Queue geometry, crossfade960 preserving old rates |
| State recall | Native controls recalled; fresh trigger |
| Disconnect/reconnect | Generation invalidation silences both |
| Non-finite recovery | Stop both; no stale playback |

## State equivalence

Exact repeated host PCM/state for identical events; original-source and packaged target PCM max1e-4 RMS1e-5 over full start and periodic medium. Diagnostic ages excluded. OFF remains exact stock.
