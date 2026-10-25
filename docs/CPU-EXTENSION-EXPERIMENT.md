# CPU extension experiment — OS 1.16

This opt-in build places native Arp and managed Flex together in DDR, with one
project-save dispatcher. It is a local emulator experiment. No firmware was
sent to a device, committed or published. Plaits and CAPI are not included;
section 7 remains the original stock SHARC image.

The preceding [extension investigation](../../Digitect%20firmware%20research%20project/work/cpu-extension-research-20261017-01/REPORT.md)
identified a candidate above stock BSS, the fixed buddy heap and known DMA
buffers. This experiment reserves only `0x47e8b000..0x47e9b000` (64 KiB).
That reservation is an engineering bound, not a measurement of all free RAM.
Physical ownership, worst-case stacks and cache behavior remain unverified.

| Resource | Experimental build |
| --- | ---: |
| DDR reservation | 65,536 bytes |
| Arp, Flex and shared CPU payloads | 15,217 bytes |
| Stored segment data, including metadata and canaries | 16,096 bytes |
| Explicit zeroed extension BSS | 4,096 bytes |
| Appended chain, including segment headers and terminator | 16,136 bytes |
| Early loader in original cave | 54 bytes |
| Decoded MAIN | 3,291,752 bytes |

These figures describe different things and must not be added as live RAM
usage. Arp still requests its existing 8 KiB state from the stock heap; Flex
PCM and descriptors retain their existing allocation/lifetime rules.

## Implementation

`lab/cpu_plan.py` separates guarded stock writes from allocated payloads. Both
native builders expose `plan_cpu`; their ordinary `patch_cpu` paths still use
the original caves and reproduce their previous image hashes. A namespaced
allocator gives each experimental component explicit, disjoint addresses.
External payloads cannot be applied through the ordinary in-image writer.

`lab/cpu_extension.py` validates aligned, bounded, nonoverlapping
`[data size, destination, BSS size, data]` segments and emits a terminator. The
54-byte ISA_A loader copies them before the original reset clear destroys the
appended source. It then calls the original copy and clear helpers once, in
order. Original SRAM-copy data stays unchanged. Loading happens before stock
cache enable; no runtime executable-code updates are introduced. The loader
trusts the builder-validated, sealed chain and does not accept external input.

