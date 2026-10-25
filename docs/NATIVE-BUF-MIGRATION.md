# First native BUF/Sketch migration slice — OS 1.16

Follow-up: the separate `buf-native-compat-os116` audit explains the differing
replies and final output as corrected Type 17 and Type 7a/9a/11a SIMD semantics
in `38dfbe4`. Reintroducing both old behaviors reproduces the baseline exactly;
the old final mix must not be a migration oracle. The current
[recorder connection](NATIVE-BUF-RECORDING.md) builds on this first slice.
Results below retain the original saved-page run's scope and open gates.

This is an opt-in path over DigiKit `38dfbe4ae88263511eed95691c07fc07e17b6f26`.
The active lab remains pinned to `277760a`; existing Flex, BUF and other feature
profiles, private fixtures and firmware emitters are preserved. No dependency
installation, firmware edit, device transfer or publication is involved.

The slice provides an authenticated-reference CPU constructor and a small
native saved-page BUF adapter. It checks existing A/B/FREEZE playback without
private FEXT/MODIFY instruction shims, then starts the candidate CPU application
with a live native DSP and opens Sketch. It does not port the recorder's
ARM/capture/FREEZE job frontend or change the default `labctl` backend.

## Constructor correction

The earlier description of duplicate main-loop signatures was wrong. The
unmodified OS1.16 entry at `0x40033d00` has bytes `487940966f3c`; Sketch replaces
those six bytes with `4ef947ee0d00`, its next-bar polling hook. Upstream's
`mainloop signature ambiguous` error covers zero matches as well as multiple
matches. The source audit finds one stock match and zero candidate matches.
This was a host constructor failure, before CPU execution.

`lab/native/reference_main.patch` adds `new_patched_with_reference` to a copied
boot crate. It authenticates the stock SYX and MAIN against DigiKit's device
registry, resolves host service anchors from that exact reference, and loads
RAM and emulated flash from the complete candidate container. The caller must
retain the reference's service addresses and ABIs. The lab separately checks
the sealed candidate against its builder and container proof.

`lab/native_migration.py` copies only the boot crate into the ignored run,
applies the patch with exact revision/source guards, retains its AGPL license,
and points its other dependencies at unmodified upstream sources. The only
changed copied files are `src/runtime.rs` and the path-adjusted `Cargo.toml`.
The upstream checkout and pinned dependency trees are not edited. Existing
constructors keep their behavior. Constructor controls check stock initial-state
equivalence, exact candidate MAIN before instruction zero, rejection of a
corrupted reference, and the original failure without the new API.

This replaces the earlier host MAIN overlay with explicit reference-based
anchor resolution. It does not execute a physical bootstrap or DSP boot ROM.

## Saved-generation adapter and comparison

`lab/native/buf_adapter.rs` exposes prepared-state creation, native LP0 page
publication, native SPI2/SEC processing, descriptor/pointer observations and
voice work-buffer reads. It fails on unknown words, native traps and instruction
bounds. It does not replace an instruction with Python or use the old private
register-FEXT/conditional-MODIFY runtime.

`migration_legacy.py` runs the unchanged old runtime in a separate process and
freezes its prepared state and expected output. `migration_inputs.py` packs the
exact candidate DSP with current upstream tools and carries over the explicit
prepared-fixture options, including bank, stack and peripheral models. These
settings are part of the fixture contract, not DSP algorithm changes. The
prepared state comes from the old emulator, not from a new physical capture.

The saved fixture is `sketch-relocated-coupled-20261023-01`, with immutable A,
replacement B and a FREEZE alias of A. Four phases total 96 blocks:

| Phase | Blocks | Required observation |
| --- | ---: | --- |
| A and frozen A | 12 | Shared descriptor and exact old-runtime voice PCM |
| B publication with retained A readers | 12 | Existing reader pointers remain unchanged |
| Current B and frozen A | 48 | BUF advances to B; frozen A keeps its allocation |
| Later frozen A triggers | 24 | Snapshot remains playable after replacement |

Two new-runtime runs must repeat exactly. An incorrect frozen-source selection
must differ. A separate run uses unmodified stock DSP code on the new emulator
with the same fixture; its voice PCM and replies are compared with the candidate.
No new recording or long retirement/stress loop is used.

## Reply compatibility remains open

