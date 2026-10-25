#!/usr/bin/env python3
"""Native bank placement -> original project save -> independent stock reload.

Prepared fixture with modeled recorder, card and DSP transport. Arp has no
allocated state in this direct-call fixture. All Flex and project operations,
including filesystem work, run as original/emitted ColdFire instructions.
"""

# ruff: noqa: E402
import argparse
import hashlib
import os
import struct
import sys
import wave
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
    "Unknown stock snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.runtime import STOCK_MAIN
from lab.cpu_extension import build_cpu
from lab.cpu_fixture import install, load_package
from lab.arp_storage import read_saved_project
from lab import flex_bank as bank
import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

samples = out / "samples"
samples.mkdir()
with wave.open(str(samples / "fixture.wav"), "wb") as wav:
    wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
    wav.writeframes(bytes(512))
card_path = out / "card.img"
entries = pd.build(str(samples), str(card_path), main_os=STOCK_MAIN.read_bytes())
report = dict(
    status="running",
    scope=__doc__,
    hardware=False,
    package=str(args.package),
    source_hashes=provenance["source_hashes"],
)
fw = reload = None


def kit_data(firmware, project):
    settings_at = firmware.call(check.SETTINGS_GET, [project])
    arg = firmware.call(check.SETTINGS_KIT_ARG, [settings_at])
    kit = project + check.PROJECT_KIT
    return firmware.call(
        firmware.u32(firmware.u32(kit) + check.KIT_DATA_VFUNC), [kit, arg]
    )


