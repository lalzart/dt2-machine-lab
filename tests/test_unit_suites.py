"""Selection boundaries and failure propagation for the scoped unit command."""

import contextlib
import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import cli, unit


class UnitSuiteTests(unittest.TestCase):
    def test_buf_flex_and_older_models_have_separate_ownership(self):
        catalog = unit.read_catalog()
        buf = set(unit.select_modules(catalog, ["buf"]))
        flex = set(unit.select_modules(catalog, ["flex"]))
        shared = set(unit.select_modules(catalog, ["recorder"]))
        self.assertEqual(buf & flex, shared)
        self.assertIn("test_buf_next_bar", buf)
        self.assertIn("test_flex_bank", flex)
        self.assertNotIn("test_flex_bank", buf)
        self.assertNotIn("test_buf_next_bar", flex)
        self.assertTrue(buf.isdisjoint(unit.select_modules(catalog, ["buf-models"])))
        self.assertTrue(buf.isdisjoint(unit.select_modules(catalog, ["capicola"])))

    def test_all_preserves_discovery_and_combined_profiles_deduplicate(self):
        catalog = unit.read_catalog()
        all_modules = unit.select_modules(catalog, ["all"])
        self.assertEqual(len(all_modules), len(set(all_modules)))
        self.assertEqual(
            set(all_modules), {p.stem for p in (unit.ROOT / "tests").glob("test_*.py")}
        )
        selected = unit.select_modules(catalog, ["buf", "flex", "buf", "all"])
        self.assertEqual(set(selected), set(all_modules))
        self.assertEqual(len(selected), len(all_modules))
        with self.assertRaisesRegex(ValueError, "Unknown test suite"):
            unit.select_modules(catalog, ["buff-typo"])

    def test_unassigned_missing_or_multiply_owned_modules_refuse(self):
        catalog = {"groups": {"a": {"modules": ["test_a"]}}, "profiles": {}}
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory)
            (tests / "test_a.py").touch()
            unit.validate_catalog(catalog, tests)
            (tests / "test_new.py").touch()
            with self.assertRaisesRegex(ValueError, "unassigned modules=.*test_new"):
                unit.validate_catalog(catalog, tests)
            (tests / "test_new.py").unlink()
            (tests / "test_a.py").unlink()
            with self.assertRaisesRegex(ValueError, "missing modules=.*test_a"):
                unit.validate_catalog(catalog, tests)
            duplicate = copy.deepcopy(catalog)
            duplicate["groups"]["b"] = {"modules": ["test_a"]}
            with self.assertRaisesRegex(ValueError, "multiple groups"):
                unit.validate_catalog(duplicate, tests)

    def test_listing_does_not_import_or_execute_tests(self):
        with (
            patch.object(unittest.TestLoader, "loadTestsFromName") as load,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(unit.run(["buf"], list_only=True), 0)
        load.assert_not_called()
        self.assertIn("tests/test_buf_next_bar.py", output.getvalue())
        self.assertNotIn("test_capicola", output.getvalue())

    def test_unit_cli_defaults_to_buf_without_private_fixture_preflight(self):
        with (
            patch.object(sys, "argv", ["labctl", "unit"]),
            patch.object(
                cli, "doctor", side_effect=AssertionError("unexpected preflight")
            ),
            patch.object(unit, "run", return_value=0) as run,
        ):
            self.assertEqual(cli.main(), 0)
        run.assert_called_once_with(["buf"], list_only=False, verbose=False)

    def test_import_failure_returns_failure_and_restores_import_path(self):
        catalog = {
            "groups": {"broken": {"modules": ["test_unit_nonexistent_module"]}},
            "profiles": {},
        }
        original_path = sys.path[:]
        with (
            patch.object(unit, "read_catalog", return_value=catalog),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(unit.run(["broken"]), 1)
        self.assertIn("FAILED (errors=1)", error.getvalue())
        self.assertEqual(sys.path, original_path)
