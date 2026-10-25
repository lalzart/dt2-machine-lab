#!/usr/bin/env python3
# ruff: noqa: E402
"""ColdFire-generated request, native LP0 decoder and advisory SHARC observer.

Card, request-wire delivery and IRQ entry are modeled. The publisher call is
captured at the existing diagnostic boundary; no duplex reply or reuse occurs.
"""

import argparse
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

from lab import recorder_retirement as r
from lab.dsp import Dsp
from lab.flex_audio import baseline_pages
from lab.flex_lite import FlexDsp, RamFirmware
from lab.flex_session import stock_inputs

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    dest = out / "frozen-sources" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, dest)
report = dict(
    status="running",
    provenance=provenance,
    scope=__doc__,
    checks={},
    native_ack_transport=False,
    native_reclamation=False,
    publisher_body_executed=False,
    source_hle_used=False,
)
fw = None
k = r.constants()
state_base = k["STATE"]
fixture = ROOT / "out/runs/recorder-freeze-queue-native-20261021-02"
EXPECTED = {
    "report.json": "5053a977dd664b473692ce3b9e9769b847d403c2440062b8af84bcdfc8a2f579",
    "pages-af.bin": "ef0b4314174803a6535feb326c3f29951c4b211d0f0ab6cbbe4615cac99eee29",
    "pages-b.bin": "e596b46a882600036d0c258eb2b66e06ccdd7e4ff52e2c85f82ac79d9218159e",
}


class Observed(FlexDsp):
    def __init__(self, blob):
        Dsp.__init__(self, blob)


def words(engine):
    return [engine.core.peek(state_base + i * 4) for i in range(22)]


def put(engine, address, value, width=4):
    require(
        engine.core.poke(address, value.to_bytes(width, "little"), 1) == width,
        "Fixture write failed",
    )


def read(engine, address, length):
    return bytes(engine.core.peek(address + i, 1) for i in range(length))


def pages(name):
    data = (fixture / name).read_bytes()
    require(len(data) % 4104 == 0, "Partial fixture page")
    return [
        (
            struct.unpack_from(">I", data, i)[0],
            data[i + 8 : i + 4104],
            struct.unpack_from(">I", data, i + 4)[0],
        )
        for i in range(0, len(data), 4104)
    ]


def observation_oracle(engine):
    s = words(engine)
    lo, hi = s[4] - k["POOL_START"], s[4] - k["POOL_START"] + s[5]
    begin, end = k["WINDOW"] + lo, k["WINDOW"] + hi
    active = retained = roots = unknown = 0
    for lane in range(32):
        base = k["VOICE_BASE"] + lane * k["VOICE_STRIDE"]
        if begin <= engine.core.peek(base) < end:
            if engine.core.peek(base + 0x1B8, 1):
                active |= 1 << lane
            else:
                retained |= 1 << lane
    cap = k["POOL_END"] - k["POOL_START"]
    for slot in range(1025):
        left, right, length, *_ = engine.slot_record(slot)
        if not length:
            continue
        if any(x >= cap or x + length > cap for x in (left, right)):
            unknown += 1
        elif any(x < hi and x + length > lo for x in (left, right)):
            roots += 1
    expected = [
        active,
        retained,
        roots,
        3 if active else 4 if unknown else 2 if roots else 1,
    ]
    require(s[9] == s[0] and s[10:13] == s[1:4], "Uncommitted or stale observation")
    require(
        s[13:17] == expected and s[20] == unknown,
        f"Native observer differs: {s[13:17]} vs {expected}, unknown {s[20]}/{unknown}",
    )
    return dict(
        revision=s[9],
        epoch=s[10],
        generation=s[11],
        sequence=s[12],
        active=active,
        retained=retained,
        roots=roots,
        status=s[16],
        unknown=unknown,
    )


def voice_bytes(engine):
    result = []
    for lane in range(32):
        base = k["VOICE_BASE"] + lane * k["VOICE_STRIDE"] + engine.h.FIELD_WORK_BUFFER
        result.extend(engine.core.peek(base + j * 4) for j in range(64))
    return struct.pack("<2048I", *result)


