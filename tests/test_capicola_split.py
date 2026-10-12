"""Split-time lifecycle, independent state, exact arithmetic and boundary rates."""

import ctypes as ct
import math
import struct
import subprocess
from pathlib import Path

import test_capicola as baseline

check = baseline.check


class CapicolaSplitTests(baseline.CapicolaTests):
    @classmethod
    def setUpClass(cls):
        # Reuse every finite-core lifecycle and buffer-boundary assertion.
        import tempfile

        cls.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        source = Path(cls.temp.name) / "test.c"
        source.write_text(
            '#include "' + str(root / "machines/capicola/split.c") + '"\n'
            "void cursor_trace(float rate,int *w,unsigned *f) {\n"
            "int whole=0; unsigned frac=0; int n;\n"
            "for(n=0;n<96000;n++) {advance_time(&whole,&frac,(unsigned)(rate*16777216.0f));w[n]=whole;f[n]=frac;}\n}\n"
        )
        lib = Path(cls.temp.name) / "split.dylib"
        subprocess.run(
            [
                "clang",
                "-std=c99",
                "-O2",
                "-ffp-contract=off",
                "-shared",
                str(source),
                "-o",
                str(lib),
            ],
            check=True,
        )
        cls.lib = ct.CDLL(str(lib))

    def test_all_cursor_steps_are_exact(self):
        trace = self.lib.cursor_trace
        trace.argtypes = [ct.c_float, ct.POINTER(ct.c_int), ct.POINTER(ct.c_uint)]
        w, f = (ct.c_int * 96000)(), (ct.c_uint * 96000)()
        for rate in [0.5, 0.7, 1, 1.1, 2]:
            rate = ct.c_float(rate).value
            trace(rate, w, f)
            self.assertTrue(
                all(w[i] + f[i] / 2**24 == (i + 1) * rate for i in range(96000))
            )

    def test_boundary_rates_and_independent_states(self):
        e = self.engine
        other = check.Engine(self.lib, "cap")
        e.load(check.generate("sine", 4800, 1))
        other.load([0] * 100)
        for bits in [
            0x3F000000,
            0x3F000001,
            0x3F7FFFFF,
            0x3F800000,
            0x3F800001,
            0x3FFFFFFF,
            0x40000000,
        ]:
            rate = struct.unpack("<f", struct.pack("<I", bits))[0]
            self.assertEqual(e.call("start", rate, rate, 128), 0)
            expected = e.render(10000)
            self.assertEqual(e.call("position"), math.ceil(4800 / rate))
            other.call("start", 1, 1, 128)
            self.assertEqual(other.render(1000), bytes(4000))
            e.call("start", rate, rate, 128)
            self.assertEqual(e.render(10000, 17), expected)
