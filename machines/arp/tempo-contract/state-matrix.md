# Core state-by-operation matrix

> Status: ready

| Operation | Held and ownership | Gate | Clock and order |
|---|---|---|---|
| Initialization | OFF/1/16 for128 patterns; clear owners | None | Phase0, known tick, existing8192-byte allocation |
| Reset | Broader new-project integration deferred; explicit core init clears owners | Caller closes first | Reinitialize after released keys |
| Panic | Clear active set; retain consumed release owners | One off | Reset phase/order |
| Freeze or capture | N/A: no latch/freeze | Unchanged | Diagnostic observation only |
| Mode change | Existing panic; same mode inert | Close current | Existing order reset |
| Rate change | Retain held/owners | Close current | Phase0; new interval and half gate; retain order |
| Tempo change | Retain held/owners | Preserve remaining beat gate | Read original getter; preserve beat phase |
| State recall | v1->same mode/1/16; v2->packed mode/rate; defaults OFF/1/16 | None | Do not restore PLAY/keys/focus/RNG |
| Disconnect/reconnect | External MIDI I/O N/A; existing UI destination panic | Off | Fresh anchor on PLAY |
| Non-finite recovery | Integer only; invalid tempo/overdue service panics | Close | No bursts |
| STOP/keyboard exit/pattern or track change | Existing native panic/release safety | Off | Existing order reset |
| Copy/undo/export | Broader integration deferred | No new claim | No new claim |

## State equivalence

Exact events/phase at equal sample calls. Native UI/storage scheduling latency
is measured separately. Codec equality is byte exact against independent AR16
v2 encoding, with explicit v1 import semantics. This candidate's physical
timing, external clock, swing and broader lifecycle remain unverified.
