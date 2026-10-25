# Arp project load and optimization results

OS 1.16; bounded DigiKit emulator prototype. Normal native menu import/recall, source tests and regression checks pass. The final musical repeat also passes under the same frozen sources.

Normal stock panel menus now bind saved-project recall to the native import's requested slot, the cache's authoritative node+0 slot, and the complete serialized v5 bytes passed to the decoder. Recall follows successful native import. Node+8 read bookkeeping can be stale after a save and is not an identity. A slot -1 live clone/export does not initiate saved-project recall.

Saved settings contain only the 128 pattern mode values. Loading closes the arp gate, stops its clock, and retains suppressed release ownership. It never restores held keys, an active gate, RNG progression or transport. Missing or corrupt settings default OFF. Recorded notes remain ordinary stock pattern data.

Card synchronization now imports dirty guest sectors and publishes only changed native sectors. GUI eMMC transfers publish only the sectors touched by that transfer. Alternating writes, deletion and snapshot replacement match the full-copy reference. Ten no-op transactions over 512 KiB took 1.317 seconds with the old full copy and 0.000863 seconds incrementally; no sectors were recopied. This is host timing, not physical storage or device CPU load.

Native card helper calls use separate diagnostic memory: stack top 0x61FFFF00 and a bounded 16 MiB scratch arena at 0x62000000. The current guest stack page and the old helper stack page, when mapped, are checked for unchanged bytes on each transaction. The earlier claim that the old helper address overlapped a live worker stack was not established: it was unmapped in the initial checkpoint. Isolation is explicit; no physical memory placement claim follows.

The menu runner waits for stock confirmation dialogs and sample-loader completion before another command. It compares the stable LOAD PROJECT row because the sidebar title can disappear after LOAD OK. Import return alone does not prove the loading screen has closed.

The full UP menu/record/save/diagnostic-reload/playback run matches the retained passing capture exactly: all control bytes, 2,120-byte arp state, 121,740-byte recorded pattern, and complete private card overlay. Native code remains 2,254 audited bytes. Prior voice PCM remains supported by this identical control stream; no new DAC or physical playback observation is claimed.

Scope remains audio track 1 at 102 BPM. Permanent firmware placement, variable tempo, more tracks/MIDI, project copy/undo/export/Transfer integration, companion cleanup, held-key transitions through broader views, on-device scheduling, hardware and release packaging remain separate work. No firmware was flashed, committed or published.

## Verification and reproduction

The final source freeze is `out/runs/arp-project-final-summary-01/freeze-final.json`.
`checks.json` records seven passing normal panel-menu imports: UP 0 → missing
companion slot 1 → saved slot 0 → slot 1 → corrupt companion slot 0, plus
separate ORDER and RANDOM imports. Every completed import preserves all
121,740 recorded pattern bytes. Correct mode vectors and stopped/empty runtime
state are checked. Each helper transaction also passes guest-stack protection.
All 180 source tests and SINE replay pass. SINE's final manifest is
`out/runs/20261014T234224Z-test-c62eb82b/manifest.json`.

From the lab, use fresh output directory names:

```sh
./labctl doctor
python3 scripts/capture-arp-modes.py out/runs/arp-new-up --record
python3 scripts/check-arp-project-load.py out/runs/arp-new-up out/runs/arp-new-load --negatives
python3 scripts/check-arp-record-save.py out/runs/arp-new-up out/runs/arp-new-independent
python3 scripts/profile-arp-storage.py out/runs/arp-new-profile
./labctl test sine --replay
```

The scripts select the configured runtime. Run the full `unittest discover -s
tests -v` suite with the Python recorded in `.local/config.json`. Menu tests use
modeled eMMC transfers on a private overlay; native sample transfer, physical
storage latency, audible playback and hardware are distinct evidence layers.
Import an existing overlay before mounting and advancing the guest, so native
filesystem caches do not retain the original card's directory state.

## Retained corrections and limits

Earlier bounded attempts remain in `out/runs/arp-project-load-probe-01` and
`arp-project-menu-*-01` through the numbered UP retries. They exposed bad dialog
assumptions, a test that stopped at import return instead of UI completion,
cache read-stamp misuse, and an overstrict guard that tried to read an unmapped
old scratch page. These are retained failures, not passing evidence. The earlier
SINE `20261014T232715Z-test-d4c19481` is a retained source-drift failure.
The proposed stock text-renderer hook did not identify these dialogs and was
removed. The runner now uses the fixture's actual panel geometry and menu row;
it does not claim a general UI automation interface for arbitrary project names.

Existing stock recording quantization is unchanged. Ordinary recorded gates
and the shortened final gate remain exactly preserved by native save/reload;
sample-exact preservation of performed note edges is not promised.

Final aggregation: `out/runs/arp-project-final-summary-01/summary-final.json`. The final musical capture is `arp-project-musical-complete-01`; all four retained parity hashes match exactly. Original SYX, MAIN, snapshot and read-only card hashes were checked again and are unchanged.
