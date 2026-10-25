"""Exercise the copied semantic patch without altering imported baseline forms."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

# lab.runtime installs the tooling path before these imports.
# isort: off
from lab import type7a_cases as cases
from lab.runtime import REPO
from lab.type7a_runtime import apply

import sharc_trace as st
from sharc_core.forms_dag import _type_7a as original
from sharc_disasm import Instruction
# isort: on


class Type7aRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        target = root / "tools/sharc_core/forms_dag.py"
        target.parent.mkdir(parents=True)
        shutil.copyfile(REPO / "tools/sharc_core/forms_dag.py", target)
        apply(root)
        spec = importlib.util.spec_from_file_location("sharc_core.lab_type7a_test", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.modified = staticmethod(module._type_7a)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_independent_sisd_state_matrix(self):
        for case in cases.cases():
            with self.subTest(case=case["name"]):
                insn = Instruction(0, 6, "7a", case["fields"], kind="confident")
                actual = self.modified(cases.state(case, st), insn, insn.fields, "7a")[0]
                cases.check(case, actual, st)

    def test_original_fails_eq_and_old_paths_are_identical(self):
        for case in cases.cases():
            insn = Instruction(0, 6, "7a", case["fields"], kind="confident")
            old = original(cases.state(case, st), insn, insn.fields, "7a")[0]
            new = self.modified(cases.state(case, st), insn, insn.fields, "7a")[0]
            if case["fields"]["cond[4:0]"] in (31, 23):
                self.assertEqual((old.uregs, old.pc_sw, old.stopped),
                                 (new.uregs, new.pc_sw, new.stopped))
            else:
                self.assertEqual(old.stopped, "unsupported Type7a predicate")

    def test_refuses_pinned_tree_and_source_drift(self):
        with self.assertRaisesRegex(ValueError, "Refuse pinned"):
            apply(REPO)
        root = Path(self.temp.name)
        with self.assertRaisesRegex(ValueError, "source drift"):
            apply(root)  # Already patched: never apply a second time.
