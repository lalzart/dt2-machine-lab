# Capicola preparation before triggering

OS1.16, 2026-10-08. **EVIDENCE:** optional family `capicola-selection`, with layout `reserved-state`, prepares the track-one selected mono sample through normal DSP maintenance blocks before it is triggered. The existing 12-second limit, 32-position preparation budget and 8 MiB sample-pool reservation are unchanged. Existing `capicola-controls` builds remain available as preserved baselines.

The resolver reads the cached SAMP command at `0x2559bc` and the native slot table at `0x257810 + slot*20`. It accepts only project slots0..1023, mono/identical channel offsets, 48kHz, aligned PCM, 141..576000 frames and complete containment inside the reduced sample pool. Invalid input cannot start analysis. Playback independently checks that the selected source and assigned voice match the published bank. Changing source cancels preparation or playback; selecting an alias of the identical eligible source can reuse it. Sample-transfer callbacks retain the existing publication epoch and reload guards.

`out/runs/capicola-selection-wire-03/report.json` passes:

- All 1,620 captured stock LP0 callbacks, followed by trigger-free captured SAMP commands. The prepared fixture's old voice pointers remain `0x8045a6c8`, while the selected sample is `0x8422ba08`; no voice-pointer, sample-table or bank injection is used for this positive path.
- READY after 153 audio blocks total (five initial held blocks plus 148 further blocks) for 2,400 PCM frames. The status finishes at 4,808/4,808 positions, counting both passes and their four padding positions. Progress is monotonic within this preparation epoch. This is the established approximately2x-duration schedule, not measured physical processing time.
- Exact host key arrays and the first subsequent trigger's entire 1,280-frame stereo voice output, including its silent tail. Maximum error `1.4901161193847656e-8`; RMS `1.0851376394619265e-9`. Stock trigger delay remains 32 samples. Intentionally shifting output by one block fails both tolerances.
- A page rewrite immediately clears readiness; status reports waiting until matching sample headers arrive. A complete reload rebuilds in 153 blocks, changes generation and produces byte-identical keys/audio.
- Twelve explicit negative metadata/slot cases: empty, preview, signed invalid slot, differing channels, stereo flag, 44.1kHz, overlength, too short, odd length, odd offset, outside pool and crossing its end. These synthetic cases are separate from the positive captured path.
- Mid-preparation selection cancellation/restart resets progress and epoch. Selecting an empty slot during playback silences the voice at the normal command pipeline boundary. Machine exit cancels preparation.
- All 204,800 bytes of the retired L2 data region remain poisoned and unchanged; four private-stack guards survive.

## Native status ABI

The new 44-byte status record lives at relocated address `0x9d14ffc8` (legacy logical address `0x200e4600`). Its eleven unsigned words are sequence, magic `0x43505331`, version 1, slot, state, reason, done, total, epoch, source and frames. Read only when sequence is even and identical before/after the snapshot. State codes: 0 off, 1 empty, 2 unsupported, 3 preparing, 4 waiting for load, 5 ready, 6 failed. Reasons: 0 none, 1 empty, 2 invalid slot, 3 stereo, 4 sample rate, 5 too long, 6 too short, 7 bounds/alignment, 8 worker failure. Progress counts both analysis passes. The record updates once per maintenance block; HANDOFF readiness and publication epochs remain the immediate playback authority when an interrupt invalidates a bank.

This is native emulator-readable feedback. It is **not yet displayed on the instrument** and is not sent through an invented/unverified reply field. The next UI step needs an evidenced DSP-to-CPU return path and a native display consumer. The existing conservative invalidation on any zero-length sample header is retained: a matching valid header is needed to unblock an unchanged source.

## Resources and artifacts

The compiled candidate uses 66,624 instruction bytes, 2,036 bytes more than the prior reserved-state candidate. Constant data remains 12,496 bytes; the status record occupies existing unused reserved working RAM, so no additional sample capacity is taken. The observed maximum full-frame count is 406,557 emulator instructions; this includes stock firmware and is **not physical DSP cycles or a utilization percentage**.

BLOB SHA-256: `9fd52edc63ccd428e076653311f796b0ea7e67758d28288b44351af76f6cf879`. MAIN remains `82b17a4f9068f47bef1b272205e3dc153e057fdb67a52db6a9726e5f09ceb8da`. The bank, source files and license lineage are inherited from the frozen Capicola contracts.

```sh
python3 scripts/check-capicola-wire.py out/runs/capicola-selection-wire \
  --capture out/runs/capicola-panel-08 --sample-load out/runs/capicola-panel-05 \
  --reserved-state --selection
python3 scripts/check-capicola-resident.py out/runs/capicola-selection-resident --selection
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

`out/runs/capicola-selection-resident-01/report.json` passes exact repeated candidate builds, byte-identical prior legacy and reserved-state builds, 184 full-frame stock/Plaits comparisons and two identical fresh DSP startup runs of 500 million instructions each. Both startup runs preserve code, constants, selector and former-area poison. The checks use the existing documented reset/peripheral model, not a coupled physical instrument.

The unit suite passes 63 tests; focused Ruff checks and `git diff --check` pass. SINE replay passes in `out/runs/20261008T054746Z-test-5fe6f828/manifest.json`. Reports retain the frozen source hashes for their runs; subsequent contract/result documentation updates do not change the tested code or image. Permanent L2 instruction-code ownership, coupled cold startup/project lifecycle, final-mix output and physical timing remain open. No installable Capicola release or hardware upload is claimed.
