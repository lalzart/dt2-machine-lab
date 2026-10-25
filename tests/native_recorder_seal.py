# ruff: noqa: E402
"""Explicit native DSP ABI controls; CPU admission is tested separately."""

import argparse
import ctypes
import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, require, sha256, write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
options = parser.parse_args()
out = options.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import recorder_ack_loop as loop
from lab import recorder_native_retirement as t
from lab import recorder_retirement as obs
from lab import recorder_retirement_gate as gate
from lab.dsp import Dsp
from lab.flex_audio import baseline_pages
from lab.flex_dsp_probe import control
from lab.flex_lite import FlexDsp
from lab.flex_session import stock_inputs
from lab.voice_read import VoiceReader

run = options.fixture.resolve()
build = options.build.resolve()
blob = (build / "RETIRE_BLOB.bin").read_bytes()
meta = json.loads((build / "build.json").read_text())
source = json.loads((run / "report.json").read_text())
listing = (build / "listing.txt").read_text()
gdirect = meta["base"]["gate"]["symbols"]["gate_direct"]
gate_listing = (build / "gate/listing.txt").read_text()
gstop = int(
    re.search(
        r"(?m)^\s+([0-9a-f]+)\s+[0-9a-f]+\s+rts$",
        gate_listing[gate_listing.index("gate_direct:") :],
    )[1],
    16,
)
seal_start = int(
    re.search(r"(?m)^\s+([0-9a-f]+)\s+[0-9a-f]+\s+r4=dm \(0x200f9120\)", listing)[1], 16
)
after_cjump = listing[listing.index("cjump seal_emit (db)") :]
seal_stop = int(re.search(r"dm \(i7,m7\)=0x([0-9a-f]+)", after_cjump)[1], 16) + 1
NativeEngine = loop.engine_class()


class Engine(FlexDsp):
    def __init__(self, blob):
        Dsp.__init__(self, blob)

    def run_segment(self, start, stop):
        self.core.set_option(self.native.OPT_STOP_PC, stop)
        self.core.fresh_call(start)
        self.core.run(400000)
        require(self.core.pc() == stop, "ABI segment did not reach exact return")
        self.core.set_option(self.native.OPT_STOP_PC, -1)


k = t.contract()["constants"]
gk = gate.contract()["constants"]
if "device_placement" in meta:
    from lab.sketch_dsp_device import audit

    require(audit(blob) == meta["device_placement"], "Device DSP placement drift")
    gk = dict(gk, STATE=meta["device_placement"]["gate_state"][0])
reader = VoiceReader(out / "reader")
wire = (run / "tx.bin").read_bytes()[-0xABC:]
checks = {}


def put(e, at, value):
    data = struct.pack("<I", value) if isinstance(value, int) else value
    require(e.core.poke(at, data, 1) == len(data), "Fixture write")


def page_list(number):
    raw = (run / f"pages-{number}.bin").read_bytes()
    return [
        (
            struct.unpack_from(">I", raw, i)[0],
            raw[i + 8 : i + 4104],
            struct.unpack_from(">I", raw, i + 4)[0],
        )
        for i in range(0, len(raw), 4104)
    ]


base = Engine(blob)
base.publish(baseline_pages(stock_inputs()["lp0"]))
base.publish(page_list(3))
state = base.state_bytes()
args = (1, source["cycles"][1]["token"], 10, 25600, 16384)
require(source["status"] == "passed-restricted-native-transaction", "Unproven fixture")
require(
    sha256(run / "pages-3.bin")
    == "ccd4bd13eab3d54c2c59469d5bdf2139c65eadb2e1e50d33894337bf5bff0bec",
    "Extent fixture drift",
)
private = 305
slot = gk["SLOTS"] + private * 20
original_descriptor = base.slot_record(private)
require(original_descriptor[2], "B private descriptor absent")


def fresh():
    e = Engine(blob)
    buf = ctypes.create_string_buffer(state)
    require(
        e.core._lib.sharc_native_import_state(e.core._handle, buf, len(state)) == 0,
        "State clone",
    )
    return e


def send(e, values=args):
    e.publish([(obs.constants()["TAG"], obs.packet(*values), 1)])


def block(e, selected=300, trigger=False):
    return e.frame(control(wire, selected, trigger=trigger))


def status(e):
    return [e.core.peek(k["DSP_STATE"] + i * 4) for i in range(8)]


def gate_state(e):
    return [e.core.peek(gk["STATE"] + i * 4) for i in range(97)]


def scan(e):
    import sharc_trace as st

    saved = {code: e.core.get_reg(code) for code in set(st.UREG_CODES.values())}
    try:
        e.run_segment(gdirect, gstop)
        put(e, k["DSP_STATE"] + 0x1120, 0x266220)
        e.run_segment(seal_start, seal_stop)
    finally:
        for code, value in saved.items():
            e.core.set_reg(code, value)


