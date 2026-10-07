#!/usr/bin/env python3
# ruff: noqa: E402
"""Exercise native Flex through original panel dispatch and OS job scheduling."""

import argparse
import math
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument(
    "--mono-right",
    action="store_true",
    help="Seed MONO R in the prepared project before exercising native UI USE",
)
args = parser.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_A0

from lab.flex_native import MAX_FRAMES, USE_ERRORS
from lab.flex_native_input import NativeFlexInput
from lab.flex_recorder import Take
from lab.flex_session import Session


def source(frequency):
    values = [
        round(9000 * math.sin(2 * math.pi * f * i / 48000))
        for i in range(12000)
        for f in ((frequency,) if args.mono_right else (frequency, frequency * 1.37))
    ]
    return Take(struct.pack(">" + "h" * len(values), *values), not args.mono_right)


report = dict(status="running", scope=__doc__, hardware=False, checks={})
report["sources"] = {
    p: sha256(ROOT / p)
    for p in (
        "lab/flex_native.py",
        "lab/flex_native_save.py",
        "lab/flex_native_build.py",
        "scripts/check-flex-native-ui.py",
    )
}
session = None
try:
    session = Session(source(440), out, adapter_factory=NativeFlexInput)
    flex, fw = session.flex, session.flex.fw
    write_json(out / "native-patches.json", flex.metadata)
    (out / "FLEX_MAIN_OS.bin").write_bytes(flex.image)
    session.screenshot("ready")
    state = flex.metadata["locations"]["state"]
    kit = fw.u32(0x80004704)
    report["initial_track_machine"] = fw.read(kit + 0xD6, 1)[0]
    require(report["initial_track_machine"] == 0, "Prepared track 1 is not ONESHOT")
    if args.mono_right:
        # Fixture setup only: observe the stock ProjectSettings getter to find
        # its data, then seed enum 2 (MONO R). Encoder changes do not land in
        # this prepared recorder snapshot. Remove this hook before recording;
        # every later getter, bool conversion and queued USE executes natively.
        channel_addresses = []

        def seed_channel(uc, *_):
            if not channel_addresses:
                address = uc.reg_read(UC_M68K_REG_A0) + 0x1BE
                require(fw.u32(address) == 0, "Unexpected initial channel fixture")
                fw.write(address, struct.pack(">I", 2))
                channel_addresses.append(address)

        hook = fw.uc.hook_add(
            UC_HOOK_CODE, seed_channel, begin=0x4004CCC6, end=0x4004CCC6
        )
        try:
            session.tap("SAMPLING")
        finally:
            fw.uc.hook_del(hook)
        require(len(channel_addresses) == 1, "ProjectSettings getter was not reached")
        report["channel_fixture"] = dict(
            address=channel_addresses[0],
            enum=2,
            setup="ProjectSettings seeded before recording; not encoder input",
        )
        session.screenshot("recorder-mono-right")
        session.tap("NO")
    session.record()
    session.screenshot("trim")
    before = fw.read(kit, 16 * 0x450)
    # Fault fixture: the completed trim exceeds the advertised twenty-second bound.
    # Guest code must show the specific error, retain the old assignment, and
    # allow a valid retry after dismissing the message.
    end = fw.read(flex.view + 0x9A4, 4)
    fw.write(flex.view + 0x9A4, struct.pack(">I", MAX_FRAMES + 1))
    session.tap("YES")
    session.advance(16000000)
    require(
        fw.u32(state + 48) == list(USE_ERRORS).index("long"),
        "Oversized take did not report its native reason",
    )
    require(
        fw.u32(state + 4) == 0 and fw.read(kit, len(before)) == before,
        "Rejected take changed the accepted sample",
    )
    session.screenshot("over-limit-error")
    session.tap("NO")
    fw.write(flex.view + 0x9A4, end)
    report["checks"]["oversize_error_and_retry"] = True
    session.tap("YES")
    for _ in range(12):
        if flex.phase == "assigned":
            break
        session.advance(8000000)
    session.advance(8000000)
    session.screenshot("after-use")
    report["after_use"] = dict(
        phase=flex.phase,
        state=list(struct.unpack(">12I", fw.read(state, 48))),
        requests=flex.input.requests,
        events=flex.events,
    )
    require(flex.phase == "assigned", "Native queued USE did not complete")
    expected = bytearray(before)
    struct.pack_into(
        ">H", expected, flex.current["track"] * 0x450 + 0x80, flex.current["slot"]
    )
    require(fw.read(kit, len(before)) == expected, "Native USE changed other controls")
    report["checks"]["native_use_preserves_controls"] = True
    require(
        flex.current["stereo"] == (not args.mono_right),
        "Panel channel setting did not reach the native sample",
    )
    report["channel"] = "mono-right" if args.mono_right else "stereo"
    report["pad"] = session.capture_pad("native-pad")
    session.record()
    session.chord("FUNC", "NO")
    require(
        fw.read(kit, len(expected)) == expected and fw.u32(state + 4) == 1,
        "Discard changed accepted sample",
    )
    session.tap("SRC")
    report["checks"]["discard_preserves_assignment"] = True
    flex.input.source = source(659)
    session.record()
    session.tap("YES")
    for _ in range(12):
        if flex.phase == "assigned":
            break
        session.advance(8000000)
    require(
        flex.phase == "assigned" and fw.u32(state + 4) == 2,
        "Native replacement did not complete",
    )
    session.screenshot("replacement")
    report["checks"]["native_replacement"] = True
    report["events"] = flex.events
    report["status"] = "passed"
except Exception as error:
    report["status"] = "failed"
    report["error"] = str(error)
    if session is not None:
        report["events"] = session.flex.events
        report["emulator_error"] = session.emu.error
    raise
finally:
    if session is not None:
        session.close()
    write_json(out / "report.json", report)
print(out / "report.json")
