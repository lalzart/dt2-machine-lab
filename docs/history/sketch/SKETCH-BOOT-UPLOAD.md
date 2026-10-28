# Sketch DSP boot stream and CPU upload — OS 1.16

The boot-format audit found three defects that the flattened emulator loader
bypassed: six added blocks followed the stock FINAL marker, the gate's literal
payload was 8,286 bytes rather than a multiple of four, and the second FIRST
header retained its old next-application span. The boot ROM stops at FINAL;
the CPU sender continues sending the section. This can hang boot on the ready
handshake. The previous boot-workspace correction was necessary but insufficient.
No affected image was sent to hardware in this work.

The device recipe now inserts the additions before the unchanged stock FINAL,
pads the gate payload with two zero bytes, and repairs the FIRST span/checksum.
Every previous loaded byte, address, FILL, INIT and entry point is preserved;
the whole stock init application remains byte-exact. The CPU MAIN is unchanged.
BUF/FREEZE algorithms, identities, allocation policy and the existing Flex
profiles are unchanged. The ordinary prepared-emulator DSP and its metadata
remain byte-exact; preserving that historical profile does not make its stream
suitable for a physical boot.

`lab/sketch_dsp_device.py` now checks the entire stream before accepting it:
header signatures and XOR, supported flags, lengths, load/count alignment,
FIRST/FINAL ordering, next-application spans, boot-workspace exclusion and the
CPU's decoded-size ceiling. It refuses malformed input instead of stopping
silently. Two focused regression cases in the existing device test module
cover serialization/payload preservation and malformed-stream controls.

