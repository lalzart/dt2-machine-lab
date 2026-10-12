# Split-time implementation gap register

- Compiled target analyzer differs from host on the short two-tone fixture: tiny float amplitude and fractional timestamp changes. Exact target analysis gate remains incomplete; reader tests use identical host-analyzed keyframes.
- Existing short-leash pitch-quality gap remains unresolved by numerical equivalence.
- Finite mono input remains limited to 48000 frames and 4096 keyframes; dense noise can exceed capacity and is rejected.
- Stereo, long-sample ownership/cache, loop/reverse, firmware transport and coexistence remain outside this experiment.
- Instruction counts are emulator observations, not physical cycle deadlines. No stock STRETCH listening comparison or hardware test.
