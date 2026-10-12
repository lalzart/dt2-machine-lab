import struct
import tempfile
import unittest
from pathlib import Path

from lab.formats import read_frames
from lab.pattern_clock import pending_interrupts


class PatternClockTests(unittest.TestCase):
    def test_pending_request_waits_for_ipl_then_disappears_on_guest_ack(self):
        memory = {}

        def write(address, value, size):
            for i, byte in enumerate(value.to_bytes(size, "big")):
                memory[address + i] = byte

        def read(address, size):
            return bytes(memory.get(address + i, 0) for i in range(size))

        write(0xFC048010, (1 << 12) | (1 << 25), 4)
        write(0xFC04806C, 5, 1)  # vector 108
        write(0xFC048079, 4, 1)  # vector 121
        # INTC masks do not suppress a software-forced request.
        write(0xFC048008, 0xFFFFFFFF, 4)
        self.assertEqual(pending_interrupts(read, 5), [])
        self.assertEqual(pending_interrupts(read, 4), [(5, 108)])
        write(0xFC048010, 1 << 25, 4)
        self.assertEqual(pending_interrupts(read, 0), [(4, 121)])
        write(0xFC048010, 0, 4)
        self.assertEqual(pending_interrupts(read, 0), [])

    def test_pattern_capture_limit_is_explicit_and_still_bounded(self):
        frame = bytes(0x100)
        blob = b"DTFR\x01\0\0\0" + struct.pack("<I", 4097)
        blob += (struct.pack("<I", len(frame)) + frame) * 4097
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pattern.dtfr"
            path.write_bytes(blob)
            with self.assertRaises(ValueError):
                read_frames(path)
            self.assertEqual(len(read_frames(path, max_frames=32768)), 4097)
            with self.assertRaises(ValueError):
                read_frames(path, max_frames=32769)


if __name__ == "__main__":
    unittest.main()