The algorithm follows the inspected
[DigiKit expansion loader](https://github.com/ElekLabs/digikit/blob/ed57b4758d45d435d07da37ce06b4090afab843b/modules/core/expansion/src/cf/loader.s).
It uses this lab's guarded instruction emitter/auditor rather than changing
the pinned dependency or adopting a new linker/backend.

There is one stock save hook: Arp prepare, Flex prepare, the original writer,
Arp commit, and unconditional Arp cleanup. Existing failure/status semantics
are retained. Private standalone wrappers remain in this first payload but
do not own the shared hook. A small wrapper counts real heartbeat calls from
the stock main loop while preserving registers and incoming condition codes.
Three stored canaries surround the payload and reservation boundary.

Dense placement exposed a real UI descriptor defect: the stock masked bitmap
blitter reads a sixth word at `+20`; the original five-word blank descriptor
implicitly consumed adjacent padding. The experimental layout supplies an
explicit pointer to its blank mask. Standalone image bytes remain preserved.

## Reproduction

Use the configured Python 3.12 environment; `labctl` and the scripts select it.
Every output name must be fresh. No dependency pin needs to change.

```sh
./labctl doctor
python3 scripts/build-cpu-extension.py out/runs/<package> \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-cpu-extension-boot.py out/runs/<package> out/runs/<boot> \
  --native-upstream <clean-digikit-ed57b475-checkout>
python3 scripts/check-upload-depacker.py out/runs/<package> \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-arp-firmware.py out/runs/<arp> --cpu-extension \
  --tempo-ui --shared-save --mode order --tempo 120 --record --storage \
  --instruction-limit 12500000000
python3 scripts/check-flex-lifetime.py out/runs/<flex> --cpu-extension \
  --managed-sources --shared-save --frames 960000 --stereo --heap-trace
./labctl test sine --replay
```

Run source tests with the configured interpreter:
`python -m unittest discover -s tests -v`.
The source suite verifies old standalone hashes, unknown-source rejection,
alignment, bounds, alias rejection, overlap rejection, explicit bitmap mask,
actual combined write coverage and one save-hook owner.

The native reset adapter explicitly requires the inspected upstream revision
`ed57b4758d45d435d07da37ce06b4090afab843b`, Rust 1.98.0 and cached Cargo
dependencies. It builds offline and records its generated Cargo lock and
runner hashes. The lab's pinned dependencies remain unchanged. It resolves
host observation addresses from authenticated stock and replaces guest MAIN
before the first reset instruction, preserving the experimental reset hook.
Disabling only that hook must fail the segment comparison; the checker runs
that causal negative automatically.

The Arp and Flex scenarios install the actual combined CPU writes into
authenticated prepared stock fixtures. They are component/lifecycle checks;
the separate reset test is what verifies loading from the packaged MAIN.
Physical recording input and stock DSP communication are modeled in those
fixtures. Exact results and artifact identities are in `CPU-EXTENSION-VERIFICATION.json`.

The final private package is
`out/runs/cpu-extension-package-20261017-07/EXPERIMENTAL_CPU_EXTENSION_ARP_FLEX_OS1.16.syx`.
Its SHA-256 is `fe06bf0a53312fc3eca2b87b61bbe9084f59297523d1db2dccf1e08182749a39`;
MAIN is `57f6c6911ae65164b42ea6d0a45be23d67d6f2d7a37442cae8ceccf682d452e7`.
Container framing/authentication, stored protected-section equality, two
decoders, exact repeat and original bootstrap depacking pass. The depacker
record uses package-04, whose complete candidate bytes match package-07.

All 223 source tests, focused Ruff checks and stable-source SINE replay pass.
The combined prepared Arp scenario preserves all 121,740 pattern bytes,
restores mode/rate and replays `67, 64, 60, 67, 64, 60, 67, 64` after normal
project-menu recall with no fault pages. The 20-second stereo Flex scenario
passes PCM equality, delayed-handle reads, save-backed handover/retirement,
Save As, invalid/missing backing controls and stock-backed reload. Both use
the exact final MAIN. Their prepared-fixture checks do not establish a single
both-active project roundtrip or coupled DSP operation.

The native reset check reaches ready at instruction 961,611,177 and runs a
further 20 million instructions: 39 original main-loop calls enter the DDR
wrapper, Arp obtains its normal heap state, all code and three canaries remain
intact, all loaded segments match at reset return, deliberately poisoned BSS
is cleared, and the appended source is erased by stock reset clear. This is a
MAIN reset test with modeled boot peripherals, separate from installing or
physically booting the SYX. An independent native call check runs the real
stock copy/clear helpers without reset-loop acceleration and preserves the
callee-saved registers across 32,373,762 instructions.

## Remaining boundaries

- The original profile did not test a both-active save/recall session.
  The later [all-feature profile](ALL-FEATURES-EXPERIMENT.md) now passes that
  scenario, including recorded-note replay and exact Flex transfer equality.
- Full coupled CPU/SHARC cold startup, sample-load pressure, USB/Overbridge,
  old-project conversion and worst-case task/interrupt stacks remain open.
- The newer native emulator at the inspected upstream revision rejects this
  combined SYX during host signature resolution (`mainloop signature ambiguous`)
  because the main-loop entry is patched. The explicit lab adapter described
  above handles host observation addresses without bypassing guest hooks.
  Direct constructor support remains upstream work; no dependency source or
  pin was changed.
- This original Arp/Flex profile places its loader in the Plaits CPU cave.
  The later [all-feature profile](ALL-FEATURES-EXPERIMENT.md) preserves Plaits
  there and moves the 54-byte loader to a separate reviewed gap instead.
- Emulator instruction counts are not physical CPU cycles, cache coherence,
  DDR timing or device readiness. A hardware trial requires a separate request.
