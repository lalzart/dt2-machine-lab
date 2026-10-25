# Optional CAPI comparison toggle implementation results

> Status: revision 3 implemented; final validation outcomes in external results note

## Proposal and contract fingerprints

- Proposal: `docs/CAPICOLA-TOGGLE.md`
- Proposal SHA-256: `5905d5eb3ec060774b7fbba0744d7082cb480468a33aa88124fb0f0eb9d369be`
- Implementation contract: `implementation-contract.json`
- Normative R3, cache, preparation, reader and Plaits engine hashes remain unchanged.

## Commands and results

Use the exact commands and final artifact links in
`docs/CAPICOLA-TOGGLE-RESULTS.md`. Revision 1 startup failed because its append area is cleared by native reset.
Revision 3 executes the appended payload from the initialized SRAM tail; final
startup and repeated panel results belong in the external note. Earlier CPU and
panel run names below validate revision 1 routing/UI, not revision 3 placement.
All standalone scripts select the configured
Python 3.12 runtime. The ready validation plan remains the frozen preimplementation
registration; this results note records the observations separately.

- 144 source tests pass.
- `capi-toggle-cpu-03/report.json`: native formatter 65,536 raw values; native
  range/accessor, 153 permissions, 4,536 reverse mappings, 128 late repacks,
  560 title cases, status aging, original RX argument/result/CCR preservation.
- `capi-toggle-native-05/report.json`: native stock PCM exact, preserved R3
  PCM exact, sixteen distinct banks/mixed controls, retrigger policy,
  unsupported fallback, WAIT/READY/UNSUP/MIX status and 56 other-machine blocks.
- `capi-toggle-panel-03/report.json`: real encoder/storage/transport,
  ON base versus OFF stored lock preview, six native status enums replayed
  through original SPI2 receive driver; no CPU fault pages.
- `capi-toggle-build-smoke-05/manifest.json`: deterministic optional package.
- `capi-toggle-omitted-01/manifest.json`: original MAIN/DSP/SYX hashes exact.
- Final package, bootstrap depacking, separate startup and required SINE results
  are recorded in the external results note so this bundle remains frozen.

## Objective observations

OFF renderer PCM equals stock. Initial OFF master/DAC-ring output also equals
stock. ON renderer maximum error to R3 is zero in the fixture. Sixteen 512-frame
mono fixtures prepare in 558 further blocks. The bank cache uses 21,984 bytes at
the recorded end, within the unchanged arena. These are emulated observations,
not physical capacity, timing, listening or utilization measurements.

The first SRC page supplies encoder C and OFF/ON; the second SRC page supplies
the native waveform and last-received engine caption. Status cache ages are
excluded from musical-state comparisons. MIX uses an explicit two-lane fixture.
Native lock preview covers parameter storage/recall, not full project storage.

## Corrections made during validation

Retained smoke runs corrected a MAIN-end assumption, exact driver call target
and one strict relocation literal. Panel-01 exposed a native string-reference
ABI error; corrected code and native panel-02/03 pass. Native-02 checked trigger
transport one block too early; native-03 compared downstream tails against a
stock-only history; native-04 expected an active caption after a finite note had
completed. The final comparator preserves exact renderer comparisons and uses
actual native active flags. No numerical tolerance was relaxed.

## Evidence ladder

| Level | Result | Artifact or observation | Remaining limitation |
|---|---|---|---|
| Research | available | Preserved source lineage | No new algorithm claim |
| Proposal | available | Approved proposal hash above | Local scope |
| Source | passed | 144 tests, unchanged normative sources | Private firmware needed |
| Host structural | passed | CPU-03, panel-03 | Modeled peripheral boundaries and prepared checkpoint |
| Host signal | passed | Native-05 | Synthetic mono and captured LP0; no listening |
| Target build | passed | Smoke-05, omitted-01 | Final startup results in external note |
| Real-time | deferred | none | Physical DSP cycles/headroom unknown |
| Connected device | deferred | none | No transfer or hardware execution |
| Listening | deferred | none | No sound-quality assertion |
| Production integration | deferred | none | Existing lifecycle/bookkeeping and distribution gates |

The DSP startup audit isolates a dropped partial final word: one byte at
`0x200966e8`, with constants/selector exact. Revision 3 pads only the optional
loader code block to four-byte alignment. Assembled engine instructions and
core source remain unchanged. Final results are in the external results note.
