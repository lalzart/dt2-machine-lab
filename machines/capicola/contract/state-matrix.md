# Core state-by-operation matrix
> Status: ready

| Operation | Effect |
|---|---|
| Initialization | Clear keyframes, cursors, errors, active flag; output silent. |
| Reset | Restart at zero with same immutable sample and controls. |
| Panic | Stop; future output zero without cursor advancement. |
| Freeze or capture | N/A: preanalysis of a supplied finite sample only. |
| Mode change | N/A: one-shot mono only. |
| State recall | N/A: no serialized state; reload and restart deterministically. |
| Disconnect/reconnect | N/A: no physical or streaming endpoint. |
| Non-finite recovery | Invalid load clears sample and reports error; invalid start stops voice. Valid load/start recovers. |

## State equivalence
Compare keyframe count and ordered amplitude/time bytes, playback position, active/splice state and PCM. Ignore pointer addresses and structure padding. Reset must reproduce PCM exactly. Partial output blocks are zero-filled past the duration.
