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
./labctl unit all             # explicit whole-repository regression
```

BUF and Flex mean different features; see [their source guide](FEATURES.md).
The routine BUF selection excludes the Capicola, Arp, Flex save/bank, older BUF
model and cross-feature suites. Counts below describe this cleanup snapshot;
new tests can increase them.

| Suite | Tests | Scope |
| --- | ---: | --- |
| `buf` (default) | 115 | Current native BUF and shared recorder |
| `flex` | 93 | Existing native Flex and shared recorder |
| `buf-native` | 99 | Native capture, next-bar/publication, FREEZE and generation lifetime |
| `recorder` | 16 | Input/takes, sample heap, pattern clock and sector overlay |
| `buf-models` | 46 | Earlier modeled BUF policies and restricted reuse proof |
| `flex-native` | 77 | Flex source lifecycle, save/discard and banks |
| `capicola` | 57 | Capicola engine, memory, layouts and quality experiments |
| `arp` | 62 | Native arp controls, clocks and persistence |
| `integration` | 30 | Cross-feature builders, any-track behavior, shared save/resources |
| `core` | 52 | Test selection, fixture integrity, tooling and diagnostics |
| `all` | 439 | Every unit test, each ID once |

Profiles overlap through `recorder`; their counts should not be added directly.
The original 428 cases are preserved. Six checks cover suite boundaries,
catalogue completeness, selection deduplication, listing, CLI dispatch and
failure propagation. Four subsequent BUF alignment cases cover empty destination,
performance edits, length refusal and assignment-free publication; one recorder
case distinguishes the explicit SSI sample clock from the legacy input default.
Cases were not merged into large catch-all assertions to
make the count smaller.

## Which checks to run

- For native BUF work, run `./labctl unit buf`. For a narrow next-bar iteration,
  the existing focused invocation remains available:
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
needed. Current BUF native fixtures live in `tests/buf_native_support.py`; it
contains helpers without test cases. BUF suites do not import other test suites
to borrow their setup.

Historical result documents retain their original repository-wide counts and
commands as evidence of those runs. They are not the current routine test policy.
