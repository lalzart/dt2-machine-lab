# Scoped unit tests

Run the checks for the feature being changed. `labctl` selects the configured
Python environment. The `unit` command uses ordinary unittest; it does not build
firmware, start a coupled audio experiment or run the private-fixture preflight.
Individual native tests still require their configured runtime, and a few
integration tests require the private fixture. Skips are reported by unittest.

```sh
./labctl unit                 # default: BUF, including recorder support
./labctl unit flex            # existing Flex, including recorder support
./labctl unit buf --list      # inspect selected modules without importing them
./labctl unit buf flex        # both features; shared modules execute once
./labctl unit core            # shared tooling or test-runner changes
./labctl unit buf-models      # earlier host models/restricted reuse proof
./labctl unit buf-full        # current plus earlier Unicorn BUF fixtures
./labctl unit all             # explicit whole-repository regression
```

BUF and Flex mean different features; see [their source guide](FEATURES.md).
The routine BUF selection excludes Capicola, Arp, Flex save/bank, earlier BUF
models and cross-feature suites. `tests/suites.json` is the current catalogue;
historical test totals are not a stable API. Use `--list` to see the current
selection instead of maintaining another hard-coded count table.

| Suite | Scope |
| --- | --- |
| `buf` (default) | Accepted Sketch/BUF workflow plus shared recorder checks. |
| `sketch` | Current selector, controls, startup, stopped capture, COPY/PASTE, LED and placement fixtures. |
| `buf-full` | Current Sketch plus the earlier Unicorn BUF/retirement fixtures and shared recorder. |
| `flex` | Legacy native Flex plus shared recorder checks. |
| `buf-native` | Earlier Unicorn BUF instruction and retirement fixtures, retained explicitly. |
| `recorder` | Shared input/takes, heap, pattern clock and sector overlay. |
| `buf-models` | Earlier host models and restricted DSP-reuse proofs. |
| `flex-native` | Legacy Flex lifecycle, save/discard and banks. |
| `capicola`, `arp` | Their feature-specific engines, controls and persistence. |
| `integration` | Cross-feature composition, any-track behavior, shared save/resources. |
| `core` | Test selection, integrity, tooling and diagnostics. |
| `all` | Explicit whole-repository regression, each test ID once. |

Native instruction cases require an explicitly built Rust ColdFire bridge, e.g.:

```sh
DT2_BUF_SELECTOR_CORE=/absolute/path/to/libcfselector.dylib ./labctl unit buf core
```

`lab/native/buf_selector_core.rs` and `scripts/check-buf-selector.py` own that
bridge at the pinned native upstream. It is a generated local library, not a
committed fixture. Other prepared cases use the configured patched Unicorn and
private inputs. Check reported skips; a skipped native case is not coverage.
See [the R8 guide](SKETCH-BUF-CHECKPOINT.md) for the exact build and integration
probe boundary. Profiles overlap through `recorder` and deduplicate modules.

The 2026-10-25 cleanup reproduced a host SIGILL at the first Unicorn `mem_map`
even in the preserved R8 source, before firmware execution. That old host runtime
is not repaired by this cleanup. The default `buf` profile now selects the
accepted Rust-bridge Sketch workflow and shared recorder models. The former
broader selection remains available as `buf-full`; no test cases are deleted
or instruction assertions weakened. `all` still includes those explicit cases.
Legacy retirement/Unicorn coverage is not claimed by a passing routine BUF run.

## Which checks to run

- For accepted Sketch/BUF work, run `./labctl unit buf`; a narrow timing-control
  iteration can select `test_sketch_controls.py`. The older next-bar invocation
  remains explicit and needs a working host Unicorn runtime:
  `"$LAB_PYTHON" -B -m unittest discover -s tests -p test_buf_next_bar.py -v`
  with `LAB_PYTHON` set to the configured interpreter.
- For existing Flex work, run `./labctl unit flex`.
- For shared recorder changes, run `./labctl unit buf flex`; the shared cases
  execute once. Add `buf-models` when changing an earlier model or probe.
- For shared tooling/test-runner changes, run `core` and the affected feature
  suite. Use `all` for broad cross-feature changes or an explicit full audit.
- For all-feature builders or shared save/resource composition, add
  `integration` and the affected feature suites.
- For DSP/adapter behavior changes, retain the appropriate stock-compatibility,
  exact-repeat and negative-control experiment and `./labctl test sine --replay`.
  Unit-only or documentation cleanup does not require another audio replay.

Do not run Capicola or Arp's detailed suites for unrelated BUF edits. Plaits DSP
and prepared-fixture replay workflows remain separate from these unit groups.
The expensive coupled recorder drivers and their 100-cycle experiments also
remain explicit commands; selecting `unit buf` does not launch them.

## Maintaining the catalogue

`tests/suites.json` assigns every `tests/test_*.py` module to exactly one group.
Profiles combine groups. `all` selects every group. The runner refuses missing,
unassigned or multiply assigned modules, unknown suites, empty test selections
and duplicate case IDs. A test import error produces a failing run.

Add a new module to its owning group. Test files retain their paths, so ordinary
`python -B -m unittest discover -s tests -v` remains compatible when explicitly
needed. Earlier native fixtures live in `tests/buf_native_support.py`, which
contains helpers without test cases. Current Sketch cases also reuse setup from
the earlier Sketch/next-bar modules with an explicit Rust Core substitution;
those helper imports do not add their test cases to the selected suite. Keep
the instruction backend explicit and inspect skips rather than falling back
silently to a different emulator.

Historical result documents retain their original repository-wide counts and
commands as evidence of those runs. They are not the current routine test policy.
