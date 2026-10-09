# Capicola reserved working memory

OS 1.16, 2026-10-08. **EVIDENCE:** the optional `reserved-state` build moves all combined Capicola/Plaits working state, constants, private stacks, wrapper scratch and the selector table into the existing 8 MiB sample-pool reservation. It does not remove any additional sample capacity or change the 12-second limit. Instruction code remains in L2; its permanent runtime ownership and physical timing remain unresolved.

The new working region is `0x9d12b9c8..0x9d15d9c8` (200 KiB). The maximum bank ends at `0x9d0c32f8`, leaving 427,728 bytes before working memory. A further 843,776 bytes remain between its end and the reservation end. Region checks reject overlaps, oversized code/constants, unknown layouts, unsupported build families and unreviewed generated address literals. Original DSP source files, pinned dependencies and legacy image bytes are preserved; relocation applies only to the optional generated assembly and linker placement.

The L2 loader payload shrinks from 466,944 bytes to the actual 64,588 instruction bytes at `0x20080000..0x2008fc4c`. Constants occupy 12,496 bytes inside the new external region. Separate event, preparation and voice stacks retain their prior relative bounds; the test-call stack has its own subdivision. Moving stacks and constants to external RAM may change physical memory latency, which the emulator instruction count does not model. This remains an explicit experimental build option rather than a performance claim.

`out/runs/capicola-resident-wire-02/report.json` passes the complete captured sample path: 1,620 stock LP0 callbacks, native sample assignment, automatic preparation, exact reference keys, later wire trigger, two matching mono lanes and the completed silent tail. Maximum signal error remains `1.4901161e-8`, RMS `1.0851376e-9`. A test pattern across all 204,800 bytes of the former L2 working region remains unchanged, and four stack-boundary guards survive. Preparation remains 151 further blocks for this 2,400-frame fixture. Reloading the same captured transfers after readiness clears publication, advances the bank generation and prepares again in 153 blocks. Reloaded keys and both playback lanes are byte-identical to the first pass. The external layout does not change the current loading schedule.

The repeat-build and stock compatibility check has passed 184 native frame comparisons across stock types 0/6 and all six Plaits models. The original controls build remains byte-identical to `ce51ec4c...2c5f`. `out/runs/capicola-resident-check-01/report.json` also passes two fresh DSP application-entry runs of 500 million instructions each, without a prepared DSP snapshot. Both finish at PC0xb863c5 with identical exported state. The code, relocated constants, selector and former-area test pattern remain unchanged. Actual RTOS heap headers describe five contiguous L1 blocks: two 4,008-byte stack allocations, two 96-byte task-record allocations and one 42,984-byte free block. These are bounded startup observations using the established peripheral/reset model, not coupled CPU/DSP startup or an exhaustive runtime-writer proof.

**RTOS mapping evidence:** task creation at SW `0xb8615d` calls allocator `0xb875c0` for stacks and task records. Its lazy initializer `0xb87577` establishes the L1 heap `0x2ca598..0x2d6d90`, outside the L2 instruction interval. The relevant decoded instructions are retained in `out/runs/capicola-arena-audit-01/rtos-heap.txt`. This identifies one real runtime owner; it does not prove the absence of every indirect or peripheral writer into L2.

Candidate BLOB SHA-256: `dcf9c499f09abecf0cad088d9bdd1e3073ef931fe90a3bd86b7df8649344643f`. MAIN stays `82b17a4f9068f47bef1b272205e3dc153e057fdb67a52db6a9726e5f09ceb8da`.

Reproduce with fresh output names:

```sh
python3 scripts/check-capicola-resident.py out/runs/capicola-resident-check
python3 scripts/check-capicola-wire.py out/runs/capicola-resident-wire \
  --capture out/runs/capicola-panel-08 --sample-load out/runs/capicola-panel-05 \
  --reserved-state
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

The unit suite passes 63 tests, including new memory-layout negative cases. SINE replay passes in `out/runs/20261008T040619Z-test-d51d9420/manifest.json`. The later sample-reload addition changes the wire test only; candidate DSP bytes remain identical. Result reports retain source hashes from each run; later result-document changes do not alter the candidate image. See [panel integration results](CAPICOLA-CONTROLS-RESULTS.md) for the inherited capture assumptions, mono/track limits, readiness and persistence gaps. No hardware firmware was sent, installed or published.
