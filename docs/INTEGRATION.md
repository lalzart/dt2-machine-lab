# SINE integration findings: Digitakt II OS 1.16

Recorded 2026-10-05 from the local source and retained run artifacts. This is
a version-specific engineering note, not a general machine API. See
[current results and scope](STATUS.md) and the
[development plan](DEVELOPMENT.md).

## Revisions and inputs

| Input | Identity |
| --- | --- |
| DigiKit base | `277760aad51b036a4756db051409d4d3b1eeccbc`, plus the local SINE files listed below |
| Original experiment branch | `codex/dt2-sine-machine` in the preserved workspace; changes remain uncommitted there |
| Selache | `2b26d3b75c53063575bc5c820fa0d38879335187` |
| Original 1.16 SYX SHA-256 | `278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec` |
| Stock MAIN SHA-256 | `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d` |
| Stock BLOB SHA-256 | `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2` |
| Patched SINE MAIN SHA-256 | `344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830` |
| Patched SINE BLOB SHA-256 | `a3e8594d07f656f2e4dc52a16f433646285e4d5f987a2728cd252b5d9dfbef25` |

Original implementation, preserved in the previous workspace under `work/digikit/`:

- `tools/dt2_machine_test.py`: CPU patch, cold boot, menu and trigger capture.
- `tools/dt2_machine_dsp.py`: DSP loader patch, assembly/linking, native replay.
- `tools/dt2_machine_verify.py`: signal, repeat, negative and lifecycle checks.
- `tools/dt2_sine.s` and `tools/dt2_sine.ldf`: original oscillator and placement.
- `tests/test_lint.py`: registers the three new Python files for lint checks.

The lab now owns `lab/cpu.py`, `lab/dsp.py`, `lab/suite.py`,
`machines/sine/dsp.s` and `machines/sine/memory.ldf`. The assembly/linker
were copied unchanged; adapters were migrated to lab-owned paths. Source
fingerprints are in [MIGRATION.json](MIGRATION.json). The original CPU
panel-capture helper remains preserved in the previous workspace; integrating
it into clean fixture generation is the next milestone.

## CPU selection and the control wire

The CPU builder clones MANUAL SLICE, type 6, as SINE, type 7. Descriptor fields
are `[248, 249, 0, 251, 252, 253, 0, 254, 10]`. For 1.16 the descriptor array
is at `0x4293b960`, stride `0x2c`. The prepared plan has 51 writes and uses
952 of 2,108 reserved CPU patch bytes. That allocation says nothing about DSP
capacity.

The actual panel path is FUNC+SRC, navigate to SINE, YES to commit, YES to
close, then TRIG 1. The capture uses the emulated panel parser. Selection
alone leaves the old transmitted machine word in this fixture; the pad
trigger refreshes it. A test that reads only the idle frame can therefore
miss a valid selection. The CPU report separately checks selected track RAM,
the transmitted type after trigger, and fault pages.

Machine type is the big-endian halfword at wire byte offset `0x94 + 2*t`,
with zero-based track `t`. The trigger/release words are at `0x22`/`0x24`;
`0x26`/`0x28` also carry one-shot events. Repeating a trigger-bearing tail
would retrigger continuously: the replay checks that the held tail has none.
The recorder receives real CPU transactions and supplies zero DSP replies;
it is not a full bidirectional CPU/DSP integration test.

Independent cold boots produced different defaults and evolving control
values. Stock-clone parity was established using the same real TEST capture
with only type 7 changed to type 6. That controlled edit is explicit in the
runner. It must not be described as two independent, identical panel runs.

## DSP dispatch, hook and memory

The stock SHARC remap table maps types 0–6 to `0,1,2,3,4,0,5`. It is at
DM `0x2567c0` (loader alias `0x282567c0`). The patch redirects the pointer
load at SW `0x1c2731` to an eight-entry table at byte `0x200f0000`, with
type 7 deliberately mapped to selector 5. The initial TEST stage used only
that extension and matched stock SLICE with identical controls.

| Integration point | Meaning in this prototype |
| --- | --- |
| DM `0x255970` | Cached machine types; checked before custom rendering. |
| DM `0x2412cc + v*0x1d8` | Voice record for lane `v`; two lanes per track. |
| Voice record `+4` | Start of the 64-float source work buffer. |
| SW `0x1c4f15` | Hook after stock voice prologue; six displaced bytes are checked before patching. |
| SW `0xbf8800` / byte `0x200f1000` | New linked SINE entry. |
| SW `0x1c4f18` | Stock continuation after replaying displaced instructions. |
| SW `0x1c524a` | Custom source rejoins the stock decimator/return path. |
| DM `0x24f0cc` | Latched trigger B used by the new source. |

Keep byte addresses and SHARC SW execution addresses distinct. Use the
loader/address helpers rather than applying one conversion to every region.
The displaced bytes are `5499a801408c`; the fallback executes them and
preserves the stock continuation. This particular prologue/epilogue contract
has been exercised by SINE; it is not a validated ABI for arbitrary engines.

