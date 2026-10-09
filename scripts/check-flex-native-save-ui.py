#!/usr/bin/env python3
# ruff: noqa: E402
"""Exercise explicit native Flex save through panel input and stock file APIs.

Recorder and sector I/O are external peer models. Dialogs, naming, filesystem,
exclusive creation and reference promotion execute as original/native CPU code.
No audio rendering, physical input or hardware save claim.
"""

import argparse
import math
import os
import struct
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--snapshot", type=Path, required=True)
p.add_argument("--managed-sources", action="store_true")
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown reload snapshot",
)
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.runtime import STOCK_MAIN
import plusdrive_check as check
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab.flex_native_input import NativeFlexInput
from lab.flex_recorder import Take
from lab.flex_session import Session
# isort: on

pcm = struct.pack(">24000h", *[round(9000 * math.sin(i / 12)) for i in range(24000)])
report = dict(status="running", scope=__doc__, hardware=False, checks={}, events=[])
report["sources"] = {
    p: sha256(ROOT / p)
    for p in (
        "lab/flex_native.py",
        "lab/flex_native_save.py",
        "lab/flex_native_build.py",
        "scripts/check-flex-native-save-ui.py",
    )
}
session = card = None
try:
    session = Session(
        Take(pcm, True),
        out,
        adapter_factory=partial(NativeFlexInput, managed_sources=args.managed_sources),
    )
    fw, locations = session.flex.fw, session.flex.metadata["locations"]
    card = check.Card(session.inputs["card"])
    card.overlay = dict(session.runtime["events"]["esdhc"].card.overlay)

    def storage_peer(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        sector, length, pointer = struct.unpack(">3I", fw.read(sp + 4, 12))
        require(0 <= sector < 0x760000 and 0 < length <= 0x10000, "Sector I/O bound")
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
        fw.uc.hook_add(UC_HOOK_CODE, storage_peer, begin=pc, end=pc)

    def observe(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == locations["save_callback"]:
            name = fw.read(fw.u32(fw.u32(sp + 8)), 61).split(b"\0")[0].decode()
            report["events"].append(dict(event="name-confirmed", name=name))
        else:
            text = fw.read(fw.u32(sp + 4), 32).split(b"\0")[0].decode()
            report["events"].append(dict(event="message", text=text))

    for key in ("save_callback", "save_message"):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=locations[key], end=locations[key])
    session.tap("SAMPLING")
    session.chord("FUNC", "RECORD")
    session.screenshot("no-flex-sample")
    require(
        report["events"][-1]["text"] == "FLEX: NO FLEX SAMPLE",
        "Missing sample feedback",
    )
    session.tap("NO")
    session.tap("NO")
    session.record()
    session.chord("FUNC", "RECORD")
    session.screenshot("use-take-first")
    require(
        report["events"][-1]["text"] == "FLEX: USE TAKE FIRST",
        "Unaccepted trim was saved",
    )
    session.tap("NO")
    session.accept()
    node = fw.u32(locations["state"])
    expected = fw.read(fw.u32(node + 20), fw.u32(node + 12))
    kit = fw.u32(0x80004704)
    track_before = fw.read(kit, 16 * 0x450)
    session.tap("SAMPLING")
    session.chord("FUNC", "RECORD")
    session.screenshot("name-dialog")
    writes_before = len(card.writes)
    session.tap("NO")
    session.screenshot("cancelled")
    require(
        fw.u32(node + 28) == 0 and len(card.writes) == writes_before,
        "Cancel wrote a sample",
    )
    require(
        not any(e["event"] == "name-confirmed" for e in report["events"]),
        "Cancel invoked writer",
    )
    report["checks"]["cancel_has_no_write"] = True
    session.chord("FUNC", "RECORD")
    session.tap("UP")  # Original filename editor: FLEX -> GLEX.
    session.screenshot("edited-name")
    session.tap("YES")
    for _ in range(20):
        if fw.u32(node + 28) == 1:
            break
        session.advance(8000000)
    require(fw.u32(node + 28) == 1, "Named save did not finish")
    session.advance(8000000)
    session.screenshot("saved")
    require(
        report["events"][-1]
        == dict(
            event="message",
            text=(
                "FLEX SAVED\nRAM 64 B\nTAKES 1/32"
                if args.managed_sources
                else "FLEX: SAMPLE SAVED"
            ),
        ),
        "Missing success feedback",
    )
    require(
        any(e.get("name") == "GLEX" for e in report["events"]),
        "Panel name edit was not saved",
    )
    durable_ref = fw.read(node + 32, 16)
    require(
        fw.read(kit, len(track_before)) == track_before, "Saving changed track controls"
    )
    if args.managed_sources:
        require(
            fw.u32(node + 20) == 0 and fw.u32(node + 48) == 0,
            "Saved source was not retired",
        )
        # The independent stock reload below remains the byte-for-byte oracle.
        report["checks"]["named_save_reclaims_ram_source"] = True
    else:
        require(
            fw.read(fw.u32(node + 20), len(expected)) == expected,
            "Saving changed RAM audio",
        )
    report["checks"]["named_save_preserves_playback_state"] = True
    session.tap("NO")
    session.chord("FUNC", "RECORD")
    session.tap("UP")
    writes_before = len(card.writes)
    session.tap("YES")
    session.advance(16000000)
    session.screenshot("existing-name-error")
    require(
        report["events"][-1] == dict(event="message", text="FLEX: SAVE FAILED"),
        "Existing name accepted",
    )
    require(
        len(card.writes) == writes_before and fw.read(node + 32, 16) == durable_ref,
        "Collision overwrote data",
    )
    report["checks"]["existing_file_preserved"] = True
    session.tap("NO")
    session.tap("NO")
    session.capture_pad("after-save-pad")
    reload = check.Firmware(session.inputs["card"], args.snapshot, STOCK_MAIN)
    try:
        reload.card.overlay = dict(card.overlay)
        reload.call(0x40154358, [])
        check.check_mount(reload, durable_ref)
        path = reload.alloc(bytes(256))
        path_ptr = reload.call(
            check.PATH_OF_ID, [int.from_bytes(durable_ref[:4], "big"), 0, path]
        )
        require(path_ptr != 0, "Stock path lookup failed")
        report["saved_path"] = reload.read(path_ptr, 256).split(b"\0")[0].decode()
        require(report["saved_path"] == "/recorded/GLEX", "Saved name differs")
        loaded = check.check_load(reload, durable_ref, 300)
        require(
            loaded["load_d0"] == 0 and all(check.sent_pcm_matches(loaded, expected)),
            "Stock reload changed PCM",
        )
        report["checks"]["independent_stock_reload_exact_pcm"] = True
    finally:
        reload.close()
    report["sector_writes"] = len(card.writes)
    report["status"] = "passed"
except Exception as error:
    report["status"], report["error"] = "failed", str(error)
    if session is not None:
        report["pc"] = hex(session.emu._uc.reg_read(k.UC_M68K_REG_PC))
        report["emulator_error"] = session.emu.error
    raise
finally:
    if session is not None:
        session.close()
    if card is not None:
        card.close()
    write_json(out / "report.json", report)
print(out / "report.json")
