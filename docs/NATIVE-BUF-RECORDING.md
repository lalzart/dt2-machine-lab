# Native BUF recorder connection — OS 1.16

Authorized by the user's “go ahead and connect it up”, 2026-10-23. Extend the
opt-in `38dfbe4` host adapter, preserving active `277760a` pins and all firmware
emitters. This is a host migration of the lab's recorder model, not new DSP.

## Implementation contract

Reuse the authenticated-reference constructor in a copied boot crate. Add an
optional OS1.16 recorder peer at the same function boundaries as
`NativeFlexInput`: START/STOP/discard observation, sample-clock count and the
command/response wrapper. Port `RecorderInput` semantics, including bounded
stereo big-endian PCM readback, extrema and one tick/frame. Normalization is
acknowledged by this existing model; it does not simulate a hardware gain pass.
Do not substitute a host commit, track assignment, loader success or FREEZE.

The working artifact is a lab-owned native runner executing current Sketch
firmware and the original recorder/worker/loader/publication jobs against a
deterministic nonzero input peer. Upstream sources, dependency pins, ordinary
Flex, allocation/retirement policy and hardware packages are outside this task.
Native host signal is the strongest possible result; physical timing, recorder
hardware, listening and real-time operation remain unqualified.

Acceptance: port/model boundary checks; one bounded empty-BUF A -> FREEZE A ->
replace B flow, shared selectors and retained readers; cancellation preserves
accepted data; exact repeat; stock DSP/file compatibility and distinguishable
wrong-source/zero/disconnected controls. Check final output separately from
voice PCM. Preserve full unmasked replies and model/core/input fingerprints.
Use saved inputs for comparisons instead of repeated capture experiments.
The default command records two accepted takes and one cancelled candidate.
Exact audio repeats use those saved pages. `--repeat-flow` explicitly opts into
an additional full capture workflow; it is not routine validation.

The previous native-reply audit explains old/new differences as corrected SIMD
semantics. Old final-output equality is not an oracle. Keep the default runtime
until the connected native path passes its own qualification.

## Results

**Native recording is connected and passes the bounded stereo, LEN 16 flow.**
The active lab dependency remains unchanged; use this opt-in command for native
BUF work. No firmware emitter, BUF/FREEZE backend or Flex profile changed.

- [Connected flow](../out/runs/native-buf-recorder-20261023-05/flow.json):
  53,232 native DSP frames, two accepted 112,960-frame stereo takes, one held-SONG
  FREEZE and one cancelled active candidate. Four old-reader lanes (0, 1, 8, 9)
  retain A across B's publication. T1/T5 remain on BUF 1 (300), T6 on frozen A
  (312). Cancellation preserves the registry, frozen descriptor, current header,
  assignments and page count. All code/canaries survive; no missing SPORT blocks.
- [Stock-file oracle](../out/runs/native-buf-recorder-20261023-05/stock-oracle/report.json):
  complete readback and CPU page payloads equal the supplied nonzero PCM; fresh
  stock CPU file loads reproduce both takes. No extra recordings.
- [Saved replay](../out/runs/native-buf-recorder-replay-20261023-02/report.json):
  96 blocks repeated twice, exact stock-file voice PCM, master mix and both
  DAC-ring halves. Full raw replies also match stock exactly in all four phases
  (zero differing bytes). The wrong-frozen-source control differs. No recordings.
- 208 BUF/core unit cases and [SINE compatibility](../out/runs/20261023T064407Z-test-6a1c3855/manifest.json)
  pass on the same source inventory as the connected flow. The subsequent
  comparator correction changes only the replay function and its launcher;
  recording/observer source is verified byte-exact against the frozen runner.
- The qualification checker refuses matching zero PCM/zero page data as proof
  of the declared nonzero input. Peer/model checks also cover wrap/count,
  extrema, bounds and unavailable completed readback. These are model/proof
  controls, not an actual native DSPI1 cable-disconnection test.

[Evidence index](../out/runs/native-buf-connect-20261023-01/verification.json) and
[native Sketch screenshot](../out/runs/native-buf-recorder-20261023-05/flow/frozen-A.png).

Development failures remain intact: the old page-sender ABI guard needed its
exact existing hook; the driver needed explicit Sketch open/close ownership;
a host helper recursion typo aborted before recording; and the reference
loader needed runtime path initialization before imports. None required a
firmware change. The original `-05/report.json` retains its comparator failure:
the callback runner was incorrectly initialized from the live cold-state
export. The corrected comparison uses the authenticated prepared callback/SEC
fixture and all its options, checked against the earlier migration evidence.
Its separate saved replay passes without repeating the capture workflow.

## Reproduction and boundaries

```sh
./labctl doctor
./labctl unit buf core
python3 scripts/check-native-buf-recording.py out/runs/YOUR-FRESH-RUN \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
./labctl test sine --replay
```

The launcher selects the configured Python and authenticates the upstream,
codec, OS1.16 source/card, reset model, generated core, local container and
current firmware build. Every execution gets a fresh output. `--prepare-only`
builds and runs the bounded peer/model checks without a capture workflow.

The adapter is installed only on DT2 OS1.16 and guards every service entry. The
one pre-existing BUF page-sender hook is accepted at its exact current device
address. Other entry changes fail. No generic callback can report publication
or assignment success. Recorder-peer state is deliberately excluded from native
snapshots; saving/restoring with it attached refuses rather than losing it.

The connected flow exercises the newer native CPU and DSP, SSI cadence and LP0
models. Its recorder still substitutes the external command/count service at
the same boundary as the older adapter. It does not implement the physical
DSPI1 producer, a processed resampling tap or hardware normalization. This
initial peer supports the validated stereo fixture; mono input is not qualified.

Stock CPU file-load references produce independent LP0 pages from the captured
PCM. Saved-page playback compares voice buffers, reply signal, master mix and
DAC-facing ring using the newer core and stock DSP code. Raw replies remain
saved in full; the documented EMUCLK timing word is distinct from audio data.


To compare a completed connected run without recording again:

```sh
python3 scripts/check-native-buf-recording.py out/runs/YOUR-FRESH-REPLAY \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4" \
  --replay out/runs/native-buf-recorder-20261023-05
```

The replay command requires a passing standalone flow report, its exact frozen
recording/observer source and native runner, unchanged recorder/firmware helpers
and core, plus authenticated DSP/template bytes. It records comparator-only
source changes explicitly. A partial run cannot qualify as a completed flow.


Global lab migration remains separate from this bounded connection. Existing
Flex and other feature tooling still use pinned APIs. Use the opt-in native
BUF runner for the next BUF experiments; changing the global backend is not
part of this result. Publication timing and musical activation policy remain
the next BUF work, using this native path and its declared transport models.
