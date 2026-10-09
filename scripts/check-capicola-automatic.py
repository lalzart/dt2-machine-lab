#!/usr/bin/env python3
"""OS1.16 automatic preparation through native frame and transfer hooks."""

# ruff: noqa: E402, I001
import argparse
import array
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import settings, doctor, require, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--controls", action="store_true")
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = out.name
doctor()
from lab.plaits import build_blob
from lab.dsp import Dsp, header
from lab.formats import read_frames
from lab.capicola_memory import BANK_BASE
import sharcldr
import sharc_trace as st

POOL = 0x8422B9C8
TOKEN = POOL + 0x4000
AUTO = 0x200E4500
H = 0x200E4000
report = dict(
    status="running",
    scope="Native emulator frame and transfer hooks; no CPU menu or hardware deadline proof",
)
try:
    sources = source_hashes()
    candidate = build_blob(
        True,
        family="capicola-controls" if args.controls else "capicola-auto",
        output=out / "candidate",
    )
    require(
        candidate
        == build_blob(
            True,
            family="capicola-controls" if args.controls else "capicola-auto",
            output=out / "repeat",
        ),
        "Build repeat",
    )
    old = build_blob(True, family="capicola-owned", output=out / "baseline")
    prior = ROOT / "out/runs/capicola-owned-hook-01/combined/PLAITS_BLOB.bin"
    require(old == prior.read_bytes(), "Prior owned family changed")

    def arena(blob):
        split = sharcldr.parse_blocks(blob)[-1]["offset"]
        return (
            blob[:split]
            + header(POOL, 0x10000)
            + bytes(0x10000)
            + header(BANK_BASE - 256, 0x697A00)
            + bytes(0x697A00)
            + blob[split:]
        )

    blob = arena(candidate)
    (out / "CAPICOLA_AUTOMATIC_TEST_BLOB.bin").write_bytes(blob)

    def entry(name):
        return int(
            re.search(
                rf"(?m)^{name}\.:\n\s+([0-9a-f]+)",
                (out / "candidate/listing.txt").read_text(),
            )[1],
            16,
        )

    def poke(e, a, *v):
        e.core.poke(a, struct.pack("<" + "I" * len(v), *v), 1)

    def peek(e, a, n):
        return b"".join(struct.pack("<I", e.core.peek(a + i)) for i in range(0, n, 4))

    def call(e, pc, regs=None, stack=None):
        r = dict(M5=0, M6=1, M7=-1, M14=1, I6=0x200D7F00, I7=0x200D7EF8)
        r.update({f"L{i}": 0 for i in range(16)})
        r.update(regs or {})
        for k, v in r.items():
            e.core.set_reg(st.UREG_CODES[k], st.Const(v))
        e.core.poke(0x200D7EFC, bytes(32), 1)
        if stack:
            poke(e, 0x200D7F04, *stack)
        before = e.core.stats()["instructions"]
        e.call(pc, 2000000)
        return e.core.stats()["instructions"] - before

    def metadata(e, source=TOKEN, n=1024, other=None):
        for voice, ptr in (
            (0x2412CC, source),
            (0x2414A4, source if other is None else other),
        ):
            poke(e, voice, ptr)
            poke(e, voice + 0x188, n)
            poke(e, voice + 0x1B8, 1)
        poke(e, 0x255970, 8)
        for a, v in (
            (0x2558DE, 60 * 256),
            (0x2559B6, 64 * 256),
            (0x2559BA, 64 * 256),
            (0x2559C8, 32768),
        ):
            poke(e, a, v)

    def slot(e, n=1024, source=TOKEN, index=1):
        return call(
            e,
            0x1C3FE5,
            dict(R4=index, R8=source - POOL, R12=source - POOL),
            [n * 2, 48000, 0],
        )

    def page(e, index):
        # Use a real page payload and the original native page-copy routine.
        return call(e, 0x1C403C, dict(R4=index, R8=0x200E6000))

    def tick(e):
        return call(e, entry("cap_maintenance"))

    def ready(e):
        return e.core.peek(H + 8) == 1

    spec = importlib.util.spec_from_file_location(
        "cap", ROOT / "scripts/check-capicola-capacity.py"
    )
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    host, _, _ = cap.build(out)
    data = array.array(
        "f", [round(x * 32767) / 32768 for x in cap.fixture("two-tone", 1024)]
    )
    pcm = b"".join(struct.pack("<h", round(x * 32768)) for x in data)
    bank = cap.Sample(host, data)
    require(bank.result == 0, "Host bank")

    def fresh():
        e = Dsp(blob)
        e.core.poke(TOKEN, pcm, 1)
        # All slot identities in this isolated fixture reference the same mono
        # PCM. Selection/transport from the CPU is a separate integration gate.
        for i in range(1025):
            poke(e, 0x257810 + 20 * i, TOKEN - POOL, TOKEN - POOL, len(pcm), 48000, 0)
        metadata(e)
        return e

    def finish(e, limit=80):
        costs = []
        for _ in range(limit):
            costs.append(tick(e))
            if ready(e):
                return costs
        raise ValueError("Preparation did not finish")

    e = fresh()
    costs = finish(e)
    require(
        peek(e, BANK_BASE, len(bank.payload())) == bank.payload(),
        "Automatic key parity",
    )
    require(e.core.peek(AUTO + 32) == 2 * (len(data) + 4), "Two-pass bounded work")
    report["direct_slices"] = len(costs)
    report["max_maintenance_instructions"] = max(costs)
    baseline_bank = peek(e, BANK_BASE, len(bank.payload()))
    for _ in range(10):
        tick(e)
    require(
        peek(e, BANK_BASE, len(bank.payload())) == baseline_bank, "Ready bank changed"
    )
    print("Automatic native keys passed", flush=True)

    # Native sample transfer: unrelated pages preserve ready; overlapping page
    # invalidates before copy, remains blocked until matching completion header.
    e.core.poke(0x200E6000, pcm + bytes(4096 - len(pcm)), 1)
    report["unrelated_page_instructions"] = page(e, 0)
    require(ready(e), "Unrelated page invalidated bank")
    epoch = e.core.peek(AUTO + 12)
    report["overlap_page_instructions"] = page(e, 4)
    require(
        not ready(e)
        and e.core.peek(AUTO + 24) == 1
        and e.core.peek(AUTO + 12) != epoch,
        "Overlapping transfer not invalidated",
    )
    for _ in range(4):
        tick(e)
    require(
        not ready(e) and e.core.peek(0x200E4418) == 0,
        "Prepared during incomplete transfer",
    )
    report["header_instructions"] = slot(e)
    require(e.core.peek(AUTO + 24) == 0, "Completion header did not unblock")
    finish(e)
    require(
        peek(e, BANK_BASE, len(bank.payload())) == bank.payload(),
        "Same-address reload parity",
    )
    # Zero-length reset can point at logical zero, unlike the old live source.
    slot(e, n=0, source=POOL - 0x400)
    tick(e)
    require(
        not ready(e) and e.core.peek(AUTO + 24) == 1, "Slot reset retained publication"
    )
    slot(e)
    finish(e)
    # Header loop-guard copying can touch the next live allocation. Observe
    # invalidation BEFORE those original stock writes, not just at publication.
    call(e, 0x1C400F, dict(R4=TOKEN - POOL - 16, R8=16))
    require(
        not ready(e) and e.core.peek(AUTO + 24) == 1, "Loop guard write not invalidated"
    )
    page(e, 4)
    slot(e)
    finish(e)
    require(
        peek(e, BANK_BASE, len(bank.payload())) == bank.payload(), "Loop guard recovery"
    )
    report["native_transfer_lifecycle"] = "passed"
    print("Native sample transfer lifecycle passed", flush=True)

    dense = array.array(
        "f", [round(x * 32767) / 32768 for x in cap.fixture("noise", 1024)]
    )
    dense_bank = cap.Sample(host, dense)
    dense_engine = fresh()
    dense_engine.core.poke(
        TOKEN, b"".join(struct.pack("<h", round(x * 32768)) for x in dense), 1
    )
    dense_costs = finish(dense_engine)
    require(
        peek(dense_engine, BANK_BASE, len(dense_bank.payload()))
        == dense_bank.payload(),
        "Dense automatic key parity",
    )
    report["max_dense_maintenance_instructions"] = max(dense_costs)
    # Invalid metadata and changing machine never use stale bank arrays.
    for source, n, other in [
        (0, 1024, 0),
        (TOKEN, 0, TOKEN),
        (TOKEN, 576001, TOKEN),
        (TOKEN + 1, 1024, TOKEN + 1),
        (BANK_BASE, 1024, BANK_BASE),
        (0x9CA2B9C6, 2, 0),
        (TOKEN, 1024, TOKEN + 4096),
    ]:
        metadata(e, source, n, other)
        tick(e)
        require(not ready(e), "Invalid source accepted")
    metadata(e)
    finish(e)
    poke(e, 0x255970, 7)
    tick(e)
    require(not ready(e), "Machine switch kept bank")
    metadata(e)
    finish(e)
    # Both epoch fields gate rendering even if publication is interrupted.
    poke(e, AUTO + 20, e.core.peek(AUTO + 12) - 1)
    poke(e, 0x24F0CC, 1)
    call(e, entry("machine"), dict(R4=0x2412CC))
    require(peek(e, 0x2412D0, 256) == bytes(256), "Stale epoch rendered")
    report["metadata_negative_cases"] = 8

    # Native complete frames, with no direct maintenance/service calls. The
    # candidate must advance and publish solely through its stock return hook.
    wires = read_frames(config["fixture"] / "captures/sine-type-7.dtfr")
    a, b = fresh(), Dsp(arena(old))
    frame_costs = []
    reference_costs = []
    for i in range(90):
        wire = bytearray(wires[i % len(wires)])
        wire[0x94:0x96] = b"\0\x08"
        if args.controls:
            for off, v in (
                (2, 60 * 256),
                (0xDA, 64 * 256),
                (0xDE, 64 * 256),
                (0xEC, 32768),
            ):
                wire[off : off + 2] = struct.pack(">H", v)
        a.frame(bytes(wire))
        frame_costs.append(a.block_instructions[-1])
        if ready(a):
            break
    require(ready(a), "Stock frames never published bank")
    require(
        peek(a, BANK_BASE, len(bank.payload())) == bank.payload(),
        "Frame-driven key parity",
    )
    report["frames_until_ready"] = i + 1
    report["max_frame_instructions"] = max(frame_costs)
    # Readiness must lead to actual audible voice PCM on a subsequent trigger.
    pcm_out = []
    for _ in range(12):
        poke(a, 0x24F0CC, 1 if not pcm_out else 0)
        call(a, entry("machine"), dict(R4=0x2412CC))
        pcm_out.extend(struct.unpack("<64f", peek(a, 0x2412D0, 256)))
    require(max(map(abs, pcm_out)) > 1e-5, "Published bank was inaudible")
    ref = cap.Reader(bank)
    require(ref.start(1, 1) == 0, "Reference start")
    expected = array.array("f")
    expected.frombytes(ref.render(12 * 32))
    expected = array.array("f", [x * 0.125 for x in expected for _ in range(2)])
    mx, rms = cap.previous.error(
        expected.tobytes(), array.array("f", pcm_out).tobytes()
    )
    require(mx <= 1e-4 and rms <= 1e-5, "Frame-prepared voice mismatch")
    report["voice_max_error"] = mx
    report["voice_rms_error"] = rms
    cap.ref.save_wav(
        out / "automatic-voice.wav", array.array("f", pcm_out[::2]).tobytes()
    )
    if args.controls:
        checks = []
        for note, tune, rate, level, pitch, advance, gain in (
            (60, 52, 0, 32768, 0.5, 0.5, 0.125),
            (60, 64, 64, 16384, 1.0, 1.0, 0.0625),
            (60, 76, 127, 32768, 2.0, 2.0, 0.125),
            (72, 64, 32, 0, 2.0, 0.75, 0.0),
            (0, 4, 255, 65535, 0.5, 2.0, 0.125),
            (127, 124, 96, 32768, 2.0, 1.0 + 32 / 63, 0.125),
        ):
            for addr, value in (
                (0x2558DE, note * 256),
                (0x2559B6, tune * 256),
                (0x2559BA, rate * 256),
                (0x2559C8, level),
                (0x24F0CC, 1),
            ):
                poke(a, addr, value)
            call(a, entry("machine"), dict(R4=0x2412CC))
            values = struct.unpack("<3f", peek(a, H + 16, 12))
            require(
                max(
                    abs(x - y)
                    for x, y in zip(values, (pitch, advance, gain), strict=True)
                )
                < 1e-6,
                "Panel control mapping",
            )
            checks.append(
                dict(note=note, tune=tune, rate=rate, level=level, actual=values)
            )
        report["dsp_control_cases"] = checks
    # Unchanged Plaits and stock full frames use identical voice output.
    for typ in (6, 7):
        a, b = Dsp(blob), Dsp(arena(old))
        for wire in wires:
            w = bytearray(wire)
            w[0x94:0x96] = struct.pack(">H", typ)
            require(a.frame(bytes(w)) == b.frame(bytes(w)), "Stock/Plaits frame parity")
        reference_costs.extend(b.block_instructions)
    report["stock_plaits_frame_cases"] = 2 * len(wires)
    report["baseline_max_frame_instructions"] = max(reference_costs)
    require(source_hashes() == sources, "Source drift during check")
    report.update(
        status="passed",
        sources=sources,
        blob_sha256=hashlib.sha256(candidate).hexdigest(),
        repeat_build_exact=True,
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
