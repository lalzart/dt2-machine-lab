"""Opt-in running CF receipt path and original SHARC SPI completion dispatch.

Cadence, capture and LP0 delivery remain explicit emulator models. All sample
generations stay pinned. This module is never used by normal firmware builds.
"""

import struct

from lab import recorder_ack as ack
from lab import recorder_retirement as obs
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

BASE, END = 0x10A00000, 0x10A04000
RECEIVE, SUBMIT, FLUSH_COPY = BASE + 0x100, BASE + 0x400, BASE + 0x900
STATE = BASE + 0x2000  # sequence, submit count, last request result, poll count
RECEIVE_SITE = 0x4002DD7A
RECEIVE_BYTES = bytes.fromhex("4fef00106008")
TASK_CALL, TASK_RETURN = 0x1C7756, 0x1C775D


def contract():
    c = read_json(ROOT / "machines/recorder-ack-loop/contract.json")
    require(c["status"] == "ready", "Control-path contract not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Proposal drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Pin drift")
    for key in (
        "approval",
        "working_artifact",
        "source_equivalence",
        "experiment",
        "controls",
        "state_matrix",
        "validation",
        "results",
        "gaps",
        "decisions",
    ):
        require(bool(c[key]), "Incomplete control-path contract: " + key)
    return c


def cpu():
    """Native completion submission and matcher at the original ISR return."""
    contract()
    c = Code()
    c.emit("4fef0010 4feffff0 48d70303")
    c.imm("4eb9", ack.CF_CONSUME)
    c.imm("2039", STATE + 12)
    c.imm("0680", 1)
    c.imm("23c0", STATE + 12)
    c.emit("4cd70303 4fef0010")
    # Original next instruction is TST; old condition codes are dead here.
    c.imm("4ef9", 0x4002DD88)
    receive = c.finish(RECEIVE)

    c = Code()
    c.emit("4fefffe8 48d70c1c")  # D2-D4/A2-A3
    c.imm("4eb9", FLUSH_COPY)  # unchanged completed logical publication
    c.imm("45f9", w.STATE)
    c.emit("202a0048 d080 d080")  # private slot -> allocation index
    c.imm("41f9", 0x405B5368)
    c.emit("d1c0 2010")
    c.imm("223c", 0x34)
    c.emit("4c010800")  # reviewed MULS.L D1,D0, stock 52-byte record
    c.imm("2079", 0x405A0F64)
    c.emit("d1c0 24280010 26280014")  # native logical extent, never CPU pointer
    c.imm("2039", STATE)
    c.imm("0680", 1)
    c.imm("23c0", STATE)
    c.emit("2f03 2f02 2f00 206a0014 2f280004 2f2a003c")
    # The control ISR may preempt the worker. Disable the previous matcher
    # before the request builder changes any tuple/table fields. It publishes
    # PENDING last. A refused diagnostic request leaves matching disabled.
    c.emit("7000")
    c.imm("23c0", ack.constants()["CF_STATE"] + ack.PHASE)
    c.imm("4eb9", ack.CF_REQUEST)
    c.emit("4fef0014")
    c.imm("23c0", STATE + 8)
    c.imm("2039", STATE + 4)
    c.imm("0680", 1)
    c.imm("23c0", STATE + 4)
    c.emit("4cd70c1c 4fef0018 4e75")
    submit = c.finish(SUBMIT)
    # FLUSH contains no relative control transfers; keep its original bytes.
    flush = w.flush()
    require(len(flush) < 256, "FLUSH copy extent drift")
    return {RECEIVE: receive, SUBMIT: submit, FLUSH_COPY: flush}


def install_cpu(fw):
    """Byte-guarded experiment only; no stock driver HLE or normal build edit."""
    require(fw.read(RECEIVE_SITE, 6) == RECEIVE_BYTES, "ISR return drift")
    require(fw.read(w.FLUSH, len(w.flush())) == w.flush(), "Native FLUSH drift")
    for base, size in (
        (obs.CF_BASE, 8192),
        (ack.constants()["CF_BASE"], 16384),
        (BASE, END - BASE),
    ):
        for at in range(base, base + size, 4096):
            fw.m.ensure(at)
        fw.write(base, bytes(size))
    fw.write(obs.CF_ENTRY, obs.sender())
    for at, data in (ack.cpu() | cpu()).items():
        fw.write(at, data)
    for at, target in ((RECEIVE_SITE, RECEIVE), (w.FLUSH, SUBMIT)):
        fw.write(at, b"\x4e\xf9" + struct.pack(">I", target))
        fw.uc.ctl_remove_cache(at, at + 6)


def engine_class():
    # Import runtime adapters lazily so contract/code tests need no DSP state.
    # isort: off
    from lab.dsp import Dsp
    from lab.flex_lite import FlexDsp
    import sharc_trace as st
    # isort: on

    class Engine(FlexDsp):
        def __init__(self, blob=None):
            Dsp.__init__(self, blob)
            c, n = self.core, self.native
            for opt in (n.OPT_PERIPHERAL_MODEL, n.OPT_STACK_MODEL, n.OPT_BANK_MODEL):
                c.set_option(opt, 1)
            # Missing peripheral reset contents in the prepared checkpoint.
            # Do not write DMA descriptors, callback arguments or receipt state.
            for at in range(0x31089000, 0x3108A000, 4):
                c.poke(at, bytes(4), 4)
            self.run_segment(0x1C0F24, 0x1C0FA5)
            self.run_segment(0x1C8173, 0x1C817A)
            self.run_segment(0x1C80A0, 0x1C80A9)
            self.startup_status = c.peek(0x31089404)
            require(c.peek(0x31089000) == 3, "Native SEC global setup")
            require(c.peek(0x31089400) == 0x10003, "Native SEC core setup")
            require(c.get_reg(st.UREG_CODES["IMASK"]).value == 0x8000, "SECI mask")
            self.completed = 0

        def run_segment(self, start, stop):
            c, n = self.core, self.native
            c.set_option(n.OPT_STOP_PC, stop)
            c.fresh_call(start)
            before = c.stats()["instructions"]
            c.run(4_000_000)
            require(
                c.pc() == stop, f"Native path {start:#x}: {c.pc():#x}, {c.halt_reason}"
            )
            c.set_option(n.OPT_STOP_PC, -1)
            return c.stats()["instructions"] - before

        def block_after_exchange(self):
            c = self.core
            shift = c.peek(self.profile.command_word_shift_src)
            count = self.run_segment(TASK_CALL, TASK_RETURN)
            require(c.peek(0x31089A2C) == c.peek(0x31089A34) == 0, "SEC not drained")
            require(c.get_reg(st.UREG_CODES["IMASKP"]).value == 0, "Interrupt active")
            require(c.peek(0x31089404) == self.startup_status, "New SEC error")
            require(
                c.peek(self.profile.command_word_shift_src) == shift ^ 1,
                "RX callback missing",
            )
            self.completed += 1
            return count

        def voices(self):
            words = []
            for lane in range(32):
                base = 0x2412CC + lane * 0x1D8 + self.h.FIELD_WORK_BUFFER
                words.extend(self.core.peek(base + i * 4) for i in range(64))
            return struct.pack("<2048I", *words)

    return Engine
