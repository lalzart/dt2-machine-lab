"""Release-source identity and relocation bounds must fail closed."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lab.capicola_layout import CODE_BASE, STATE_BASE, relocate_assembly
from lab.capicola_memory import BANK_END
from lab.capicola_reddit import (
    COLD_BASE,
    COLD_END,
    HOT_BASE,
    HOT_END,
    RING_BASE,
    RING_BYTES,
    VOICE_BASE,
    VOICE_BYTES,
    prepare,
    replace_exact,
    validate_sources,
    widen_adds,
)


class AuthorPortTests(unittest.TestCase):
    def test_sketch_relocation_changes_only_generated_linker_placement(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            default = prepare(root / "default").parent
            moved = prepare(
                root / "moved", cold_base=0x200B0000, cold_end=0x200C0000
            ).parent
            differences = [
                str(p.relative_to(default))
                for p in default.rglob("*")
                if p.is_file()
                and p.read_bytes() != (moved / p.relative_to(default)).read_bytes()
            ]
            self.assertEqual(differences, ["sharc/l1l2.ldf"])
            self.assertIn(
                "START(0x200b0000) END(0x200bffff)",
                (moved / "sharc/l1l2.ldf").read_text(),
            )

    def test_generated_cold_placement_refuses_unaligned_or_foreign_regions(self):
        cases = (
            (COLD_BASE - 4, COLD_END),
            (COLD_BASE, COLD_END + 4),
            (COLD_BASE + 1, COLD_END),
            (COLD_BASE, COLD_BASE),
        )
        with TemporaryDirectory() as folder:
            for i, (start, end) in enumerate(cases):
                with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                    prepare(Path(folder) / str(i), cold_base=start, cold_end=end)

    def test_exact_source_and_separate_static_regions(self):
        lock = validate_sources()
        self.assertEqual(
            lock["sha256"],
            "87bb2b073dae7253d7694198eced9a63ea4313373eb5ac1573902560cf19ad23",
        )
        self.assertEqual(len(lock["files"]), 66)
        self.assertLess(CODE_BASE, COLD_BASE)
        self.assertEqual(COLD_END, VOICE_BASE)
        self.assertLessEqual(VOICE_BASE + VOICE_BYTES, 0x200F2000)
        self.assertLessEqual(RING_BASE + RING_BYTES, STATE_BASE)
        self.assertLess(STATE_BASE, BANK_END)
        self.assertLess(HOT_BASE, HOT_END)

    def test_foreign_and_missing_address_literals_rejected(self):
        self.assertIn(
            hex(STATE_BASE + 0x21000),
            relocate_assembly("R0=0x200e1000;", "kernel", family="integration"),
        )
        for text in ["R0=0x200e1004;", "R0=0x200e1000; R1=0x200e4000;", "R0=0;"]:
            with self.assertRaises(ValueError):
                relocate_assembly(text, "kernel", family="integration")

    def test_generated_overlay_refuses_drift_and_changes_no_float_math(self):
        self.assertEqual(replace_exact("abc", "b", "d"), "adc")
        for text in ["ac", "abbc"]:
            with self.assertRaises(ValueError):
                replace_exact(text, "b", "d")
        text = "R0 = R0 + R1;\nF0 = F0 + F1;\n"
        wide = widen_adds(text)
        self.assertIn(".NOCOMPRESS;\nR0 = R0 + R1;\n.COMPRESS;", wide)
        self.assertIn("F0 = F0 + F1;", wide)
        self.assertEqual(wide.count(".NOCOMPRESS"), 1)
