#!/usr/bin/env python3
"""Actual OS 1.16 panel flow with native Flex UI, naming and guest file I/O.

Recorder audio and sector I/O are modeled peers. Screenshots are unedited guest
framebuffers. No physical recording, audio continuity or device timing claim.
"""

# ruff: noqa: E402
import argparse
import hashlib
import html
import math
import os
import struct
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--snapshot", type=Path, required=True)
p.add_argument("--package", type=Path)
args = p.parse_args()
provenance = doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown independent reload snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# Runtime owns the pinned DigiKit import paths used by plusdrive_check.
# isort: off
from lab.runtime import STOCK_MAIN
from lab.flex_native_input import NativeFlexInput
from lab.flex_recorder import Take
from lab.flex_session import Session
import plusdrive_check as check
from emu import panel
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

pcm = struct.pack(">24000h", *[round(9000 * math.sin(i / 12)) for i in range(24000)])
report = dict(
    status="running",
    scope=__doc__,
    hardware=False,
    checks={},
    screenshots=[],
    events=[],
    source_hashes=provenance["source_hashes"],
    package=str(args.package),
)
session = card = None
try:
    session = Session(
        Take(pcm, True),
        out,
        adapter_factory=partial(
            NativeFlexInput, save_screen=True, package=args.package
        ),
    )
    fw, loc = session.flex.fw, session.flex.metadata["locations"]
    card = check.Card(session.inputs["card"])
    card.overlay = dict(session.runtime["events"]["esdhc"].card.overlay)
    fault = [False]
    views = {"name": 0, "message": 0, "recorder": 0}

    def peer(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == 0x40158626:
            if not fault[0]:
                return
            path = fw.read(fw.u32(sp + 4), 80).split(b"\0")[0]
            require(path.startswith(b"/recorded/"), "Fault reached unexpected open")
            fault[0] = False
            report["events"].append(
                dict(event="injected-open-failure", path=path.decode())
            )
            result = 1
        else:
            sector, length, pointer = struct.unpack(">3I", fw.read(sp + 4, 12))
            require(
                0 <= sector < 0x760000 and 0 < length <= 0x10000, "Sector I/O bounds"
            )
            if pc == check.EMMC_READ:
                card.reads.append((sector, length))
                fw.write(pointer, card.read(sector, length))
            else:
                card.writes.append((sector, length))
                card.write(sector, fw.read(pointer, length))
            result = 0
        uc.reg_write(k.UC_M68K_REG_D0, result)
        uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
        uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

    for pc in (check.EMMC_READ, check.EMMC_WRITE, 0x40158626):
        fw.uc.hook_add(UC_HOOK_CODE, peer, begin=pc, end=pc)

    def observe(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc in (0x4011B0D2, 0x4011AEEA):
            view = fw.u32(sp + 4)
            if pc == 0x4011B0D2:
                kind = {
                    0x4021D0F4: "name",
                    0x4021D410: "message",
                    0x401EEC54: "recorder",
                }.get(fw.u32(view))
                if kind:
                    views[kind] = view
            else:
                for kind, active in views.items():
                    if active == view:
                        views[kind] = 0
        elif pc == loc["save_callback"]:
            text = fw.read(fw.u32(fw.u32(sp + 8)), 61).split(b"\0")[0].decode()
            report["events"].append(dict(event="name-confirmed", text=text))
        else:
            text = fw.read(fw.u32(sp + 4), 80).split(b"\0")[0].decode()
            report["events"].append(dict(event="message", text=text))

    for pc in (loc["save_callback"], loc["save_message"], 0x4011B0D2, 0x4011AEEA):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def wait_for(predicate, message):
        for _ in range(24):
            if predicate():
                return
            session.advance(8_000_000)
        require(predicate(), message)

    def capture(name):
        # Wait for a complete nonblank latched firmware frame, never read an
        # in-progress front/back buffer or draw/compose a replacement image.
        for _ in range(12):
            session.advance(4_000_000)
            frame = bytes(session.emu._panel_latch or b"")
            if len(frame) == panel.SIZE and len(panel.lit(frame)) > 100:
                break
        require(
            len(frame) == panel.SIZE and len(panel.lit(frame)) > 100,
            "UI did not render",
        )
        panel.write_png(frame, str(out / (name + ".png")))
        (out / (name + ".frame")).write_bytes(frame)
        report["screenshots"].append(
            dict(
                path=name + ".png",
                sha256=sha256(out / (name + ".png")),
                lit_pixels=len(panel.lit(frame)),
                framebuffer_sha256=hashlib.sha256(frame).hexdigest(),
            )
        )
        print("CAPTURE", name, flush=True)

    def select(track):
        session.chord("TRK", f"TRIG {track}")

    def machine(index):
        session.chord("FUNC", "SRC")
        # The stock chooser remembers its cursor across tracks. Home the
        # bounded list before selecting a machine; do not assume it opens on
        # the newly selected track's current engine.
        for _ in range(7):
            session.tap("UP")
        for _ in range(index):
            session.tap("DOWN")
        capture(f"machine-choice-{index}")
        session.tap("YES")
        session.advance(8_000_000)

    session.record()
    capture("01-recorded-trim")
    session.accept()
    node1 = fw.u32(loc["state"])
    original1 = fw.read(fw.u32(node1 + 20), fw.u32(node1 + 12))
    slot1 = session.flex.current["slot"]
    kit = fw.u32(0x80004704)
    machine(2)
    require(fw.read(kit + 0xD6, 1) == b"\x02", "Panel did not select STRETCH")
    require(
        int.from_bytes(fw.read(kit + 0x80, 2), "big") == slot1,
        "Machine change lost sample",
    )
    capture("02-track1-stretch")

    select(2)
    session.tap("SAMPLING")
    capture("03-other-track-recorder")
    session.tap("YES")
    require(session.flex.phase == "recording", "Other track could not record")
    session.advance(8_000_000)
    session.tap("YES")
    session.accept()
    require(session.flex.current["track"] == 1, "USE followed a stale remembered track")
    node2 = fw.u32(loc["state"])
    require(
        node2 != node1 and fw.u32(node1 + 28) == 0,
        "Other recording replaced first take",
    )
    machine(4)
    # Display row 4 is SLICE, whose stable machine identity is 6 (GRID is 4).
    require(fw.read(kit + 0x450 + 0xD6, 1) == b"\x06", "Panel did not select SLICE")
    capture("04-track2-slice")
    report["checks"]["other_track_can_record_and_use_follows_selected_track"] = True

    select(1)
    track_before = fw.read(kit, 16 * 0x450)
    session.tap("SAMPLING")
    capture("05-return-to-track1-save")
    requests = len(session.flex.input.requests)
    session.tap("RECORD")
    session.turn("H", 1)
    capture("06-recording-still-blocked")
    require(
        fw.u32(node1 + 28) == 0 and len(session.flex.input.requests) == requests,
        "Blocked recorder action altered accepted take",
    )
    session.tap("YES")
    wait_for(lambda: views["name"], "Filename editor did not open")
    capture("07-name-dialog")
    require(
        not any(e["event"] == "name-confirmed" for e in report["events"]),
        "Opening gesture auto-confirmed filename",
    )
    writes = len(card.writes)
    session.tap("NO")
    wait_for(lambda: not views["name"], "Filename cancel did not close editor")
    capture("08-cancel-keeps-save-screen")
    require(
        fw.u32(node1 + 28) == 0 and len(card.writes) == writes,
        "Cancel saved or lost the recording",
    )
    report["checks"]["cancel_has_no_write_and_no_automatic_confirmation"] = True

    session.tap("YES")
    wait_for(lambda: views["name"], "Retry filename editor did not open")
    fault[0] = True
    session.tap("YES")
    wait_for(lambda: fw.u32(loc["bank_state"] + 24) == 1 and not views["name"], "Bank chooser did not open")
    session.tap("YES")
    wait_for(
        lambda: not fault[0] and not views["name"] and views["message"],
        "Injected save failure did not finish",
    )
    capture("09-save-failure")
    require(not fault[0] and fw.u32(node1 + 28) == 0, "Failed save unlocked take")
    require(
        fw.read(fw.u32(node1 + 20), len(original1)) == original1,
        "Failed save changed audio",
    )
    session.tap("NO")
    wait_for(lambda: not views["message"], "Failure dialog did not close")
    session.tap("NO")
    capture("10-failure-keeps-save-screen")
    report["checks"]["write_failure_preserves_take_and_guard"] = True

    session.tap("YES")
    wait_for(lambda: views["name"], "Final filename editor did not open")
    session.tap("UP")
    capture("11-named-take")
    session.tap("YES")
    wait_for(lambda: fw.u32(loc["bank_state"] + 24) == 1 and not views["name"], "Final bank chooser did not open")
    capture("11b-project-ram-bank")
    session.tap("YES")
    for _ in range(24):
        session.advance(8_000_000)
        if fw.u32(node1 + 28) == 1:
            break
    require(fw.u32(node1 + 28) == 1, "Save did not complete")
    wait_for(
        lambda: not views["name"] and views["message"], "Save confirmation did not open"
    )
    capture("12-saved-to-plusdrive")
    require(
        fw.read(kit, len(track_before)) == track_before,
        "Save changed playback controls",
    )
    require(fw.u32(node2 + 28) == 0, "Saving T1 also saved unrelated T2")
    durable = fw.read(node1 + 32, 16)
    require(fw.u32(node1 + 20) == 0, "Saved source not retired normally")
    report["checks"]["successful_save_preserves_machines_and_other_take"] = True
    session.tap("NO")
    wait_for(lambda: not views["message"], "Save confirmation did not close")
    session.tap("NO")
    select(2)
    session.tap("SAMPLING")
    capture("13-track2-still-unsaved")
    session.tap("NO")
    select(1)
    session.tap("SAMPLING")
    capture("14-track1-recorder-unlocked")
    session.tap("YES")
    require(
        session.flex.phase == "recording", "Successful save did not unlock recorder"
    )
    session.advance(8_000_000)
    session.tap("YES")
    session.accept()
    require(
        session.flex.current["track"] == 0 and fw.read(kit + 0xD6, 1) == b"\x02",
        "New recording failed on STRETCH or changed machine",
    )
    report["checks"]["new_recording_and_use_on_stretch_after_save"] = True

    reload = check.Firmware(session.inputs["card"], args.snapshot, STOCK_MAIN)
    try:
        reload.card.overlay = dict(card.overlay)
        reload.call(0x40154358, [])
        check.check_mount(reload, durable)
        path = reload.alloc(bytes(256))
        pointer = reload.call(
            check.PATH_OF_ID, [int.from_bytes(durable[:4], "big"), 0, path]
        )
        require(pointer, "Stock path lookup failed")
        report["saved_path"] = reload.read(pointer, 256).split(b"\0")[0].decode()
        require(report["saved_path"] == "/recorded/GLEX", "Incorrect filename")
        loaded = check.check_load(reload, durable, 300)
        require(
            loaded["load_d0"] == 0 and all(check.sent_pcm_matches(loaded, original1)),
            "Independent stock reload changed PCM",
        )
    finally:
        reload.close()
    report["checks"]["independent_stock_reload_exact_pcm"] = True
    report.update(
        status="passed",
        cpu_sha256=hashlib.sha256(session.flex.image).hexdigest(),
        source_unchanged=source_hashes() == provenance["source_hashes"],
        sector_writes=len(card.writes),
        first_track=1,
        second_track=2,
        fault_pages=len(session.emu._faulted_pages),
    )
    require(report["source_unchanged"], "Source drift during UI validation")
    cards = "".join(
        '<figure><img src="'
        + html.escape(row["path"])
        + '" alt="'
        + html.escape(Path(row["path"]).stem.replace("-", " "))
        + '"><figcaption>'
        + html.escape(Path(row["path"]).stem.replace("-", " "))
        + "</figcaption></figure>"
        for row in report["screenshots"]
    )
    (out / "flow.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Flex save flow</title>'
        "<style>body{background:#16191c;color:#f3f4f5;font:16px system-ui;max-width:1100px;"
        "margin:40px auto;padding:0 24px}main{display:grid;grid-template-columns:repeat(auto-fit,"
        "minmax(340px,1fr));gap:24px}figure{margin:0}img{width:100%;image-rendering:pixelated;"
        "border:1px solid #50565c}figcaption{padding:8px 0;color:#c9d0d7}</style>"
        "<h1>Flex: save before recording again</h1><p>Actual OS 1.16 firmware UI in the "
        "emulator. Recorder audio and storage hardware are modeled. Screenshots preserve "
        "the guest framebuffer pixels.</p><main>" + cards + "</main></html>"
    )
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    if session is not None:
        report["pc"] = hex(session.emu._uc.reg_read(k.UC_M68K_REG_PC))
        report["emulator_error"] = session.emu.error
        session.screenshot("failure-screen")
        report["machines"] = [
            session.flex.fw.read(session.flex.fw.u32(0x80004704) + i * 0x450 + 0xD6, 1)[
                0
            ]
            for i in range(16)
        ]
    raise
finally:
    if session is not None:
        session.close()
    if card is not None:
        card.close()
    write_json(out / "report.json", report)
print(out / "report.json", flush=True)
