# G sensitivity follow-up — 2026-10-16

Authorized scope: the user reports the arp is almost perfect on the device and
requests much lower G sensitivity plus a memory/hook optimization review.
The exact installed package hash is unconfirmed. Preserve musical timing,
note ownership, recording, AR16 v2 format and the previous firmware artifacts.
No DSP edits, new runtime allocation, hardware upload, commit or publication.

Selected implementation: use original OS1.16 encoder wrapper 0x40111B62 with
the existing Keyboard Settings accumulator at view+0x74 and enum configuration
0x44D2E600. The neighboring E/F controls already use its underlying scaler
0x401119FA and the same configuration. This reuses the view's original timer,
direction filtering and acceleration rather than interpreting each raw pulse
as a whole choice. The normal configuration divides accumulated motion by six;
its cooldown also affects response, so this is not a fixed physical detent ratio.
Clamp the resulting change to the existing four choices. G push resets only
G's partial motion/acceleration fields before switching mode/rate focus.
Ignore scaled-zero and unchanged-boundary edits without redraw or config writes.

Acceptance: execute original scaler instructions with small turns, reversals,
large turns and decay; compare G's results to an independent call to that stock
scaler. Verify focus clears partial input, busy/direct guards preserve settings,
no-change input preserves held notes and avoids redraw, and legacy MAIN remains
byte identical. Run actual UART panel gestures and the native note sequence.
Build a distinct R2 package, check repeat/protected sections, original depacker
and bounded startup. Physical knob feel requires the user's next device trial.

Resource review: the existing OS1.16 heap decoder and allocator tracing show
power-of-two blocks. The arp requests 8192 bytes once; currently used state ends
at 4500. A 4500-byte request still takes 8192 bytes. Packing it below 4096 would
require changing core tables or persistence buffers, with substantially more
regression risk than this UI fix. Retain the layout. No per-note arp allocation,
new hook, new state word, DSP patch or additional timer is needed for this fix.

## Verification and resource findings

- `arp-g-sensitivity-discovery-01`: original scaler instructions run under the
  configured CFV4E runtime. Slow positive/negative pulse streams are filtered;
  large turns remain responsive. The ready-state enum resource is retained
  privately with the probe. `resource-audit.json` compares all native payloads
  against the untouched R1 baseline at identical relocation addresses: only
  `encoder` and `rate_focus` differ. Clock, rates, notes, journal, save/load,
  allocation and other control payloads are identical under that comparison.
- Native source checks compare both mode and rate editing with independent
  calls into the actual stock scaler, including reversals, zero, fast turns,
  clamps and stock decay. Tiny motion and saturated boundaries preserve held
  notes without redraw; BUSY/DIRECT ignore edits without consuming accumulator
  state. G push clears partial motion. Legacy default MAIN remains exact.
  The required source regression suite passes (`arp-g-r2-regression-01.log`).
- `arp-g-r2-panel-01`: actual UART G turns/pushes select mode and all four rate
  positions; a single raw pulse leaves OFF unchanged. Original Tempo-menu
  input reaches 120 BPM. REC+PLAY followed by the held chord generates
  60,64,67,60,64,67,60,64, with eight stock captured trigs, eight native offs
  and no fault pages. STOP leaves no held owners or active gate. This is CPU
  control/recording evidence, with no SHARC audio render or physical feel claim.
- Runtime state remains one 8192-byte allocation, with used extent 4500 and
  no added state words. Native code grows by 56 bytes (encoder +42, focus +14).
  Padded cave use is 7936 of 9182 reviewed bytes, leaving 1246 aggregate bytes;
  cave fragments remain separately guarded by the builder. No new hook, timer,
  per-note arp allocation or DSP change. The scaler runs only on G input, so
  the periodic clock path gains no work. This is not a measured physical CPU
  utilization or real-time headroom result.
- The original project hash work still occurs on save/load, never per note or
  per G pulse, and uses the stock serialization buffer. Repacking state into
  4096 bytes or changing that hash/lifecycle would be a separate, riskier change;
  neither is needed to address this request. Full native project save/load is
  inherited from R1; this UI-only follow-up reruns native journal compatibility
  checks and proves those emitted routines unchanged, rather than claiming a
  new complete project lifecycle run.

## Package and reproduction

Private candidate:
`out/runs/arp-g-r2-package-01/EXPERIMENTAL_ARP_STOCK_OS1.16_TEMPO_RATE_R2.syx`.

- SYX SHA256: `54a7c9e93b07d56ce7279542b2b2b35896f1e77ff479e49796c7ce4aea551830`
- MAIN SHA256: `eec11e5201fa39b42d9b4919c05ff83b7f3973425783712a2d2a092b40121f44`
- R1 baseline source copies: `arp-g-r2-baseline-01`.
- Final source/test freeze: `arp-g-r2-freeze-01`; source hashes match the build.

Exact repeat, stock container reconstruction and protected/DSP-section checks
pass. `arp-g-r2-boot-01/boot.json` passes bounded 400M-instruction native startup
and static patch retention; state is still unallocated at that checkpoint, so
the separate ready-snapshot panel run supplies the playable-control evidence.
Original bootstrap depacking is recorded in the package's `device-depacker.json`
and final `release-verification.json`. Hardware knob feel requires a new user
trial. Previous firmware and failed development probes are preserved.

Use the Python in `.local/config.json` (scripts also re-exec it):

```sh
python3 -m unittest discover -s tests -p test_arp_tempo.py -v
python3 -m unittest discover -s tests -v
python3 scripts/check-arp-firmware.py out/runs/<fresh-panel> --tempo-ui --tempo 120 --rate 1/16 --mode up --record
python3 scripts/build-arp-firmware.py out/runs/<fresh-package> --tempo-ui --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-upload-depacker.py out/runs/<package> --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-arp-firmware-boot.py out/runs/<package> out/runs/<fresh-boot>
```