try:
    for name, digest in EXPECTED.items():
        require(sha256(fixture / name) == digest, "Unknown worker fixture: " + name)
    report["inputs"] = EXPECTED
    proof = read_json(fixture / "report.json")
    require(proof["status"] == "passed", "Unproven worker fixture")
    blob, metadata = r.build(out / "dsp")
    report["build"] = metadata
    actual, oracle = Observed(blob), FlexDsp()
    wire = bytearray.fromhex(proof["audio_inputs"]["wire"])
    for track, slot in ((0, 300), (4, 300), (5, 312)):
        struct.pack_into(">H", wire, 0xE0 + track * 0x60, slot)
    pa, pb = pages("pages-af.bin"), pages("pages-b.bin")
    require(pb[: len(pa)] == pa, "Page history changed")
    first, second = proof["checks"]["first"], proof["checks"]["second"]
    args_a = (
        1,
        k["FIRST_ID"],
        1,
        first["allocation"]["start"],
        first["allocation"]["size"],
    )
    args_b = (
        1,
        k["FIRST_ID"] + 1,
        2,
        second["allocation"]["start"],
        second["allocation"]["size"],
    )
    for engine in (actual, oracle):
        engine.publish(baseline_pages(stock_inputs()["lp0"]))
        engine.publish(pa)
    pcm_hash = hashlib.sha256()
    block_count = 0
    measured = []

    def block(mask=0):
        global block_count
        frame = bytearray(wire)
        for offset in (0x22, 0x24, 0x26, 0x28, 0x2A):
            struct.pack_into(">H", frame, offset, mask if offset in (0x22, 0x26) else 0)
        for e in (actual, oracle):
            e.frame(bytes(frame))
        pcm = voice_bytes(actual)
        require(pcm == voice_bytes(oracle), "Observer changed stock voice PCM")
        pcm_hash.update(pcm)
        for bank in (0, 1):
            addr = 0x266220 + bank * 0x1000
            require(
                read(actual, addr, 0xABC) == read(oracle, addr, 0xABC),
                "Observer changed reply bytes",
            )
        for slot in (300, 304, 305, 312):
            require(
                actual.slot_record(slot) == oracle.slot_record(slot),
                "Observer mutated slot",
            )
        measured.append(
            dict(
                native=actual.block_instructions[-1],
                stock=oracle.block_instructions[-1],
            )
        )
        block_count += 1
        if words(actual)[0]:
            return observation_oracle(actual)

    # Use the existing proven pad-capture timeline: its first frame carries
    # the trigger. A zero-trigger priming frame did not arm these stock voices.
    block(1 | 16 | 32)
    require(words(actual)[:6] == [0] * 6, "No-request state changed")
    report["checks"]["no-request"] = True

    # Native CF packet construction; publisher is the named diagnostic seam.
    inputs = stock_inputs()
    fw = RamFirmware(inputs["card"], inputs["snapshot"])
    for address in (r.CF_BASE, r.CF_PACKET):
        fw.m.ensure(address)
    fw.write(r.CF_BASE, bytes(8192))
    fw.write(r.CF_ENTRY, r.sender())
    fw.pages.clear()
    require(
        fw.call(r.CF_ENTRY, list(args_a)) == 0 and len(fw.pages) == 1,
        "Native sender failed",
    )
    req = fw.pages[0]
    require(
        req == (k["TAG"], r.packet(*args_a), 1),
        "Native CF packet differs from independent oracle",
    )
    for args in (
        (0, *args_a[1:]),
        (1, k["LAST_ID"] + 1, *args_a[2:]),
        (*args_a[:2], 0, *args_a[3:]),
        (*args_a[:3], 0, args_a[4]),
        (*args_a[:3], k["POOL_END"] - 8192, 16384),
        (*args_a[:4], 1),
    ):
        fw.pages.clear()
        require(
            fw.call(r.CF_ENTRY, list(args)) == 0xFFFFFFFF and not fw.pages,
            "Native sender accepted invalid extent/identity",
        )
    require(not fw.card.writes, "Observer sender wrote storage")
    report["checks"]["cpu-serializer"] = True
    # Stock ignores this tag: its descriptor and subsequent PCM are unchanged.
    old = [oracle.slot_record(x) for x in (300, 304, 312)]
    actual.publish([req])
    oracle.publish([req])
    require(
        [oracle.slot_record(x) for x in (300, 304, 312)] == old,
        "Stock tag control mutated descriptors",
    )
    report["checks"]["ignored-stock-tag"] = True
    require(
        words(actual)[0] == 1 and words(actual)[9] == 0, "LP0 fabricated an observation"
    )
    report["checks"]["deferred-until-block"] = True
    result = block()
    require(
        result["active"] == 0xF03 and result["roots"] == 3,
        "A reader/root fixture mismatch",
    )
    report["checks"]["active-a"] = result
    while block_count < 12:
        block()
    for page in pb[len(pa) :]:
        actual.publish([page])
        oracle.publish([page])
        block()
    while block_count < 24:
        block()

    def send(args):
        page = (k["TAG"], r.packet(*args), 1)
        actual.publish([page])
        oracle.publish([page])

    send(args_b)
    queued = block(1 | 16 | 32)
    require(queued["active"] == 0, "Prepared queued-trigger boundary drifted")
    result = block()
    require(result["active"] == 0x303, "Independent B reader identity mismatch")
    report["queued_control_negative"] = dict(
        trigger_block=queued,
        following_block=result,
        idle_scan_is_not_retirement=True,
    )
    report["checks"]["independent-b"] = result
    args_a3 = (1, k["FIRST_ID"], 3, *args_a[3:])
    send(args_a3)
    result = block()
    require(result["active"] == 0xC00 and result["roots"] == 2, "Frozen A root lost")
    report["checks"]["frozen-root"] = result
    # T6 retains its independent low-pitch settings. Derive a bounded wait
    # from its installed native reader step instead of assuming clip seconds.
    voice = k["VOICE_BASE"] + 10 * k["VOICE_STRIDE"]
    step_q31 = actual.core.peek(voice + 0x1A8) | (actual.core.peek(voice + 0x1AC) << 32)
    length = actual.core.peek(voice + 0x188)
    require(
        step_q31 > 0 and not actual.core.peek(voice + 0x1BC, 1),
        "Natural-end fixture is stopped or looping",
    )
    wait_bound = math.ceil(length / (step_q31 / 2**31 * 64)) + 128
    require(wait_bound <= 5000, "Natural-end fixture exceeds bounded experiment")
    report["natural_end_fixture"] = dict(
        length=length, step_q31=step_q31, wait_bound=wait_bound
    )
    for index in range(wait_bound):
        result = block()
        if not result["active"]:
            break
        if index % 500 == 499:
            print("natural-end blocks", index + 1, "of", wait_bound, flush=True)
    require(not result["active"], "A never completed")
    report["checks"]["natural-end"] = dict(result, blocks=block_count)
    # An idle reader mask is not an irreversible retirement acknowledgement.
    block(32)
    late = block()
    require(late["active"] == 0xC00, "Late old trigger failed to reacquire A")
    report["checks"]["late-trigger"] = late

    before = words(actual)
    invalid = []
    for index, value in (
        (0, 0),
        (1, 2),
        (2, 0),
        (3, k["FIRST_ID"] - 1),
        (4, 0),
        (5, 0),
        (5, k["POOL_END"]),
        (5, args_a[3] + 1),
        (6, 0),
        (6, 1),
        (6, k["POOL_END"]),
        (7, 0),
        (8, 1),
        (15, 0),
    ):
        data = bytearray(r.packet(*args_a3))
        struct.pack_into(">I", data, index * 4, value)
        actual.publish([(k["TAG"], bytes(data), 1)])
        require(words(actual)[:6] == before[:6], "Bad packet replaced request")
        invalid.append(dict(word=index, value=value))
    require(
        words(actual)[7] - before[7] == len(invalid),
        "Missing malformed-packet rejection",
    )
    report["checks"]["bad-packets"] = invalid
    before = words(actual)
    send(args_a3)
    require(
        words(actual)[0] == before[0] and words(actual)[6] == before[6] + 1,
        "Duplicate not idempotent",
    )
    send(args_a)
    require(words(actual)[7] == before[7] + 1, "Old sequence accepted")
    send((1, k["FIRST_ID"] + 1, 3, *args_a[3:]))
    require(words(actual)[7] == before[7] + 2, "Conflicting duplicate accepted")
    send((2, k["FIRST_ID"], 1, *args_a[3:]))
    rev = words(actual)[0]
    send((1, k["FIRST_ID"], 100, *args_a[3:]))
    require(words(actual)[0] == rev, "Old epoch accepted")
    block()
    report["checks"]["stale-and-duplicate"] = True

    # Pure observer ABI fixtures: these are not claims of 32 audible voices.
    synth = Observed(blob)
    synth.core.poke(k["SLOTS"], bytes(1025 * 20), 1)
    synth.publish([req])
    base = k["WINDOW"] + args_a[3] - k["POOL_START"] + 32
    for lane in range(32):
        put(synth, k["VOICE_BASE"] + lane * k["VOICE_STRIDE"], base)
        put(synth, k["VOICE_BASE"] + lane * k["VOICE_STRIDE"] + 0x1B8, 1, 1)
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(observation_oracle(synth)["active"] == 0xFFFFFFFF, "Upper reader bits lost")
    for lane in range(32):
        put(synth, k["VOICE_BASE"] + lane * k["VOICE_STRIDE"] + 0x1B8, 0, 1)
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(
        observation_oracle(synth)["retained"] == 0xFFFFFFFF, "Inactive pointers hidden"
    )
    report["checks"]["inactive-retained"] = True
    for lane in range(32):
        address = k["VOICE_BASE"] + lane * k["VOICE_STRIDE"] + 0x1B8
        put(synth, address, 1, 1)
        synth.call(metadata["symbols"]["observer_direct"], 200000)
        require(
            observation_oracle(synth)["active"] == 1 << lane, "Lane bit mapping differs"
        )
        put(synth, address, 0, 1)
    report["checks"]["all-lane-bits"] = True
    # Preview and overlapping-start descriptors must also count as roots.
    lo = args_a[3] - k["POOL_START"]
    for slot, offset in ((0, lo - 4), (1024, lo)):
        synth.core.poke(
            k["SLOTS"] + slot * 20, struct.pack("<5I", offset, offset, 8, 48000, 0), 1
        )
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(observation_oracle(synth)["roots"] == 2, "Boundary/preview root omitted")
    synth.core.poke(k["SLOTS"], bytes(1025 * 20), 1)
    # A genuine native cooperative mid-scan replacement invalidates the result.
    # This fixture bypasses LP0 delivery, so reproduce its metadata word order.
    synth.core.poke(
        k["REQUEST"], struct.pack("<1024I", *struct.unpack(">1024I", r.packet(*args_b))), 1
    )
    put(synth, state_base + k["FAULT_WORD"] * 4, 1)
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(
        words(synth)[9] == 0 and words(synth)[18] == 1,
        "Superseded scan published stale result",
    )
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(observation_oracle(synth)["sequence"] == 2, "New request was not observed")
    # Unknown descriptors must prevent an idle interpretation, even without
    # an active lane; this is an ABI fixture, not a real project transition.
    synth.core.poke(
        k["SLOTS"], struct.pack("<5I", k["POOL_END"], 0, 8, 48000, 0), 1
    )
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(words(synth)[16] == 4 and words(synth)[20] == 1, "Unknown root hidden")
    observation_oracle(synth)
    synth.core.poke(k["SLOTS"], bytes(20), 1)
    synth.call(metadata["symbols"]["observer_direct"], 200000)
    require(words(synth)[16] == 1, "Rootless state was not IDLE_UNSEALED")
    observation_oracle(synth)
    report["synthetic_result"] = words(synth)
    # Refuse revision wrap rather than permitting request ABA.
    put(synth, state_base, 0xFFFFFFFF)
    before = words(synth)
    synth.publish([(k["TAG"], r.packet(2, *args_b[1:]), 1)])
    require(
        words(synth)[:6] == before[:6] and words(synth)[7] == before[7] + 1,
        "Revision exhaustion accepted a request",
    )
    report["checks"]["supersede"] = True
    report["checks"]["exact-pcm"] = dict(
        blocks=block_count, lanes=32, sha256=pcm_hash.hexdigest()
    )
    report["checks"]["reply-preserved"] = True
    report["instructions"] = measured
    report["sampled_state"] = words(actual)
    report["synthetic_state_fixture"] = True
    require(
        set(report["checks"]) == set(r.contract()["experiment"]["conditions"]),
        "Unexecuted contract condition",
    )
    require(source_hashes() == sources, "Source changed during run")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if "actual" in globals():
        report["failure_state"] = words(actual)
    if "synth" in globals():
        report["synthetic_failure_state"] = words(synth)
    if "result" in globals():
        report["last_observation"] = result
    raise
finally:
    if fw:
        fw.close()
    write_json(out / "report.json", report)
