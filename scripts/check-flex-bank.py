#!/usr/bin/env python3
"""Native Flex name/bank/save UI and independent stock PCM reload, OS 1.16.

Only recorder and storage/DSP peripherals are modeled. Screenshots are original
guest framebuffers; no physical sound, recording or timing claim is made.
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--package", type=Path)
args = parser.parse_args()
provenance = doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown stock reload snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.runtime import STOCK_MAIN
from lab.flex_native_input import NativeFlexInput
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab import flex_bank as bank
import plusdrive_check as check
from emu import panel
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

report = dict(
    status="running",
    scope=__doc__,
    hardware=False,
    package=str(args.package),
    source_hashes=provenance["source_hashes"],
    checks={},
    screenshots=[],
    events=[],
)
session = card = None
try:
    pcm = struct.pack(
        ">24000h", *[round(9000 * math.sin(i / 12)) for i in range(24000)]
    )
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
    views = {"name": 0, "message": 0}

    def peer(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == 0x40158626:
            if not fault[0]:
                return
            path = fw.read(fw.u32(sp + 4), 80).split(b"\0")[0]
            require(path.startswith(b"/recorded/"), "Unexpected fault-injection target")
            fault[0] = False
            result = 1
            report["events"].append(
                dict(event="injected-file-open-failure", path=path.decode())
            )
        else:
            sector, length, pointer = struct.unpack(">3I", fw.read(sp + 4, 12))
            require(0 <= sector < 0x760000 and 0 < length <= 0x10000, "Sector bounds")
            if pc == check.EMMC_READ:
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
        if pc == loc["save_message"]:
            report["events"].append(
                dict(
                    event="message",
                    text=fw.read(fw.u32(sp + 4), 80).split(b"\0")[0].decode(),
                )
            )
            return
        view = fw.u32(sp + 4)
        if pc == 0x4011B0D2:
            kind = {0x4021D0F4: "name", 0x4021D410: "message"}.get(fw.u32(view))
            if kind:
                views[kind] = view
        else:
            for kind, active in views.items():
                if active == view:
                    views[kind] = 0

    for pc in (loc["save_message"], 0x4011B0D2, 0x4011AEEA):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def wait_for(test, message):
        for _ in range(30):
            if test():
                return
            session.advance(8_000_000)
        require(test(), message)

    def capture(name):
        # Wait for complete latched guest frames. Preserve the raw pixels too.
        candidates = []
        for _ in range(12):
            session.advance(4_000_000)
            frame = bytes(session.emu._panel_latch or b"")
            if len(frame) == panel.SIZE and len(panel.lit(frame)) > 100:
                candidates.append(frame)
        # The emulator can latch a partially redrawn page. On the black bank
        # page select the complete raw frame with all its labels, never combine
        # pixels from different frames. Other screens retain the last frame.
        if fw.u32(loc["bank_state"] + bank.PHASE) == 1 and not views["message"]:
            frame = max(candidates, key=lambda value: len(panel.lit(value)))
        else:
            frame = candidates[-1] if candidates else b""
        require(
            len(frame) == panel.SIZE and len(panel.lit(frame)) > 100, "No panel frame"
        )
        panel.write_png(frame, str(out / (name + ".png")))
        (out / (name + ".frame")).write_bytes(frame)
        report["screenshots"].append(
            dict(
                path=name + ".png",
                sha256=sha256(out / (name + ".png")),
                framebuffer_sha256=hashlib.sha256(frame).hexdigest(),
            )
        )
        print("CAPTURE", name, flush=True)

    def select(track):
        session.chord("TRK", f"TRIG {track}")

    def name_and_bank():
        session.tap("YES")
        wait_for(lambda: views["name"], "Name editor did not open")
        session.tap("YES")
        wait_for(
            lambda: not views["name"] and fw.u32(loc["bank_state"] + bank.PHASE) == 1,
            "Bank page did not open",
        )

    # Control take on T1; the edited take is on T9 and changes to STRETCH.
    session.record()
    session.accept()
    other = fw.u32(loc["state"])
    other_pcm = fw.read(fw.u32(other + 20), fw.u32(other + 12))
    select(9)
    session.record()
    session.accept()
    node, old = fw.u32(loc["state"]), session.flex.current["slot"]
    source = fw.u32(node + 20)
    original = fw.read(source, fw.u32(node + 12))
    kit = fw.u32(bank.LIVE_KIT)
    session.chord("FUNC", "SRC")
    for _ in range(7):
        session.tap("UP")
    for _ in range(2):
        session.tap("DOWN")
    session.tap("YES")
    session.advance(8_000_000)
    require(fw.read(kit + 8 * 0x450 + 0xD6, 1) == b"\x02", "STRETCH not selected")
    # Shared-use fixture: only the selected T9 should change its numeric slot.
    fw.write(kit + 2 * 0x450 + 0x80, old.to_bytes(2, "big"))
    before = fw.read(kit, 16 * 0x450)
    session.tap("SAMPLING")
    capture("01-flex-save-menu")
    writes = len(card.writes)
    session.tap("YES")
    wait_for(lambda: views["name"], "Name editor missing")
    capture("02-name-sample")
    session.tap("NO")
    wait_for(lambda: not views["name"], "Name cancel failed")
    require(
        len(card.writes) == writes and fw.u32(node + 28) == 0,
        "Name cancel wrote/lost take",
    )
    name_and_bank()
    require(
        fw.u32(loc["bank_state"] + bank.BANK) == old >> 7,
        "Did not default to current bank",
    )
    capture("03-current-bank-default")
    session.tap("RIGHT")
    session.tap("NO")
    require(fw.u32(loc["bank_state"] + bank.PHASE) == 0, "Bank cancel did not return")
    require(
        len(card.writes) == writes
        and fw.read(kit, len(before)) == before
        and fw.read(source, len(original)) == original,
        "Bank cancel changed audio or controls",
    )
    report["checks"]["name_and_bank_cancel_have_no_write"] = True
    # Navigating away clears the pending choice, including a shared take alias.
    name_and_bank()
    select(3)
    select(9)
    require(
        fw.u32(loc["bank_state"] + bank.PHASE) == 0, "Track navigation retained dialog"
    )
    name_and_bank()
    # Full-bank fixture uses recognizable occupied refs, never real overwrites.
    pool = fw.u32(loc["bank_state"] + bank.POOL)
    saved_h = fw.read(pool + 897 * 16, 127 * 16)
    ref_other = fw.read(other + 4, 16)
    fw.write(pool + 897 * 16, ref_other * 127)
    for _ in range((old >> 7) + 1):
        session.tap("LEFT")
    require(fw.u32(loc["bank_state"] + bank.BANK) == 7, "LEFT did not select H")
    capture("04-full-bank-h")
    session.tap("YES")
    wait_for(lambda: views["message"], "Full-bank result missing")
    require(
        len(card.writes) == writes and fw.u32(node + 28) == 0,
        "Full bank wrote/lost take",
    )
    capture("05-full-bank-preserves-take")
    session.tap("NO")
    wait_for(lambda: not views["message"], "Full-bank message did not close")
    fw.write(pool + 897 * 16, saved_h)
    # H -> A -> B -> C -> D.
    for _ in range(4):
        session.tap("RIGHT")
    require(fw.u32(loc["bank_state"] + bank.BANK) == 3, "RIGHT did not select D")
    capture("06-select-bank-d")
    fault[0] = True
    session.tap("YES")
    wait_for(lambda: not fault[0] and views["message"], "Injected write error missing")
    require(
        fw.u32(node + 28) == 0
        and fw.read(kit, len(before)) == before
        and fw.read(source, len(original)) == original,
        "Write failure changed take",
    )
    require(
        fw.u32(pool + 385 * 16) == 0xFFFFFFFF
        and fw.u32(bank.LOADED + 385 * 16) == 0xFFFFFFFF,
        "Failed candidate was not unloaded",
    )
    capture("07-write-failure-keeps-take")
    session.tap("NO")
    wait_for(lambda: not views["message"], "Write-error message did not close")
    capture("08-retry-bank-d")
    session.tap("YES")
    wait_for(
        lambda: fw.u32(node + 28) == 1 and views["message"], "Save did not complete"
    )
    capture("09-saved-to-d001")
    new = int.from_bytes(fw.read(kit + 8 * 0x450 + 0x80, 2), "big")
    require(new == 385, "Wrong destination slot")
    expected = bytearray(before)
    expected[8 * 0x450 + 0x80 : 8 * 0x450 + 0x82] = new.to_bytes(2, "big")
    require(fw.read(kit, len(expected)) == expected, "Unrelated controls changed")
    durable = fw.read(node + 32, 16)
    for slot in (old, new):
        require(
            fw.read(pool + slot * 16, 16) == durable,
            "Old/new alias lost durable reference",
        )
    require(
        fw.u32(node + 20) == 0
        and fw.u32(other + 28) == 0
        and fw.read(fw.u32(other + 20), len(other_pcm)) == other_pcm,
        "Source retirement or unrelated take changed",
    )
    report["checks"].update(
        default_current_bank=True,
        full_bank_no_write=True,
        failed_write_rolls_back_candidate=True,
        selected_track_only_moved=True,
        stretch_and_controls_preserved=True,
        old_shared_slot_preserved=True,
        saved_source_retired=True,
    )
    session.tap("NO")
    wait_for(lambda: not views["message"], "Success message did not close")
    capture("10-recorder-unlocked")
    session.tap("YES")
    require(session.flex.phase == "recording", "Recorder not unlocked")
    report["checks"]["record_again_after_save"] = True
    reload = check.Firmware(session.inputs["card"], args.snapshot, STOCK_MAIN)
    try:
        reload.card.overlay = dict(card.overlay)
        reload.call(0x40154358, [])
        check.check_mount(reload, durable)
        path = reload.alloc(bytes(256))
        pointer = reload.call(
            check.PATH_OF_ID, [int.from_bytes(durable[:4], "big"), 0, path]
        )
        saved_path = reload.read(pointer, 256).split(b"\0")[0].decode()
        require(saved_path == "/recorded/FLEX", "Wrong saved filename")
        loaded = check.check_load(reload, durable, new)
        require(
            loaded["load_d0"] == 0 and all(check.sent_pcm_matches(loaded, original)),
            "Independent stock PCM mismatch",
        )
    finally:
        reload.close()
    report["checks"]["independent_stock_reload_exact_pcm"] = True
    report.update(
        status="passed",
        old_slot=old,
        new_slot=new,
        saved_path=saved_path,
        durable_reference=durable.hex(),
        sector_writes=len(card.writes),
        cpu_sha256=hashlib.sha256(session.flex.image).hexdigest(),
        fault_pages=len(session.emu._faulted_pages),
        source_unchanged=source_hashes() == provenance["source_hashes"],
    )
    require(report["source_unchanged"], "Source drift during run")
    figures = "".join(
        '<figure><img src="'
        + html.escape(row["path"])
        + '"><figcaption>'
        + html.escape(Path(row["path"]).stem.replace("-", " "))
        + "</figcaption></figure>"
        for row in report["screenshots"]
    )
    (out / "flow.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Flex RAM bank save</title><style>body{background:#16191c;color:#f3f4f5;font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px}figure{margin:0}img{width:100%;image-rendering:pixelated}figcaption{padding:8px 0}</style><h1>Flex: save to a project RAM bank</h1><p>Actual OS 1.16 guest framebuffer captures. Recorder and storage hardware are modeled.</p><main>'
        + figures
        + "</main></html>"
    )
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    if session:
        report["pc"] = hex(session.emu._uc.reg_read(k.UC_M68K_REG_PC))
        report["emulator_error"] = session.emu.error
        session.screenshot("failure-screen")
    raise
finally:
    if session:
        session.close()
    if card:
        card.close()
    write_json(out / "report.json", report)
print(out / "report.json", flush=True)
