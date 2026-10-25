"""Composition invariants against independently guarded legacy feature images."""

import tempfile
import unittest
from pathlib import Path

from lab.all_features_base import BASE_SHA, LOADER
from lab.cpu_extension import CAVE, build_cpu
from lab.cpu_fixture import install, segments
from lab.dt2_116 import BASE
from lab.project import ROOT
from lab.resources import patch_conflicts


class AllFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin"
        if not path.is_file():
            raise unittest.SkipTest("Private OS1.16 fixture required")
        cls.stock = path.read_bytes()

    def test_all_features_preserve_ddr_payloads_and_original_plaits_code(self):
        # Load the optional adapter only after the configured dependency path.
        from lab import runtime  # noqa: F401

        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temporary:
            output = Path(temporary)
            image, meta = build_cpu(self.stock, features="all", output=output)
            previous, prior = build_cpu(self.stock)
            self.assertEqual(segments(image, meta), segments(previous, prior))
            self.assertEqual(meta["base"]["sha256"], BASE_SHA)
            self.assertTrue(meta["base"]["retirement_reversible"])
            self.assertEqual(meta["loader_address"], LOADER)
            oracle = (output / "PLAITSCAPI_NOFLEX_MAIN.bin").read_bytes()
            self.assertEqual(
                image[CAVE - BASE : 0x40312000 - BASE],
                oracle[CAVE - BASE : 0x40312000 - BASE],
            )
            self.assertFalse(
                patch_conflicts([(str(i), [w]) for i, w in enumerate(meta["writes"])])
            )
            self.assertEqual(
                len([w for w in meta["writes"] if w["address"] == 0x40043A30]), 1
            )
            self.assertEqual(
                image[0x40312000 - BASE : len(self.stock)],
                self.stock[0x40312000 - BASE :],
            )
            self.assertEqual(
                (image, meta), build_cpu(self.stock, features="all", output=output)
            )

    def test_prepared_install_uses_sram_destination_without_clobbering_live_bss(self):
        from lab import runtime  # noqa: F401

        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temporary:
            image, meta = build_cpu(self.stock, features="all", output=Path(temporary))
            writes = []
            install(lambda addr, data: writes.append((addr, data)), image, meta)
            self.assertFalse(
                any(0x40320000 <= addr < meta["chain_address"] for addr, _ in writes)
            )
            self.assertTrue(
                any(addr == 0x8000F180 and data == bytes(32) for addr, data in writes)
            )
            self.assertTrue(any(addr == 0x47E8B000 for addr, _ in writes))
            with self.assertRaises(ValueError):
                segments(image[:-4], meta)

    def test_unknown_feature_profile_and_missing_output_are_refused(self):
        for options in (dict(features="unknown"), dict(features="all")):
            with self.assertRaises(ValueError):
                build_cpu(self.stock, **options)
