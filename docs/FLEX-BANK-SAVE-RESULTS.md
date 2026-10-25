# Flex RAM-bank save R5 — 2026-10-20

Implemented the [name → RAM bank → save flow](FLEX-BANK-SAVE.md) for accepted
Flex takes, using the stock filename editor and native CPU drawing/input.
LEFT/RIGHT chooses A–H; the destination slot is visible before YES saves.
The current bank/slot is the default. NO, full banks and failed operations
preserve the take. Machine settings survive the change in sample slot.

When changing banks, the old project slot remains an alias for other tracks,
patterns and sample locks. Both slots point to one +Drive file. This consumes
an additional project slot and deliberately avoids project-wide relocation.

## Experimental package

Final artifact:
[R5 OS 1.16](../out/runs/flex-bank-r5-package-20261019-02/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_FLEX_SAVE_SCREEN_R5_BANK_OS1.16.syx).
Includes the existing any-track Arp/Plaits, repaired CAPI R2, managed Flex,
immediate Discard and R4 project-save repair. No hardware transfer was made.
The earlier `...package-20261019-01` build precedes the final loader-readiness
guard; use the final `...-02` artifact linked here.

| Component | SHA256 |
| --- | --- |
| SYX | `668b5fa644427dffbe7d1bde757ac31ac1824fd8b28e5a8e647dd240f911b3b1` |
| MAIN | `aae7e143078638bf7717906a28e631a06f9d7f2c2c0aa9bd36b3ec2650ff8479` |
| DSP | `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2` |

MAIN is 3,299,048 bytes. The existing 64 KiB DDR reservation is unchanged.
All emitted instructions pass the ColdFire subset audit. CPU/DSP builds and
container assembly repeat exactly within the package builder. DSP and stored
sections 2/4/5/7/8 match R4 exactly; Arp metadata is also exact. Building without
the save screen reproduces the previous any-track MAIN hash
`95e1b3b5bcf2b40f31942349a2e34ba99f79547926db9ba5e0e47d59d45b5831`.

## Verification

- **281 source tests** and scoped Ruff pass. Native transaction cases include
  all banks, H127, reserved/occupied slots, all 16 tracks and six sample engines,
  exact identity guards, stale captures, cancellation, invalid names, full banks,
  failed/zero-length loads, failed writes and ownership changes during calls.
- **Exact-package native panel flow:** T9 STRETCH names a take, defaults to its
  existing C bank, cancels without writing, rejects full H, chooses D001,
  preserves the take through an injected file-open failure, retries, saves,
  retires its CPU source and records again. Only T9's slot changes; shared T3
  retains the old slot, other controls and the unrelated T1 take stay intact.
  An independent stock CPU reload uploads byte-exact saved PCM.
- **Exact-package native project save/reload:** original project writer saves
  the working-project slot 128 with old/new aliases plus a missing temporary
  reference. An independent stock decoder recalls exact kit bytes, references
  and both aliases' PCM. A fresh descriptor-empty patched runtime saves again.
  This direct-call fixture has no initialized Arp state; it does not establish
  a combined active-Arp project-save scenario or a physical Save As trial.
- **Exact-package immediate Discard regression:** first YES discards, the
  native allocator frees the source once, aliases clear, unrelated audio stays
  intact, recording works again and the subsequent name/bank/save route passes.
- **Native CPU reset/ready:** both poisoned/normal reset checks, loader-disabled
  negative, relocated segment checks and BSS clearing pass; no coupled DSP.
- **Prepared SINE replay:** baseline PCM, exact repeat, stock isolation,
  clone/negative and lifecycle pass. This run predates only the final CPU-only
  readiness guard in `lab/flex_bank.py`; no SINE/DSP source changed afterward.

The UI uses modeled recorder and storage peripherals, with no host callback
implementing the bank selection or save transaction. Screenshots preserve raw
guest pixels. Bank-page captures select a complete latched frame rather than
combining pixels. No physical listening, continuity, timing, power-loss or
hardware validation is claimed for R5.

## Actual flow and evidence

- [Full screenshot gallery](../out/runs/flex-bank-r5-ui-20261019-02/flow.html)
- [Stock filename editor](../out/runs/flex-bank-r5-ui-20261019-02/02-name-sample.png)
- [Choose D001](../out/runs/flex-bank-r5-ui-20261019-02/06-select-bank-d.png)
- [Save confirmation](../out/runs/flex-bank-r5-ui-20261019-02/09-saved-to-d001.png)
- [Native panel report](../out/runs/flex-bank-r5-ui-20261019-02/report.json)
- [Native project report](../out/runs/flex-bank-r5-project-20261019-02/report.json)
- [Discard report](../out/runs/flex-bank-r5-discard-20261019-02/report.json)
- [Reset report](../out/runs/flex-bank-r5-boot-20261019-02/report.json)
- [SINE replay](../out/runs/20261019T145536Z-test-99e5b324/manifest.json)
- [Source snapshots, tests and parity](../out/runs/flex-bank-r5-verification-20261019-02/verification.json)

Reproduction commands are in [the implementation note](FLEX-BANK-SAVE.md).
No commit, push, publication or hardware installation was performed.
