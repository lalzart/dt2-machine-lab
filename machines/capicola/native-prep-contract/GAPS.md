# Native preparation gap register

- Stock background scheduling and firmware-owned arena allocation are not wired. Caller must serialize preparation/render and retain immutable source and arrays.
- CPU selector, parameters and UI feedback remain open. There is no installable Capicola package.
- Native target checks use short PCM; twelve-second worker coverage is host-side. Physical preparation latency and audio deadlines remain unmeasured.
- Target ratio correction is limited to exact int16 derivative magnitudes; it does not fix or authorize changing the preserved general float analyzer.
- Final mix, listening quality, project-reload lifecycle and hardware remain unverified.
