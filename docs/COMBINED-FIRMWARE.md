# Combined experimental OS 1.16 firmware

The user authorized a local firmware build on 2026-10-08. This recipe combines
the existing validated Plaits R3, managed streaming Flex, and Capicola live
STRETCH R3 implementations. No DSP algorithm changes or hardware upload are
part of this build.

The CPU recipe is stock OS 1.16 → Plaits R3 → managed Flex → existing menu order
→ Capicola's six guarded sample-pool bounds. The managed/menu intermediate must
reproduce `bc034b810768979db5459b79b05a53ea62c6411bbb07e40c3de337a0129fdef6`.
The new reservation baseline is explicit; the legacy guard remains unchanged.
Every previous Flex/menu write must survive and only the six pool immediates
may differ from that intermediate.

The DSP recipe is the existing `capicola-stretch-live` / `reserved-state` build,
which already incorporates Plaits R3. It must reproduce
`0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf`.
There is no separate Capicola selector or RATE overlay. STRETCH remains type 2,
Plaits type 7, and MIDI type 5. Other playback paths retain stock dispatch.

Only MAIN section 3 and DSP section 7 are replaced in the owner-supplied stock
container. Acceptance requires exact repeat, independent decoder agreement,
protected-section parity, canonical transport/integrity checks, conservative
flash/staging bounds, actual bootstrap depacking, native allocator boundary
checks, bounded CPU startup/patch retention, source tests and SINE regression.
The manifest records source fingerprints and refuses drift during construction.

This is a **local experimental target build**. It does not establish physical
timing, coupled processor boot, permanent DSP instruction-memory ownership,
full STRETCH playhead bookkeeping, or complete Flex identity/GC lifecycle.
Capicola retains a shared 8 MiB reservation, 12-second eligible mono sources,
up to sixteen banks/thirty-two lanes subject to bank density, and stock fallback.
The project sample pool becomes 392 MiB. Flex retains its 32-identity boot limit.
Flashing or sending this package requires a separate user request.

```sh
python3 scripts/build-combined-firmware.py out/runs/UNIQUE \
  --elekloader-reference out/references/elekloader-upload-audit
```
