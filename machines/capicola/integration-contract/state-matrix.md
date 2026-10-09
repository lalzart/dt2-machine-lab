# Core state-by-operation matrix
> Status: ready

| Operation | Effect |
|---|---|
| Initialization | Bank starts unbound and not ready; reader starts detached and silent. Array bytes are caller-owned and need not be zeroed. |
| Reset | Restart at zero with same immutable sample and controls. |
| Panic | Stop; future output zero without cursor advancement. |
| Freeze or capture | N/A: preanalysis of a supplied finite sample only. |
| Mode change | N/A: one-shot mono only. |
| State recall | N/A: no serialized state; reload and restart deterministically. |
| Disconnect/reconnect | N/A: no physical or streaming endpoint. |
| Non-finite recovery | Invalid load clears sample and reports error; invalid start stops voice. Valid load/start recovers. |

## State equivalence
Compare keyframe count and ordered amplitude bytes and split times within 2^-24 samples of double reference, playback position, active/splice state and PCM. Ignore pointer addresses and structure padding. Reset must reproduce PCM exactly. Partial output blocks are zero-filled past the duration.

Capacity extension: bank count pass is read-only; load clears readiness before validation, commits frames/count on success, and advances generation on all attempts. Bound readers silence on generation mismatch. Reader reset/start and stop leave the bank untouched. Bank replacement is serialized with rendering. Two readers share immutable arrays, never transport state. Caller owns lifetime and storage; no concurrent mutation.

Integration: type7 dispatches unchanged Plaits and clears Capicola activity; type8 clears Plaits activity, handles invalid bank as silence, and snapshots controls on trigger. Other types clear Capicola activity and fall through to stock. Unsupported voice records return without touching either track-1 lane. Prepared handoff publishes a generation and source identity.
