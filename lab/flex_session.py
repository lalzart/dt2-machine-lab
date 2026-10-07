"""Prepared stock GUI session shared by the Flex Lite check and window."""

import json
import os
import struct
import time
from pathlib import Path

from lab.project import ROOT, require, sha256
from lab.runtime import REPO, STOCK_MAIN

EXPECTED = {
    "snapshot": "3852f53c7e45c358702ed9cefb8bb3ef2af194f4f501e70b6cfbcba333494867",
    "card": "f0a30d418c256ad2d8a87c395a36ffbce2fb8ad0119d755927b442f77df28cea",
    "main": "57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d",
    "lp0": "3a71cae37303d089fe68c44679d664b26237788e4eb21d932ec13f9a7716eaa8",
}


def stock_inputs():
    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    original = Path(inputs["sections"]).parents[2]
    inputs["snapshot"] = str(
        original / "snapshots/dt2-1.16-auto/be080a1acd14/ready.snap"
    )
    inputs["main"] = str(STOCK_MAIN)
    inputs["lp0"] = str(Path(inputs["snapshot"]).with_name("flexbus.raw"))
    for key, digest in EXPECTED.items():
        require(sha256(inputs[key]) == digest, f"Unknown stock {key}")
    require(Path(inputs["lp0"]).is_file(), "Missing matching sample feed")
    return inputs


class Session:
    def __init__(self, source, output, *, enabled=True, adapter_factory=None):
        from emu import gui

        from lab.flex_ui import FlexUI
        from lab.pattern_clock import Recorder, install

        self.gui = gui
        self.inputs = stock_inputs()
        self.output = Path(output)
        os.environ.update(
            DT2_DEVICES=str(REPO / "devices"),
            DT2_SYX=self.inputs["syx"],
            DT2_SECTIONS=self.inputs["sections"],
            DT2_MAIN_IMG=self.inputs["main"],
        )
        self.recorder = Recorder()
        self.recorder.recording = False
        self.runtime = install(gui, self.recorder)
        self.flex = (adapter_factory or FlexUI)(
            gui,
            self.runtime,
            source,
            self.inputs["card"],
            STOCK_MAIN.read_bytes(),
            enabled=enabled,
        )
        self.emu = gui.Emulator(
            self.inputs["snapshot"],
            syx=self.inputs["syx"],
            card_image=self.inputs["card"],
            live=self.recorder,
            fast=False,
            realtime=False,
            panel_dwell=4,
        )
        self.runtime["worker"] = self.emu
        self.emu.pause.set()
        self.emu.start()
        deadline = time.monotonic() + 120
        while not self.emu.ready.wait(0.1):
            require(self.emu.is_alive(), "CPU initialization worker exited")
            require(time.monotonic() < deadline, "CPU initialization timeout")
        deadline = time.monotonic() + 30
        while self.emu.stats["status"] != "paused":
            require(
                not self.emu.error and time.monotonic() < deadline,
                f"CPU failed: {self.emu.error}",
            )
            time.sleep(0.01)
        # The stock checkpoint predates live audio. Match Live FrameForcer's
        # explicit gate setup, while SSI supplies the normal frame cadence.
        from emu.livesharc import frame_profile

        gate = frame_profile(self.inputs["main"])["gate"]
        self.frame_gate_before = bytes(self.emu._uc.mem_read(gate, 4)).hex()
        self.emu._uc.mem_write(gate, bytes(4))
        self.advance()
        # Let the stock 1500-frame startup delay expire in original code.
        # A ready panel alone does not prove that DSPI2 is exchanging frames.
        for _ in range(12):
            if self.emu.live_peer.frames:
                break
            self.advance(20_000_000)
        require(self.emu.live_peer.frames > 0, "No CPU control frames after warmup")

    def advance(self, count=4_000_000):
        target = self.emu.stats["instrs"] + count + self.gui.BUDGET
        self.runtime["pause_after"] = target
        self.emu.pause.clear()
        deadline = time.monotonic() + 120
        while self.emu.stats["status"] != "paused" or self.emu.stats["instrs"] < target:
            require(
                not self.emu.error and self.emu.is_alive(),
                f"CPU failed: {self.emu.error}",
            )
            require(time.monotonic() < deadline, "Panel advance exceeded 120 seconds")
            time.sleep(0.005)
        require(not self.emu._faulted_pages, "Unexpected CPU fault pages")

    def button(self, name, kind):
        code = next(
            k for k, v in self.emu.button_names.items() if v.upper() == name.upper()
        )
        self.emu.inbox.append((kind, code, None))
        self.advance()

    def tap(self, name):
        self.button(name, "press")
        self.button(name, "release")

    def chord(self, modifier, name):
        self.button(modifier, "press")
        self.tap(name)
        self.button(modifier, "release")

    def turn(self, name, delta):
        code = next(
            k for k, v in self.emu.encoder_names.items() if v == f"ENCODER {name}"
        )
        self.emu.inbox.append(("encoder", code, delta))
        self.advance()

    def screenshot(self, name):
        from emu import panel

        require(self.emu._panel_latch is not None, "No rendered panel")
        panel.write_png(self.emu._panel_latch, str(self.output / f"{name}.png"))

    def record(self):
        self.tap("SAMPLING")
        self.tap("YES")
        require(self.flex.phase == "recording", "YES did not start recording")
        self.advance(8_000_000)
        self.tap("YES")
        require(self.flex.phase == "trim", "YES did not finish recording")

    def accept(self):
        self.tap("YES")
        self.advance()
        require(self.flex.phase == "assigned", f"USE failed: {self.flex.error}")

    def capture_pad(self, name):
        require(self.flex.current is not None, "No accepted take")
        track = self.flex.current["track"]
        self.recorder.frames.clear()
        self.recorder.ticks.clear()
        self.recorder.recording = True
        self.tap(f"TRIG {track + 1}")
        # Bounded audition: enough for short takes; at most one second for
        # longer takes. Controls (pitch/loops/envelopes) can extend playback.
        desired_frames = min(1500, max(332, self.flex.current["frames"] // 32 + 150))
        while len(self.recorder.frames) < desired_frames:
            self.advance(4_000_000)
        self.recorder.recording = False
        frames = list(self.recorder.frames)
        events = [
            i
            for i, f in enumerate(frames)
            if int.from_bytes(f[0x22:0x24], "big") & (1 << track)
        ]
        require(len(events) == 1, f"Expected one pad trigger, got {events}")
        slot_offset = 0xE0 + track * 0x60
        require(
            int.from_bytes(frames[events[0]][slot_offset : slot_offset + 2], "big")
            == self.flex.current["slot"],
            "Accepted slot did not reach pad frame",
        )
        path = self.output / f"{name}.dtfr"
        path.write_bytes(
            b"DTFR"
            + struct.pack("<II", 1, len(frames))
            + b"".join(struct.pack("<I", len(f)) + f for f in frames)
        )
        return {
            "path": str(path),
            "frames": len(frames),
            "trigger": events[0],
            "slot": self.flex.current["slot"],
            "track": track,
            "seconds": len(frames) / 1500,
            "preview_bound_seconds": 1,
        }

    def dump_pages(self):
        path = self.output / "accepted-pages.bin"
        path.write_bytes(
            b"".join(
                struct.pack(">II", tag, header) + data
                for tag, data, header in self.flex.pages
            )
        )
        return path

    def close(self):
        self.emu.stop_flag.set()
        self.emu.pause.clear()
        self.emu.join(30)
        if self.flex.fw:
            self.flex.fw.close()
