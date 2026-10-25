#!/usr/bin/env python3
# ruff: noqa: E402
"""Native pending-reference/ownership diagnostics; no free or identity reuse.

Capture pages, wire delivery and LP0 callback entry are modeled. Stock control,
slot lookup, readers and diagnostic decisions execute SHARC instructions.
"""
import argparse
import ctypes
import hashlib
import math
import os
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import (
    ROOT,
    doctor,
    read_json,
    require,
    sha256,
    source_hashes,
    write_json,
)

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

from lab import recorder_retirement as old
from lab import recorder_retirement_gate as gate
from lab.dsp import Dsp
from lab.flex_audio import baseline_pages
from lab.flex_lite import FlexDsp
from lab.flex_session import stock_inputs

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    dest = out / "frozen-sources" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, dest)
k = gate.contract()["constants"]
fixture = ROOT / "out/runs/recorder-freeze-queue-native-20261021-02"
expected = {
    "report.json": "5053a977dd664b473692ce3b9e9769b847d403c2440062b8af84bcdfc8a2f579",
    "pages-af.bin": "ef0b4314174803a6535feb326c3f29951c4b211d0f0ab6cbbe4615cac99eee29",
    "pages-b.bin": "e596b46a882600036d0c258eb2b66e06ccdd7e4ff52e2c85f82ac79d9218159e",
}
report = dict(status="running", provenance=provenance, checks={}, native_reuse=False,
              native_retirement_ack=False, host_authorization=False, scope=__doc__)


class Observed(FlexDsp):
    def __init__(self, blob, state=None):
        Dsp.__init__(self, blob)
        if state is not None:
            buf = ctypes.create_string_buffer(state)
            require(self.core._lib.sharc_native_import_state(self.core._handle, buf, len(state)) == 0,
                    "Clone import failed")


def put(e, address, data):
    require(e.core.poke(address, data, 1) == len(data), "Fixture write failed")


def word(e, index, value):
    put(e, k["STATE"] + index * 4, struct.pack("<I", value))


def view(e):
    s = gate.state(e)
    require(s[27] == 0, "Diagnostic granted permission")
    if s[10]:
        require(s[28] == 127, "Unknown CPU/transport roots hidden")
    return dict(revision=s[10], epoch=s[11], generation=s[12], sequence=s[13],
                reasons=s[14], active=s[15], retained=s[16], logical=s[17], private=s[18],
                snapshots=s[19], preview=s[20], other=s[21], cached=s[22], bank0=s[23],
                bank1=s[24], unknown_descriptors=s[25], status=s[26], permission=s[27],
                unknown_ownership=s[28], control_serial=s[1], completed_serial=s[4],
                completed_revision=s[5], lookups=s[6], last_lookup_serial=s[7],
                last_lookup_slot=s[8], trigger_mask=s[31])


def voice(e):
    return struct.pack("<2048I", *[e.core.peek(0x2412CC + lane*472 + 4 + i*4)
                                 for lane in range(32) for i in range(64)])


def page_list(name):
    raw = (fixture / name).read_bytes()
    require(len(raw) % 4104 == 0, "Partial capture")
    return [(struct.unpack_from(">I", raw, i)[0], raw[i+8:i+4104],
             struct.unpack_from(">I", raw, i+4)[0]) for i in range(0, len(raw), 4104)]


def clear_header(slot):
    # Stock metadata order is slot, left, right, rate, bytes, flags.
    return (0xFFFFFFFF, struct.pack(">6I", slot, 0, 0, 48000, 0, 0) + bytes(4072), 1)


