"""The firmware's post-write length check cannot protect a too-small buffer."""

import unittest

from lab.sharc_tools import header
from lab.upload import DSP_STAGE_BYTES, verify_dsp_staging


class DspBootStagingTests(unittest.TestCase):
    def test_hardware_failed_build_is_rejected_and_command_byte_counts(self):
        for packed, decoded in [
            (0x40000, 1_314_460),
            (1, 0x100000),
            (0x100001, 1),
            (0, 1),
            (1, 0),
        ]:
            with self.assertRaises(ValueError):
                verify_dsp_staging(packed, decoded)
        result = verify_dsp_staging(DSP_STAGE_BYTES, DSP_STAGE_BYTES - 1)
        self.assertEqual(result["output_headroom"], 0)
        self.assertEqual(result["command_bytes"], 1)

    def test_fill_header_sets_flag_and_recomputes_checksum(self):
        import struct

        target, count = 0x200E0000, 32768
        raw = header(target, count, fill=0)
        word, address, extent, argument = struct.unpack("<4I", raw)
        self.assertEqual((address, extent, argument), (target, count, 0))
        self.assertTrue(word & 0x100)
        self.assertFalse(struct.unpack_from("<I", header(target, count))[0] & 0x100)
        xor = 0
        for b in raw:
            xor ^= b
        self.assertEqual(xor, 0)
