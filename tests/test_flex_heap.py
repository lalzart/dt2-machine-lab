"""Heap telemetry must reject broken lists rather than report invented capacity."""

import struct
import unittest

from lab.flex_heap import (
    EXPECTED_BASE,
    EXPECTED_BITMAP,
    EXPECTED_HEADS,
    MAX_ORDER,
    PARAMS,
    UNITS,
    block_bytes,
    inspect_heap,
)


class HeapTests(unittest.TestCase):
    def setUp(self):
        self.data = {}
        self.put(
            PARAMS,
            struct.pack(
                ">7I",
                1,
                EXPECTED_BASE,
                EXPECTED_BITMAP,
                EXPECTED_HEADS,
                MAX_ORDER,
                UNITS,
                4,
            ),
        )
        self.heads = [-1] * 22

    def put(self, address, bytes_):
        self.data.update({address + i: b for i, b in enumerate(bytes_)})

    def read(self, address, size):
        return bytes(self.data.get(address + i, 0) for i in range(size))

    def node(self, index, previous=-1, next_=-1):
        self.put(
            EXPECTED_BASE + index * 16,
            struct.pack(">Iii", ~(previous + next_) & 0xFFFFFFFF, previous, next_),
        )

    def inspect(self):
        self.put(EXPECTED_HEADS, struct.pack(">22i", *self.heads))
        return inspect_heap(self.read)

    def test_fragmentation_distinguishes_free_total_from_largest(self):
        self.heads[16] = 0
        self.node(0, next_=131072)
        self.node(131072, previous=0)
        r = self.inspect()
        self.assertEqual((r.free_bytes, r.largest_block), (2 << 20, 1 << 20))
        self.assertGreater(r.free_bytes, r.largest_block)
        self.assertEqual(block_bytes(1920080), 2 << 20)
        self.assertEqual(block_bytes(3840080), 4 << 20)

    def test_unknown_parameters_and_requests_fail(self):
        self.put(PARAMS, b"\0" * 28)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.inspect()
        for n in (0, -1, (32 << 20) + 1):
            with self.assertRaises(ValueError):
                block_bytes(n)

    def test_bad_checksum_backlink_cycle_and_alignment_fail(self):
        self.heads[2] = 4
        self.node(4)
        for blob in (
            struct.pack(">Iii", 0, -1, -1),
            struct.pack(">Iii", 0, UNITS, -1),
            struct.pack(">Iii", 0xFFFFFFFC, -1, 4),
        ):
            self.put(EXPECTED_BASE + 64, blob)
            with self.assertRaises(ValueError):
                self.inspect()
        self.heads[2] = 3
        self.node(3)
        with self.assertRaisesRegex(ValueError, "alignment"):
            self.inspect()

    def test_overlapping_free_classes_fail(self):
        self.heads[2] = 0
        self.heads[1] = 2
        self.node(0)
        self.node(2)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.inspect()
