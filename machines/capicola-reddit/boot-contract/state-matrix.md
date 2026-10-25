# Author engine state-by-operation matrix

> Status: ready

| Operation | Required behavior |
|---|---|
| Initialization | Cleared static state and frame/search scratch; original GEN_BUILD=0 initialization |
| Reset | Native PHASE/voice identity rebuilds state |
| Panic | Native stop/envelope silences playback |
| Freeze or capture | N/A immutable stock sample reader |
| Mode change | Author block dispatch OFF stock; ON author WSOLA |
| State recall | Stock controls/trigger drive fresh source state |
| Disconnect/reconnect | Native source identity invalidation/retrigger; no analyzed cache |
| Non-finite recovery | Original bad_out guard; bounded silent recovery |

Exact host golden records; target max1e-4 RMS1e-5; OFF exact stock.

## State equivalence

Exact host repeat and golden checks; same target/host input max1e-4 RMS1e-5.