The added loader block reserves `[0x200f0000, 0x200f2000)`:

| Offset | Use |
| --- | --- |
| `+0x000` | Eight-entry remap table, 32 bytes. |
| `+0x100`, `+0x110` | Independent state for lanes 0/1: phase, age, active, previous-SINE. |
| `+0x130` | New-code execution counter; state/diagnostics reserve 64 bytes total. |
| `+0x400` | 256 float32 sine entries, 1,024 bytes. |
| `+0x1000` | Linked code, currently 632 bytes, with a 2 KiB code limit. |

The builder checks that this 8 KiB arena does not overlap stock loader
segments, adds a checksummed block before the final loader block, and parses
the result again. Absence from the loader is not proof that the running
firmware never owns this memory. Runtime allocation/stack/heap conflicts and
physical placement remain unverified.

Only track 1's two lanes generate the tone. Unsupported custom lanes are
cleared. Stock types execute the fallback. Retrigger resets phase and age;
leaving SINE clears state; returning without a trigger stays silent.

## Audio and toolchain lessons

The oscillator uses a 32-bit phase accumulator with increment `19685267`,
a 256-point sine table with linear interpolation, gain 0.125, and a 250 ms
envelope with 5 ms attack/release. The source fixture is 64 samples per block
at 96 kHz. A trigger at replay frame 150 starts source processing at 151,
after the stock latch advances. Include that delay in signal expectations.

The WAV renderer reads the two voice work buffers and averages adjacent
samples into 32-sample, 48 kHz stereo blocks. The new code rejoins the stock
decimator, but this WAV tap is not final mixer/DAC output and does not verify
downstream AMP/filter/FX behavior. Audio replay imports a stock-initialized,
sample-loaded DSP state; patched SHARC initialization was checked separately.
Sample-free startup is still open.

Link before injecting code: branches have relocations. Selache's indirect
operand spelling is `DM(-5, I6)` or `DM(1, I0)`, not the pretty-disassembler's
`DM(I6-5)` form. Some compressed integer ADD encodings did not agree with the
local DigiKit decoder; the source uses explicit `.NOCOMPRESS` regions for
affected additions. The fallback uses checked NOP placeholders replaced
with the original six instruction bytes. Keep those checks and the linked
listing/decoder comparison when refactoring.

Native replay disables optimized blocks and enables runtime decoding so the
loaded patched bytes are executed. Re-enabling generated blocks requires
regeneration for the candidate image and equivalence checks against this
reference. Do not use a stock-image compiled block as proof of patched-code
execution.

## Existing reproduction and its limits

From the machine lab root, using the imported, hash-checked fixture:

```sh
./labctl render sine
```

This reassembles the DSP patch and replays the named SINE control capture.
It does not recreate every prerequisite. The baseline PCM SHA-256 is
`2a38b64c83b1636b9f1a3793f6e78c71275d0a64ca2473c2e6b20bc183673eae`.
The retained measurements are 440.000005 Hz, source peak 0.125, and maximum
analytic error `9.45e-6`; exact repeat, negative-control, stock-isolation and
retrigger/switch checks passed. See the existing
[fixture expectations](../tests/fixtures/sine-1.16.json) and current run reports under `out/runs/`.

Original fixture dependencies, relative to the preserved `work/digikit/`:

- `out/plusdrive/auto/be080a1acd14/dt2.img` and its ready snapshot.
- `out/native/live/state-66912e66cfed237d2628f167.pack`.
- `out/native/playground-116/target/release/libsharc_native.dylib`.
- `out/machine-test-116/sine-type-7.dtfr` and supporting TEST/SLICE captures.
- The sibling `work/selache/` build and patched Unicorn environment.

The CPU wrapper reuses snapshots by existence; the DSP wrapper imports a
native state through a private API; verification references earlier TEST
artifacts by filename. These are the main reproducibility gaps to replace
with input-derived cache keys and an explicit fixture builder. `uv sync`
must be followed by the pinned patched-Unicorn installer during setup; use
the existing `.venv/bin/python` for ordinary runs.

The saved one-second render took 40.94 host seconds and recorded 328,715,999
emulated instructions across the replay. These are whole-replay counters,
not isolated oscillator cost or hardware cycles. No CPU/DSP load percentage
was established. The next useful instrumentation reports per-block and
per-region work against the same stock fixture, with host speed separate.

## Migration improvements

The lab imports only the two firmware sections, native library/state and
three control captures. Their hashes are tracked; their bytes stay ignored.
It generates the symbol database in its own versioned cache. `labctl` checks
inputs before and after execution, allocates a new run directory, and reports
subprocess failure or timeout. Verification uses explicit checks that remain
active under Python `-O`. Stock/clone comparisons read actual generated PCM,
not just previously saved metadata. The current Python environment is an
explicit dependency in ignored `.local/config.json`; no old fixture or
database path is required by replay.
