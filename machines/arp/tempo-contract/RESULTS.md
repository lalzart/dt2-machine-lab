# Tempo/rates results

## Commands and results

Completed implementation and validation notes: [native tempo/rates results](../../../docs/ARP-TEMPO-RATES-RESULTS.md).

- Focused native rational timing/mode/rate, state bounds, input guards and independent v1/v2 journal checks pass. Equal-sequence mixed versions fail safe.
- Final MAIN panel run `arp-tempo-r1-fast-panel-03`: stock Tempo-menu300 BPM, G1/32, exact eight-note UP vector. Native service jitter and monophonic gate preemption are measured, not hidden.
- `arp-tempo-r1-storage-record-05`:120 BPM, ORDER1/16, ordinary live recording then normal menu Save Project0 and working autosave128; independent companion readback and saved checkpoint pass. Its subsequent dialog-wait failure is retained.
- `arp-tempo-r1-storage-recall-05`: checkpoint-resumed native menu load, mode/rate restoration after explicit RAM clearing,121740 exact pattern bytes and recorded-note replay pass. This spans retained checkpoints rather than an uninterrupted cold boot.
- Final source suite and SINE offline voice-buffer replay regression pass. SINE is a separate regression, not new arp PCM/listening evidence.
- `arp-tempo-r1-package-04` repeats package03 exactly. Guarded build/container, unchanged DSP, actual original bootstrap depack8/3/7 and bounded CPU startup pass. `release-verification.json` binds the final file, MAINs and checks.

## Evidence ladder

Research/proposal, implemented source, native host structural/control and target-build evidence are available. New arp voice PCM, physical real-time, new-candidate hardware, listening and production integration remain deferred. Prior user listening success applies only to the earlier installed build of unconfirmed hash.

Source freeze04 is retained independently from this report backfill. Nothing was flashed, sent, committed or published.
