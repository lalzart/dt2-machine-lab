#!/usr/bin/env python3
# ruff: noqa: E402
"""Gate A: original recorder save flow, stock or NORMAL candidate, OS 1.16.

Run variants in separate processes with identical fixtures. No host resource,
file open/write, assignment or naming callback replaces the original logic.
Recorder audio and low-level sector I/O remain explicitly modeled peers.
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--stock", action="store_true")
p.add_argument("--mono", action="store_true")
p.add_argument("--explore", action="store_true")
p.add_argument(
    "--prebuffer",
    action="store_true",
    help="Commit BUF 1 first, then verify NORMAL still works",
)
p.add_argument(
    "--native-freeze",
    action="store_true",
    help="Recheck NORMAL with native resource/slot/project thunks installed",
)
p.add_argument(
    "--native-worker",
    action="store_true",
    help="Recheck NORMAL with native queued BUF worker installed",
)
p.add_argument("--queued-freeze", action="store_true")
args = p.parse_args()
provenance = doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.recorder_normal import NormalBufferUI, StockRecorderPeer
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.recorder_overlay import sector_overlay
from lab.runtime import STOCK_MAIN
import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

sources = source_hashes()
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
write_json(out / "sources.json", sources)
report = dict(
    status="running",
    scope=__doc__,
    stock=args.stock,
    mono=args.mono,
    provenance=provenance,
    events=[],
    checks={},
    screenshots=[],
)
session = card = None


def stage(name):
    session.advance()
    session.screenshot(name)
    report["screenshots"].append(name + ".png")


def track_slot():
    return int.from_bytes(fw.read(fw.u32(0x80004704) + 0x80, 2), "big")


try:
    pcm = b"".join(
        struct.pack(">h", (i * (37 + channel * 30)) % 18001 - 9000)
        for i in range(2400)
        for channel in range(1 if args.mono else 2)
    )
    adapter = StockRecorderPeer if args.stock else NormalBufferUI
    if args.native_freeze:
        require(not args.stock, "Native candidate cannot be untouched stock")
        from lab.recorder_freeze_native import NativeFreezeUI

        adapter = NativeFreezeUI
    if args.native_worker:
        require(not args.stock, "Worker candidate cannot be untouched stock")
        from lab.recorder_worker_native import NativeWorkerUI

        adapter = NativeWorkerUI
    if args.queued_freeze:
        require(not args.stock, "Queue candidate cannot be untouched stock")
        from lab.recorder_freeze_worker_native import QueuedFreezeUI

        adapter = QueuedFreezeUI
    session = Session(
        Take(pcm, not args.mono),
        out,
        adapter_factory=adapter,
    )
    fw = session.flex.fw
    card = check.Card(session.inputs["card"])
    # Esdhc.Card stores byte offsets -> byte values; check.Card stores sector
    # numbers -> complete 512-byte blocks. They are not interchangeable maps.
    initial_bytes = session.runtime["events"]["esdhc"].card.overlay
    card.overlay = sector_overlay(initial_bytes, card.read)
    report["initial_overlay_bytes"] = len(initial_bytes)

    def peer(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        sector, length, pointer = struct.unpack(">3I", fw.read(sp + 4, 12))
        require(0 <= sector < 0x760000 and 0 < length <= 0x10000, "Sector bound")
        if pc == check.EMMC_READ:
            card.reads.append((sector, length))
            fw.write(pointer, card.read(sector, length))
        else:
            card.writes.append((sector, length))
            card.write(sector, fw.read(pointer, length))
        uc.reg_write(k.UC_M68K_REG_D0, 0)
        uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
        uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

    for pc in (check.EMMC_READ, check.EMMC_WRITE):
        fw.uc.hook_add(UC_HOOK_CODE, peer, begin=pc, end=pc)
    fault = [False]

    def fail_open(uc, pc, *_):
        if not fault[0]:
            return
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        path = fw.read(fw.u32(sp + 4), 100).split(b"\0")[0]
        require(path.startswith(b"/recorded/"), "Open fault reached unrelated resource")
        fault[0] = False
        report["events"].append(dict(injected_open_failure=path.decode()))
        uc.reg_write(k.UC_M68K_REG_D0, 1)
        uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
        uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

    fw.uc.hook_add(UC_HOOK_CODE, fail_open, begin=0x40158626, end=0x40158626)

    def observe(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        fields = dict(pc=hex(pc), tick=session.flex.tick(), slot=track_slot())
        if pc == 0x40153994:
            path = fw.u32(sp + 4)
            fields.update(
                path=fw.read(path, 100).split(b"\0")[0].decode("ascii", "replace"),
                args=fw.read(sp + 4, 16).hex(),
            )
        report["events"].append(fields)

    for pc in (
        0x40022FBE,
        0x40023026,
        0x40153994,
        0x40154540,
        0x400F0AB8,
        0x4002074E,
        0x4002060C,
        0x4001FC48,
    ):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)
    if args.mono:
        seeded = []

        def seed_channel(uc, *_):
            if not seeded:
                address = uc.reg_read(k.UC_M68K_REG_A0) + 0x1BE
                require(fw.u32(address) == 0, "Unexpected initial CHAN")
                fw.write(address, struct.pack(">I", 2))
                seeded.append(address)

        hook = fw.uc.hook_add(
            UC_HOOK_CODE, seed_channel, begin=0x4004CCC6, end=0x4004CCC6
        )
        try:
            session.tap("SAMPLING")
        finally:
            fw.uc.hook_del(hook)
        session.tap("NO")
        require(seeded, "Mono fixture was not seeded")
        report["mono_fixture"] = (
            "Original settings storage seeded as MONO R before record; same stock and candidate setup"
        )
    settings_data = []

    def observe_monitor(uc, *_):
        if not settings_data:
            settings_data.append(uc.reg_read(k.UC_M68K_REG_A0))

    monitor_hook = fw.uc.hook_add(
        UC_HOOK_CODE, observe_monitor, begin=0x4004CD26, end=0x4004CD26
    )
    session.tap("SAMPLING")
    fw.uc.hook_del(monitor_hook)
    require(settings_data, "Original MON getter was not reached")
    monitor = settings_data[0] + 0x1B6
    monitor_before = fw.u32(monitor)
    for _ in range(6):
        session.turn("E", -127 if monitor_before else 127)
    monitor_after = fw.u32(monitor)
    require(monitor_after != monitor_before, "Original E/MON did not change")
    report["checks"]["monitor"] = [monitor_before, monitor_after]
    stage("00-monitor-on-e")
    session.tap("NO")
    if args.prebuffer:
        require(
            not args.stock and not args.mono, "Prebuffer is a stereo candidate case"
        )
        session.tap("SAMPLING")
        for _ in range(14):
            if session.flex.destination == 1:
                break
            session.turn("C", 5)
        session.tap("SRC")
        session.record()
        session.accept()
        report["buffer_before_normal"] = dict(session.flex.current)
        session.tap("SAMPLING")
        for _ in range(14):
            if session.flex.destination == 0:
                break
            session.turn("C", -5)
        require(session.flex.destination == 0, "C did not return to NORMAL")
        stage("00-return-to-normal")
        session.tap("SRC")
    normal_event_start = len(session.flex.events)
    before = track_slot()
    session.record()
    view = session.flex.view
    for _ in range(12):
        session.turn("E", 5)
        if fw.u32(view + 0x9A0) > 0:
            break
    for _ in range(12):
        session.turn("H", -5)
        if fw.u32(view + 0x9A4) < 2400:
            break
    trim = [fw.u32(view + off) for off in (0x9A0, 0x9A4)]
    require(0 < trim[0] < trim[1] < 2400, "Original trim controls did not move")
    report["trim"] = trim
    report["slot_before"] = before
    require(
        fw.read(0x402296FB, 7) == b"Y:SAVE\0",
        "NORMAL did not preserve stock SAVE label",
    )
    stage("01-original-trim-save")
    session.tap("YES")
    for index in range(8):
        session.advance(8_000_000)
        if index in (0, 7):
            stage(f"02-after-stock-yes-{index}")
    if args.explore:
        for index in range(4):
            session.tap("YES")
            session.advance(8_000_000)
            stage(f"03-following-yes-{index}")
    else:
        # The first YES opens the original filename editor. Cancel, reopen,
        # edit its first character with UP, then SAVE and choose TRIG 1.
        writes_before = len(card.writes)
        session.tap("NO")
        stage("03-name-cancel")
        require(
            track_slot() == before and len(card.writes) == writes_before,
            "Cancel changed sample/file",
        )
        report["checks"]["cancel"] = True
        session.tap("YES")
        session.tap("UP")
        stage("04-edited-stock-name")
        session.tap("YES")
        session.advance(24_000_000)
        stage("05-stock-assignment-prompt")
        session.tap("TRIG 1")
        session.advance(24_000_000)
        stage("06-stock-assigned")
        accepted = track_slot()
        require(accepted != before, "Stock assignment did not select a new sample")
        require(
            session.flex.input.requests and card.writes,
            "Stock save did not read PCM/write storage",
        )
        durable_ref = fw.read(check.LOADER_KEYS + accepted * 16, 16)
        expected = pd.build_native_sample(
            pcm[trim[0] * (2 if args.mono else 4) : trim[1] * (2 if args.mono else 4)],
            not args.mono,
        )
        reload_snapshot = (
            ROOT.parent
            / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
        )
        require(
            sha256(reload_snapshot)
            == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
            "Reload fixture drift",
        )
        reload = check.Firmware(session.inputs["card"], reload_snapshot, STOCK_MAIN)
        try:
            reload.card.overlay = dict(card.overlay)
            reload.call(0x40154358, [])
            check.check_mount(reload, durable_ref)
            loaded = check.check_load(reload, durable_ref, 300)
            require(
                loaded["load_d0"] == 0
                and all(check.sent_pcm_matches(loaded, expected)),
                "Stock reload PCM differs",
            )
            report["checks"]["independent_stock_reload"] = True
            report["saved"] = dict(
                slot=accepted,
                ref=durable_ref.hex(),
                expected_sha256=hashlib.sha256(expected).hexdigest(),
                stereo=loaded["stereo"],
                length=loaded["len"],
            )
        finally:
            reload.close()
        session.tap("SRC")
        session.tap("ENCODER D")
        for _ in range((accepted // 128 - before // 128) % 8):
            session.tap("LEFT")
        for _ in range(abs(accepted % 128 - before % 128)):
            session.tap("UP" if accepted % 128 > before % 128 else "DOWN")
        stage("07-original-selector")
        session.tap("YES")
        require(
            track_slot() == before, "Original selector did not restore previous sample"
        )
        report["checks"]["selector_reassignment"] = True
        # Negative file-open seam only; otherwise original file APIs execute.
        session.tap("SRC")
        session.tap("SAMPLING")
        session.chord("FUNC", "NO")  # Stock keeps the accepted recorder take.
        session.tap("SRC")
        session.record()
        session.tap("YES")
        writes_before = len(card.writes)
        overlay_before = dict(card.overlay)
        fault[0] = True
        session.tap("YES")
        session.advance(24_000_000)
        stage("08-original-file-error")
        require(not fault[0], "Open-failure control did not reach stock writer")
        require(
            track_slot() == before
            and card.overlay == overlay_before
            and len(card.writes) == writes_before,
            "Stock failure changed previous track/storage",
        )
        report["checks"]["file_error_preserves_previous"] = True
    report["slot_after"] = track_slot()
    report["peer_requests"] = session.flex.input.requests
    report["recorder_events"] = session.flex.events
    report["sector_writes"] = len(card.writes)
    report["overlay_sectors"] = len(card.overlay)
    report["phase"] = session.flex.phase
    report["checks"]["not_buffer_use"] = not any(
        e.get("event") in ("use", "buffer-use")
        for e in session.flex.events[normal_event_start:]
    )
    require(report["checks"]["not_buffer_use"], "NORMAL intercepted by buffer USE")
    if not args.stock and not args.prebuffer:
        require(
            not session.flex.setup_done and not session.flex.buffers.generations,
            "NORMAL initialized buffer resources",
        )
    require(sources == source_hashes(), "Source drift during NORMAL test")
    # Exploratory output cannot pass the full parity gate.
    report["status"] = "observed" if args.explore else "passed"
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["recorder_events"] = session.flex.events
        report["emulator_error"] = session.emu.error
        session.screenshot("failure")
    raise
finally:
    if session:
        session.close()
    if card:
        report["overlay"] = {
            str(sector): data.hex() for sector, data in card.overlay.items()
        }
        card.close()
    write_json(out / "report.json", report)
print(out / "report.json", flush=True)
