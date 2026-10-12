# STRETCH state-by-operation matrix
> Status: ready

| Operation | Effect |
| --- | --- |
| Initialization | Zero reader, no bank retained, stock backend. |
| Reset | Zero reader, no bank retained, stock backend. |
| Trigger | Attach current published generation and native controls; choose stock/custom once. |
| Panic | Stop/inactivate according to native voice/envelope; no retired source read. |
| Pitch/tempo | Change increments without resetting cursors/splice. |
| Mode change | Latched until next trigger in R1. |
| Sample/machine change | Stop stale reader; next trigger resolves current source. |
| Reload | Invalidate epoch before modifying PCM; reprepare; no mid-note takeover. |
| State recall | Resolve current slot; never serialize pointers. |
| Disconnect/reconnect | Resolve current slot; never serialize pointers. |
| Freeze or capture | N/A: recorded immutable source only. |
| Non-finite recovery | Start/update rejects and stops before dereference. |

## State equivalence
Exact Q24 cursor progression and block-partition equality; numerical PCM oracle tolerance max 1e-4 and RMS 1e-5. Padding and diagnostic counters are not serialized musical state. Bank reload prevents any old-generation read.
