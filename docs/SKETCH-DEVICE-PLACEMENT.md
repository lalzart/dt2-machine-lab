# Sketch/BUF device placement experiment — OS 1.16

**Superseded DSP placement:** the initial `-07` DSP layout below overlaps ADI's
boot-kernel workspace. It is preserved as emulator evidence. The device recipe
now moves the gate state and rejects that overlap; use the `-09` build and
[boot-memory correction/results](history/sketch/SKETCH-DSP-BOOT-MEMORY.md) for current preparation.
The historical unchanged-DSP results below apply to the initial build only.

Local preparation for the existing Sketch ARM/FREEZE workflow. The new
`scripts/build-sketch-device.py` builds a standalone experimental MAIN and the
unchanged BUF DSP. It does not produce a SYX or access a device. This is the
next preparation stage after [combined DSP validation](SKETCH-VALIDATION.md),
not a change to the capture/publication algorithm or its measured latency.

## Layout and initialization

`lab/sketch_device.py` composes the final native install graph without a GUI
Machine, host recording commit or runtime code patcher. It keeps each inherited
arena's offsets, places the arenas consecutively, and adds a 256-byte canary
before and after each one. Preserving offsets retains local branches, structure
arithmetic and callback ABI; the initial reservation deliberately includes holes.

| Quantity | This profile |
| --- | ---: |
| Experimental CPU reservation | `0x47e9b000..0x47ef3000` |
| Reservation size | 360,448 bytes / 352 KiB |
| Native code, constants and initialized state payloads | 32,347 bytes |
| Stored segment data including internal padding and canaries | 205,324 bytes |
| Explicit zeroed tail storage | 154,612 bytes |
| Appended segment chain including headers | 205,868 bytes |
| Expanded MAIN | 3,481,484 bytes |
| MAIN staging ceiling | 4,193,280 bytes / `0x3ffc00` |

These are separate accounting categories. The reservation is not live heap use,
free-memory telemetry, or a reservation for recorded PCM. Stock CPU allocation,
DSP sample storage, immutable generation lifetimes and retirement fences retain
their existing rules. No memory-management feature is added.

The range follows the previously inspected OS1.16 CPU extension candidate above
stock data/heap and known DMA structures, below the preserved reset-stack margin.
It starts after the existing 64 KiB Arp/Flex reservation. See the
[CPU extension notes](CPU-EXTENSION-EXPERIMENT.md) and their linked original
address/alias investigation. This is an experimental engineering bound, not
proof of permanent physical ownership or worst-case stack/cache/DMA behavior.

The existing 54-byte reset loader copies initialized segments and zeroes BSS
before calling the original data-copy/clear helpers. Stock SRAM initialization
source remains exact. Code is installed before cache enable; there are no new
runtime executable writes. Fresh reset initializes epoch=1, empty registries,
idle jobs, NORMAL recorder destination and Sketch's independent BUF=1 preference.
Preference survives view close/reopen within the session and resets on reboot.

Relocation operates on independently audited ColdFire instruction boundaries:
only the reviewed long extension operand is eligible. Pointer tables/vtables
are classified explicitly; text, identities, local branches and stock addresses
are preserved. Unknown synthetic addresses, unsupported encodings, overlapping
payloads, duplicate hook owners, unexpected stock bytes and bounds violations
refuse the build. There are 1,158 recorded operand/table/hook relocations.
Authenticated stock trampoline prefixes are kept exact and their jump tails
are audited separately. The padded worker FINISH dispatch/body are classified
as separate code ranges.

The DEST cell/filter emitters moved unchanged into
`lab/recorder_destination.py`, shared by the existing emulator installer and the
device builder. Existing imports remain available through the earlier modules.
`segment_chain` accepts an explicit bounded reservation; its default remains
the original 64 KiB profile. Existing Flex and all-feature builders are unchanged.

## Separate profile and remaining gates

BUF and the packaged Flex R5 implementation own several of the same resource,
recorder, save and loader hooks. Independent data addresses do not resolve that
conflict. This builder requires exact stock MAIN and exposes no all-feature
option; it cannot be applied on top of Flex, Arp, Plaits or Capicola builds.
The original profiles remain the baseline for those features.

The DSP rebuild retains the accepted BUF observer/receipt/retirement blob:
`db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7`,
339,070 bytes. Its SHARC arenas are unchanged. Loaded-image overlap checks and
earlier prepared DSP results do not establish board ownership of every arena
or full coupled cold initialization. Both CPU and SHARC physical placement,
aliases, cache/DMA behavior, worst-case stacks, load pressure and hardware
startup remain qualification work.

