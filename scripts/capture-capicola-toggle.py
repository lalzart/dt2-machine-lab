#!/usr/bin/env python3
"""Exercise CAPI through native OS1.16 panel, locks and SPI reply replay."""

# ruff: noqa: E402, I001
import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, source_hashes, write_json, sha256

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
p.add_argument("--replies", type=Path)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_session import Session
from lab.flex_recorder import Take
from lab.flex_ui import FlexUI
from lab.runtime import STOCK_MAIN
from lab.capicola_toggle import BASE, TITLES
from emu import livesharc
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

package = a.package.resolve()
image = (package / "PLAITS_R3_FLEX_CAPICOLA_MAIN_OS.bin").read_bytes()
meta = json.loads((package / "manifest.json").read_text())["cpu"]["capi_toggle"]
old = STOCK_MAIN.read_bytes()
feedback = {"response": bytes(0xABC)}


class ReplyPeer(livesharc.LiveFramePeer):
    def exchange(self, tx):
        super().exchange(tx)
        return feedback["response"]


livesharc.LiveFramePeer = ReplyPeer


class Adapter(FlexUI):
    def install(self, original):
        super().install(original)
        # Install before any new SRC widgets are constructed. This is an
        # explicit prepared-stock checkpoint adaptation, not a cold boot claim.
        pos = 0
        while pos < len(old):
            if old[pos] == image[pos]:
                pos += 1
                continue
            start = pos
            while pos < len(old) and old[pos] != image[pos]:
                pos += 1
            require(
                self.fw.read(BASE + start, pos - start) == old[start:pos],
                "Checkpoint image drift",
            )
            self.fw.write(BASE + start, image[start:pos])
        self.fw.write(BASE + len(old), image[len(old) :])
        # A prepared checkpoint already ran reset. Initialize only the newly
        # reserved tail; the separate cold-start check executes the real copy.
        source = meta["source_arena_start"]
        payload = image[source - BASE :]
        live = meta["arena_start"]
        require(
            self.fw.read(live, len(payload)) == bytes(len(payload)), "SRAM tail in use"
        )
        self.fw.write(live, payload)
        self.fw.uc.ctl_remove_cache(BASE, BASE + len(image))
        self.fw.uc.ctl_remove_cache(live, live + len(payload))


