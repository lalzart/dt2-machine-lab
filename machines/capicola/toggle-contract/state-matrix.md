# Optional CAPI state-by-operation matrix

> Status: ready

| Operation | Musical controls/state and timing | Feedback and buffers |
|---|---|---|
| Initialization | OFF by default; original R3 init; CPU status/ages zero | Original immutable banks; diagnostic ages excluded from musical state |
| Reset | Native defaults and original reader clear; reset diagnostic cache | Original immutable banks; diagnostic ages excluded from musical state |
| Panic | Original active clear; no resurrection; next status reports idle | Original immutable banks; diagnostic ages excluded from musical state |
| Freeze or capture | N/A - immutable file banks; native wire and PCM capture are observations | Original immutable banks; diagnostic ages excluded from musical state |
| Mode change | CAPI intent changes now; backend latches at trigger; original PLAY/trim transitions retained | Original immutable banks; diagnostic ages excluded from musical state |
| State recall | Native parameter204 storage restored; trigger uses restored value; status asynchronous | Original immutable banks; diagnostic ages excluded from musical state |
| Disconnect/reconnect | Original reload/reset contract; invalid replies clear cache; hardware deferred | Original immutable banks; diagnostic ages excluded from musical state |
| Non-finite recovery | Malformed integer CAPI selects stock; original numeric/generation guards stop invalid readers | Original immutable banks; diagnostic ages excluded from musical state |

## State equivalence

OFF renderer PCM is exact to stock. ON matches R3 at max1e-4/RMS1e-5. Trigger policy and omitted-option images are exact. Diagnostic ages and host timestamps are excluded from musical equality.
