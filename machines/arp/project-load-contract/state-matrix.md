# Core state-by-operation matrix

> Status: ready

| Operation | Held and ownership | Gate | Clock and order |
|---|---|---|---|
| Initialization | Zero all counts | None | Known tick, phase zero, last pitch -1 |
| Reset | Clear all bytes including owners | Caller releases first | Initialize at supplied tick |
| Panic | Clear active set, retain suppressed owners until releases | One off if active | Stop, clear phase/order |
| Freeze or capture | N/A: no phrase capture | Unchanged | Diagnostic read only |
| Mode change | OFF clears active set, retains owners; all mode changes clear active set and reset seed/order | OFF emits off | Reset phase/order |
| State recall | Only mode configuration; discard keys/gates/timers on recall | None | No recall |
| Disconnect/reconnect | Panic; reset after all releases | Off | Fresh anchor |
| Non-finite recovery | N/A: integer only; reject invalid integers | Unchanged on rejection | Late clock panics; unsigned wrap normal |
| PLAY | Retain pre-play held set | None initially | First deadline after one interval |
| STOP | Clear active set, retain owners | Off | Clear phase/order |
| Last release | Remove final contribution | Off immediately | Last pitch reset |

## State equivalence

Compare complete core state bytes at equal ticks. Adapter repeats compare
musical event kind, pitch, velocity and sample tick; host times and diagnostic
instruction counts are excluded. Neither is physical timing evidence.

ORDER preserves duplicate position; a final release/re-press assigns a new stamp.
RANDOM seed resets at Stop/panic/mode change; saved notes preserve realized choices.

Project load entry: panic, stopped clock, all modes OFF, retain release ownership. Successful return: consume authenticated buffer/slot binding and recall checked companion. Failed/unknown load: stay OFF. Overlay transaction: synchronize dirty guest sectors, publish changed native sectors; no original file writes.

Normal GUI load uses original live-project import 400F5050 and decoder 400DF7F6, with its requested slot, exact cache buffer and successful import return. Non-live export buffers do not trigger arp recall. Fresh-reader and Project::load diagnostic paths stay separate. The native project dialogs may skip the save prompt; follow the fixture panel dialogs and wait for the fixture LOAD PROJECT parent row or LOAD OK after sample-loader completion. Calls use a separate guarded diagnostic stack and 16 MiB scratch arena; active guest stack pages must remain unchanged.

Cache identity: node+0 is authoritative; node+8 may retain prior read bookkeeping after save. A slot -1 live clone/export is not saved-project recall.
