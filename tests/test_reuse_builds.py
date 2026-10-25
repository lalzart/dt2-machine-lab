"""Baseline hashes and rejection paths exercise the actual CPU builders."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lab import arp_firmware, flex_native_build
from lab.diagnostics import make_snapshot, render_html
from lab.mods import cpu_plan, resource_declarations
from lab.project import ROOT


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin"
        if not path.is_file():
            raise unittest.SkipTest("Private OS1.16 fixture required")
        cls.stock = path.read_bytes()

    def test_default_native_images_preserve_independent_frozen_hashes(self):
        arp, _ = arp_firmware.patch_cpu(self.stock, tempo_ui=True)
        flex, _ = flex_native_build.patch_cpu(self.stock, managed_sources=True)
        self.assertEqual(
            hashlib.sha256(arp).hexdigest(),
            "eec11e5201fa39b42d9b4919c05ff83b7f3973425783712a2d2a092b40121f44",
        )
        self.assertEqual(
            hashlib.sha256(flex).hexdigest(),
            "562061c4c17d86d7eec0c9e12fbb3455b865131d39502128c42b39c1d573a19a",
        )
        bad = bytearray(self.stock)
        bad[100] ^= 1
        for builder in (arp_firmware.patch_cpu, flex_native_build.patch_cpu):
            with self.assertRaises(ValueError):
                builder(bytes(bad))

    def test_shared_save_variants_fit_separately_and_change_actual_hook_target(self):
        for builder, options, label in (
            (arp_firmware.patch_cpu, dict(tempo_ui=True), "save hook"),
            (
                flex_native_build.patch_cpu,
                dict(managed_sources=True),
                "project_save hook",
            ),
        ):
            _, legacy = builder(self.stock, **options)
            image, shared = builder(self.stock, shared_save=True, **options)
            self.assertNotEqual(shared["sha256"], legacy["sha256"])
            write = next(w for w in shared["writes"] if w["label"] == label)
            self.assertEqual(
                image[
                    write["address"] - 0x40000400 : write["address"]
                    - 0x40000400
                    + len(bytes.fromhex(write["after"]))
                ],
                bytes.fromhex(write["after"]),
            )
            self.assertTrue(
                any(
                    "save_prepare" in name or "arp_prepare" in name
                    for name in shared["locations"]
                )
            )

    def test_actual_composition_refuses_the_known_space_and_hook_conflicts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temporary:
            report = cpu_plan(["arp", "flex"], Path(temporary))
            self.assertFalse(report["compatible"])
            self.assertFalse(report["raw_payloads_fit"])
            self.assertEqual(len(report["overlaps"]), 86)
            self.assertEqual(sum(report["payload_bytes"].values()), 14803)
            self.assertFalse(report["unverified_memory_admitted"])
            with self.assertRaises(ValueError):
                cpu_plan(["sine", "capicola"], Path(temporary))

    def test_build_compatibility_import_does_not_require_a_run_environment(self):
        environment = dict(os.environ)
        environment.pop("DT2_LAB_RUN_DIR", None)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "from lab.plaits import build_cpu,build_blob; from lab.context import BuildContext",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class ResourceImportTests(unittest.TestCase):
    def test_nested_bounds_are_explicit_and_unsupported_hardware_claims_are_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "resources.json"
            report = resource_declarations()
            path.write_text(json.dumps(report))
            snapshot = make_snapshot([], integration_reports=[path])
            page = render_html(snapshot)
            self.assertIn("not additive", page)
            self.assertIsNone(snapshot["hardware"]["cpu_load_percent"])
            report["hardware_utilization"] = 25
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                make_snapshot([], integration_reports=[path])
            report["hardware_utilization"] = None
            report["records"][0]["bytes"] = -1
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                make_snapshot([], integration_reports=[path])
