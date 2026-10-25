# Native stock arp results

> Status: prototype; native target build and bounded CPU control/storage pass.

## Commands and results

See docs/ARP-STOCK-FIRMWARE-RESULTS.md for reproduction, package hashes and exact
scope. The final artifact is out/runs/arp-native-stock-package-01/
EXPERIMENTAL_ARP_STOCK_OS1.16.syx. Its MAIN matches the passing native UP record,
normal GUI project-load and replay capture exactly. Source/SINE hashes agree
with the package freeze; subsequent edits are reporting Markdown only.

## Evidence ladder

EVIDENCE: source, native ColdFire core/clock/G controls, native AR16 codec and
stock filesystem calls, ordinary recorded pattern and scheduled GUI recall,
stock-only container build, original bootstrap depacker and bounded CPU startup.
No Python arp feature callbacks are used. Native eMMC is modeled on a private
overlay. Existing stock DSP is preserved. New voice PCM, final DAC, physical
timing, connected hardware, listening and production integration are unverified.


2026-10-15 hardware follow-up: original package produces no arp in the user trial.
The keyboard flag mismatch is reproduced explicitly; the replacement reads the
stock setting and passes the mismatch fixture plus the native getter regression.
New exact MAIN: 5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310.
Package, bounded startup and original depacker pass. Physical cause and replacement
hardware result remain unconfirmed; full saved-project flow was not repeated.
See docs/ARP-STOCK-FIRMWARE-RESULTS.md for exact artifacts and limits.


D1 diagnostic continuation: no new physical fix claimed. Optional --diagnostics
instruments the keyboard-fixed port with native H/P/K/C/N/A and caller readouts.
Default MAIN remains exact 5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310.
D1 exact MAIN: 3c622ff76fceb3e5ea0cd9a15be532c3a0965d5ffaa18b3eae48790ed9c72c7a.
The final native run arp-diagnostics-d1-readout-panel-02 and package
arp-diagnostics-d1-readout-package-01 share the source freeze and image hash.
UP notes/offs, release/STOP, original caller and counter observations pass.
Original OS formatting is executed in a focused read-only diagnostic test.
Native readouts are visually legible; no additional hardware action was taken.
Physical input/clock/output diagnosis waits for the device readouts.
