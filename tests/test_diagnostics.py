"""Reject misleading resource comparisons and incomplete accounting evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.diagnostics import (
    Inputs,
    bank_accounting,
    compare_profiles,
    load_flex,
    load_layout,
    load_profile,
    load_reservation,
    load_stock,
    main,
    make_snapshot,
    render_html,
    series,
)
from lab.metrics import distribution
from lab.project import ROOT


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        firmware = json.loads((ROOT / "profiles/dt2-1.16/profile.json").read_text())
        self.manifest = {
            "status": "passed",
            "finished_utc": "2026-10-08T00:00:00Z",
            "fixture_files": {
                "sections/section_3_MAIN_OS.bin": firmware["stock_main_sha256"],
                "sections/section_7_BLOB.bin": firmware["stock_blob_sha256"],
                "native/state.pack": "state",
                "native/libsharc_native.dylib": "library",
            },
            "dependencies": {"digikit": "revision"},
            "platform": {"machine": "arm64"},
        }
        self.dump(self.run / "manifest.json", self.manifest)
        self.profile = self.write_profile("stock", [10, 20, 30])
        self.flex = {
            "status": "PASS",
            "scope": "Native OS 1.16 experiment",
            "frames": 141,
            "stereo": False,
            "accounting_after_accept": [1, 0, 282, 426],
            "managed_handover": {"accounting_after_save": [1, 1, 0, 64]},
            "sequential_reuse": {
                "cycles": 2,
                "retained_source_bytes": 0,
                "retained_descriptor_bytes": 128,
            },
            "heap_trace": {
                "pending_calls": 0,
                "minimum_free": 300,
                "initial": {
                    "arena_bytes": 1024,
                    "free_bytes": 800,
                    "largest_block": 512,
                },
                "final": {"arena_bytes": 1024, "free_bytes": 700, "largest_block": 256},
                "events": [
                    {"free_before": 800, "free_after": 300, "largest_after": 128},
                    {
                        "free_before": 300,
                        "free_after": 700,
                        "largest_after": 256,
                        "failed": True,
                    },
                ],
            },
        }

    def dump(self, path, data):
        path.write_text(json.dumps(data))
        return path

    def write_profile(self, name, instructions, **changes):
        scope = {
            "boundary": "whole DSP handler",
            "instruction_unit": "emulated instructions",
            "instructions_per_block": distribution(instructions),
            "host_us_per_block": distribution([1.0] * len(instructions)),
            "target_cpu_load_percent": None,
            "target_dsp_load_percent": None,
        }
        record = {
            "frames": len(instructions),
            "capture_sha256": "capture",
            "preroll_trigger_frame": None,
            "sample_rates": {"source": 96000},
            "dsp_blob_sha256": name,
            "profile": scope,
        }
        record.update(changes)
        self.dump(self.run / (name + ".json"), record)
        return self.dump(
            self.run / (name + "-profile.json"),
            {
                "instructions": instructions,
                "host_us": [1.0] * len(instructions),
                "scope": scope,
            },
        )

    def test_raw_peaks_and_unknown_hardware(self):
        snapshot = make_snapshot([self.run])
        profile = snapshot["profiles"][0]
        self.assertEqual(profile["instructions_per_block"]["max_observed"], 30)
        self.assertTrue(all(v is None for v in snapshot["hardware"].values()))
        self.assertIn("not a combined live", snapshot["scope"])

    def test_only_matching_replay_compares_and_zero_baseline_is_safe(self):
        baseline = load_profile(self.profile, Inputs())
        candidate = load_profile(self.write_profile("custom", [20, 30, 40]), Inputs())
        delta = compare_profiles(candidate, baseline)
        self.assertTrue(delta["eligible"])
        self.assertEqual(delta["instruction_deltas"]["mean"]["percent"], 50)
        for key in baseline["workload"]:
            altered = copy.deepcopy(candidate)
            altered["workload"][key] = "different"
            with self.subTest(key=key):
                self.assertFalse(compare_profiles(altered, baseline)["eligible"])
        empty = load_profile(self.write_profile("silent", [0, 0, 0]), Inputs())
        self.assertIsNone(
            compare_profiles(candidate, empty)["instruction_deltas"]["mean"]["percent"]
        )

    def test_failed_run_wrong_firmware_and_inconsistent_stats_refused(self):
        for mutation in ("failed", "unknown-firmware", "stats", "hardware", "count"):
            with self.subTest(mutation=mutation):
                self.dump(self.run / "manifest.json", self.manifest)
                self.write_profile("stock", [10, 20, 30])
                if mutation in ("failed", "unknown-firmware"):
                    altered = copy.deepcopy(self.manifest)
                    if mutation == "failed":
                        altered["status"] = "failed"
                    else:
                        altered["fixture_files"]["sections/section_3_MAIN_OS.bin"] = (
                            "wrong"
                        )
                    self.dump(self.run / "manifest.json", altered)
                else:
                    data = json.loads(self.profile.read_text())
                    if mutation == "stats":
                        data["instructions"][0] = 1000
                    elif mutation == "count":
                        data["host_us"].pop()
                    else:
                        data["scope"]["target_dsp_load_percent"] = 2
                        record = json.loads((self.run / "stock.json").read_text())
                        record["profile"] = data["scope"]
                        self.dump(self.run / "stock.json", record)
                    self.dump(self.profile, data)
                with self.assertRaises(ValueError):
                    load_profile(self.profile, Inputs())

    def test_invalid_series(self):
        for values in (
            [],
            [float("nan")],
            [float("inf")],
            [-1],
            [True],
            ["10"],
            [10**500],
            [1e308, 1e308],
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                series(values, "bad")
        with self.assertRaises(ValueError):
            series([1.5], "instructions", integral=True)

    def test_bank_arrays_are_inside_reservation_and_checked(self):
        bank = {
            "keys": 100,
            "capacity": 102,
            "frames": 2400,
            "allocated_array_bytes": 1224,
            "shared_readers_bytes": 4224,
            "total_reserved_bytes": 8388608,
        }
        self.assertEqual(bank_accounting(bank), bank)
        self.assertIsNone(bank_accounting(None))
        for key, value in (
            ("keys", 103),
            ("capacity", 576005),
            ("frames", 576001),
            ("allocated_array_bytes", 1223),
            ("total_reserved_bytes", 1024),
            ("shared_readers_bytes", -1),
        ):
            altered = {**bank, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                bank_accounting(altered)

    def test_pairing_uses_actual_library_and_identical_stock_capture(self):
        stock_hash = self.manifest["fixture_files"]["sections/section_7_BLOB.bin"]
        self.write_profile("stock", [10, 20, 30], dsp_blob_sha256=stock_hash)
        self.write_profile("custom", [20, 30, 40])
        self.write_profile("other-capture", [30, 40, 50], capture_sha256="other")
        self.write_profile(
            "other-library", [30, 40, 50], native_library_sha256="new-library"
        )
        result = make_snapshot([self.run], paired_stock=True)
        profiles = {Path(p["id"]).name: p for p in result["profiles"]}
        self.assertTrue(profiles["custom-profile.json"]["comparison"]["eligible"])
        self.assertFalse(
            profiles["other-capture-profile.json"]["comparison"]["eligible"]
        )
        self.assertFalse(
            profiles["other-library-profile.json"]["comparison"]["eligible"]
        )
        self.assertEqual(
            profiles["other-library-profile.json"]["workload"]["native_library_sha256"],
            "new-library",
        )
        with self.assertRaises(ValueError):
            make_snapshot([self.run], baseline=self.profile, paired_stock=True)
        self.write_profile("duplicate-stock", [10, 20, 30], dsp_blob_sha256=stock_hash)
        result = make_snapshot([self.run], paired_stock=True)
        self.assertTrue(
            all(not p["comparison"]["eligible"] for p in result["profiles"])
        )

    def test_stock_heap_requires_healthy_verified_capture(self):
        stock = {
            "status": "passed",
            "main_sha256": self.manifest["fixture_files"][
                "sections/section_3_MAIN_OS.bin"
            ],
            "stock_blob_sha256": self.manifest["fixture_files"][
                "sections/section_7_BLOB.bin"
            ],
            "cpu_snapshot_sha256": "snapshot",
            "scope": "stock checkpoint",
            "faulted_pages": [],
            "worker_error": None,
            "worker_stopped": True,
            "cpu_stages": [
                {
                    "name": "idle",
                    "machine_types": [0] * 16,
                    "heap": {
                        "arena_bytes": 1024,
                        "free_bytes": 800,
                        "largest_block": 512,
                    },
                }
            ],
        }
        path = self.dump(self.run / "stock-capture.json", stock)
        result = load_stock(path, Inputs())
        self.assertEqual(result["stages"][0]["occupied_bytes"], 224)
        snapshot = make_snapshot([self.run], stock_reports=[path])
        self.assertIn("Stock OS 1.16 CPU heap", render_html(snapshot))
        for key, value in (
            ("status", "failed"),
            ("main_sha256", "custom"),
            ("worker_stopped", False),
            ("faulted_pages", [123]),
            ("worker_error", "halt"),
        ):
            altered = copy.deepcopy(stock)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_stock(self.dump(path, altered), Inputs())
        stock["cpu_stages"][0]["heap"]["largest_block"] = 801
        with self.assertRaises(ValueError):
            load_stock(self.dump(path, stock), Inputs())

    def test_source_changes_detected(self):
        inputs = Inputs()
        inputs.read(self.profile)
        self.write_profile("stock", [20, 30, 40])
        with self.assertRaises(ValueError):
            inputs.verify()
        with self.assertRaises(ValueError):
            inputs.read(self.profile)

    def test_flex_requested_bytes_are_separate_from_whole_heap(self):
        path = self.dump(self.root / "flex.json", self.flex)
        result = load_flex(path, Inputs())
        self.assertEqual(result["stages"][0]["requested_heap_bytes"], 426)
        self.assertEqual(result["stages"][1]["requested_heap_bytes"], 64)
        self.assertEqual(result["heap"]["peak_occupied_bytes"], 724)
        self.assertEqual(result["heap"]["minimum_observed_largest_free_block"], 128)
        self.assertEqual(result["heap"]["allocation_failures"], 1)
        self.assertEqual(result["reuse"]["retained_descriptor_bytes"], 128)

    def test_incomplete_or_corrupt_memory_refused(self):
        for mutation in ("pending", "minimum", "capacity", "negative", "failed"):
            altered = copy.deepcopy(self.flex)
            if mutation == "pending":
                altered["heap_trace"]["pending_calls"] = 1
            elif mutation == "minimum":
                altered["heap_trace"]["minimum_free"] = 200
            elif mutation == "capacity":
                altered["heap_trace"]["final"]["largest_block"] = 701
            elif mutation == "negative":
                altered["accounting_after_accept"][2] = -1
            else:
                altered["status"] = "FAIL"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                load_flex(self.dump(self.root / "flex.json", altered), Inputs())

    def test_placement_is_not_live_memory_and_overlap_is_refused(self):
        layout = {
            "layout": "reserved-state",
            "state_base": 1000,
            "state_bytes": 100,
            "reservation_end": 2000,
            "instruction_code": {"bytes": 50, "runtime_ownership_verified": False},
            "hardware_verified": False,
            "regions": [{"name": "state", "start": 1000, "end": 1050}],
        }
        path = self.dump(self.root / "layout.json", layout)
        result = load_layout(path, Inputs())
        self.assertNotIn("sample_pool_reserved_bytes", result)
        self.assertFalse(result["instruction_ownership_verified"])
        layout["regions"].append({"name": "overlap", "start": 1049, "end": 1090})
        with self.assertRaises(ValueError):
            load_layout(self.dump(path, layout), Inputs())
        reservation = {
            "reserved_bytes": 1000,
            "sample_bytes": 5000,
            "bank_base": 1001,
            "bank_end": 2000,
            "sha256": "candidate",
            "hardware_verified": False,
        }
        result = load_reservation(
            self.dump(self.root / "reservation.json", reservation), Inputs()
        )
        self.assertEqual(result["sample_pool_reserved_bytes"], 1000)

    def test_screen_escapes_labels_and_never_overwrites_output(self):
        snapshot = make_snapshot([self.run])
        snapshot["profiles"][0]["label"] = "<script>alert(1)</script>"
        page = render_html(snapshot)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Unmeasured", page)
        args = type(
            "Args",
            (),
            dict(
                run=[self.run],
                flex_report=[],
                layout=[],
                reservation=[],
                baseline=None,
                output=self.root / "output",
            ),
        )()
        with patch("builtins.print"):
            self.assertEqual(main(args), 0)
            original = (args.output / "snapshot.json").read_bytes()
            self.assertEqual(main(args), 1)
        self.assertEqual((args.output / "snapshot.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