report = dict(status="running", hardware_verified=False, stages=[])
sources = source_hashes()
session = None
try:
    session = Session(
        Take(bytes(2048), False), out, enabled=False, adapter_factory=Adapter
    )
    uc = session.emu._uc
    session.recorder.recording = True
    titles = []

    def caption(uc, pc, size, data):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        ptr = int.from_bytes(uc.mem_read(sp + 8, 4), "big")
        ptr = int.from_bytes(uc.mem_read(ptr, 4), "big")
        text = bytes(uc.mem_read(ptr, 18)).decode(errors="replace")
        if text.startswith("STRETCH "):
            titles.append(text)

    hook = uc.hook_add(UC_HOOK_CODE, caption, begin=0x4005B1E0, end=0x4005B1E0)

    def val():
        wire = session.recorder.frames[-1]
        return dict(
            machine=int.from_bytes(wire[0x94:0x96], "big"),
            capi=int.from_bytes(wire[0xDE:0xE0], "big"),
        )

    def stage(name):
        session.screenshot(name)
        report["stages"].append(
            dict(name=name, wire=val(), title=titles[-1] if titles else None)
        )
        print(report["stages"][-1], flush=True)

    session.chord("FUNC", "SRC")
    for _ in range(10):
        session.tap("UP")
    for _ in range(2):
        session.tap("DOWN")
    session.tap("YES")
    session.tap("YES")
    session.tap("TRIG 1")
    session.advance(8_000_000)
    session.tap("AMP")
    session.tap("SRC")
    require(val()["machine"] == 2, "STRETCH selection failed")
    stage("initial-off")
    require(val()["capi"] == 0, "Existing default was not OFF")
    for name, delta, expected in (
        ("capi-on", 8, 256),
        ("capi-off", -8, 0),
        ("capi-on-again", 8, 256),
    ):
        for _ in range(4):
            session.turn("C", delta)
        for _ in range(12):
            session.advance(8_000_000)
            if val()["capi"] == expected:
                break
        ptr = int.from_bytes(uc.mem_read(0x80004704, 4), "big")
        raw = int.from_bytes(uc.mem_read(ptr + 0x48 + 27 * 2, 2), "big")
        require(
            raw == expected and val()["capi"] == expected,
            f"Native encoder/storage/transport {name}: {raw}, {val()}",
        )
        stage(name)
    # Native grid editing, lock store and preview. Base ON, step 5 OFF.
    session.tap("RECORD")
    session.chord("FUNC", "PLAY")
    session.chord("FUNC", "PAGE")
    session.tap("PAGE")
    session.tap("NO")
    for step in (1, 5):
        session.tap(f"TRIG {step}")
    session.tap("SRC")
    session.button("TRIG 5", "press")
    session.advance(30_000_000)
    for _ in range(4):
        session.turn("C", -8)
    session.tap("YES")
    session.button("TRIG 5", "release")

    def preview(step):
        session.button(f"TRIG {step}", "press")
        start = len(session.recorder.frames)
        session.tap("YES")
        session.advance()
        wires = [
            f
            for f in session.recorder.frames[start:]
            if int.from_bytes(f[0x22:0x24], "big") & 1
        ]
        require(len(wires) == 1, "Native preview trigger count")
        value = int.from_bytes(wires[0][0xDE:0xE0], "big")
        session.button(f"TRIG {step}", "release")
        return value

    unlocked, locked = preview(1), preview(5)
    require(unlocked == 256 and locked == 0, f"Native lock recall {unlocked},{locked}")
    report["locks"] = {"base": unlocked, "step5": locked, "preview_native": True}
    stage("locked-off-base-on")
    session.tap("RECORD")
    # Buffered native replies go through the original SPI2 receive driver and
    # its new observer. No direct cache writes establish the UI result.
    if a.replies:
        # Clear the last step preview through a real unlocked pad trigger and
        # restore ON through the panel before checking idle readiness captions.
        session.tap("TRIG 1")
        for _ in range(4):
            session.turn("C", 8)
        session.advance(20_000_000)
        require(val()["capi"] == 256, "Feedback fixture base not ON")
        origin = a.replies.resolve()
        result = json.loads((origin / "report.json").read_text())
        require(result["status"] == "passed", "Native replies not verified")
        payload = (origin / "native-replies.bin").read_bytes()
        rows = json.loads((origin / "native-statuses.json").read_text())
        require(len(payload) == len(rows) * 0xABC, "Reply size mismatch")
        feedback_cases = []
        for state in sorted({r["state"] for r in rows if r["track"] == 0}):
            index = next(
                i for i, r in enumerate(rows) if r["track"] == 0 and r["state"] == state
            )
            feedback["response"] = payload[index * 0xABC : (index + 1) * 0xABC]
            session.advance(20_000_000)
            cache = bytes(uc.mem_read(meta["cache"], 32))
            require(
                cache[0] == state and cache[16] > 0,
                "Original receive path did not deliver status",
            )
            want = TITLES[state]
            require(
                titles and titles[-1] == want,
                f"Actual SRC title {state}: {titles[-3:]}",
            )
            stage("reply-" + str(state))
            feedback_cases.append(dict(state=state, actual=titles[-1]))
        feedback["response"] = bytes(0xABC)
        session.advance(20_000_000)
        require(titles[-1] == TITLES[0], "Malformed/missing feedback title")
        report["feedback_cases"] = feedback_cases
        report["reply_sha256"] = sha256(origin / "native-replies.bin")
    require(not session.emu._faulted_pages and not session.emu.error, "CPU faults")
    for write in meta["writes"]:
        if "runtime_address" in write and not write.get("mutable"):
            expected = bytes.fromhex(write["after"])
            require(
                bytes(uc.mem_read(write["runtime_address"], len(expected))) == expected,
                "Panel changed SRAM payload " + write["label"],
            )
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed",
        sources=sources,
        title_transitions=titles,
        scope="Prepared checkpoint; native panel, control storage, lock preview and buffered SPI2 replies; no full project save/reload or coupled hardware",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    if session:
        frames = session.recorder.frames
        (out / "capi.dtfr").write_bytes(
            b"DTFR"
            + struct.pack("<II", 1, len(frames))
            + b"".join(struct.pack("<I", len(f)) + f for f in frames)
        )
        session.close()
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
