#!/usr/bin/env python3
# ruff: noqa: E402
"""Stock recorder/selector buffer prototype; opt-in, emulator only."""

import argparse
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import (
    doctor,
    git,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
from datetime import UTC, datetime

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", nargs="?", type=Path)
p.add_argument("--check", action="store_true")
p.add_argument("--input", type=Path)
p.add_argument("--window-seconds", type=int, default=900)
args = p.parse_args()
require(10 <= args.window_seconds <= 1800, "Window bound is 10..1800 seconds")
doctor()
out = (
    args.output
    or ROOT / "out/runs" / datetime.now(UTC).strftime("flex-buffers-%Y%m%dT%H%M%S%fZ")
).resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_buffer_ui import BufferUI
from lab.flex_recorder import Take
from lab.flex_session import Session


def demo(number):
    return Take(
        b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(12000)
        ),
        True,
    )


sources = source_hashes()
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
write_json(out / "sources.json", sources)
report = dict(
    status="running",
    head=git(ROOT, "rev-parse", "HEAD"),
    branch=git(ROOT, "branch", "--show-current"),
    initial_status=git(ROOT, "status", "--porcelain=v1"),
    scope="Original recorder/selector, emitted ColdFire DEST cell/setter, host buffer transaction; original stock DSP in separate buffered replay. No native retirement/readback, physical input, real time or device claim.",
    checks={},
    snapshots=[],
    native_save=False,
)
session = None


def stage(name):
    session.advance()
    session.screenshot(name)
    report["snapshots"].append(name + ".png")


def destination(value):
    for _ in range(14):
        current = session.flex.destination
        if current == value:
            return
        session.turn("C", 5 if current < value else -5)
    raise ValueError("DEST encoder did not reach selection")


def slot(track):
    return int.from_bytes(
        session.flex.fw.read(session.flex.fw.u32(0x80004704) + track * 0x450 + 0x80, 2),
        "big",
    )


def record(number, *, trim=False):
    session.flex.input.source = demo(number)
    # Normal sampling toggle opens from SRC; caller keeps recorder open only
    # after cancellation/failure.
    session.record()
    if trim:
        before = [
            session.flex.fw.u32(session.flex.view + off) for off in (0x9A0, 0x9A4)
        ]
        for _ in range(12):
            session.turn("E", 5)
            if session.flex.fw.u32(session.flex.view + 0x9A0) > before[0]:
                break
        for _ in range(12):
            session.turn("H", -5)
            if session.flex.fw.u32(session.flex.view + 0x9A4) < before[1]:
                break
        after = [session.flex.fw.u32(session.flex.view + off) for off in (0x9A0, 0x9A4)]
        require(
            before[0] < after[0] < after[1] < before[1],
            "Original trim controls did not move",
        )
        report["checks"]["trim"] = dict(before=before, after=after)


