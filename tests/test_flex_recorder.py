import struct
import tempfile
import unittest
import wave
from pathlib import Path

from lab.flex_recorder import MAX_FRAMES, RecorderInput, Take


class RecorderTests(unittest.TestCase):
    def source(self, stereo=True, frames=2000):
        words = [v for i in range(frames) for v in ((i, -i) if stereo else (i,))]
        return Take(struct.pack(f">{len(words)}h", *words), stereo)

    def test_record_stop_trim_and_response_boundaries(self):
        r = RecorderInput(self.source())
        r.begin(100)
        self.assertEqual(r.count(2100), 1000)
        r.finish(3100)
        r.count(99999)
        self.assertEqual(r.captured, 1500)
        expected = r.source.pcm[7 * 4 : 1032 * 4]
        chunks = b"".join(
            r.chunk(start, count, 0)
            for start, count in ((7, 512), (519, 512), (1031, 1))
        )
        self.assertEqual(chunks, expected)
        self.assertEqual(r.candidate(7, 1032).pcm, expected)

    def test_next_capture_cannot_mutate_accepted_take(self):
        r = RecorderInput(self.source(False))
        r.begin(0)
        r.finish(1000)
        accepted = r.candidate(0, 500)
        r.begin(1000)
        r.finish(2000)
        r.discard()
        self.assertEqual(accepted.pcm, self.source(False).pcm[:1000])
        self.assertIsNone(r.completed)

    def test_incomplete_and_invalid_requests_are_rejected(self):
        r = RecorderInput(self.source())
        r.begin(0)
        with self.assertRaises(ValueError):
            r.chunk(0, 1, 0)
        with self.assertRaises(ValueError):
            r.candidate(0, 500)
        r.finish(1000)
        for args in ((0, 513, 0), (-1, 1, 0), (499, 2, 0), (0, 1, 1)):
            with self.assertRaises(ValueError):
                r.chunk(*args)
        for trim in ((0, 140), (0, 501), (100, 99)):
            with self.assertRaises(ValueError):
                r.candidate(*trim)

    def test_eof_caps_capture_and_clock_wrap_is_continuous(self):
        r = RecorderInput(self.source())
        r.begin(0xFFFFFF00)
        self.assertEqual(r.count(0x100), 256)
        self.assertEqual(r.count(0xFFFF), 2000)

    def test_explicit_ssi_sample_clock_preserves_legacy_default(self):
        legacy = RecorderInput(self.source())
        sample_clock = RecorderInput(self.source(), ticks_per_frame=1)
        for recorder in (legacy, sample_clock):
            recorder.begin(0xFFFFFF00)
            recorder.finish(0x100)
        self.assertEqual(legacy.captured, 256)
        self.assertEqual(sample_clock.captured, 512)
        self.assertEqual(sample_clock.candidate(0, 512).pcm, self.source().pcm[:2048])
        with self.assertRaises(ValueError):
            RecorderInput(self.source(), ticks_per_frame=0)

    def test_wave_input_requires_exact_supported_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input.wav"
            with wave.open(str(p), "wb") as w:
                w.setparams((1, 2, 48000, 0, "NONE", "none"))
                w.writeframes(struct.pack("<200h", *range(200)))
            take = Take.from_wav(p)
            self.assertEqual(take.pcm, struct.pack(">200h", *range(200)))
            with wave.open(str(p), "wb") as w:
                w.setparams((1, 2, 44100, 0, "NONE", "none"))
                w.writeframes(bytes(400))
            with self.assertRaises(ValueError):
                Take.from_wav(p)

    def test_bounds_and_partial_stereo_are_rejected(self):
        for data in (bytes(140 * 4), bytes(141 * 4 + 1), bytes((MAX_FRAMES + 1) * 4)):
            with self.assertRaises(ValueError):
                Take(data, True)

    def test_waveform_has_signed_independent_channel_extrema(self):
        r = RecorderInput(self.source())
        r.begin(0)
        r.finish(2000)
        self.assertEqual(struct.unpack(">4i", r.extrema(7, 12)), (7, 11, -11, -7))
        self.assertEqual(r.extrema(1000, 1001), bytes(16))


if __name__ == "__main__":
    unittest.main()
