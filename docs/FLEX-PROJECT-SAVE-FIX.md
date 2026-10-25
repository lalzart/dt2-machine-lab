# Flex project-save repair — OS 1.16 R4

The user reported Quick Save and Save Project As failing, including a new named
slot and another attempt after reboot. A controlled missing-reference fixture
reproduces the generic **ERROR** in the exact R3 CPU/UI. This establishes a real
save blocker; the user's project has not been read, so it does not establish
that this is the only cause of their physical-device failure.

On 2026-10-19 the user reported that the supplied R4 OS installed successfully
and Save Project As into a new project succeeded. This confirms resolution of
the reported save operation on their device. The exact stale reference was not
read from their project, and hardware reload, power-cycle persistence and a
broader Flex session have not been reported. See the separate
[user hardware report](FLEX-PROJECT-SAVE-HARDWARE-REPORT.json); earlier automated
reports retain their original no-agent-hardware-access scope.

## Cause and change

The Flex pre-save operation scanned all 1024 project sample references. Any
temporary identity without a current RAM descriptor aborted the whole project
save. A reference can survive in the working project after the corresponding
RAM take disappears at reboot, including an unused sample-pool entry. The
original stock writer accepts the same fixture and preserves its missing
sample reference.

R4 treats references without an exact current-take match as stock missing
samples: their complete 16-byte references remain untouched and the rest of
the project can save. It does not delete them, choose a replacement file,
reassign them to a new take sharing the ID, or claim to recover lost RAM audio.
Discard cleanup now checks the complete reference before clearing a tombstone
alias, so a different boot's reference cannot be erased by a same-ID tombstone.

Every exact live take still has to persist successfully before the stock
project writer may run. Failed writes and invalid durable backing still stop
the save and preserve the recording. The legacy builder retains its strict
missing-reference policy; this repair is enabled with `--flex-save-screen`.
No IDs are recycled and no allocation limit is increased.

## Experimental OS

[R4 experimental OS](../out/runs/flex-project-save-r4-package-20261019-01/EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_ANY_TRACK_R1_FLEX_SAVE_SCREEN_R4_SAVE_FIX_OS1.16.syx)

SYX SHA-256: `e8a0bb48d171b66f9118aa68dca5c95b9dd50f0ba497457473f6d4d605e0263a`

MAIN SHA-256: `85ba2bc62aa4c0e9d1ca393afbe899d2ee9a63e599ffc22fac796eb820428c26`

DSP SHA-256: `fdd5619fbdc6c4f1cc35ce781896400791c1d1a38c91c603fe75548e7ea7f2a2`

The MAIN length is unchanged; 82 stored MAIN bytes differ from R3. Arp metadata
and code, the DSP section, and all other container sections remain exact.
The audio engine is unchanged. The agent performed no hardware transfer or
commit; the user subsequently reported successful installation and Save As.

## Verification and reproduction

- **266 tests pass**, including empty runtime state, preserved unknown refs,
  mixed missing/live takes with a failed write, same-ID different references,
  exact tombstone cleanup, and unchanged legacy rejection. Scoped Ruff passes.
- Original R3 guard returns false before the stock writer. Restoring the
  original writer on that same fixture returns byte `1` and preserves the
  missing reference. The R3 native GUI shows **ERROR**.
- Exact R4 native CPU saves a project containing a live take, a discarded take,
  an unknown temporary reference and a different reference sharing a tombstone
  ID. An independent stock CPU reloads it, preserves missing-reference bytes,
  and reloads the surviving sample with exact PCM. Installing fresh R4 runtime
  state on that decoded project permits another original project save.
- Native reset/ready, extension copies, initialized state, erased appended
  source and canaries pass. This is CPU reset with modeled peripherals.
- The actual R4 GUI quick-save path returns success from named slot `0` and
  temporary slot `128`, commits both Arp journals and displays **DONE**. This
  UI test explicitly models stock SHA-256 with `hashlib` to bound emulator
  runtime. It does not establish native hashing time or full hardware timing.
  Recorder/storage/DSP peers are modeled. The direct native project test
  skips uninitialized Arp, and is not a combined active-Arp hardware test.
- Two complete builds produce identical SYX and MAIN hashes. The package
  source hash set remains unchanged throughout validation.

Evidence:

- [Original CPU failure/control](../out/runs/project-save-orphan-native-20261019-01/report.json)
- [Original GUI ERROR](../out/runs/project-save-orphan-ui-20261019-01/02-orphan-save-error.png)
- [R4 native save/reload](../out/runs/flex-project-save-r4-native-20261019-01/report.json)
- [R4 GUI DONE](../out/runs/flex-project-save-r4-ui-20261019-01/02-project-save-complete.png)
- [R4 reset](../out/runs/flex-project-save-r4-boot-20261019-01/report.json)
- [Validation index](FLEX-PROJECT-SAVE-VERIFICATION.json)

Build from the lab root with the configured Python:

```sh
python scripts/build-cpu-extension.py out/runs/<fresh-output> \
  --elekloader-reference out/references/elekloader-upload-audit \
  --all-features --any-track --flex-save-screen
python -m unittest discover -s tests -v
```

Frozen sources and scenario runners are in
`out/runs/flex-project-save-r4-verification-20261019-01/` and
`out/runs/project-save-reboot-baseline-20261019-01/`. The user has confirmed
installation and Save As success. This does not establish every Flex workflow
or device durability condition.
