"""Device placement boundaries and relocation without changing legacy profiles."""

import struct
import unittest

from lab.cpu_extension import CANDIDATE_END, LIMIT, Segment, segment_chain
from lab.project import ROOT
from lab.sketch_device import (
    ARENAS,
    END,
    START,
    Overlay,
    build,
    relocate,
    relocate_code,
)
from lab.sketch_device_validation import AddressView, read_segments
from lab.sketch_dsp_device import (
    BOOT_WORKSPACE,
    GATE_END,
    GATE_STATE,
    blocks,
    check_regions,
    check_stream,
    finish_stream,
    header,
)


class PlacementTests(unittest.TestCase):
    def test_device_stream_inserts_before_final_and_preserves_loaded_bytes(self):
        stock = (
            header(0x5001, 0x1C1338, 0, 36)
            + header(1, 0x20000000, 4, 0)
            + b"base"
            + header(0x8001, 0x1C1338, 0, 0)
        )
        extras = b"".join(
            header(flags, target, 6 if flags == 1 else 0x4000, 0)
            + (b"abcdef" if flags == 1 else b"")
            for flags, target in (
                (1, 0x20080000),
                (0x101, 0x200F4000),
                (1, 0x200D0000),
                (0x101, GATE_STATE),
                (1, 0x200C0000),
                (0x101, 0x200F8000),
            )
        )
        legacy = stock + extras
        with self.assertRaisesRegex(ValueError, "terminal FINAL"):
            check_stream(legacy)
        result = finish_stream(legacy, stock)
        self.assertEqual(finish_stream(legacy, stock), result)
        self.assertTrue(check_stream(result)["final_is_last"])
        self.assertEqual(blocks(result)[1][4], b"base")
        self.assertEqual(blocks(result)[-1], blocks(stock)[-1])
        for b in blocks(result)[2:-1]:
            if b[0] == 1:
                self.assertEqual((b[2], b[4]), (8, b"abcdef\0\0"))
        with self.assertRaisesRegex(ValueError, "headers changed"):
            finish_stream(header(0x5001, 0x1C1338, 0, 0) + legacy[16:], stock)

    def test_boot_stream_rejects_bad_headers_spans_alignment_and_workspace(self):
        def stream(target=0x20000000, data=b"base", span=None):
            return (
                header(0x5001, 0x1C1338, 0, 32 + len(data) if span is None else span)
                + header(1, target, len(data), 0)
                + data
                + header(0x8001, 0x1C1338, 0, 0)
            )

        good = stream()
        check_stream(good)
        bad_checksum = bytearray(good)
        bad_checksum[2] ^= 1
        cases = (
            (bytes(bad_checksum), "checksum"),
            (good[:-1], "Truncated"),
            (stream(data=b"xx"), "Unaligned"),
            (stream(target=0x20000002), "Unaligned"),
            (stream(target=BOOT_WORKSPACE[0]), "boot workspace"),
            (stream(span=0), "next-application"),
            (good + good[-16:], "after FINAL"),
            (good[:-16], "terminal FINAL"),
        )
        for blob, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                check_stream(blob)

    def test_dsp_boot_workspace_refuses_fill_and_partial_overlap(self):
        check_regions([(0x20000000, 0x2001AB7C), (GATE_STATE, GATE_END)])
        check_regions(
            [(0x200F8000, BOOT_WORKSPACE[0]), (BOOT_WORKSPACE[1], 0x20100004)]
        )
        for region in (
            (0x200FC000, 0x20100000),
            BOOT_WORKSPACE,
            (BOOT_WORKSPACE[0] - 4, BOOT_WORKSPACE[0] + 4),
            (BOOT_WORKSPACE[1] - 4, BOOT_WORKSPACE[1] + 4),
        ):
            with (
                self.subTest(region=region),
                self.assertRaisesRegex(ValueError, "boot workspace"),
            ):
                check_regions([region])

    def test_operands_move_but_local_branch_and_identity_do_not(self):
        source = 0x11101000
        raw = bytes.fromhex("203911100004 41f911105008 223c7ffb0001 60000004 7000 4e75")
        result, changes = relocate_code(raw, source)
        self.assertEqual(
            result[:6], bytes.fromhex("2039") + struct.pack(">I", relocate(0x11100004))
        )
        self.assertEqual(
            result[6:12],
            bytes.fromhex("41f9") + struct.pack(">I", relocate(0x11105008)),
        )
        self.assertEqual(result[12:], raw[12:])
        self.assertEqual(len(changes), 2)
        with self.assertRaisesRegex(ValueError, "Unowned synthetic"):
            relocate_code(bytes.fromhex("4ef910500000"), source)
        with self.assertRaises(ValueError):
            relocate_code(bytes.fromhex("4ef91110"), source)

    def test_arena_guards_and_explicit_reservation_are_bounded(self):
        self.assertEqual(START, LIMIT)
        self.assertLess(END, CANDIDATE_END)
        for a, b in zip(ARENAS, ARENAS[1:], strict=False):
            self.assertLess(a.destination + a.size, b.destination)
        with self.assertRaises(ValueError):
            segment_chain((Segment(START, b"abcd"),))
        self.assertTrue(
            segment_chain((Segment(START, b"abcd"),), reservation=(START, END))
        )
        for bounds in (
            (START - 0x8000000, END),
            (START, CANDIDATE_END + 4),
            (END, START),
        ):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                segment_chain((Segment(START, b"abcd"),), reservation=bounds)


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin"
        if not path.is_file():
            raise unittest.SkipTest("Private stock OS1.16 required")
        cls.stock = path.read_bytes()

    def test_diagnostic_profile_changes_only_admission_and_feedback_payloads(self):
        from lab import buf_next_bar as nb
        from lab import sketch as s

        image, base = build(self.stock)
        changed_image, diagnostic = build(self.stock, arm_diagnostics=True)
        self.assertNotEqual(image, changed_image)
        self.assertTrue(diagnostic["arm_diagnostics"])
        for name in ("arenas", "reservation", "guards", "hooks"):
            self.assertEqual(base[name], diagnostic[name])
        ordinary = {w["address"]: w for w in base["writes"]}
        modified = {w["address"]: w for w in diagnostic["writes"]}
        changed_code = {at for at, w in ordinary.items() if w != modified[at]}
        self.assertEqual(
            changed_code,
            {relocate(at) for at in (nb.ARM_ONLY, s.ARM_SUBMIT, s.DRAW, s.TEXTS)},
        )
        self.assertTrue(
            all(
                modified[at]["kind"] == "data"
                for at in modified.keys() - ordinary.keys()
            )
        )

    def test_clock_fix_changes_only_clock_qualification_and_diagnostic_ui(self):
        from lab import buf_next_bar as nb
        from lab import sketch as s

        _, base = build(self.stock, arm_diagnostics=True)
        image, fixed = build(self.stock, arm_diagnostics=True, clock_fix=True)
        self.assertEqual(
            (image, fixed), build(self.stock, arm_diagnostics=True, clock_fix=True)
        )
        self.assertTrue(fixed["clock_fix"])
        for field in ("hooks", "arenas", "reservation", "guards"):
            self.assertEqual(base[field], fixed[field])
        before = {w["address"]: w for w in base["writes"]}
        after = {w["address"]: w for w in fixed["writes"]}
        self.assertEqual(
            {at for at in before if before[at] != after[at]},
            {relocate(at) for at in (nb.IRQ, nb.CHECK, s.ARM_SUBMIT, s.DRAW, s.TEXTS)}
            | {
                at
                for at, write in before.items()
                if write["after"] == b"BUSY FREEZE %u\0".hex()
            },
        )
        self.assertTrue(
            all(after[at]["kind"] == "data" for at in after.keys() - before.keys())
        )
        with self.assertRaisesRegex(ValueError, "requires diagnostics"):
            build(self.stock, clock_fix=True)

    def test_operation_diagnostics_are_separate_from_clock_and_preserve_backend(self):
        from lab import buf_next_bar as nb
        from lab import recorder_freeze_worker_code as q
        from lab import sketch as s

        _, base = build(self.stock, arm_diagnostics=True)
        image, changed = build(
            self.stock, arm_diagnostics=True, operation_diagnostics=True
        )
        self.assertEqual(
            (image, changed),
            build(self.stock, arm_diagnostics=True, operation_diagnostics=True),
        )
        self.assertTrue(changed["operation_diagnostics"])
        self.assertNotIn("clock_fix", changed)
        for field in ("hooks", "arenas", "reservation", "guards"):
            self.assertEqual(base[field], changed[field])
        before = {w["address"]: w for w in base["writes"]}
        after = {w["address"]: w for w in changed["writes"]}
        sample_label = next(
            at
            for at, write in before.items()
            if write["after"] == b"BUSY FREEZE %u\0".hex()
        )
        self.assertEqual(
            {at for at in before if before[at] != after[at]},
            {
                relocate(at)
                for at in (q.ENTER, q.LEAVE, nb.ARM_ONLY, s.ARM_SUBMIT, s.DRAW, s.TEXTS)
            }
            | {sample_label},
        )
        extra_code = {
            at for at in after.keys() - before.keys() if after[at]["kind"] == "code"
        }
        self.assertEqual(extra_code, {relocate(nb.OP_SNAPSHOT), relocate(s.OP_DIAG)})
        for flags in (
            {"operation_diagnostics": True},
            {"arm_diagnostics": True, "operation_diagnostics": True, "clock_fix": True},
        ):
            with self.assertRaisesRegex(ValueError, "Operation diagnostics require"):
                build(self.stock, **flags)

    def test_exact_repeat_full_coverage_and_no_synthetic_operands(self):
        image, m = build(self.stock)
        self.assertEqual((image, m), build(self.stock))
        self.assertLessEqual(len(image), 0x3FFC00)
        for w in m["writes"]:
            self.assertGreaterEqual(w["address"], START)
            self.assertLess(w["address"] + len(bytes.fromhex(w["after"])), END)
            if w["kind"] == "code":
                # A second relocation must be a no-op, detecting stale operands.
                raw = bytes.fromhex(w["after"])
                self.assertEqual(relocate_code(raw, w["address"]), (raw, []))
        for a, b in zip(
            sorted(m["writes"], key=lambda w: w["address"]),
            sorted(m["writes"], key=lambda w: w["address"])[1:],
            strict=False,
        ):
            self.assertLessEqual(
                a["address"] + len(bytes.fromhex(a["after"])), b["address"]
            )
        changed = {
            i for i, (a, b) in enumerate(zip(self.stock, image, strict=False)) if a != b
        }
        covered = {
            i
            for h in m["hooks"]
            for i in range(
                h["address"] - 0x40000400,
                h["address"] - 0x40000400 + len(bytes.fromhex(h["after"])),
            )
        }
        self.assertTrue(changed <= covered)
        self.assertEqual(m["profile"], "isolated-sketch-buf")
        self.assertFalse(m["hardware_ready"])

    def test_unknown_image_hook_drift_and_duplicate_owner_refuse(self):
        changed = bytearray(self.stock)
        changed[0] ^= 1
        with self.assertRaisesRegex(ValueError, "exact OS1.16"):
            build(bytes(changed))
        overlay = Overlay(self.stock)
        with self.assertRaisesRegex(ValueError, "hook drift"):
            overlay.jump(0x4005DC58, bytes(8), 0x11101800, "bad")
        before = bytes.fromhex("4e56ffa448d73cfc")
        overlay.jump(0x4005DC58, before, 0x11101800, "first")
        with self.assertRaisesRegex(ValueError, "Duplicate hook"):
            overlay.jump(0x4005DC58, before, 0x11101800, "second")

    def test_prepared_reader_rejects_truncation_and_tampered_segments(self):
        image, meta = build(self.stock)
        segments = read_segments(image, meta)
        self.assertEqual(len(segments), 45)
        for changed in (image[:-1], image[:-4] + bytes(4)):
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                read_segments(changed, meta)
        changed = bytearray(image)
        changed[meta["chain_address"] - 0x40000400 + 12] ^= 1
        with self.assertRaisesRegex(ValueError, "Segment data changed"):
            read_segments(changed, meta)

    def test_observation_symbols_do_not_rebind_emitter_globals(self):
        from lab import sketch

        raw = sketch.payload(self.stock, arm_enabled=True, freeze_enabled=True)
        view = AddressView(sketch)
        self.assertEqual(view.DRAW, relocate(sketch.DRAW))
        self.assertEqual(view.BUF, sketch.BUF)
        self.assertEqual(view.END - view.BASE, sketch.END - sketch.BASE)
        self.assertIs(view.payload, sketch.payload)
        self.assertEqual(
            raw, view.payload(self.stock, arm_enabled=True, freeze_enabled=True)
        )
        self.assertEqual(sketch.DRAW, 0x11103000)


if __name__ == "__main__":
    unittest.main()
