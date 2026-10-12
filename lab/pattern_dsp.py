"""Bounded OS 1.16 replay adapter for one missing register-FEXT instruction.

The pinned native core already implements immediate FEXT. At the guarded
register-form site, lower the current R4 operand to that existing operation.
Execute it at the original PC/width; firmware bytes stay unchanged. A private
native copy adds only a resume ABI, with unchanged instruction semantics. No other trap is accepted and no instruction is skipped.
"""

import ctypes
from collections import Counter

from lab.dsp import Dsp
from lab.pattern_native import library
from lab.project import require
from lab.runtime import STOCK_BLOB

FEXT_PC = 0xB88E8B
FEXT_BYTES = bytes.fromhex("a401d40d")


def execute_fext(core, native):
    import sharc_trace as st

    require(core.pc() == FEXT_PC, "Unexpected FEXT PC")
    address = 0x20000000 + (FEXT_PC - 0xB80000) * 2
    actual = bytes(core.peek(address + i, 1) for i in range(4))
    require(actual == FEXT_BYTES, "FEXT instruction changed")
    mode = core.get_reg(st.UREG_CODES["MODE1"])
    operand = core.get_reg(st.UREG_CODES["R4"])
    require(
        isinstance(mode, st.Const) and not mode.value & (1 << 21),
        "FEXT SIMD unsupported",
    )
    require(isinstance(operand, st.Const), "Unknown FEXT operand")
    # PRM: RY[5:0] = position, RY[11:6] = length (bits 7..18 in 40-bit notation).
    packed = operand.value & 0xFFF
    fields = {
        "cond[4:0]": 31,
        "dataex[3:0]": packed >> 8,
        "shiftimm[22:16]": 0x10,
        "shiftimm[15:0]": ((packed & 255) << 8) | 0xDD,
    }
    require(
        core.exec_insn(native.pack_insn("6b_shiftimm", 4, "confident", fields)),
        "FEXT lowering failed",
    )
    require(core.pc() == FEXT_PC + 2, "FEXT changed instruction width")
    # Resume after the successful replacement, preserving RAM and stacks.
    resume = core._lib.sharc_native_resume_after_insn
    resume.argtypes, resume.restype = [ctypes.c_void_p], ctypes.c_int32
    require(resume(core._handle) == 0, "Native resume failed")
    core._halted_reason = None


class PatternDsp(Dsp):
    def __init__(self, blob):
        self.library = library()
        super().__init__(blob, library=self.library)
        self.fallbacks = Counter()

    def call(self, pc, limit):
        self.core.fresh_call(pc)
        remaining = limit
        while remaining > 0:
            remaining -= self.core.run(remaining)
            why = self.core.halt_reason or ""
            if "return without followed call" in why:
                return
            if self.core.pc() != FEXT_PC or not why.startswith(
                "native-trap: sharc_core.compute._compute:339: raise ValueError"
            ):
                raise RuntimeError(f"DSP call {pc:#x}: {why}")
            execute_fext(self.core, self.native)
            self.fallbacks[hex(FEXT_PC)] += 1
            remaining -= 1
        raise RuntimeError(f"DSP call {pc:#x}: instruction bound exceeded")


def check_fext():
    """Check values, flags, unrelated state and PC against a Python instruction.

    Only register/PC state is needed: this exact 2a_short instruction has no
    memory accesses. Full pattern replay checks the surrounding native calls.
    """
    import sharc_core.compute_shift as shift
    import sharc_trace as st

    dsp = Dsp(STOCK_BLOB.read_bytes(), library=library())
    core, native = dsp.core, dsp.native

    def register_fext(rn, rx, ry, left, right, values, special, approx_recips):
        position, length = right.value & 63, (right.value >> 6) & 63
        value = st.Const((left.value >> position) & ((1 << min(length, 32)) - 1))
        return (
            rn,
            value,
            "field-extract-register",
            shift._astatx_fext(position + length, value),
        )

    require(0x40 not in shift.SHIFT_OPS, "Dependency now supports FEXT; review adapter")
    count = 0
    for source in (0, 0x80000000, 0x12345678, 0xFFFFFFFF):
        for position, length in (
            (0, 0),
            (0, 23),
            (5, 8),
            (31, 1),
            (0, 32),
            (31, 32),
            (63, 63),
        ):
            core.fresh_call(FEXT_PC)
            core.set_reg(st.UREG_CODES["MODE1"], st.Const(0))
            core.set_reg(st.UREG_CODES["R13"], st.Const(source))
            core.set_reg(
                st.UREG_CODES["R4"], st.Const(0xCAFE0000 | (length << 6) | position)
            )
            before = core.export_state()
            state = native.sd.import_state(before)
            instruction = st.Instruction(
                offset=0,
                length_bytes=4,
                type_name="2a_short",
                kind="confident",
                fields={"compute[22:16]": 0x24, "compute[15:0]": 0x0DD4},
            )
            shift.SHIFT_OPS[0x40] = register_fext
            try:
                expected = st._execute(state, instruction)[0]
            finally:
                del shift.SHIFT_OPS[0x40]
            execute_fext(core, native)
            wanted = native.sd.export_state(expected, page_hash=False)
            actual = core.export_state()
            wanted.pop("page_hashes", None)
            actual.pop("page_hashes", None)
            require(
                not native.sd.compare_states(wanted, actual),
                "FEXT state comparison failed",
            )
            count += 1
    return count
