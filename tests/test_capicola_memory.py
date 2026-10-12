"""Reservation composition must preserve all unrelated CPU bytes and guards."""

import hashlib
import struct
import unittest
from unittest.mock import patch

from lab import capicola_memory as memory


class ReservationTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(b"\xa5" * (memory.SITES[-1][0] - memory.BASE + 6))
        for address, opcode, before, _, _ in memory.SITES:
            offset = address - memory.BASE
            data[offset : offset + 6] = bytes.fromhex(opcode) + struct.pack(
                ">I", before
            )
        return bytes(data)

    def test_managed_reservation_changes_only_six_immediates(self):
        image = self.fixture()
        digest = hashlib.sha256(image).hexdigest()
        with patch.object(memory, "MANAGED_BASE_SHA", digest):
            result, report = memory.patch_cpu(image, managed_flex=True)
            self.assertEqual(memory.patch_cpu(image, managed_flex=True)[0], result)
            with self.assertRaises(ValueError):
                memory.patch_cpu(result, managed_flex=True)
        allowed = {a - memory.BASE + i for a, *_ in memory.SITES for i in range(2, 6)}
        self.assertEqual(len(image), len(result))
        self.assertTrue(
            all(
                a == b or i in allowed
                for i, (a, b) in enumerate(zip(image, result, strict=True))
            )
        )
        self.assertEqual(report["baseline_sha256"], digest)
        self.assertEqual(report["sample_bytes"], 392 * 1024 * 1024)
        self.assertEqual(len(report["writes"]), 6)

    def test_legacy_guard_does_not_accept_managed_baseline(self):
        image = self.fixture()
        with (
            patch.object(memory, "MANAGED_BASE_SHA", hashlib.sha256(image).hexdigest()),
            self.assertRaises(ValueError),
        ):
            memory.patch_cpu(image)
        for managed in (False, True):
            with self.assertRaises(ValueError):
                memory.patch_cpu(b"unknown", managed_flex=managed)

    def test_instruction_guard_survives_known_image_hash(self):
        image = bytearray(self.fixture())
        image[memory.SITES[2][0] - memory.BASE] ^= 1
        with (
            patch.object(memory, "MANAGED_BASE_SHA", hashlib.sha256(image).hexdigest()),
            self.assertRaisesRegex(ValueError, "instruction guard"),
        ):
            memory.patch_cpu(bytes(image), managed_flex=True)
