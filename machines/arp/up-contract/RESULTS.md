# UP keyboard arp first experiment implementation results

> Status: source, host structural and host signal passed; device integration deferred

## Proposal and contract fingerprints

- Proposal: `docs/ARP-UP.md`
- Proposal SHA-256: `89292636d55e96a2b4f1cec74ac5e600754932da2354354074176943245549e3`
- Implementation contract: `implementation-contract.json`

## Commands and results

Commands, inputs, corrected failures and retained run paths are recorded in
[ARP-UP-RESULTS.md](../../../docs/ARP-UP-RESULTS.md). Audit, 154 source tests,
deterministic UP repeats, native OFF comparison, held-gate Stop, stock voice
replay and SINE regression exited successfully. The configured DigiKit Python
runtime was used. `out/runs/arp-up-summary-01/summary.json` records interpreter
identity, source hashes, artifact hashes and exact comparison results.

## Objective observations

Reverse-entered G–E–C yielded rising C–E–G. Releasing E left C–G. Twelve note-on
and twelve note-off events repeated exactly, as did complete control bytes and
ticks. All generated pitches reached stock DSP control frames 32 modeled samples
later. A separate sounding-gate Stop test emitted exactly one off and retained
suppressed-input ownership until release. OFF emitted no arp events and
preserved immediate stock G–E–C native calls. Unsupported track 2 stayed stock.

Two stock SHARC voice replays were byte-identical: 2.24 seconds, twelve nonzero
note intervals, all finite, peak 0.3230743408. Voice PCM is separate from final
output, real-time and physical-device evidence. No subjective listening claim.

## Corrections made during validation

The first capture's final input assertion included a pre-arm preparation press.
Added an armed-input boundary and reran; the retained failure is
`out/runs/arp-up-panel-01`. A unit expectation included an off whose deadline
lay beyond its capture endpoint; the endpoint expectation was corrected. No
implementation behavior or timing tolerance was relaxed. Subsequent stricter
control-frame checks and the held-gate Stop case passed in new directories.

## Evidence ladder

| Level | Result | Artifact or observation | Remaining limitation |
|---|---|---|---|
| Research | available | Sibling ARP-FEASIBILITY.md | OS 1.16 scoped findings |
| Proposal | available | Fingerprinted revision 1 | UP first; eventual ORDER/RANDOM |
| Source | passed | Core plus collection-wrapper audit, 1,426 bytes | Emulator-only placement |
| Host structural | passed | Ten native arp tests; 154 full tests; repeated actual CPU captures | Diagnostic clock/context adapter; requested transport events |
| Host signal | passed | Stock SHARC voice buffers, exact two-pass replay | No final mix/DAC proof |
| Target build | deferred | None | No packaged native firmware placement/link |
| Real-time | deferred | None | No physical scheduler or deadline measurement |
| Connected device | deferred | None | No hardware operation authorized/performed |
| Listening | deferred | WAV available | No subjective listening performed |
| Production integration | deferred | None | G control, recording/save, tempo/rate and permanent integration |

The validation plan retains its pre-implementation planned statuses so the ready
bundle validator remains a record of the gate taken before implementation.
This result table records the evidence subsequently obtained.
