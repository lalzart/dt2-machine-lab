# Worker state-by-operation matrix
> Status: ready

| Operation | Effect |
|---|---|
| Initialization | Initialize worker and bank before first begin; no source retained. |
| Reset | Begin invalidates bank/readers and resets analyzer to count pass. |
| Panic | Cancel invalidates bank and clears source pointer. |
| Freeze or capture | Unsupported; immutable source must remain owned through both passes. |
| Mode change | Cancel before leaving loading mode or replacing source. |
| State recall | Begin a new load; never restore raw pointers. |
| Disconnect/reconnect | Cancel and begin with newly owned source. |
| Non-finite recovery | Int16 source cannot be non-finite; invalid control arguments fail closed. |

## State equivalence
Exact host key arrays independent of step budget; target audio tolerances in proposal. Cancelled and invalid banks are silent, unused array bytes are unspecified. Worker steps and bank operations serialize with rendering.

## Selection extension

# Selection state operations
Status: ready.

Initialization clears source, bank and progress. Reset, panic or machine exit cancel and silence. Selection change invalidates then begins only for eligible immutable mono metadata. Source reload interrupts invalidate the publication epoch; matching complete metadata allows a fresh two-pass analysis. Recall and reconnect resolve current slot anew; pointers are never persisted. Capture/freeze are unsupported. Invalid/non-finite controls remain governed by the unchanged core validation. Status uses a sequence guard and updates after each maintenance call; progress is monotonic within an unchanged source epoch. Bank contents and complete output use the existing exact-key and bounded-audio equivalence rules.

## Feedback states

OFF has no tag. Empty, unsupported, preparing, waiting, ready and failed retain the selection ABI meanings. A tagged malformed or unknown reply must fall back to a neutral CAPICOLA caption. Screen state must not affect audio publication.