try:
    # An extent with only the internal owner seals after an actual new control pass.
    e = fresh()
    send(e)
    scan(e)
    require(
        status(e)[1] == 0 and e.slot_record(private) == original_descriptor,
        "Direct-call observation fabricated a fence",
    )
    checks["no-fresh-control"] = status(e)
    for _ in range(3):
        block(e)
    require(status(e)[1] and not any(e.slot_record(private)), "Native seal missing")
    require(gate_state(e)[27:29] == [0, 127], "General permission changed")
    checks["private-only-native-seal"] = status(e)
    # Exact retry succeeds; an empty descriptor without matching tuple does not.
    send(e, (1, args[1], 11, *args[3:]))
    block(e)
    block(e)
    require(status(e)[7] == 2, "Exact native sealed-tuple retry failed")
    checks["exact-retry"] = status(e)
    send(e, (1, args[1] + 10, 12, *args[3:]))
    block(e)
    block(e)
    require(status(e)[1] == 0 and status(e)[5] == 3, "Wrong token reused empty proof")
    checks["wrong-token-empty-descriptor"] = status(e)
    # Inactive retained reader: a pointer alone must prevent descriptor sealing.
    e = fresh()
    address = 0x2412CC + 20 * 472
    put(e, address, 0x8422B9C8 + original_descriptor[0])
    put(e, address + 0x1B8, bytes(1))
    send(e)
    block(e)
    block(e)
    require(
        gate_state(e)[16] & (1 << 20) and status(e)[1] == 0,
        "Inactive retained reader ignored",
    )
    checks["retained-inactive-reader"] = dict(
        seal=status(e), retained=gate_state(e)[16]
    )
    # Independent cached/incoming private selection; CPU guard rejects this input.
    e = fresh()
    send(e)
    block(e, private, True)
    g = gate_state(e)
    require(
        g[15] == 0 and (g[22] or g[23] or g[24]) and status(e)[1] == 0,
        "Zero-reader pending private selection allowed a seal",
    )
    checks["pending-private-selection"] = dict(seal=status(e), gate=g)
    # Descriptor-only destructive comparator: prove that this refusal matters.
    pending = e.state_bytes()
    bad = fresh()
    buf = ctypes.create_string_buffer(pending)
    require(
        bad.core._lib.sharc_native_import_state(bad.core._handle, buf, len(pending))
        == 0,
        "Pending clone",
    )
    put(bad, slot, bytes(20))
    block(e, private)
    block(bad, private)
    require(reader.read(e) != reader.read(bad), "Unsafe comparator did not alter PCM")
    checks["destructive-pending-comparator"] = True
    # Native acquisition is now an active original ONESHOT reader.
    require(gate_state(e)[15] and status(e)[1] == 0, "Active reader ignored")
    checks["active-reader"] = dict(seal=status(e), active=gate_state(e)[15])
    # Every nonprivate descriptor class and unknown extent independently blocks.
    for label, index in [
        ("logical", 301),
        ("snapshot", 312),
        ("preview", 1024),
        ("other", 2),
    ]:
        e = fresh()
        put(e, gk["SLOTS"] + index * 20, struct.pack("<5I", *original_descriptor))
        send(e)
        block(e)
        block(e)
        require(
            status(e)[1] == 0 and e.slot_record(private) == original_descriptor,
            label + " root ignored",
        )
        checks[label + "-root"] = dict(seal=status(e), gate=gate_state(e))
    e = fresh()
    put(e, gk["SLOTS"] + 2 * 20, struct.pack("<5I", gk["POOL_END"], 0, 8, 48000, 0))
    send(e)
    block(e)
    block(e)
    require(gate_state(e)[25] and status(e)[1] == 0, "Unknown descriptor ignored")
    checks["unknown-extent"] = status(e)

    # Paired contexts have the same valid private owner and request. The enabled
    # original SEC path must seal; disabling its interrupt must leave it pinned.
    def native_context():
        e = NativeEngine(blob)
        e.publish(baseline_pages(stock_inputs()["lp0"]))
        e.publish(page_list(3))
        send(e)
        return e

    e = native_context()
    for _ in range(3):
        e.core.spi2_exchange(control(wire, 300))
        e.block_after_exchange()
    require(
        status(e)[1] and not any(e.slot_record(private)), "Enabled SEC did not seal"
    )
    checks["enabled-sec"] = dict(seal=status(e), completed=e.completed)
    e = native_context()
    import sharc_trace as st

    e.core.set_reg(st.UREG_CODES["IMASK"], st.Const(0))
    e.core.spi2_exchange(control(wire, 300))
    e.core.set_option(e.native.OPT_STOP_PC, loop.TASK_RETURN)
    e.core.fresh_call(loop.TASK_CALL)
    e.core.run(1_000_000)
    require(
        status(e)[1] == 0
        and e.slot_record(private) == original_descriptor
        and (e.core.peek(0x31089A2C) or e.core.peek(0x31089A34)),
        "Disabled SEC did not retain its pending request and private owner",
    )
    checks["disabled-sec"] = dict(
        pc=e.core.pc(),
        seal=status(e),
        completed=e.completed,
        pending=[e.core.peek(0x31089A2C), e.core.peek(0x31089A34)],
    )
    result = dict(
        status="passed-native-dsp-controls",
        checks=checks,
        blob_sha256=hashlib.sha256(blob).hexdigest(),
        source_scope=__doc__,
        script_sha256=sha256(Path(__file__)),
        input_pages_sha256=sha256(run / "pages-3.bin"),
    )
except BaseException as exc:
    result = dict(
        status="failed",
        error=repr(exc),
        checks=checks,
        seal=status(e),
        gate=gate_state(e),
        private=e.slot_record(private),
        public=e.slot_record(300),
        request=[e.core.peek(obs.constants()["STATE"] + i * 4) for i in range(16)],
    )
    raise
finally:
    write_json(out / "report.json", result)
print("PASS", out / "report.json")
