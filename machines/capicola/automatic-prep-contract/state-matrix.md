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
