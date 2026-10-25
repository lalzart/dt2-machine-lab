# Fixed BUF slots — OS 1.16

The user chose a fixed public mapping with no reassignment controls:
BUF 1 = H124, BUF 2 = H125, BUF 3 = H126, BUF 4 = H127. Native IDs are
1020–1023. The four aliases before A00 resolve to these same entries. NORMAL/A00
remain defaults. The preserved R3 profile and package are unchanged.

`--fixed-buf-slots` selects this staged Sketch profile, alongside the existing
ARM diagnostics, clock, selector, performance-controls and navigation flags.
This build-time comparison switch does not expose runtime configuration.
No per-project setting, new menu, automatic migration or alternate public slot
is provided. An occupied fixed slot blocks the complete setup and shows
`BUF: H124 IN USE` (or the actual H125–H127 row). Ordinary samples are retained.

`lab/buf_fixed_slots.py` replaces only the native setup emitter. It validates
all four public entries and finds all eight private entries before committing
reservations or names. Private slots keep the existing ascending free-slot
policy, excluding the fixed public entries. Failure cannot publish a partial
reservation. No PCM arena, generation identity, retirement rule, worker/job
admission guard, FREEZE backend or DSP code changes.

A project reference with the exact matching BUF marker, nonzero epoch and zero
trailing words may be adopted at its matching H slot only when loader cache and
loaded length are empty. It becomes an EMPTY BUF. This reconstructs slot
identity in prepared retained-metadata tests; it does not restore lost audio
or establish actual device reboot/working-state persistence. Unknown, malformed,
mismatched or already loaded references refuse setup. Old B17 references and
track assignments remain untouched; use the BUF selector for an intentional
new assignment. The explicit volatile-project save/load guards remain.

Ten new instruction checks cover fixed/private placement, atomic conflict and
capacity refusal, retained/malformed markers, legacy reference preservation,
idempotence/live audio, pool identity, aliases/defaults, native feedback formatting
and exact R3 output with the profile disabled. Together with affected selector,
navigation, controls, device-build and test-catalogue checks, 60 checks pass.
The current staged source has a local MAIN build with unchanged 360,448-byte
reservation and unchanged DSP SHA-256
`2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a`.

The native validation is deliberately scoped to an injected occupied-reference
negative control, all four real selector aliases, one modeled NOW capture into
H124 shared by two tracks, held-SONG FREEZE, and saved-page playback. It omits
unrelated menu and long replacement tests. Its replay compares 40 blocks twice
against original DSP with identical native LP0 pages and checks an unloaded-sample
negative control. It is not an independent CPU file-loader comparison, physical
timing, listening or device trial.

## Results

The native `fixed-h-native-01/flow.json` component passes: all four fixed aliases,
an injected H124 conflict with zero jobs, H124 shared by T1/T5, one 113,632-frame
stereo NOW publication, and held-SONG FREEZE to separate slot 308 with an identical
DSP descriptor. All assignments, NORMAL DEST, CPU code and canaries stay intact.
The normal SRC field visibly shows H124. Input PCM matches the modeled source.

That run's parent report remains **failed**: its extra replay passed raw 4,104-byte
recorder trace records into an adapter requiring 4,100-byte little-endian LP0
packets. It failed before running replay audio. The two validation helpers now
use the existing page decoder/converter and an explicitly named `.lp0` input.
Neither helper change alters emitted firmware or DSP. No capture was repeated.

`fixed-h-replay-02/report.json` passes using the saved take and corrected packing.
Forty controlled voice blocks, repeated twice, match original DSP given the same
native pages; an unloaded-sample control differs. Voice SHA-256 is
`ec9545cd98a57a2a52304d4e0ba49d4a160706ea4a9704ae0171cb451652fbb9`.
The source native run retains its failed whole-run status; its passed component
is authenticated against the final identical MAIN/patch metadata.

Final build `fixed-h-device-03` has MAIN SHA-256
`7c5e0bdea8b5c7c8feb5cfc8c695d0f27dbd4a070624994215b2f288d0012de1`,
identical to the native container and initial build. Build 02 stopped at the
sealed workflow document fingerprint after a documentation addition; the
original contract was restored and the fixed-layout decision stays in this
separate note. The failed attempt is retained. Native hooks and the reservation
remain identical to R3; payload changes are only setup and Sketch feedback.

SINE replay `20261024T033515Z-test-a997fadf` passes. Its source snapshot predates
the two replay-helper corrections; firmware/DSP sources are identical and this
explicit helper-only difference is audited. Original R3 sources/package and
pinned dependencies remain preserved. No physical reboot, hardware timing,
listening or actual project-save/working-state round trip was performed. Retained
marker restoration is instruction-fixture evidence. The captured Sketch status
line still displays REC:PROCESSING after publication/FREEZE, while job counters
and BUF READY/FREEZE READY confirm completion; settled recorder-label refresh
remains a separate UI limitation and is not claimed fixed by this change.

[Native occupied-slot feedback](../out/runs/fixed-h-native-01/flow/fixed-H124-conflict.png),
[normal H124 SRC field](../out/runs/fixed-h-native-01/flow/fixed-H124-source.png),
[published BUF](../out/runs/fixed-h-native-01/flow/fixed-H124-ready.png),
[native flow component](../out/runs/fixed-h-native-01/flow.json), and
[saved-take replay](../out/runs/fixed-h-replay-02/report.json).

Reproduce from this staged lab with its configured Python and a fresh output:

```sh
"$LAB_PYTHON" -B scripts/build-sketch-device.py out/runs/UNIQUE \
  --arm-diagnostics --clock-fix --buf-selector --performance-controls \
  --navigation-fixes --fixed-buf-slots
"$LAB_PYTHON" -B scripts/check-native-buf-recording.py out/runs/UNIQUE-NATIVE \
  --native-upstream /absolute/path/to/digikit-at-38dfbe4 \
  --clock-only --performance-controls --navigation-fixes --fixed-buf-slots
```

The implementation stage performed no hardware access, commit or distributable
firmware packaging. Existing source/artifacts are preserved in the prior stage.

## Authorized R4 package follow-up

The user subsequently requested the OS. The local
[fixed-H R4 package](../out/runs/fixed-h-experimental-02/package/README.md)
contains the exact tested MAIN/DSP and native candidate container. SYX SHA-256:
`c49e55c552380ec68e63942a3d0eef03ba8e978939d94b1d8382ebad1cc53690`.

`fixed-h-upload-01` passes stream rules and native CPU sender/backpressure checks.
The sender fixture uses stock MAIN for native construction and installs sealed
candidate MAIN before instruction zero; the full candidate container is separately
verified and was used for the native recording flow. DSP ROM and physical SPI
FIFO/timing are not executed by this check. The original native parent remains
failed, with its passed flow component and corrected saved-take replay recorded
separately in the package manifest. No new captures or firmware source changes
were needed for packaging.

Reproduce the local package gates from this staged lab using a fresh output:

```sh
"$LAB_PYTHON" -B ../package-fixed-h-os.py out/runs/UNIQUE-PACKAGE
```

The package README lists slot conflicts, old assignment migration, startup wait,
volatile audio and stale REC label limitations. R3 and all 946 original baseline
files are rehashed unchanged. This R4 image remains untested on physical hardware;
no device transfer, commit or publication was performed.
