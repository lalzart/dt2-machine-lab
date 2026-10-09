# Flex finalization scope — 2026-10-08

The current bounded native build remains reproducible from the current sources.
All 95 source tests pass. The managed MAIN is still
`562061c4c17d86d7eec0c9e12fbb3455b865131d39502128c42b39c1d573a19a`;
the existing combined SYX remains
`c01bdc72cd82a76e55ad77e4892c1a9b9e717fb70ebd84c10048ff4562eab06d`.
The [streaming results](FLEX-CAPACITY-RESULTS.md) remain the behavioral evidence
for that image. No firmware/native feature changes or device upload occurred in
this recheck. Evidence is in
`out/research/flex-finalization-2026-10-08-01/recheck.json` and `source-tests.log`.

The user's "let's finish it" can describe either finalizing this bounded build
or completing the remaining memory manager and removing the boot-lifetime limit.
That scope clarification is pending. The latter is a functional redesign, not
a packaging step or a safe constant-only cap increase.

Read-only OS1.16 disassembly confirms that `ProjectSettings::reloadAllSamples`
calls the stock slot reset at `0x4004e976` when its reset flag is set. The earlier
native lifecycle experiment also establishes that an already-open synthetic
handle remains readable after stock slot clear. Consequently slot emptiness does
not establish that a logical take identity or descriptor is unreferenced.
The raw absolute-call scan is not exhaustive callgraph or concurrency proof.
Disassemblies and the scan are retained beside the recheck report.

The stock file handle is four words: resource ID, position, a word initialized
to zero on reference-open, and an open flag. Stock close clears the open flag
before releasing its owner. Current synthetic handles retain boot-owned
descriptors and do not yet establish a generation/lease protocol for recycling.
These inspected ABI facts identify prerequisites; they do not authorize reuse.

Twenty-second mono/stereo, recorder USE, explicit named Save As, automatic
project persistence, saved-source reclamation, 32 KiB backed Save As and the
Plaits-before-MIDI display order are already implemented. Still open: full
project/undo/clipboard/pending-consumer roots, bounded identity recycling and
project epochs, protected stock-demand headroom, and physical-device validation.
Unreferenced unsaved-take reclamation must remain conservative until those roots
and completion boundaries are established. No cap or unknown lifetime was
silently changed to label the broader design complete.
