# Arp integration results

> Status: prototype — native emulator controls, recording/storage and host voice PCM verified; stock recording quantization and GUI recall limits remain explicit.

## Proposal and contract fingerprints

Proposal: docs/ARP-INTEGRATION.md; SHA-256: b7ca385299c155efceed8cfc967f754f4c87a9a0ed835285c6b0003c9e5ffd57

## Commands and results

See `docs/ARP-INTEGRATION-RESULTS.md` for exact commands, behavior, retained
failures, corrections and version boundaries. `out/runs/arp-integration-summary-01/summary-final.json`
authenticates the final source freeze, test sources, native instruction audit,
three complete menu/record/save/recall captures, independently decoded patterns
and unchanged firmware/snapshot/card inputs. All 171 source tests and the final
SINE regression pass. Before/after the unbound-GUI-load guard, all three modes'
control bytes, native state, recorded pattern and card-overlay bytes match.
The preceding `summary.json` retains the exact UP repeat and OFF comparator.

`arp-integration-core-01/core.json`: 2,254 audited native bytes, 2,120 state bytes.
`arp-integration-audio-01/replay/render.json`: eight intervals, 1.484 seconds,
finite/nonzero/nonclipping, peak 0.3230743408, two native replays byte-identical.
No final mixer/DAC, listening, real-time or physical-device result is claimed.

## Evidence ladder

EVIDENCE: source, native emulator CPU/UI/control, original project/file APIs,
exact full decoded runtime-pattern equality and native stock voice-buffer PCM.
Mode recall is checked through the explicit diagnostic API; normal GUI project
load defaults OFF until its companion slot is authenticated. Stock recording
preserves recorded duration bytes on save/reload, but very short performed
notes and onset timing are subject to the recorder's quantization.

Documentation backfill occurs after captures; it does not change their recorded
code hashes or the approved proposal fingerprint.
