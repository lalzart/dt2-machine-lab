# Core state-by-operation matrix

> Status: ready

| Operation | Held and ownership | Gate | Clock and order |
|---|---|---|---|
| Initialization | Zero all counts | None | Known tick, phase zero, last pitch -1 |
| Reset | Clear all bytes including owners | Caller releases first | Initialize at supplied tick |
| Panic | Clear active set, retain suppressed owners until releases | One off if active | Stop, clear phase/order |
| Freeze or capture | N/A: no phrase capture | Unchanged | Diagnostic read only |
| Mode change | OFF clears active set, retains owners; UP arms before direct inputs | OFF emits off | Reset phase/order |
| State recall | N/A: no persistence | None | No recall |
| Disconnect/reconnect | Panic; reset after all releases | Off | Fresh anchor |
| Non-finite recovery | N/A: integer only; reject invalid integers | Unchanged on rejection | Late clock panics; unsigned wrap normal |
| PLAY | Retain pre-play held set | None initially | First deadline after one interval |
| STOP | Clear active set, retain owners | Off | Clear phase/order |
| Last release | Remove final contribution | Off immediately | Last pitch reset |

## State equivalence

Compare complete core state bytes at equal ticks. Adapter repeats compare
musical event kind, pitch, velocity and sample tick; host times and diagnostic
instruction counts are excluded. Neither is physical timing evidence.