try:
    image, meta = (
        load_package(args.package)[:2]
        if args.package
        else build_cpu(STOCK_MAIN.read_bytes(), flex_save_screen=True)
    )
    loc = meta["flex"]["locations"]
    fw = check.Firmware(card_path, args.snapshot, STOCK_MAIN)
    fw.call(0x40154358, [])
    check.check_mount(fw, entries[0]["ref"])
    check.check_project(fw)
    install(fw.write, image, meta, read=fw.read)
    project = fw.call(check.PROJECT_GET, [])
    pool = fw.call(loc["save_pool"], [])
    kit = kit_data(fw, project)
    # Activate the prepared project's live kit; no UI task runs in this fixture.
    fw.write(bank.LIVE_KIT, kit.to_bytes(4, "big"))
    fw.write(kit + 8 * 0x450 + 0xD6, b"\x02")
    old = next(
        slot
        for slot in range(1, 1024)
        if slot % 128
        and fw.u32(pool + slot * 16) == fw.u32(bank.LOADED + slot * 16) == 0xFFFFFFFF
        and fw.u32(bank.LENGTHS + slot * 4) == 0
    )
    new = 385
    require(
        fw.u32(pool + old * 16) == fw.u32(bank.LOADED + old * 16) == 0xFFFFFFFF,
        "Original fixture slot occupied",
    )

    def recorder(uc, _pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        pointer = fw.u32(sp + 8)
        command, mono, first, count = struct.unpack(">HHII", fw.read(pointer, 12))
        require(command == 4 and mono == 0, "Unexpected recorder request")
        pcm = b"".join(
            struct.pack(">HH", i * 17 & 65535, (30000 - i * 29) & 65535)
            for i in range(first, first + count)
        )
        fw.write(0x4FE79340, pcm.ljust(2048, b"\0"))
        uc.reg_write(k.UC_M68K_REG_D0, 0)
        uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
        uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

    hook = fw.uc.hook_add(UC_HOOK_CODE, recorder, begin=0x400124A0, end=0x400124A0)
    node = fw.call(loc["accept"], [loc["state"], 0, 2400, 1, old], limit=200_000_000)
    require(node not in (0, 0xFFFFFFFF), "Native take creation failed")
    original = fw.read(fw.u32(node + 20), fw.u32(node + 12))
    require(fw.call(loc["assign"], [old, 8, kit]) == 0, "Native assignment failed")
    fw.uc.hook_del(hook)
    # Shared T3 uses the old slot. Keeping that slot also avoids rewriting
    # numeric references held by inactive patterns and sample locks.
    fw.write(kit + 2 * 0x450 + 0x80, old.to_bytes(2, "big"))
    before = fw.read(kit, 16 * 0x450)
    fw.write(
        loc["bank_state"],
        struct.pack(">7I", node, pool, kit, 8, old, 3, 1)
        + b"Native bank take\0".ljust(64, b"\0"),
    )
    require(
        fw.call(loc["bank_commit"], [loc["bank_state"]], limit=300_000_000) == new,
        "Native bank commit failed",
    )
    durable = fw.read(node + 32, 16)
    expected = bytearray(before)
    expected[8 * 0x450 + 0x80 : 8 * 0x450 + 0x82] = new.to_bytes(2, "big")
    require(
        fw.read(kit, len(expected)) == expected and fw.u32(node + 20) == 0,
        "Bank assignment/retirement failed",
    )
    require(
        all(fw.read(pool + slot * 16, 16) == durable for slot in (old, new)),
        "Alias identity mismatch",
    )
    # Previously failing missing-reference case must coexist with the bank save.
    missing = struct.pack(">4I", 0x7FFE001F, 0xBAD, 123456, 9876)
    fw.write(pool + 99 * 16, missing)
    callback = fw.alloc(bytes(16))
    require(
        fw.call(0x40043A30, [project, 128, callback], limit=800_000_000) & 255 == 1,
        "Original project writer failed",
    )
    report.update(
        native_bank_save=True,
        original_project_save=True,
        missing_reference_preserved=True,
    )
    reload = check.Firmware(card_path, args.snapshot, STOCK_MAIN)
    reload.card.overlay = dict(fw.card.overlay)
    reload.call(0x40154358, [])
    check.check_mount(reload, durable)
    storage = reload.call(0x4019E41C, [])
    reload.call(0x400F4A62, [storage])
    reload.call(0x4012F01E, [reload.call(0x4019D8FE, []), 128])
    buffer, blob = read_saved_project(reload, 128)
    active = reload.call(check.PROJECT_GET, [])
    require(
        reload.call(0x40043F74, [active, buffer, 0], limit=800_000_000) & 255 == 1,
        "Stock project decoder failed",
    )
    settings_at = reload.call(check.SETTINGS_GET, [active])
    settings_data = reload.call(
        reload.u32(reload.u32(settings_at) + 0x28), [settings_at]
    )
    reloaded_pool = settings_data + 0x1D2
    require(
        all(
            reload.read(reloaded_pool + slot * 16, 16) == durable for slot in (old, new)
        ),
        "Reload lost aliases",
    )
    require(
        reload.read(reloaded_pool + 99 * 16, 16) == missing,
        "Reload altered missing sample",
    )
    recalled_kit = kit_data(reload, active)
    require(
        reload.read(recalled_kit, len(expected)) == expected,
        "Stock reload changed kit controls/slots",
    )
    for slot in (old, new):
        loaded = check.check_load(reload, durable, slot)
        require(
            loaded["load_d0"] == 0
            and loaded["data_pages"] > 0
            and all(check.sent_pcm_matches(loaded, original)),
            "Fresh stock PCM differs",
        )
        reload.call(0x401540C6, [slot])
        reload.call(0x40153BEA, [slot])
    report.update(
        stock_project_reload=True,
        stock_reload_kit_exact=True,
        stock_reload_both_aliases_exact_pcm=True,
        project_sha256=hashlib.sha256(blob).hexdigest(),
    )
    # A fresh descriptor-empty runtime must still save this project normally.
    install(reload.write, image, meta, read=reload.read)
    callback = reload.alloc(bytes(16))
    require(
        reload.call(0x40043A30, [active, 128, callback], limit=800_000_000) & 255 == 1,
        "Fresh runtime project save failed",
    )
    report.update(
        status="passed",
        fresh_runtime_save=True,
        old_slot=old,
        new_slot=new,
        main_sha256=hashlib.sha256(image).hexdigest(),
        durable_reference=durable.hex(),
        source_unchanged=source_hashes() == provenance["source_hashes"],
    )
    require(report["source_unchanged"], "Source drift during native project check")
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    if fw:
        fw.close()
    if reload:
        reload.close()
    write_json(out / "report.json", report)
print(out / "report.json", flush=True)
