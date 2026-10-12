# Capicola sample-pool reservation results

2026-10-08, Digitakt II OS 1.16. The experimental MAIN now reserves eight MiB from the existing 400 MiB sample pool, leaving 392 MiB for ordinary samples. Compiled Capicola preparation and playback use that reserved range in the emulator. This does not rely on the unverified assumption that memory outside the stock sample pool is unused.

## Implementation

`lab/capicola_memory.py` accepts only the exact current Plaits R3/Flex/menu MAIN, guards six instructions and replaces their sample-pool limits. It updates free/total queries, the tail-allocation bound and two initial-allocation checks. Every other MAIN byte is preserved. The preview transfers beyond the original pool retain their original addresses.

The original logical sample range starts at 0x400 and ends at 0x19000400. New allocation end is 0x18800400. The verified stock sample-page mapping places the reserved range at DSP bytes [0x9ca2b9c8,0x9d22b9c8). The bank starts 256 bytes inside, at 0x9ca2bac8, so test sentinels also lie inside the reservation. The 6,912,048-byte maximum bank leaves 1,476,304 bytes after the leading guard.

`capicola-owned` is a separate DSP build family. The prior adapters now accept a compile-time bank base; their defaults reproduce the original Capicola BLOB exactly. The native count/write worker and reader arithmetic are unchanged. The service caller still controls source lifetime and schedules preparation; a firmware task has not been hooked yet.

## Evidence

- `out/runs/capicola-owned-cpu-02/report.json`: 42 native tail-allocation cases against stock/candidate,16 native empty-path branch cases, exact free/total queries, unchanged preview destinations, wrong-image rejection and delta coverage all pass. Stock accepts boundary allocations in the carved-out band that the candidate refuses.
- Full native tail-allocation function executes with empty or fabricated valid occupied tails. Three reference-copy/destruction helpers are stubbed; their identities are recorded. The initial-load/feasibility branch tests execute only the original bound branches, not full filesystem loading. This is deliberately narrower than a complete loader lifecycle claim.
- `out/runs/capicola-owned-hook-01/report.json`: native preparation writes exact oracle keys in the reserved range; three control cases match host audio with maximum error 2.24e-8. One hundred actual voice-entry blocks, six Plaits models on both lanes, eight audible stock fallback blocks, eleven invalid handoffs and deterministic builds pass. Twenty-three full captured frames with unpublished bank remain silent and fault-free.
- `out/runs/capicola-legacy-build-01/parity.txt`: original Capicola BLOB byte-identical to integration-03 after introducing the configurable bank base.

All 59 configured-runtime unit tests, focused Ruff and whitespace checks pass. SINE replay passes in `out/runs/20261008T003959Z-test-500f7fca/manifest.json`. Result notes were updated after the combined run; executable source is unchanged.

MAIN SHA-256: `7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3`.
Reserved-bank test BLOB SHA-256: `4b564e3a4b285d74bceebb4c5b435b90c4375933e09fd6f16ba7fc15f938ce7a`.
These are ignored emulator artifacts, not a packaged OS.

## Reproduce

```sh
python3 scripts/check-capicola-owned.py out/runs/<unique-cpu>
python3 scripts/check-capicola-integration.py out/runs/<unique-audio> --owned-memory
./labctl test sine --replay
```

The existing private Plaits/Flex/menu package is the exact MAIN baseline. All binaries stay local and ignored. Use a fresh allocator lifecycle: resuming a stock snapshot whose live allocations already exceed 392 MiB is not supported. Existing projects above that amount may exhaust sample capacity in this experimental build.

## Remaining work

Connect stock background scheduling, machine selection and parameter transport; verify selected-source replacement and reload through the actual loader. The reservation checks cover inspected allocator paths, not every firmware writer or physical DDR ownership. Full twelve-second native preparation latency, final mixer output, listening and hardware remain unverified. No firmware was flashed or committed.
