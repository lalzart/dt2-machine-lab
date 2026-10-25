# Track routing state-by-operation matrix

> Status: ready

Exact requirements in docs/ANY-TRACK-FEATURES.md.

| Operation | Controls | DSP/audio state | Buffers | Random/scheduler | Provenance/UI | Timing and failure |
|---|---|---|---|---|---|---|
| Initialization | ARP OFF/1/16; stock Plaits defaults | Zero independent lanes | Existing reservation | Original seeds | Native views | No new allocator |
| Reset | Existing defaults/recall | Reinitialize native owned state | Existing zero fill | Original reset | Exact source guards | Reject unknown image |
| Panic | Keep saved settings | Close old track arp gate, clear active set | Keep owner refs for releases | Reset original phase/order | Stock OFF API old track | No stuck outputs |
| Freeze or capture | N/A no new capture operation | N/A existing Flex untouched | N/A | N/A | N/A | N/A |
| Mode change | Existing ranges | Arp panic; Plaits initializes selected lane on trig | Others unchanged | Lane-local seed | G / SRC retained | No cross-track writes |
| State recall | Existing AR16 settings | Panic before applying recall | Unchanged serialization | No runtime state persisted | Native project menu | Fail safe OFF |
| Disconnect/reconnect | N/A no new endpoint | N/A | N/A | N/A | N/A | N/A |
| Non-finite recovery | No new math | Existing core behavior; tests reject non-finite output | No corrupt publication | Original policy | No invented success | Retain failed artifact |

## State equivalence

Bit-exact PCM and independent musical state for identical inputs. CPU destination and independent lane addresses intentionally differ; no timestamps or musical outputs normalized away.
