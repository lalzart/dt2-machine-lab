# Combined Sketch, Capicola R2 and selected-track ARP

Local OS1.16 build requested on 2026-10-27. Use the current managed Sketch,
assignment popup and early-buffer startup profile, the latest retained author
Capicola port (R2, archive SHA-256
`87bb2b073dae7253d7694198eced9a63ea4313373eb5ac1573902560cf19ad23`), and the
existing selected-track/stopped keyboard ARP. No new synthesis algorithm,
Plaits machine, legacy Flex UI, buffer persistence or hardware upload.

Integration design: keep Sketch's installed hooks and loader-owned arenas;
place ARP in its existing separate DDR interval. Chain the four shared CPU
boundaries explicitly (GUI tick, main key handler, project save and load).
Keep Sketch's refusal/ownership checks ahead of ARP and native continuations.
Reuse the authenticated CAPI parameter/UI payload, with a stock-only machine
descriptor fallback. Retain its 8 MiB sample-pool reservation. Place only the
Capicola author engine and support state in the DSP, moving its cold code to
free L2 at 0x200b0000 so Sketchbook readback at 0x200a0000 remains intact.
Preserve original author files and notices; generate relocation changes only
inside ignored build output.

Validation must check explicit hook/region conflicts, disabled/default build
identity, source repeat, package decoding and CPU staging bounds, CAPI versus
its retained native PCM oracle, ARP selected-track/stopped behavior, and the
combined cold-boot Sketch capture/FREEZE/assignment/export workflow. Emulator
results do not establish physical timing or listening quality.

Existing BUF retirement remains conservative: automatic reclamation requires
ONESHOT tracks. Adding CAPI does not broaden that reader qualification. This
integration must not weaken those guards to make a combined build appear to
work; mixed-machine lifetime qualification remains a separate issue.

Reproduce with `python3 -B scripts/build-sketch-combined.py
out/runs/<fresh-name>`. The builder selects the current managed Sketch flags,
including the assignment popup, loading labels and early BUF setup. It creates
a local SysEx and records source, dependency, MAIN and DSP hashes.

The CAPI switch remains at encoder C on the STRETCH SRC page: OFF uses stock STRETCH; ON
uses the retained author port. ARP remains in FUNC + KEYBOARD: G selects mode,
and pushing G switches between mode and rate. One keyboard arp follows the
selected track, including when transport is stopped. Existing ARP configuration
storage is retained; unsaved BUF audio and its preferences remain volatile.

The supplied `/Users/lanceship/Films/dt2-capicola-main` snapshot matches all 66
retained upstream files and their build-manifest hashes. This integration uses
the author's release-default STRETCH engine; it does not include the standalone
repo's REPITCH, SLICE/GRID modes, extended BARS or full UI2 changes.

The first combined package accidentally omitted the separate `capicola_ui`
switch layer, leaving the older CFADE knob drawing callback. The corrected
builder reuses the guarded stock AMP RSET switch template from the accepted R2
port. Only two MAIN bytes at 0x401c267e–0x401c267f change; the complete DSP image,
parameter transport and other CPU behavior remain byte-identical. The original
package and its validation reports below are retained as the pre-fix baseline.

Validation on 2026-10-27:

- 386 BUF/core/integration/ARP/Capicola tests pass, including generated-linker
  isolation and invalid cold-memory placement controls.
- `sketch-capi-arp-build-20261027-02` and `-03` reproduce identical MAIN, DSP,
  SysEx and CPU layout metadata. The default Capicola compilation remains
  byte-exact against the authenticated earlier R2 package.
- `sketch-capi-arp-oracle-20261027-01` passes the published host tests and the
  native audio oracle. `sketch-capi-arp-routing-20261027-01` passes all-track
  CAPI routing, stock OFF/output parity, native stock-machine parity and the
  300-block final-ring causal mute control.
- `sketch-capi-arp-cpu-20261027-01` executes the CAPI descriptor/formatter and
  bounds, stock descriptor fallbacks, chained stopped ARP on T16/T8, and the
  real MAIN DSP depacker. Decoded DSP is 411,896 bytes, leaving 636,679 bytes
  in the staging allocation after the command byte; its canary stays intact.
- Actual bootstrap decoding of sections 8/3/7 passes. SINE replay passes at
  `20261027T134515Z-test-b98e3343`.
- `sketch-capi-arp-native-20261027-01` passes the coupled CPU-reset/SHARC-entry
  record, popup NO/T16 assignment, per-BUF settings, FREEZE, preview, native
  save, injected readback failure and retry workflow. Code and arena guards
  remain intact. This model excludes DSP ROM/upload and physical timing.
- `sketch-capi-arp-native-panel-20261027-01` passes cold-boot native panel
  selection on T16 and T8, G mode/rate editing and push focus, stopped UP and
  ORDER sequences, release handling and arena guards. Notes are observed at
  the original firmware note endpoint; no host arp chooses or schedules them.

The older prepared ARP panel adapter cannot accept Sketch's additional DSP
transactions and stopped at its fixed-frame-size assertion. That is retained
as `sketch-capi-arp-panel-T16-20261027-01`; it is not a passing check. The native
coupled panel adapter in `sketch-capi-arp-native-panel-20261027-01` uses the same
actual package and existing recorder/SHARC transport. Its source and recipe
are retained under ignored output, separate from the pinned dependency.

No physical upload or listening test was performed. Exact release hashes and
report identities are recorded beside the delivered SysEx.

Switch correction validation on 2026-10-27: 141 core/integration/Capicola tests,
exact independent repeated builds, combined CPU/MAIN-depacker checks and actual
bootstrap section 8/3/7 decoding pass. The native CPU reset probe executes the
real callback clone: the corrected build installs the switch manager/invoker;
the original build is the negative control and installs the knob pair. Each
clone retains its own allocation and leaves the template unchanged. Reports
are under `out/runs/sketch-capi-switch-{verify,cpu,native}-20261027-01`; build
outputs are `sketch-capi-switch-build-20261027-01` and `-02`. This is initializer
execution evidence, not a fresh panel rendering or hardware test. The broader
audio/workflow checks above belong to the pre-fix baseline; the new package's
DSP is byte-exact and its only CPU difference is the two-byte switch operand.