The rules are from the public
[ADSP-2156x Hardware Reference](https://www.analog.com/media/en/dsp-documentation/processor-manuals/adsp-2156x_hwr.pdf),
chapter 40, printed pp.40-39–43 and 40-85. The FIRST span is a retained stock
convention, rather than a demonstrated SPI-slave ROM check. ADI also documents
the [active-low SPI ready handshake and command 0x03](https://ez.analog.com/dsp/f/q-a/541744/adzs-21569-ezkit-spi-slave-boot).

## Validation boundary

`scripts/check-sketch-boot-upload.py` uses read-only DigiKit native upstream
`38dfbe4ae88263511eed95691c07fc07e17b6f26`, leaving lab dependency pins intact.
Its independent Python checker and Rust `patchkit::bootrom` checker accept the
stock and corrected streams and reject the old `-09` stream. Neither executes
the actual ROM binary. Their agreement is a documented-rules check, not proof
of undocumented silicon behaviour.

The native CPU executes the OS1.16 application-reset path, allocation, section-7
lookup, flash read, actual MAIN depacker, byte sender and cleanup. It sends
command 3, the complete candidate DSP stream and one terminal frame. Every
PUSHR write is captured and compared byte-for-byte. A host-driven busy GPIO
holds it before the command and during the transfer; the CPU must remain in
its polling loop without advancing its pointer or writing, then resume exactly
after release. Upstream forces the DSPI transfer-complete status. No physical
FIFO depth, SPI timing or ROM receiver is simulated by this probe.

The ignored full candidate container is independently checked for exact MAIN
and DSP contents, protected sections, transport integrity, seal, reserved bytes,
flash extent, bootstrap in-place MAIN depack and DSP staging bounds. A direct
native construction from that container currently fails before execution:
upstream searches decoded MAIN bytes for a startup signature whose entry is
intentionally replaced by Sketch's polling hook (`mainloop signature ambiguous`).
The later migration audit establishes zero matches, rather than duplicates;
the earlier duplicate-code explanation was incorrect. This is an emulator
constructor limitation, not an observed CPU boot fault. The opt-in reference
constructor described in [native migration](../../NATIVE-BUF-MIGRATION.md) addresses it.

The bounded native sender probe therefore constructs the CPU from a separate
stock-MAIN container carrying the exact candidate DSP section, then installs
the exact candidate MAIN before instruction zero. Flash reads and section-7
depacking are native; the CPU MAIN installation is a harness action. The full
candidate container is checked separately. This does not establish unmodified
whole-container native startup or execution of the physical bootstrap.

The CPU sender has no ready-line timeout. The busy holds prove a bounded stall
and recovery when the model releases ready; they do not prove device recovery
from a ROM error. The command-plus-stream tail is not a multiple of 1,024 bytes
(the stock stream also has a short tail). Actual FIFO/ready-line tail acceptance,
ROM execution, physical memory/cache/DMA/stack ownership, recording timing and
listening remain open. No firmware is flashed, transferred or published.

## Reproduction

```sh
./labctl doctor
python3 scripts/build-sketch-device.py out/runs/sketch-device-build-FRESH
python3 scripts/check-sketch-boot-upload.py \
  out/runs/sketch-device-build-FRESH out/runs/sketch-boot-upload-FRESH \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
./labctl unit buf core integration
./labctl test sine --replay
```

Use fresh ignored output directories. The runner selects configured Python
3.12, authenticates private fixtures and upstream revisions, freezes sources,
builds offline, bounds execution and refuses source drift. Reuse saved native
BUF pages for backend controls; no new recordings are needed for this change.

The old `-07` and `-09` artifacts remain evidence for their recorded application
or prepared-state layers. They must not be used as boot-qualified candidates.
The separate [coupled application startup](../../SKETCH-COLD-STARTUP.md) results retain
their original scope and image hashes.

## Results — 2026-10-23 JST

Current sealed build: `out/runs/sketch-device-build-20261023-13/`.
The [evidence index](../../../out/runs/sketch-rom-upload-20261023-07/verification.json)
and [upload report](../../../out/runs/sketch-rom-upload-20261023-07/report.json)
pass with the explicit limits above.

| Image | SHA-256 |
| --- | --- |
| MAIN, unchanged | `cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c` |
| Corrected DSP stream | `2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a` |

The 110-block stream is 339,072 bytes, packed to 210,652 bytes. Including
command 3 leaves 709,503 bytes in the actual 1 MiB output allocation. The
stock init application and every prior loaded byte are exact. Only the gate's
literal block grows, from 8,286 to 8,288 bytes. The full local test container
is 2,234,528 bytes, with protected sections intact, positive in-place MAIN
depacking gap and flash end `0x22e720` below the guarded ceiling `0x380000`.
Those are local packaging checks, not physical bootstrap execution.

The native sender produces 339,073 data frames including command 3, followed
by one `0x18000000` terminal frame. Captured data-frame controls are
`0x90010000 | byte`. The two 100,000-instruction busy holds occur before the
first byte and after 11,766 bytes. Neither advances the pointer or emits a
PUSHR write. Release resumes the exact complete byte stream; allocation cleanup
finishes and the sender returns success. These instruction counts are emulator
observations, not physical timing. The full-container constructor limit is
reproduced and recorded in the same final report.

All 15 prepared native DSP seal/refusal controls pass on these exact DSP bytes,
using the existing saved pages and no new recording. All 229 BUF/core/integration
unit tests and focused Ruff pass. SINE compatibility passes at
`out/runs/20261023T024134Z-test-ebd7f228/`. That replay finished before the final
two standalone upload-validator files were adjusted for the constructor limit;
the evidence index verifies that all other sources, including DSP/CPU emitters,
runtime and SINE paths, remain exact. The final upload run freezes and verifies
the complete current source manifest. No repeated recording/stress suite is used.

Earlier runs are retained. Initial harness attempts caught a copied runner's
missing executable mode and a one-million-instruction cleanup budget that was
too short after a complete transfer. The bounded final cleanup allowance is
20 million instructions. Intermediate positive sender runs pass; the direct
candidate-container attempt is retained at `sketch-rom-upload-20261023-06/`
with its constructor error. These do not establish device failures or ROM
execution. The final runner, lockfile, transmitted bytes and PUSHR trace are
preserved in `sketch-rom-upload-20261023-07/`.
