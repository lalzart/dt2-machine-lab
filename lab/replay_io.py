"""Shared prepared-replay I/O; no signal or reference-algorithm implementation."""

import sharc_trace as st
from sharc_transpile_run import OPT_STOP_PC

from lab.project import require


def load_pcm(engine, raw):
    core = engine.core
    regs = [f"{k}{i}" for k in ("R", "I", "M", "L") for i in range(16)]
    saved = {r: core.get_reg(st.UREG_CODES[r]) for r in regs}
    core.set_option(OPT_STOP_PC, 0x1C834A)
    for pos in range(0, len(raw), 4100):
        core.poke(0x268240, raw[pos : pos + 4100], 1)
        values = dict(
            M5=0,
            M6=1,
            M7=-1,
            M14=1,
            I6=0x200D7F00,
            I7=0x200D7EF8,
            R4=0,
            R8=4,
            R12=0x268220,
        )
        values.update({f"L{i}": 0 for i in range(16)})
        for reg, value in values.items():
            core.set_reg(st.UREG_CODES[reg], st.Const(value))
        core.poke(0x200D7EFC, bytes(32), 1)
        core.fresh_call(0x1C7E1F)
        core.run(50000)
        require(core.pc() == 0x1C834A, "LP0 callback did not resubmit")
    core.set_option(OPT_STOP_PC, 0)
    for reg, value in saved.items():
        core.set_reg(st.UREG_CODES[reg], value)
