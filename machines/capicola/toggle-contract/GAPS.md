# Optional CAPI comparison toggle implementation gap register

> Status: local feature complete; device evidence deferred

| ID | Gap | Severity | Owner/stage | Current decision | Proof required | Disposition |
|---|---|---|---|---|---|---|
| GAP-001 | Physical DSP timing and worst-case headroom | high | Device validation | No utilization claim | Authorized hardware timing under full load | deferred |
| GAP-002 | Permanent CPU SRAM-tail and DSP instruction ownership | high | Device integration | Guard bytes and bounded separate startup | Coupled runtime ownership and sustained operation | deferred |
| GAP-003 | Full project save/reload/undo and continuous coupled feedback | medium | Integration | Native storage/lock preview and buffered replies only | Exact package persistence and coupled transport | deferred |
| GAP-004 | Existing R3 playhead/progress and Flex source lifecycle | medium | Existing integration | Preserve current behavior | Separate native lifecycle implementation and tests | deferred |
| GAP-005 | Sound quality and proprietary distribution | medium | Listening/release | Preserve AGPL/MIT lineage; local private artifact | Listening protocol and distribution review | deferred |
