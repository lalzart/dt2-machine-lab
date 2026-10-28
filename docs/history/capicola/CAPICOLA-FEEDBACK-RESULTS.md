# Capicola preparation feedback results

2026-10-08. The optional `capicola-feedback` build sends native preparation state and percentage in the existing DSP reply, and the CPU shows a status caption when SRC opens. This is an emulator integration slice. The caption is cached while the page stays open; automatic refresh remains the next UI step. The twelve-second cap and existing8MiB reservation remain unchanged. No installable release or physical-device validation is claimed.

## Implementation and resources

The selection worker still owns preparation and publication. A default-empty notification hook preserves the previous selection binary. Feedback encodes state and integer percentage in the unused reply halfword at0x1a, using the existing266220/267220 buffers and existing2748-byte SPI frame. Off sends zero. The existing CPU driver copies the previous reply to8000488c; the native getter reads its word at800048a6. Unknown tags, states, invalid percentages and READY without100% show a neutral caption. This word is informational: it cannot publish a bank, control memory lifetime or permit playback.

CPU captions are EMPTY, FORMAT, WAIT, READY, ERROR and preparation ranges P<25%, P<50%, P<75%, P<100%. The getter borrows static flash strings. The existing native title formatter runs when the page opens; it can use its normal temporary string allocations. The overlay itself introduces no heap ownership or per-frame allocation. A CAPICOLA-only width adjustment fits the caption into the available110 pixels. Other machine hints use the exact original getter.

DSP instruction payload67126 bytes versus66624 previously:502 additional bytes. Constants remain12496 bytes, working-region size and bank storage are unchanged. Percentage calculation needs at most seven bounded comparisons; maximum arithmetic product115200800 fits32 bits. In the short captured-sample replay, maximum block instruction count406632 versus406557 previously, a75-instruction increase at the observed maximum. This is an emulator instruction count, not physical cycles, worst-case hardware load or a performance guarantee.

Exact BLOB SHA256:459c667dee6850dc59f0582d20289ca1539cac2e6cd303032ca0003b091fc88e. Exact MAIN SHA256:98979261e1e7345749273a6c79f1e74e4fbf5f2af4e3b7ed9667232fb988288c. The previous selection BLOB9fd52edc63ccd428e076653311f796b0ea7e67758d28288b44351af76f6cf879 and legacy controls BLOBce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f rebuild unchanged. The CPU overlay accepts only the prior exact82b17a4f... image and audited zero padding. CPU-only Flex/menu source hashes no longer block SHARC compilation because those files are not DSP compiler inputs; original core/DSP locks and exact CPU image/patch-site guards remain. Unrelated managed Flex changes were preserved.

## Evidence

The captured LP0 sample load, native preparation and voice comparison pass in `out/runs/capicola-feedback-wire-02/report.json`:1620 stock callbacks, selected2400-frame mono slot7 prepared before any trigger, exact host keyframes, unchanged old voice pointers,4808/4808 positions at READY,32-sample first-trigger latency,1280 compared output frames, maximum error1.4901161193847656e-8 and RMS1.0851376394619265e-9. Twelve invalid-selection cases, page invalidation, waiting for header, same-address reload, mid-preparation/active cancellation and machine exit pass. Retired204800-byte L2 working region and four stack guards are intact. There are166 recorded full native reply-buffer snapshots. These originate in the real block handler; they are not a SPI2 peripheral execution claim by themselves.

`out/runs/capicola-feedback-transport-02/report.json` records exact repeated CPU/DSP builds,299 full reply/voice comparisons across stock types0..6 and six Plaits models, an unused-word sentinel in both prior buffers,65536 native CPU decoder cases and12 original/invalid type comparisons. Reply parity excludes only the four clock-report bytes and the newly owned halfword. A fresh DSP application entry executes500million native instructions with the documented reset-value/peripheral model. Sixteen actual native SPI2/SPORT exchanges transmit EMPTY status0xd480 through both ping-pong buffers after the first two exchanges. This smoke uses a genuinely empty slot, without sample metadata or readiness injection. It verifies the return field and byte order, separately from the selected-sample worker replay.

The native CPU display replay passes12 cases in `out/runs/capicola-feedback-ui-03/capture.json`. Recorded native replies enter through DSPI2/eDMA, then the original driver copies the complete2748 bytes to its consumer buffer. Normal panel gestures reopen SRC; its native getter and renderer show all four ranges, READY, WAIT, EMPTY and FORMAT. Missing, unknown, malformed READY and excessive progress replies remain neutral. The last four cases are explicit synthetic reply negatives. Screenshots include `feedback-Punder50percent.png` and `feedback-READY.png`. This is buffered reply replay with each snapshot held for the display check, not live coupled timing or an audio-output measurement.

All95 source tests pass; Ruff and diff checks pass. SINE replay passes in `out/runs/20261008T075828Z-test-1ad9c1ca/manifest.json`. The SINE snapshot precedes final path-resolution and diagnostic reporting edits; the DSP and emitted CPU image bytes are unchanged. Initial diagnostic trials remain in ignored output: one wire trial correctly rejected source changes during formatting, and one UI trial exposed the relative-path resolution issue, fixed before the final UI run. The first SPI report called the X-modify value a count; the final runner records both correct registers.

## Reproduction

Use fresh names under `out/runs`; existing run directories are refused. The pinned private1.16 fixture and captured panel/sample artifacts are required.

```sh
python3 scripts/check-capicola-wire.py out/runs/<wire> --capture out/runs/capicola-panel-08 --sample-load out/runs/capicola-panel-05 --reserved-state --selection --feedback
python3 scripts/check-capicola-feedback.py out/runs/<transport>
python3 scripts/capture-capicola.py out/runs/<ui> --prepared out/runs/capicola-panel-05/capicola-ready.snap --feedback-replies out/runs/<wire>
./labctl test sine --replay
```

The CPU caption can remain stale until SRC is reopened, including after selection or reload. The reply lacks a generation/slot identity and must stay informational. Next: a narrowly scoped native refresh hook with state/selection correlation, followed by project-change/reload lifecycle checks. Permanent L2 code ownership, complete coupled startup and selected-sample return transmission, full mixed output, listening, resource stress and physical deadlines remain open. No hardware was flashed or contacted, and no firmware or derived binary is committed.
