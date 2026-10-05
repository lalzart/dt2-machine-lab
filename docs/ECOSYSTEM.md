# Related tools

## DigiKit and Selache

[DigiKit](https://github.com/m-dwyer/digikit) supplies emulation, patch planning,
firmware inspection and SHARC execution. [Selache](https://github.com/js216/selache)
supplies the public assembler/linker used by SINE. Both revisions are fixed
in [deps.lock.json](../deps.lock.json); the lab owns machine-specific adapters.
Their repositories retain their own license notices. No vendor firmware is
included in this repository.

## Elekloader

[Elekloader](https://github.com/irpina/elekloader) is an optional future
integration reference. Reviewed documentation revision:
`793b2e473dc0f0fa1a6d6f14e69a8cc166ce9300` (2026-10-05 review).

Its [DTII documentation](https://github.com/irpina/elekloader/blob/793b2e473dc0f0fa1a6d6f14e69a8cc166ce9300/docs/ADAPTING.md)
describes OS 1.17 control/UI hooks, including tick, draw, key, encoder and
settings events. DTII render events are excluded because audio runs on the
DSP. Its mod format, resource conflict checks and UI hooks could help with
future packaging and control integration.

Keep the current 1.16 SINE profile independent. A future adapter must verify
the firmware version, shared hooks, resource allocations and output format.
The reviewed format restricts mods to the main OS; our prototype changes
both MAIN and the SHARC BLOB. Do not assume existing packaging represents
both changes. Establish that capability, validate the packed output, then
repeat the emulator tests before considering a hardware route.

No Elekloader code is copied or executed by this lab, and it is not required
for a SINE build. The reference is pinned so later work can distinguish these
findings from upstream changes.
