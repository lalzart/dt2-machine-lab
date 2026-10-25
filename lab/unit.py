"""Feature-scoped unittest selection; no firmware build or private-fixture preflight."""

import json
import sys
import unittest

from lab.project import ROOT


def read_catalog(root=ROOT, *, validate=True):
    catalog = json.loads((root / "tests/suites.json").read_text())
    if validate:
        validate_catalog(catalog, root / "tests")
    return catalog


def validate_catalog(catalog, tests):
    groups, profiles = catalog["groups"], catalog["profiles"]
    if "all" in groups or "all" in profiles or groups.keys() & profiles.keys():
        raise ValueError("Suite names must be unique; 'all' is reserved")
    owners = {}
    for name, group in groups.items():
        if not group["modules"]:
            raise ValueError(f"Empty test group: {name}")
        for module in group["modules"]:
            if module in owners:
                raise ValueError(f"Test module {module} belongs to multiple groups")
            owners[module] = name
    discovered = {path.stem for path in tests.glob("test_*.py")}
    missing = sorted(owners.keys() - discovered)
    unassigned = sorted(discovered - owners.keys())
    if missing or unassigned:
        raise ValueError(
            f"Update tests/suites.json: missing modules={missing}, "
            f"unassigned modules={unassigned}"
        )
    for name, profile in profiles.items():
        if not profile["groups"] or set(profile["groups"]) - groups.keys():
            raise ValueError(f"Unknown or empty groups in test profile: {name}")


def select_modules(catalog, names):
    groups, profiles = catalog["groups"], catalog["profiles"]
    selected = []
    for name in names:
        if name == "all":
            members = groups
        elif name in profiles:
            members = profiles[name]["groups"]
        elif name in groups:
            members = [name]
        else:
            raise ValueError(f"Unknown test suite: {name}")
        for group in members:
            selected.extend(groups[group]["modules"])
    return list(dict.fromkeys(selected))


def add_arguments(parser):
    # Catalogue completeness gates unit execution, not unrelated build commands.
    catalog = read_catalog(validate=False)
    parser.add_argument(
        "suites", nargs="*", metavar="SUITE", help="suite names (default: buf)"
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="list selected modules without importing or running them",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.epilog = "Default: buf. Groups: " + "; ".join(
        f"{name}: {group['description']}"
        for name, group in {**catalog["profiles"], **catalog["groups"]}.items()
    )


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def run(names, *, list_only=False, verbose=False):
    try:
        modules = select_modules(read_catalog(), names)
        if not modules:
            raise ValueError("No test modules selected")
        print(f"Unit suites: {', '.join(names)} ({len(modules)} modules)", flush=True)
        if list_only:
            for module in modules:
                print(f"tests/{module}.py")
            return 0
        # Existing tests use flat helper imports. Keep their import path active
        # through execution, without changing firmware/dependency configuration.
        original_path = sys.path[:]
        sys.path.insert(0, str(ROOT / "tests"))
        try:
            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            for name in modules:
                loaded = loader.loadTestsFromName(name)
                if not loaded.countTestCases():
                    raise ValueError(f"No tests found in {name}")
                suite.addTests(loaded)
            tests = list(cases(suite))
            ids = [test.id() for test in tests]
            if not ids or len(ids) != len(set(ids)):
                raise ValueError("Empty selection or duplicate test IDs in unit suite")
            result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            sys.path[:] = original_path
    except (ValueError, OSError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
