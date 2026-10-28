"""Explicit profile-build regressions; run when changing builders or packaging.

Moved from the behavior suites to avoid rebuilding historical profiles during
ordinary control/UI work. Original assertions and byte guards are retained.
"""

import unittest


class ProfileBuildTests(unittest.TestCase):
    def test_device_flag_is_opt_in_and_preserves_working_clock_image(self):
        import struct
        from hashlib import sha256

        from lab import buf_selector as s
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build, relocate

        stock = STOCK_MAIN.read_bytes()
        before, baseline = build(stock, arm_diagnostics=True, clock_fix=True)
        after, changed = build(
            stock, arm_diagnostics=True, clock_fix=True, buf_selector=True
        )
        self.assertEqual(
            sha256(before).hexdigest(),
            "4d2e6af70a1faf2593cfc3eab45d1b664f46f678038fc49ffb4dd555f6fa22f8",
        )
        self.assertEqual(baseline["reservation"], changed["reservation"])
        self.assertEqual(
            after[0x401EE50C - 0x40000400 : 0x401EE510 - 0x40000400],
            struct.pack(">I", relocate(s.ROTATE)),
        )
        base = {h["address"] for h in baseline["hooks"]}
        added = {h["address"] for h in changed["hooks"]} - base
        self.assertEqual(added, set(s.HOOKS) | set(s.POINTERS))
        # Exercise the sealed-build validation API with the flag, rather than
        # only the low-level emitter. No CPU/DSP fixture is executed here.
        import json
        import tempfile
        from pathlib import Path

        from lab.project import ROOT
        from lab.sketch_device_validation import DeviceBuild

        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as folder:
            folder = Path(folder)
            (folder / "MAIN.bin").write_bytes(after)
            (folder / "BLOB.bin").write_bytes(b"test-only DSP identity")
            (folder / "native-patches.json").write_text(json.dumps(changed))
            manifest = dict(
                status="local-build-complete",
                source_hashes={},
                cpu=dict(path="MAIN.bin", **changed),
                dsp=dict(
                    path="BLOB.bin",
                    blob_sha256=sha256(b"test-only DSP identity").hexdigest(),
                ),
            )
            (folder / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(DeviceBuild(folder, stock).image, after)

    def test_profile_disabled_reproduces_R2_and_changes_no_storage_hooks(self):
        from hashlib import sha256

        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
        )
        before, baseline = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            sha256(before).hexdigest(),
            "7b3c783fcedd97fa459fb5005c73d3cc0978107acdf98cd37ce7ad209fc22d66",
        )
        after, changed = build(STOCK_MAIN.read_bytes(), **flags, navigation_fixes=True)
        self.assertNotEqual(before, after)
        self.assertEqual(baseline["reservation"], changed["reservation"])
        self.assertEqual(baseline["hooks"], changed["hooks"])
        self.assertTrue(changed["navigation_fixes"])

    def test_opt_in_profile_keeps_R3_exact_and_has_no_new_reservation(self):
        import hashlib

        from lab import buf_fixed_slots as fixed
        from lab.project import ROOT
        from lab.sketch_device import build

        STOCK = ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin"

        flags = {
            "arm_diagnostics": True,
            "clock_fix": True,
            "buf_selector": True,
            "performance_controls": True,
            "navigation_fixes": True,
        }
        old, old_meta = build(STOCK.read_bytes(), **flags)
        self.assertEqual(
            hashlib.sha256(old).hexdigest(),
            "df5d524e037e2412aeaadb31e01108ebae381fb551aa002118d4d09aafdacf0c",
        )
        new, meta = build(STOCK.read_bytes(), **flags, fixed_buf_slots=True)
        self.assertNotEqual(old, new)
        self.assertEqual(meta["buf_public_slots"], list(fixed.PUBLIC))
        self.assertEqual(meta["reservation"], old_meta["reservation"])
        self.assertEqual(
            build(STOCK.read_bytes(), **flags, fixed_buf_slots=True), (new, meta)
        )
        with self.assertRaisesRegex(ValueError, "navigation"):
            build(STOCK.read_bytes(), fixed_buf_slots=True)

    def test_opt_out_is_exact_device_confirmed_R9(self):
        import json

        from lab import buf_freeze_slots as slots
        from lab.project import ROOT
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        profile = json.loads((ROOT / "profiles/sketch-buf-r8.json").read_text())
        flags = {name.replace("-", "_"): True for name in profile["build_flags"]}
        flags["monitor_labels"] = True
        _, old = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            old["sha256"],
            "b0d5a3ecb3feb038e40c523f5fcde69b2014acdae10e14f71ffa7ac33d79e54d",
        )
        _, new = build(STOCK_MAIN.read_bytes(), freeze_h_slots=True, **flags)
        self.assertEqual(new["reservation"], old["reservation"])
        self.assertEqual(new["guards"], old["guards"])
        self.assertEqual(new["hooks"], old["hooks"])
        self.assertEqual(new["freeze_public_slots"], list(slots.SLOTS))

    def test_opt_in_off_reproduces_user_tested_selector_image(self):
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        main, metadata = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
        )
        self.assertEqual(
            metadata["sha256"],
            "701a29543c5da385cd607bc5f8f2586742e3089e98165fd8854d6586dcdd9795",
        )
        changed, enabled = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
        )
        self.assertNotEqual(main, changed)
        self.assertEqual(metadata["reservation"], enabled["reservation"])
        self.assertTrue(enabled["performance_controls"])

    def test_build_keeps_all_backend_parts_hooks_and_original_profile_exact(self):
        from lab import sketch as s
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build, compose

        options = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
            startup_capture=True,
        )
        stock = STOCK_MAIN.read_bytes()
        base, meta = build(stock, **options)
        self.assertEqual(
            meta["sha256"],
            "eea6d8bb70c0a91ea26a34b50232a4cedb80b436fafdc4be35fa53f132e6ba7c",
        )
        old = compose(stock, **options)
        new = compose(stock, **options, copy_shortcuts=True)
        self.assertEqual(old.hooks, new.hooks)
        self.assertEqual(old.pointer_hooks, new.pointer_hooks)
        self.assertEqual(
            {at: v for at, v in old.parts.items() if not s.BASE <= at < s.END},
            {at: v for at, v in new.parts.items() if not s.BASE <= at < s.END},
        )
        candidate, after = build(stock, **options, copy_shortcuts=True)
        self.assertNotEqual(candidate, base)
        self.assertEqual(after["reservation_bytes"], 360448)
        self.assertTrue(after["copy_shortcuts"])

    def test_disabled_profile_is_exact_R4(self):
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        _, meta = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
        )
        self.assertEqual(
            meta["sha256"],
            "7c5e0bdea8b5c7c8feb5cfc8c695d0f27dbd4a070624994215b2f288d0012de1",
        )
        self.assertEqual(meta["buf_public_slots"], [1020, 1021, 1022, 1023])

    def test_opt_out_is_byte_identical_and_no_new_hooks_or_memory(self):
        from lab import buf_next_bar as b
        from lab import buf_startup as startup
        from lab import buf_stopped as free
        from lab import recorder_freeze_worker_code as q
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
            startup_capture=True,
            copy_shortcuts=True,
        )
        _, old = build(STOCK_MAIN.read_bytes(), **flags)
        _, new = build(STOCK_MAIN.read_bytes(), **flags, stopped_recording=True)
        self.assertEqual(
            old["sha256"],
            "f31a427d81afec033ff8c97bb33eaa2462ce27afb5a130adf4a5db149fdb519e",
        )
        self.assertEqual(old["hooks"], new["hooks"])
        self.assertGreaterEqual(free.FINISH, b.OP_CONTEXT + len(q.OP_FIELDS) * 4)
        self.assertLess(free.FINISH, startup.BATCH_ACTIVE)
        self.assertEqual(old["reservation"], new["reservation"])

    def test_opt_out_is_exact_R7_and_opt_in_adds_only_LED_hook_and_code(self):
        from lab import sketch_led as led
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
            startup_capture=True,
            copy_shortcuts=True,
            stopped_recording=True,
        )
        stock = STOCK_MAIN.read_bytes()
        _old_image, old = build(stock, **flags)
        self.assertEqual(
            old["sha256"],
            "b5f167e5bbfb9ac35f1de9db7e507e3775663c8702450e270945e4040277f7af",
        )
        _image, new = build(stock, recording_led=True, **flags)
        self.assertEqual(new["reservation"], old["reservation"])
        self.assertEqual(new["guards"], old["guards"])
        self.assertEqual(
            [h for h in new["hooks"] if h["address"] != led.SITE], old["hooks"]
        )
        additions = [w for w in new["writes"] if w not in old["writes"]]
        self.assertEqual(
            {w["source_address"] for w in additions}, {led.ENTRY, led.TRAMP}
        )
        self.assertTrue(all(w in new["writes"] for w in old["writes"]))
        self.assertEqual(
            new["payload_bytes"] - old["payload_bytes"],
            sum(len(bytes.fromhex(w["after"])) for w in additions),
        )

    def test_optional_profile_preserves_baseline_bytes_and_uses_guarded_arena(self):
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import END, MANAGED_END, build

        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
            startup_capture=True,
            copy_shortcuts=True,
            stopped_recording=True,
            recording_led=True,
            monitor_labels=True,
            freeze_h_slots=True,
            sketchbook_save=True,
        )
        _, old = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            old["sha256"],
            "0f85c967ff1034e3e22ac0d9134fd33e89d198e0df9693076a6d924493adfd1d",
        )
        image, new = build(STOCK_MAIN.read_bytes(), **flags, managed_buffers=True)
        self.assertEqual(new["reservation"][1], MANAGED_END)
        self.assertEqual(old["reservation"][1], END)
        self.assertTrue(new["managed_buffers"])
        from lab.sketch_device_validation import read_segments

        self.assertEqual(len(read_segments(image, new)), len(new["segments"]))
        self.assertEqual(
            (image, new), build(STOCK_MAIN.read_bytes(), **flags, managed_buffers=True)
        )

    def test_off_preserves_previous_managed_image_and_on_is_guarded(self):
        import json

        from lab.project import ROOT
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import ASSIGN_END, MANAGED_END, build
        from lab.sketch_device_validation import read_segments

        flags = {
            name.replace("-", "_"): True
            for name in json.loads((ROOT / "profiles/sketch-managed.json").read_text())[
                "build_flags"
            ]
        }
        _, off = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            off["sha256"],
            "4c7f99100063de90164bf47197761a2fb0d19e45a4763219e5a40b44ebcb58bf",
        )
        image, on = build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        self.assertEqual(on["reservation"][1], ASSIGN_END)
        self.assertEqual(off["reservation"][1], MANAGED_END)
        self.assertEqual(len(read_segments(image, on)), len(on["segments"]))
        self.assertEqual(
            (image, on), build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        )
        with self.assertRaisesRegex(ValueError, "requires managed"):
            build(STOCK_MAIN.read_bytes(), assign_popup=True)

    def test_optional_flags_preserve_previous_image_and_arenas(self):
        import json

        from lab.project import ROOT
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        flags = {
            k.replace("-", "_"): True
            for k in json.loads((ROOT / "profiles/sketch-managed.json").read_text())[
                "build_flags"
            ]
        }
        _, old = build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        self.assertEqual(
            old["sha256"],
            "b62584d425f31c22f1e8013234e23f03c36177d8ab6a0312767e7568d91d4431",
        )
        _, new = build(
            STOCK_MAIN.read_bytes(),
            **flags,
            assign_popup=True,
            buf_loading=True,
            early_buf_setup=True,
        )
        self.assertEqual(new["arenas"], old["arenas"])
        self.assertEqual(new["reservation"], old["reservation"])
        with self.assertRaisesRegex(ValueError, "requires managed"):
            build(STOCK_MAIN.read_bytes(), buf_loading=True)
        with self.assertRaisesRegex(ValueError, "requires loading"):
            build(STOCK_MAIN.read_bytes(), **flags, early_buf_setup=True)
