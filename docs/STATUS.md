# Current status

2026-10-05: the local machine lab is initialized with source, repeat commands
and engineering notes. No remote is configured; generated artifacts stay local.

Implemented: pinned dependency checks, guarded CPU/DSP image construction,
private-fixture import, offline SINE replay, regression checks, per-block
instruction/host-time reporting, and separate run manifests/logs.

Validation passed on 2026-10-05:

- Eight source-only harness tests, plus lint and formatting checks.
- CPU and DSP builds match the original SINE image hashes exactly.
- The migrated one-second render matches the original PCM SHA-256 exactly:
  `2a38b64c83b1636b9f1a3793f6e78c71275d0a64ca2473c2e6b20bc183673eae`.
- Measured 440.000005 Hz, peak 0.125, maximum analytic error `9.45e-6`.
- Exact repeat, stock-machine isolation, controlled clone parity, disabled-hook
  negative control, retrigger, switch-away clearing and silent return all pass.
- A separate fresh-directory import and CPU/DSP build reproduce both image
  hashes. This relocation check did not repeat the audio suite.

The full replay report is retained in
[`out/runs/20261005T040725Z-test-108cd765/manifest.json`](../out/runs/20261005T040725Z-test-108cd765/manifest.json),
with its audio, raw PCM, profiles and logs. The independent path check is
recorded in [`out/relocation-check.json`](../out/relocation-check.json).
These are local, ignored artifacts; the portable expected hashes are in
[`tests/fixtures/sine-1.16.json`](../tests/fixtures/sine-1.16.json).

The successful run resolved firmware symbols through a newly generated lab
database. The first migration attempt exposed an old default database path;
that failure report remains in `out/runs/` and the adapter now uses a cache
keyed by firmware hash and DigiKit revision.

Clean fixture generation, sample-free startup, final output, live audio, and
physical CPU/DSP timing remain open.

Read [INTEGRATION](INTEGRATION.md) before changing the firmware hook and
[DEVELOPMENT](DEVELOPMENT.md) for the next steps. Elekloader is recorded in
[ECOSYSTEM](ECOSYSTEM.md) as an optional future integration.