Voice PCM matches the old runtime bit-for-bit in all four phases, with retained
readers and the frozen allocation preserved. Native replies repeat exactly,
but old/new reply bytes differ. The first difference is in block 4 at wire
offset `0xb2`. The current emulator produces identical replies with stock and
candidate DSP code, so this comparison does not identify a BUF-specific change.
It also does not establish which emulator's replies are correct.

The differences are retained with per-phase hashes, counts and first offsets.
They are not masked, normalized or copied into new expected results. Reply
semantics, final mix and possible recorder feedback effects need investigation
before switching the default backend or qualifying native capture integration.
`default_migration_ready` stays false. A completed diagnostic run can therefore
report `native-first-slice-validated-reply-parity-open`; that is not a passing
default-migration gate.

## Reproduction and evidence layers

```sh
./labctl doctor
python3 scripts/check-native-sketch.py out/runs/native-sketch-FRESH \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
./labctl unit buf core integration
./labctl test sine --replay
```

Use a fresh ignored output directory. `--skip-boot` runs the constructor and
saved-page comparisons while developing the adapter. The complete command also
initializes the DSP from its loader application entry, constructs the CPU from
the complete candidate container without a MAIN overlay, checks reset segments,
BSS and code/canaries, requires native replies/sample loading, and opens Sketch
with normal NO/SONG panel input. Sources, generated core, runner, inputs and
dependencies are fingerprinted; source drift prevents a valid result.

The CPU starts at the upstream application-reset entry. DSP initialization is
independent of CPU-to-ROM upload. The SSI rate and DSP instruction cadence remain
models; prepared-page playback is a separate test from coupled startup. Voice
PCM, control replies, final mix, physical timing, listening and hardware remain
distinct evidence layers. Keep OS1.16 and the BUF/FREEZE product contract intact
while migrating the host tooling.

## Results — 2026-10-23 JST

Final run: `out/runs/sketch-native-migration-20261023-07/`.
[Report](../out/runs/sketch-native-migration-20261023-07/report.json),
[evidence index](../out/runs/sketch-native-migration-20261023-07/verification.json).
Its status is `native-first-slice-validated-reply-parity-open`, with
`default_migration_ready=false`.

The complete container is the previously checked `sketch-device-build-20261023-13`
candidate: MAIN `cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c`,
DSP `2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a`.
These firmware bytes and the prior inputs are unchanged. Constructor stock-state
equivalence and corrupted-reference refusal pass. The normal constructor's
zero-match failure remains reproduced as a control.

The native CPU reaches application-ready, loads all 45 reset segments with their
declared BSS, retains its code and 30 canaries, and renders Sketch after native
NO/SONG input. The DSP independently initializes in 238,750,000 instructions.
Through panel interaction, 6,878 coupled frames produce 6,875 nonzero native
replies; 1,620 LP0 units drain, with zero missing SPORT blocks. These counts are
model observations, not device timing or final-audio equivalence.

All 96 saved blocks match old-runtime voice PCM exactly, repeated twice. The
current stock DSP comparator matches both the candidate's PCM and replies.
The prepared state overlaps neither the changed stock-code literal ranges nor
the three added DSP code ranges in the stock comparator. The wrong frozen-source
control differs, and publication preserves all six observed reader pointers
and the frozen A descriptor. Old/new replies differ by 812, 2,073, 7,550 and
3,152 bytes in the four respective phases. Their full binary outputs are saved.
Their meaning and any final-output/recorder-feedback effect remain unqualified.

229 BUF/core/integration unit tests, focused Ruff and SINE compatibility pass.
SINE: `out/runs/20261023T033046Z-test-ffd825e4/`. Native and SINE runs use the
same frozen current source manifest; the source-preservation check allows only
the seven added migration files. Firmware emitters, dependency pins, upstream
sources and existing fixture bytes remain exact. No new recordings, private
instruction shims on the new runtime, or default-backend switch occurred.

Earlier prototype runs remain intact. They caught the native PC's 128-bit host
type, incomplete transfer of prepared-state options, and an overly strict
assumption that the option table ended the SHFP file. After carrying the exact
fixture options, voice PCM matched; the remaining reply differences were kept
as an open qualification gate. Those attempts do not establish device faults.

![Sketch on the opt-in native path](../out/runs/sketch-native-migration-20261023-07/panel.png)
