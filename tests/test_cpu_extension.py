"""Real native plans, strict reservations and unchanged standalone builds."""

import struct
import unittest

from lab.cpu_extension import (
    CAVE,
    GUARD,
    LIMIT,
    MAIN_LIMIT,
    RESET,
    START,
    STATE,
    Segment,
    build_cpu,
    loader,
    segment_chain,
)
from lab.cpu_plan import NativePlan
from lab.dt2_116 import BASE
from lab.project import ROOT
from lab.resources import PaddingAllocator, patch_conflicts


class SegmentTests(unittest.TestCase):
    def test_chain_has_bss_only_and_explicit_terminator(self):
        self.assertEqual(
            segment_chain((Segment(START, b"abcd", 8), Segment(STATE, b"", 4))),
            struct.pack(">III", 4, START, 8)
            + b"abcd"
            + struct.pack(">III", 0, STATE, 4)
            + bytes.fromhex("ffffffff"),
        )

    def test_bad_destinations_sizes_and_overlap_are_refused(self):
        cases = [
            (),
            (Segment(START),),
            (Segment(START, b"x"),),
            (Segment(START + 1, b"abcd"),),
            (Segment(START, b"", -4),),
            (Segment(START - 4, b"abcd"),),
            (Segment(LIMIT - 4, b"abcd", 4),),
            (Segment(START, b"abcd"), Segment(START, b"abcd")),
            (Segment(START + 0x08000000, b"abcd"),),
        ]
        for segments in cases:
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                segment_chain(segments)

    def test_loader_calls_original_helpers_and_rejects_unaligned_source(self):
        code = loader(0x4031FF60)
        self.assertEqual(len(code), 54)
        self.assertEqual(code[-14:], bytes.fromhex("4eb94000045c4eb9400004b24e75"))
        with self.assertRaises(ValueError):
            loader(0x4031FF61)

    def test_external_payload_requires_allocation_and_loader(self):
        allocator = PaddingAllocator(((START, LIMIT),))
        allocator.allocate("x", 4)
        plan = NativePlan(bytes(16), allocator)
        plan.put(START, bytes(4), b"abcd", "x", "data", payload=True)
        with self.assertRaises(ValueError):
            plan.apply()
        with self.assertRaises(ValueError):
            plan.put(START + 4, bytes(4), b"abcd", "unowned", "data", payload=True)
        with self.assertRaises(ValueError):
            plan.put(START, bytes(4), b"abcd", "duplicate", "data", payload=True)


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin"
        if not path.is_file():
            raise unittest.SkipTest("Private stock OS1.16 required")
        cls.stock = path.read_bytes()

    def test_actual_plans_relocate_with_one_stock_save_owner_and_repeat(self):
        image, m = build_cpu(self.stock)
        self.assertEqual((image, m), build_cpu(self.stock))
        self.assertLessEqual(len(image), MAIN_LIMIT)
        self.assertEqual(m["reservation_bytes"], 65536)
        self.assertEqual(m["loader_bytes"], 54)
        self.assertEqual(len([w for w in m["writes"] if w["address"] == 0x40043A30]), 1)
        self.assertEqual(len(m["save_phases"]["prepare"]), 2)
        self.assertFalse(
            patch_conflicts([(str(i), [w]) for i, w in enumerate(m["writes"])])
        )
        for mod in ("arp", "flex"):
            self.assertTrue(
                all(START <= x < STATE for x in m[mod]["locations"].values())
            )
        for w in m["writes"]:
            if not w["payload"]:
                off = w["address"] - BASE
                self.assertEqual(
                    image[off : off + len(bytes.fromhex(w["after"]))],
                    bytes.fromhex(w["after"]),
                )
        # Entire original image, including reset-copy data, changes only at declared stock writes.
        covered = set()
        for w in m["writes"]:
            if not w["payload"]:
                off = w["address"] - BASE
                covered.update(range(off, off + len(bytes.fromhex(w["after"]))))
        self.assertTrue(
            all(
                i in covered
                for i, (a, b) in enumerate(zip(self.stock, image, strict=False))
                if a != b
            )
        )
        self.assertEqual(image[RESET - BASE : RESET - BASE + 2], bytes.fromhex("4eb9"))
        self.assertEqual(
            image[CAVE - BASE : CAVE - BASE + 54], loader(BASE + len(self.stock))
        )
        self.assertEqual(m["guards"][0], [START, len(GUARD)])
        bitmap = next(w for w in m["writes"] if w["label"] == "arp/g_blank")
        descriptor = bytes.fromhex(bitmap["after"])
        self.assertEqual(len(descriptor), 24)
        self.assertEqual(
            struct.unpack_from(">I", descriptor, 20)[0],
            m["arp"]["locations"]["g_pixels"],
        )

    def test_unknown_source_is_refused(self):
        bad = bytearray(self.stock)
        bad[100] ^= 1
        with self.assertRaises(ValueError):
            build_cpu(bad)