try:
    for name, digest in expected.items():
        require(sha256(fixture / name) == digest, "Worker fixture drift: " + name)
    report["inputs"] = expected
    proof = read_json(fixture / "report.json")
    require(proof["status"] == "passed", "Unproven input")
    blob, meta = gate.build(out / "dsp")
    report["build"] = meta
    actual, stock = Observed(blob), FlexDsp()
    wire = bytearray.fromhex(proof["audio_inputs"]["wire"])
    for track, slot in ((0, 300), (4, 300), (5, 312)):
        struct.pack_into(">H", wire, 0xE0 + track*0x60, slot)
    pa, pb = page_list("pages-af.bin"), page_list("pages-b.bin")
    require(pb[:len(pa)] == pa, "Capture history changed")
    args = [(1, old.constants()["FIRST_ID"]+i, i+1, proof["checks"][label]["allocation"]["start"],
             proof["checks"][label]["allocation"]["size"]) for i, label in enumerate(("first", "second"))]
    for e in (actual, stock):
        e.publish(baseline_pages(stock_inputs()["lp0"]))
        e.publish(pa)
    trace, counts, pcm = [], [], hashlib.sha256()
    total = 0

    def frame(mask=0):
        x = bytearray(wire)
        for at in (0x22, 0x24, 0x26, 0x28, 0x2A):
            struct.pack_into(">H", x, at, mask if at in (0x22, 0x26) else 0)
        return bytes(x)

    def block(mask=0):
        global total
        for e in (actual, stock):
            e.frame(frame(mask))
        data = voice(actual)
        require(data == voice(stock), "Gate changed original voice PCM")
        pcm.update(data)
        for bank in (0, 1):
            at = 0x266220 + bank*4096
            require([actual.core.peek(at+i*4) for i in range(687)] ==
                    [stock.core.peek(at+i*4) for i in range(687)], "Gate changed reply")
        for slot in (300, 304, 305, 312):
            require(actual.slot_record(slot) == stock.slot_record(slot), "Slot changed")
        s = view(actual)
        trace.append(s)
        counts.append([actual.block_instructions[-1], stock.block_instructions[-1]])
        total += 1
        return s

    def send(e, values):
        e.publish([(old.constants()["TAG"], old.packet(*values), 1)])

    block(49)
    require(view(actual)["revision"] == 0, "No-request observation invented")
    report["checks"]["no-request"] = True
    for e in (actual, stock):
        send(e, args[0])
    a1 = block()
    require(a1["active"] == 0xF03 and a1["snapshots"] == 1 and a1["logical"] == 1,
            "A ownership changed")
    report["checks"]["active-a"] = a1
    while total < 12:
        block()
    for page in pb[len(pa):]:
        for e in (actual, stock):
            e.publish([page])
        block()
    while total < 24:
        block()
    for e in (actual, stock):
        send(e, args[1])
    pending = block(49)
    require(pending["active"] == 0 and pending["cached"] & 17 == 17 and
            pending["trigger_mask"] & 17 == 17 and pending["reasons"] & 8,
            "Pending shared B was hidden by zero reader mask")
    report["checks"]["shared-b-pending"] = pending
    report["unsafe_idle_comparator"] = dict(would_release=pending["active"] == 0,
                                             rejected_by_native_reasons=pending["reasons"])
    # Independent destructive descriptor-only negative: no PCM is freed/reused.
    bad = Observed(blob, actual.state_bytes())
    for slot in (300, 305):
        bad.publish([clear_header(slot)])
        require(bad.slot_record(slot)[2] == 0, "Bad negative header order")
    bad.call(meta["gate"]["symbols"]["gate_direct"], 400000)
    cleared_pending = view(bad)
    require(cleared_pending["cached"] & 17 == 17 and cleared_pending["reasons"] & 8,
            "Descriptor clear erased cached generation identity")
    result = block()
    bad.frame(frame())
    require(voice(bad) != voice(actual), "Premature descriptor clear did not falsify PCM")
    require(bad.core.peek(0x2412CC) == 0 and actual.reading(300), "Pending B not destroyed")
    report["checks"]["descriptor-clear-negative"] = dict(
        before_consume=cleared_pending, cached_identity_survives_clear=True,
        premature_clear_loses_pending_b=True, unsafe_pcm_sha256=hashlib.sha256(voice(bad)).hexdigest())
    require(result["active"] == 0x303 and result["lookups"] >= 4 and result["last_lookup_slot"] == 300,
            "Native slot acquisition not observed")
    report["checks"]["native-lookup"] = result
    for e in (actual, stock):
        send(e, (1, args[0][1], 3, *args[0][3:]))
    frozen = block()
    require(frozen["snapshots"] == 1 and frozen["private"] == 1 and not frozen["logical"],
            "Snapshot A root missing after B replacement")
    report["checks"]["snapshot-root"] = frozen
    v = 0x2412CC + 10*472
    step = actual.core.peek(v+0x1A8) | (actual.core.peek(v+0x1AC) << 32)
    length = actual.core.peek(v+0x188)
    bound = math.ceil(length / (step / 2**31 * 64)) + 128
    require(0 < bound <= 5000, "Natural-end bound")
    for i in range(bound):
        result = block()
        if not result["active"]:
            break
        if i % 500 == 499:
            print("natural end", i+1, "of", bound, flush=True)
    require(not result["active"] and result["snapshots"] == 1 and result["reasons"], "Idle snapshot released")
    block(32)
    result = block()
    require(result["active"] == 0xC00, "Frozen A failed late reacquisition")
    report["checks"]["late-frozen-trigger"] = result
    # Explicit ABI fixtures below: not actual CPU/project root closure.
    synth = Observed(blob)
    for at, size in ((k["SLOTS"], 1025*20), (0x2412CC, 32*472),
                     (k["PARAM"], 0x804), (k["COMMAND0"], 4096), (k["COMMAND1"], 4096)):
        put(synth, at, bytes(size))
    send(synth, args[0])
    direct = meta["gate"]["symbols"]["gate_direct"]
    synth.call(direct, 400000)
    result = view(synth)
    require(result["reasons"] & 16 and result["status"] == 1, "Direct call fabricated fence")
    report["checks"]["direct-call-no-fence"] = result
    synth.frame(frame())
    result = view(synth)
    require(result["status"] == 2 and result["reasons"] == 0 and result["permission"] == 0,
            "Rootless DSP fixture classification differs")
    report["checks"]["clear-dsp-fixture"] = dict(result, synthetic_only=True)
    pointer = 0x8422B9C8 + args[0][3] - 1024 + 32
    put(synth, 0x2412CC, struct.pack("<I", pointer))
    synth.call(direct, 400000)
    require(view(synth)["retained"] == 1 and view(synth)["reasons"] & 2, "Inactive pointer ignored")
    report["checks"]["retained-reader"] = view(synth)
    put(synth, 0x2412CC, bytes(4))
    lo = args[0][3] - 1024
    for slot in (2, 1024):
        put(synth, k["SLOTS"]+slot*20, struct.pack("<5I", lo+32, lo+32, 8, 48000, 0))
    synth.call(direct, 400000)
    require(view(synth)["preview"] == view(synth)["other"] == 1, "Preview/alias root hidden")
    report["checks"]["preview-alias"] = view(synth)
    put(synth, k["SLOTS"], struct.pack("<5I", k["POOL_END"], 0, 8, 48000, 0))
    synth.call(direct, 400000)
    require(view(synth)["unknown_descriptors"] == 1 and view(synth)["reasons"] & 32, "Unknown extent ignored")
    report["checks"]["unknown-root"] = view(synth)
    before = gate.state(synth)[0]
    send(synth, (0, *args[0][1:]))
    synth.call(direct, 400000)
    require(gate.state(synth)[0] == before, "Invalid epoch changed gate")
    send(synth, (2, args[0][1], 1, *args[0][3:]))
    synth.call(direct, 400000)
    project = view(synth)
    require(project["epoch"] == 2 and project["reasons"] & 16, "New epoch inherited old completion")
    send(synth, (1, args[0][1], 100, *args[0][3:]))
    synth.call(direct, 400000)
    require(view(synth)["epoch"] == 2, "Stale epoch accepted")
    report["checks"]["stale-and-project"] = dict(project, protocol_only=True,
                                                  actual_project_drain_proven=False)
    word(synth, 1, 0xFFFFFFFF)
    synth.frame(frame())
    require(view(synth)["reasons"] & 128 and gate.state(synth)[29], "Serial wrap accepted")
    report["checks"]["serial-exhaustion"] = view(synth)
    report["checks"]["exact-pcm"] = dict(blocks=total, lanes=32, sha256=pcm.hexdigest())
    report["checks"]["permission-never-granted"] = True
    require(set(report["checks"]) == set(gate.contract()["experiment"]["conditions"]), "Case missing")
    require(source_hashes() == sources, "Source drift")
    report.update(status="passed", synthetic_fixtures=True)
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if "actual" in globals():
        report["failure_state"] = gate.state(actual)
    if "synth" in globals():
        report["synthetic_failure_state"] = gate.state(synth)
    raise
finally:
    if "trace" in globals():
        write_json(out / "trace.json", trace)
        write_json(out / "instruction-counts.json", counts)
    write_json(out / "report.json", report)
