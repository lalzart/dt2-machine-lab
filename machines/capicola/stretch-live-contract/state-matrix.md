# STRETCH state-by-operation matrix
> Status: ready

| Operation | Effect |
| --- | --- |
| Initialization | Zero reader, no bank retained, stock backend. |
| Reset | Zero reader, no bank retained, stock backend. |
| Trigger | Attach current published generation and native controls; choose stock/custom once. |
| Panic | Stop/inactivate according to native voice/envelope; no retired source read. |
| Pitch/tempo | Change increments without resetting cursors/splice. |
| Mode change | Live R3: clamped ideal source position and 64-sample reader transition; latest configuration queued during transition. |
| Sample/machine change | Stop stale reader; next trigger resolves current source. |
| Reload | Invalidate epoch before modifying PCM; reprepare; no mid-note takeover. |
| State recall | Resolve current slot; never serialize pointers. |
| Disconnect/reconnect | Resolve current slot; never serialize pointers. |
| Freeze or capture | N/A: recorded immutable source only. |
| Non-finite recovery | Start/update rejects and stops before dereference. |

## State equivalence
Exact Q24 cursor progression and block-partition equality; numerical PCM oracle tolerance max 1e-4 and RMS 1e-5. Padding and diagnostic counters are not serialized musical state. Bank reload prevents any old-generation read.

## R2 cache operations
Selected or active banks cannot be evicted. Unreferenced inactive banks may be evicted only in maintenance, invalidating generation first. Overlapping LP0 writes invalidate only the affected source epochs. Pressure retains stock backend and retries when a suitable extent is released; no mid-note takeover. Reset clears all descriptors only under serialized control.

## R3 live controls
Trim uses the same transition as mode. Pitch/timing update both readers without reset. Finite completion never resurrects a note. Pending configuration is latest-only and is cancelled if controls return to the current configuration. Both readers stop on retired source or nonfinite controls.
