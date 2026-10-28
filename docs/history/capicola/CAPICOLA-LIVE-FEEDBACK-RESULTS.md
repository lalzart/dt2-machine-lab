# Separate-machine automatic feedback: partial, superseded

2026-10-08. The user's correction redirects Capicola to the existing STRETCH
backend. The type-8 automatic-caption work stops here. Its source and runs are
preserved; the active direction is [STRETCH replacement](../../CAPICOLA-STRETCH-REPLACEMENT.md).

Native quarter-progress/slot-correlated DSP replies and voice comparisons pass
in `out/runs/capicola-live-wire-02/report.json`. Native CPU decoding, compatibility
and actual SPI2/SPORT transmission pass in
`out/runs/capicola-live-transport-03/report.json`. Ninety-five source tests and
the SINE replay (`out/runs/20261008T083716Z-test-b8be7e0b/manifest.json`) pass.

**Automatic visible feedback does not pass.** The draw-hook candidate updates
an initially stale SRC page, but a correctly rebuilt page does not draw while
idle. `capicola-live-ui-03` remains at P<25% when the injected reply reaches
P<50%. The earlier `capicola-live-ui-02` had stale/blank controls and cannot be
counted as a complete UI success. No new polling hook was implemented after
the user redirected the product.

These results do not prove coupled CPU/DSP timing, physical behavior or a
replacement for STRETCH. The old successful page-open feedback and all prior
engine experiments remain separate reproducible baselines.
