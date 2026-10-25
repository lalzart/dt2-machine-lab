# Any-track features — OS1.16, 2026-10-19

Implementation and final source-frozen validation passed. This is an experimental
local build; physical device and listening checks remain separate.

## Resulting behavior

- The keyboard arp follows the selected track, 1–16. It is one active keyboard
  arp, with the existing shared mode/rate per pattern. G settings, stopped
  playback at the current tempo, recording and existing AR16 data are retained.
  Changing tracks closes the gate on its old track before changing destination.
- Plaits type 7 is permitted on all 16 tracks, with independent state for all
  32 stereo lanes. The six engine cores are unchanged. Full-width macro
  transport and the late repack bypass now use each track's own addresses.
- Capicola already supports all 16 tracks; its engine, CAPI control and repaired
  zero-fill boot encoding are unchanged. Flex already assigns to any compatible
  ONESHOT destination, with one shared recorder and retained takes. Its allocator,
  resource ownership and persistence code are unchanged.

No assignment setting or larger state reservation is needed. The optional
`--any-track` build includes stopped arp. Omission preserves the older builds.

## Artifact and reproduction

The final package is in `out/runs/any-track-package-20261019-05/`:

`EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_OS1.16.syx`

| Component | SHA256 |
|---|---|
| SYX | `1e89c105392e65fcf6d6eef9c9b2771ae9d011be74a02c7211146c31fc860745` |
| MAIN | `95e1b3b5bcf2b40f31942349a2e34ba99f79547926db9ba5e0e47d59d45b5831` |
| DSP | `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2` |

```sh
python3 scripts/build-cpu-extension.py out/runs/<fresh-package> \
  --all-features --any-track \
  --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-any-track.py out/runs/<fresh-pcm> \
  --package out/runs/<fresh-package>
```

The pre-edit source and accepted stopped-arp build are preserved in
`out/runs/track-unlock-baseline-20261019-01/`. Final sources and test sources are
copied into `out/runs/any-track-verification-20261019-02/source/`.

## Verification boundaries

The [hash-bound verification record](ANY-TRACK-FEATURES-VERIFICATION.json) lists
the exact report paths and hashes. All final reports bind to the final sources;
the packaged DSP and MAIN repeat exactly. The 110 original engine/Flex source
files checked against the preserved baseline remain byte-identical.

| Check | Result |
|---|---|
| Full source suite and focused lint | 247 tests pass; lint passes |
| Native CPU routines | All-track permissions, raw transport, repack, compatible Flex assignments and arp ownership pass |
| Native Plaits PCM | 24 bit-exact comparisons, six initial models on T1/T2/T8/T16, including triggered model changes |
| State/control transitions | All 16 tracks, zero/maximum level, machine exit and untouched-lane checks pass |
| Mixed native frames | Plaits T2/T8/T16 raw PCM/state match solo runs; CAPI T1 reader state matches its solo run; all produce nonzero audio |
| Native panel | T16 stopped UP at 127.5 BPM passes; T8 ORDER recording/replay returns 67/64/60/67/64/60/67/64 |
| Existing CAPI checks | Host/native author oracles, sixteen-track stereo/stock routing and final-ring causal comparison pass |
| SINE | Source-frozen replay passes |
| Package/reset | Actual section 8/3/7 depacker, reset/canaries and disabled-loader negative pass |
| DSP boot staging | 626560 decoded bytes plus one command byte; 422015 bytes headroom in the unchanged 1 MiB allocation |

Only MAIN and DSP sections differ from stock. Every other stored section is
byte-identical. Both earlier accepted R2 package variants also reproduce exactly.

The actual permission, raw transport, repack, Flex assignment and arp note
routines execute in native CPU tests. Raw Plaits machine PCM is compared with
the accepted T1 DSP on T1/T2/T8/T16; no PCM tolerance is widened. Separate
checks cover model changes, zero/maximum level, machine exit, lane state,
mixed Plaits/CAPI tracks and T1 post-filter parity. Existing CAPI author
oracles and sixteen-track stock/stereo/final-ring checks are retained.

The original R2 and the user-confirmed stopped-arp package reproduce their
accepted SYX hashes exactly. Package checks retain the actual section 8/3/7
bootstrap depacker, unchanged bootloader sections, the 1 MiB DSP staging bound,
repeat builds and CPU reset/canaries. These are bounded emulator/package checks,
not a physical flash-safety guarantee or a coupled CPU/DSP cold boot.

The prepared stock CPU snapshot already owns a seven-entry stock machine menu.
Failed attempts to test Plaits selection through that copied menu are retained;
they do not test the extended menu built by a fresh firmware startup. Plaits
permissions are checked in the actual native permission routine on every track.
Non-T1 arp panel and recording tests use the normal stock menu objects.

All exploratory runs remain under `out/runs/any-track-*`. They include wrong
post-filter tap comparisons, a silent CAPI tap in the first mixed fixture,
inapplicable cached-menu probes and source-drift failures while test harnesses
were being developed. Passing results must come from the final frozen run set.

No flash, Git staging, commit, push or publication was performed. Physical
controls, real-time load, external sync, maximum simultaneous capacity and
listening remain unverified for this new candidate. The resource monitor is
outside this change.
