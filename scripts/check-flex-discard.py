#!/usr/bin/env python3
"""Actual OS 1.16 Flex immediate-discard/back/busy flow and native heap reclamation.

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
from lab import runtime  # noqa: F401 -- initializes pinned emulator imports
from lab.flex_native_input import NativeFlexInput
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.flex_heap import inspect_heap
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
    frees = []

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
        if pc == 0x4011E8FC:
            frees.append(fw.u32(sp + 4))
        elif pc in (0x4011B0D2, 0x4011AEEA):
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

    for pc in (
        loc["save_callback"],
        loc["save_message"],
        0x4011B0D2,
        0x4011AEEA,
        0x4011E8FC,
    ):
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

    # Existing take on T1 is the unrelated-audio control.
    session.record()
    session.accept()
    node1 = fw.u32(loc["state"])
    source1 = fw.read(fw.u32(node1 + 20), fw.u32(node1 + 12))
    select(9)
    session.record()
    session.accept()
    node9 = fw.u32(loc["state"])
    slot9 = session.flex.current["slot"]
    source9 = fw.u32(node9 + 20)
    pcm9 = fw.read(source9, fw.u32(node9 + 12))
    count_before = fw.u32(loc["state"] + 4)
    kit = fw.u32(0x80004704)
    # Fixture setup for a shared assignment. The UI and deletion execute natively.
    fw.write(kit + 2 * 0x450 + 0x80, slot9.to_bytes(2, "big"))
    controls = fw.read(kit, 16 * 0x450)
    heap_before = inspect_heap(fw.read).report()
    session.tap("SAMPLING")
    capture("01-track9-save-menu")
    pool = fw.u32(loc["screen_state"] + 4)
    session.tap("DOWN")
    capture("02-discard-selected")
    writes = len(card.writes)
    session.tap("NO")
    session.tap("SAMPLING")
    capture("03-back-keeps-take")
    require(
        fw.u32(node9 + 20) == source9 and fw.read(source9, len(pcm9)) == pcm9,
        "Cancel lost take",
    )
    require(
        fw.u32(node9 + 56) == 0 and len(card.writes) == writes, "Cancel mutated take"
    )
    report["checks"]["back_preserves_pcm_and_has_no_write"] = True
    session.tap("DOWN")
    # Inject one outstanding source lease; native busy guard must preserve PCM.
    fw.write(node9 + 48, (1).to_bytes(4, "big"))
    session.tap("YES")
    wait_for(lambda: views["message"], "Busy result did not open")
    capture("04-active-reader-busy")
    require(
        fw.u32(node9 + 20) == source9 and fw.u32(node9 + 56) == 0,
        "Busy reader lost source",
    )
    fw.write(node9 + 48, bytes(4))
    session.tap("NO")
    wait_for(lambda: not views["message"], "Busy dialog did not close")
    capture("05-retry-save-menu")
    session.tap("DOWN")
    session.tap("YES")
    wait_for(
        lambda: fw.u32(node9 + 56) == 1 and views["message"], "Discard did not finish"
    )
    capture("06-discarded-on-first-yes")
    heap_after = inspect_heap(fw.read).report()
    require(fw.u32(node9 + 20) == 0, "CPU source not freed")
    require(
        frees.count(source9) == 1, "Source not freed exactly once by original allocator"
    )
    report["discard_source"] = dict(
        address=hex(source9), native_free_count=frees.count(source9), bytes=len(pcm9)
    )
    require(
        heap_after["free_bytes"] > heap_before["free_bytes"], "Heap did not recover"
    )
    require(fw.u32(loc["state"] + 4) == count_before, "Issued identity recycled")
    require(fw.u32(pool + slot9 * 16) == 0xFFFFFFFF, "Project alias survived")
    require(fw.u32(0x405B1368 + slot9 * 16) == 0xFFFFFFFF, "Loaded alias survived")
    for track in (8, 2):
        require(
            fw.read(kit + track * 0x450 + 0x80, 2) == bytes(2),
            "Shared track not detached",
        )
    expected = bytearray(controls)
    for track in (8, 2):
        expected[track * 0x450 + 0x80 : track * 0x450 + 0x82] = bytes(2)
    require(fw.read(kit, len(expected)) == expected, "Unrelated controls changed")
    require(
        fw.read(fw.u32(node1 + 20), len(source1)) == source1,
        "Unrelated track lost audio",
    )
    require(len(card.writes) == writes, "Discard wrote a file")
    report["checks"]["native_discard_frees_cpu_heap_and_clears_shared_uses"] = True
    report["checks"]["first_yes_discards_without_confirmation"] = True
    report["heap_before"] = heap_before
    report["heap_after"] = heap_after
    report["checks"]["unrelated_take_and_track_controls_preserved"] = True
    session.tap("NO")
    wait_for(lambda: not views["message"], "Discard message did not close")
    capture("07-recorder-restored")
    session.tap("YES")
    require(session.flex.phase == "recording", "Discard did not unlock recorder")
    session.advance(8_000_000)
    session.tap("YES")
    session.accept()
    require(session.flex.current["track"] == 8, "New USE failed on track 9")
    new = fw.u32(loc["state"])
    require(
        new != node9 and fw.u32(new + 4) != fw.u32(node9 + 4), "Take identity reused"
    )
    report["checks"]["record_and_use_again_on_track9"] = True
    session.tap("SAMPLING")
    capture("08-new-take-defaults-to-save")
    # Verify the pre-existing naming/save route still works after discard.
    session.tap("YES")
    wait_for(lambda: views["name"], "Filename editor did not open")
    capture("09-name-editor")
    session.tap("YES")
    wait_for(lambda: fw.u32(loc["bank_state"] + 24) == 1 and not views["name"], "Bank chooser did not open")
    capture("09b-project-ram-bank")
    session.tap("YES")
    wait_for(lambda: fw.u32(new + 28) == 1 and views["message"], "New take save failed")
    capture("10-new-take-saved")
    require(fw.u32(new + 20) == 0, "Saved take source did not retire")
    require(fw.u32(node1 + 28) == 0, "Unrelated take unexpectedly saved")
    report["checks"]["save_still_works_after_discard"] = True
    report.update(
        status="passed",
        cpu_sha256=hashlib.sha256(session.flex.image).hexdigest(),
        source_unchanged=source_hashes() == provenance["source_hashes"],
        sector_writes=len(card.writes),
        first_track=1,
        second_track=9,
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
        "<h1>Flex: save or discard</h1><p>Actual OS 1.16 firmware UI in the "
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
