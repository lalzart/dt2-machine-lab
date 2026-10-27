# Optional Sketch assignment prompt

OS1.16 experiment layered on the volatile managed Sketch profile. After a
successful BUF publication, show the stock recorder's `ASSIGN SAMPLE TO TRACK?`
box. A fresh press and release of TRG 1–16 assigns that live BUF to the chosen
sample track; NO dismisses without changing any assignment. MIDI tracks leave
the prompt open. This is a live buffer association, not a FREEZE or disk save.

The prompt captures the completed recording's BUF and identity, independently
of the currently selected BUF/track. Failed/cancelled recordings do not prompt.
Defer behind other dialogs; discard pending requests on a new capture or changed
project/kit/pool/take. Modal events are consumed before native track listeners,
including the release that dismisses the prompt. Preserve existing recorder,
generation protection, FREEZE, settings restore and explicit +Drive export.
Opening waits for held buttons and existing Sketch key ownership to clear, so
pre-existing note releases still reach their original controls. The native
main page retains keyboard, grid, parameter, transport, LED and help views in
its controller list; only those authenticated resident classes are skipped
when checking for an actual modal dialog. Unknown views defer the popup.

Implementation reuses the authenticated stock OS1.16 drawing routine at
`0x40018BE6`, with a separate base View and key action. The stock AssignPrompt
constructor/key action cannot be reused: they allocate and load a saved file.
The new action uses the ordinary sample parameter setter only after context,
identity, idle and destination-machine checks.

Build switch: `--assign-popup`, requiring `--managed-buffers`. The managed
wrapper accepts the switch; leaving it off reproduces the previous managed
image byte for byte. This is the rollback path. Nothing is persisted at shutdown.

Acceptance: native instruction tests for release ownership, NO, track bounds,
MIDI, stale contexts, failure and busy paths; unchanged off-build hash; coupled
native recording to prompt to explicit assignment, native bitmap inspection,
and existing capture/FREEZE/export checks. Physical controls/timing and listening
remain separate device tests. No upload, commit or publication is part of this work.

## Reproduce or remove

```sh
python3 -B scripts/build-sketch-managed.py out/runs/assign-build-NEW --assign-popup
DT2_BUF_SELECTOR_CORE='/Users/lanceship/Documents/Codex/Digitect firmware research project/work/buf-selector-implementation-20261023-01/lab/out/runs/selector-panel-11/libcfselector.dylib' \
  ./labctl unit buf core integration

python3 -B scripts/check-sketch-managed.py out/runs/assign-native-NEW --assign-popup \
  --reference-spec out/runs/sketchbook-r14-native-20261026-01/spec.json \
  --dsp-build out/runs/assign-build-NEW/sketchbook-dsp \
  --reset-inputs out/runs/sketchbook-persistence-20261025-01/dsp-inputs-05 \
  --native-upstream '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit-main' \
  --native-boot '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/buf-stopped-recording-20261024-01/lab/out/runs/stopped-native-02/native-boot'
```

To remove the experiment, omit `--assign-popup`. The existing managed profile
and default wrapper remain unchanged. Its MAIN SHA-256 is still
`4c7f99100063de90164bf47197761a2fb0d19e45a4763219e5a40b44ebcb58bf`.
The popup adds a separate guarded 20 KiB CPU reservation, with no extra audio
generation or DSP changes. No additional settings/menu entry is required.

## Local validation — 2026-10-27

Final build: `out/runs/sketch-assign-build-20261027-05`; aggregate evidence is
`validation.json` in that directory. Coupled native run:
`out/runs/sketch-assign-native-20261027-06` (`report.json`, `flow.json`, panel
captures, source hashes and local `candidate-test-fixture.syx`).

| Artifact | SHA-256 |
| --- | --- |
| MAIN | `b62584d425f31c22f1e8013234e23f03c36177d8ab6a0312767e7568d91d4431` |
| DSP, unchanged | `37270ca2f528a6dae7d0bd8aa8f463d21e523c1e82217fa12717d849f1f568ae` |
| Local experimental SYX | `8de82617a2cc18efcab643fd31cbc933966aed1e0355ee3af714fe216659c9c0` |

- 254 BUF/core/integration tests passed, no skips. Fifteen new cases exercise
  the popup instructions and optional placement, including T1/T16, every BUF,
  supported sample machines, MIDI refusal, stale contexts, failed publication,
  busy/held-key deferral, fast presses, modal ownership and exact rollback bytes.
- The coupled cold-boot CPU/SHARC run passed in 376.2 seconds. Recording BUF 2
  from ordinary track pages opened the stock-style prompt; NO preserved the
  entire kit. FREEZE and replacement recording succeeded. The second prompt
  assigned H125/BUF 2 to T16 on release, changing its sample from slot 11 to
  1021 and preserving the other fifteen track structures. Sketch remained open
  underneath, and no duplicate popup appeared.
- Preview, native filename cancellation, explicit exports, duplicate-name
  refusal, disabled-readback failure/retry, CPU guards and code-integrity checks
  passed. Accepted frozen PCM remained unchanged across replacement. Source
  hashes matched throughout the final run. Ruff and `git diff --check` passed.
- Native screen captures are `assign-A-stock-prompt.draw.png` over SRC and
  `assign-B-stock-prompt.draw.png` over Sketch. They render the target-produced
  bitmap immediately after the original assignment drawing routine returns.

Earlier local runs remain preserved: native `-01`, `-02` and `-04` exposed an
overly narrow main-page admission check; `-03` caught a diagnostic-probe compile
error. Run `-05` caught the probe observing the new view pointer before its open
counter was incremented. The final probe waits for completed opening. These
failed runs are not passing evidence; `-06` is the complete accepted local run.

The recorder input, peripherals and storage are emulated. This does not validate
physical timing, LEDs, listening or device operation. No new DSP behavior or
project persistence was added. Inherited managed-buffer work and dependency
pins are preserved; changes remain uncommitted and no hardware upload occurred.
