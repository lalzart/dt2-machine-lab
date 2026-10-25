"""Read-only batching of native peek; scalar equality is checked by the probe."""

import ctypes
import subprocess
import sys

from lab.project import ROOT, require, sha256, write_json


class VoiceReader:
    def __init__(self, output):
        require(
            sys.byteorder == "little", "Voice byte oracle requires little-endian host"
        )
        output.mkdir(exist_ok=False)
        source = ROOT / "lab/native_voice_read.c"
        target = output / "voice_read.dylib"
        command = ["clang", "-O2", "-dynamiclib", "-o", str(target), str(source)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        write_json(
            output / "build.json",
            dict(
                command=command,
                source_sha256=sha256(source),
                library_sha256=sha256(target),
                scope="Read-only unchanged public peek ABI; no core or DSP edits",
            ),
        )
        self.lib = ctypes.CDLL(str(target))
        self.fn = self.lib.read_voice_words
        self.fn.argtypes = [
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self.fn.restype = ctypes.c_int
        self.words = (ctypes.c_uint32 * 2048)()

    def read(self, engine):
        core = engine.core
        function = ctypes.cast(core._lib.sharc_native_peek, ctypes.c_void_p).value
        require(
            self.fn(
                function,
                core._handle,
                0x2412CC,
                0x1D8,
                engine.h.FIELD_WORK_BUFFER,
                32,
                64,
                self.words,
            )
            == 0,
            "Native voice peek failed",
        )
        return bytes(self.words)