The native boot check is CPU-only with modeled peripherals and an authenticated
stock container replaced by MAIN before its first reset instruction. It is
distinct from booting the paired CPU/DSP image, decoding a full candidate SYX,
or installing firmware. The subsequent [device-address validation](history/sketch/SKETCH-RELOCATED-VALIDATION.md)
passes the prepared coupled recording/FREEZE workflow with code/canaries intact
and no old-arena accesses. Paired cold startup and physical ownership remain open.

One presentation limit remains in the legacy recorder: its stock ready-page
label stays `Y:SAVE` even with DEST=BUF. The emulator's conditional label change
was host presentation code and is deliberately not represented as native device
behavior. Sketch's own menu and labels are native. Preview, persistence, other
capture lengths and broader machine/retirement support remain outside this step.

## Reproduction and evidence

Use fresh ignored run directories and the configured interpreter. No dependency
pin changes or hardware connection are needed.

```sh
./labctl doctor
./labctl unit buf core integration
python3 scripts/build-sketch-device.py out/runs/sketch-device-build-FRESH
python3 scripts/check-sketch-device-boot.py \
  out/runs/sketch-device-build-FRESH out/runs/sketch-device-boot-FRESH \
  --native-upstream <clean-inspected-digikit-ed57b475-checkout>
./labctl test sine --replay
```

The native adapter is the same explicitly inspected, read-only revision used
for the previous CPU extension experiment, `ed57b4758d45d435d07da37ce06b4090afab843b`,
with Rust 1.98.0 and offline cached dependencies. Pinned lab dependencies stay
unchanged. Firmware images, captures and generated native runners stay ignored.

The evidence index for this step is
`out/runs/sketch-device-placement-20261023-01/verification.json`.
The source installer comparison passes all 282 payload blocks and 28 hooks,
performing zero recordings. 224 BUF/core/integration tests and focused Ruff pass.
The build must repeat exactly. The cold check poisons target RAM, validates
every copied segment and zeroed tail, checks source erasure and canaries, uses
ordinary panel input, and requires disabling only the reset loader to fail.
Earlier failed setup checks remain preserved: they expected SONG to bypass the
stock FILE SYSTEM OK modal, and one incorrectly waited for the adapter's lazy
input-ready flag before supplying any input. A later check reached and rendered
Sketch, then exposed that the stock encoder scaler needs repeated detents.
These are setup/test failures; they consumed no recordings and did not require
changing the native firmware payload.

The final build is `out/runs/sketch-device-build-20261023-07/`; MAIN SHA-256 is
`cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c`.
The original default Arp/Flex CPU extension still builds byte-exact to
`57f6c6911ae65164b42ea6d0a45be23d67d6f2d7a37442cae8ceccf682d452e7`.
Final-source SINE replay passes at `out/runs/20261023T010836Z-test-52f748f0/`.
Build, boot, stream and SINE source hashes agree. Only the shared segment-chain
bound and the two UI modules exporting the factored DEST emitters change among
inherited source files; existing DSP and BUF behavior emitters remain exact.
The final native boot run is `out/runs/sketch-device-boot-20261023-06/`:

- Ready at modeled instruction 961,866,419; the complete check ends at
  1,190,365,087. These counts are not physical CPU timing.
- All 45 copied/zeroed/canary segments match after reset clear, poisoned BSS
  is cleared, and the original appended source is erased.
- SONG respects the stock startup modal. After ordinary NO dismissal, SONG
  opens Sketch and its native drawing helpers render the menu from relocated
  callbacks/vtables. Encoder A changes the single BUF preference; it survives
  normal SONG close/reopen. No recorder or FREEZE job is submitted.
- All 30 canaries and all classified code/hook bytes remain exact after panel
  interaction. The separate no-loader run detects absent segment copying.

The compressed-stream check also passes using the actual OS1.16 routines:
the bootstrap depacker reproduces all 3,481,484 MAIN bytes from a 1,399,896-byte
stream. MAIN's DSP depacker reproduces all 339,070 DSP bytes from 210,444 bytes,
preserving command byte 3 and the canary after its actual 1 MiB allocation.
Decoded DSP plus command leaves 709,505 bytes of headroom; oversize input and
output controls refuse. These checks use the exact local binaries and create
no candidate SYX. Reproduction helper and results are retained as
`out/runs/sketch-device-placement-20261023-01/verify-streams.py` and `streams.json`.

![Sketch rendered after native CPU cold startup](../out/runs/sketch-device-boot-20261023-06/sketch.png)