try:
    source = Take.from_wav(args.input) if args.input else demo(1)
    session = Session(source, out, adapter_factory=BufferUI)
    if not args.check:
        from lab.flex_window import open_window

        open_window(
            session,
            seconds=args.window_seconds,
            input_name=args.input.name if args.input else "deterministic stereo",
        )
    else:
        fw = session.flex.fw
        session.tap("SAMPLING")
        stage("01-dest-take")
        # MON draw/setter/label must be byte-for-byte original again.
        from lab.runtime import STOCK_MAIN

        main = STOCK_MAIN.read_bytes()
        for start, end in (
            (0x40020334, 0x40020372),
            (0x40022316, 0x40022402),
            (0x4004D0D2, 0x4004D0F0),
        ):
            require(
                fw.read(start, end - start)
                == main[start - 0x40000400 : end - 0x40000400],
                "MON code was modified",
            )
        report["checks"]["original_monitor_code"] = True
        destination(1)
        require(session.flex.destination == 1, "DEST did not select BUF 1")
        stage("02-dest-buf1")
        with fw.transaction():
            settings = fw.u32(session.flex.view + 0xA0)
            monitor_before = fw.call(0x4004CD02, [settings])
        for _ in range(6):
            session.turn("E", -127 if monitor_before else 127)
        stage("03-monitor-on-e")
        require(session.flex.destination == 1, "Monitoring changed DEST")
        with fw.transaction():
            monitor_after = fw.call(0x4004CD02, [settings])
        report["controls"] = session.flex.events
        report["text_calls"] = session.flex.selector_names
        report["monitor_values"] = [monitor_before, monitor_after]
        require(
            monitor_after != monitor_before,
            "Stock E/MON did not change original setting",
        )
        report["checks"]["monitor"] = [monitor_before, monitor_after]
        session.tap("SRC")
        record(1, trim=True)
        stage("04-trim")
        session.accept()
        require(session.flex.current["name"] == "BUF 1", "USE did not commit BUF 1")
        first = dict(session.flex.current)
        first_pages = list(session.flex.pages)
        stage("05-buf1-ready")
        capture_a = session.capture_pad("buffer-a")
        write_json(out / "generation-a.json", first)
        (out / "pages-a.bin").write_bytes(
            b"".join(
                struct.pack(">II", tag, header) + block
                for tag, block, header in first_pages
            )
        )
        session.tap("ENCODER D")
        stage("06-stock-selector-buf1")
        session.tap("NO")
        # Second ONESHOT track is deliberate fixture preparation through stock
        # machine selection if necessary. No other sound fields are edited.
        session.chord("TRK", "TRIG 5")
        live = fw.u32(0x80004704) + 4 * 0x450
        machine = fw.read(live + 0xD6, 1)[0]
        if machine:
            session.chord("FUNC", "SRC")
            for _ in range(8):
                session.tap("UP")
            session.tap("YES")
            session.tap("YES")
        require(fw.read(live + 0xD6, 1) == b"\0", "T5 must be ONESHOT")
        # Standard sample selector, including its original bank navigation.
        session.tap("SRC")
        session.tap("ENCODER D")
        current = slot(4)
        target = session.flex.buffer_slots[0]
        for _ in range((target // 128 - current // 128) % 8):
            session.tap("RIGHT")
        for _ in range(target % 128 - current % 128):
            session.tap("DOWN")
        # Scroll the four logical rows into the stock selector's viewport.
        for _ in range(3):
            session.tap("DOWN")
        for _ in range(3):
            session.tap("UP")
        stage("06b-buffer-rows-in-stock-selector")
        drawn = [
            item["text"]
            for item in session.flex.selector_names
            if item.get("kind") == "stock-selector-row"
        ]
        require(
            all(any(f"BUF {i}" in row for row in drawn) for i in range(1, 5)),
            "Stock selector did not draw all four buffer names",
        )
        report["checks"]["selector_rows"] = sorted(set(drawn))
        session.tap("YES")
        print("Manual selector", current, "->", slot(4), "expected", target, flush=True)
        require(slot(4) == target, "Original selector did not assign BUF 1 to T5")
        stage("07-t5-shared-buf1")
        report["checks"]["manual_selector"] = dict(
            track=5, slot=slot(4), host_assignment=False
        )
        # Buffer commits now autoassign the newly selected compatible track.
        record(2)
        session.accept()
        second = dict(session.flex.current)
        require(
            first["slot"] == second["slot"] == slot(0) == slot(4),
            "Shared logical slots changed",
        )
        require(
            first["allocation"]["start"] != second["allocation"]["start"],
            "Old PCM was overwritten",
        )
        stage("08-buf1-rerecorded")
        capture_b = session.capture_pad("buffer-b")
        second_pages = list(session.flex.pages)
        (out / "pages-ab.bin").write_bytes(
            b"".join(
                struct.pack(">II", tag, header) + block
                for tag, block, header in second_pages
            )
        )
        session.tap("SAMPLING")
        destination(2)
        stage("09-dest-buf2")
        session.tap("SRC")
        record(3)
        session.accept()
        third = dict(session.flex.current)
        require(third["slot"] != first["slot"], "BUF 2 did not remain independent")
        stage("10-buf2-ready")
        # Cancel a later candidate and retain the committed buffer.
        record(4)
        previous = session.flex.buffers.current[1]
        session.chord("FUNC", "NO")
        require(session.flex.buffers.current[1] == previous, "Cancel replaced BUF 2")
        stage("11-cancel-keeps-buffer")
        destination(0)
        stage("12-back-to-take")
        session.tap("SRC")
        record(5)
        session.accept()
        require(
            session.flex.current["name"].startswith("TEMP"), "TAKE workflow was changed"
        )
        stage("13-independent-take")
        report["checks"]["workflow"] = dict(
            first=first,
            replacement=second,
            second_buffer=third,
            take=dict(session.flex.current),
            capture_a=capture_a,
            capture_b=capture_b,
        )
        # Save guard executes at original Project::save entry, before any write.
        with fw.transaction():
            before_writes = len(fw.card.writes)
            result = fw.call(0x40043A30, [0, 0, 0])
            require(
                result == 0 and len(fw.card.writes) == before_writes,
                "Volatile project save escaped guard",
            )
        report["checks"]["project_save_blocked"] = True
        # Repeat USE failures against an already committed BUF 2. These are
        # named host fault seams, not claimed physical allocation failures.
        session.tap("SAMPLING")
        destination(2)
        session.tap("SRC")
        record(6)
        previous = session.flex.buffers.current[1]
        for failure in ("allocation", "publication"):
            session.flex.inject_failure = failure
            session.tap("YES")
            session.advance()
            require(
                session.flex.phase == "trim"
                and session.flex.buffers.current[1] is previous,
                "Failed candidate changed the committed buffer",
            )
            report["checks"]["failure-" + failure] = session.flex.error
        session.flex.inject_failure = None
        session.chord("FUNC", "NO")
        session.flex.buffers.max_bytes = session.flex.buffers.occupied
        session.tap("YES")
        session.advance(8_000_000)
        session.tap("YES")
        session.tap("YES")
        session.advance()
        require(
            session.flex.phase == "trim"
            and session.flex.buffers.current[1] is previous,
            "Capacity rejection lost previous buffer",
        )
        report["checks"]["capacity"] = session.flex.error
        session.chord("FUNC", "NO")
        session.flex.buffers.max_bytes = 4 * 1024 * 1024
        session.tap("SRC")
        with fw.transaction():
            require(
                fw.call(0x400F5050, [0, 0, 0, 0]) == 0,
                "Project load escaped lifetime guard",
            )
        report["checks"]["project_load_blocked"] = True
        report["checks"]["no_file_writes"] = len(fw.card.writes) == 0
        require(not fw.card.writes, "Workflow wrote a file")
        report["buffer_slots"] = session.flex.buffer_slots
        report["private_slots"] = session.flex.private_slots
        report["memory"] = dict(
            dsp_bytes=session.flex.buffers.occupied,
            generations=len(session.flex.buffers.generations),
            issued=session.flex.issued,
            max_generations=session.flex.buffers.max_generations,
            guest_cpu_buffer_sources=0,
            retained_host_take_sources=len(fw.sources),
        )
        # Explicit host epoch transition test. Real project loads remain
        # blocked above until a fresh emulator session can own their lifecycle.
        session.flex.change_project()
        require(
            session.flex.buffers.current == [None] * 4
            and session.flex.destination == 0,
            "Epoch transition retained logical buffers",
        )
        require(
            session.flex.project_transition_blocked,
            "Old slot identities could cross projects",
        )
        report["checks"]["host_project_epoch_clears_buffers"] = True
    report["events"] = session.flex.events
    report["inputs"] = {
        k: sha256(v) for k, v in session.inputs.items() if k != "sections"
    }
    require(sources == source_hashes(), "Source drift during prototype")
    report["status"] = "passed"
    write_json(out / "report.json", report)
    print(f"PASS: {out / 'report.json'}", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["events"] = session.flex.events
        session.screenshot("failure")
    write_json(out / "report.json", report)
    raise
finally:
    if session:
        session.close()
