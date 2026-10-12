# Capicola implementation gap register

| Gap | Status | Next evidence |
|---|---|---|
| Target position precision | Confirmed blocker for direct port | Integer/fraction or fixed-point timestamp contract, then comparisons with the existing double oracle including decimal rates. |
| Extreme short-leash pitch metric | Incomplete at pitch 0.5 / advance 2 / leash 16 | Whole-signal pitch/quality assessment; preserve 2 Hz criterion and do not call absent measurements passing. |
| Dense sample capacity | Explicit 4096-keyframe overflow, tested | Storage/cache design for longer and high-density samples. |
| Firmware integration | Deferred | Sample ownership, access, code/data placement, one-track control path and stock parity. |
| Musical improvement | Unmeasured | Matched stock STRETCH/candidate renders and listening. |
| Stereo/reverse/loops | Excluded from this slice | Separate source semantics and tests. |
| Physical timing/hardware | Not attempted | Separate authorized device work and measured deadline margin. |

No dependency updates, firmware packaging, hardware transfer, commit or publication occurred.
