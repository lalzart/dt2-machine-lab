"""Bounded mapped-key UP experiment; native core and stock CPU note APIs."""
import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--off", action="store_true")
p.add_argument("--stop-held", action="store_true",
               help="Also press Stop during a sounding arp gate, then release its held input")
args = p.parse_args()
require(not (args.off and args.stop_held), "Held-gate Stop check requires UP")
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.runtime import REPO
from lab.pattern_clock import Recorder, install
from lab.arp_ui import ArpUI
from emu import gui, panel

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(sha256(inputs["main"]) == "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830",
        "Unexpected prepared CPU fixture")
main = Path(inputs["main"]).read_bytes()
os.chdir(REPO)
os.environ.update(DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"],
                  DT2_MAIN_IMG=inputs["main"])
gui.BUDGET = 50_000
recorder = Recorder()
clock = install(gui, recorder)
arp = ArpUI(gui, clock, main, enabled=not args.off)
worker = gui.Emulator(inputs["snapshot"], syx=inputs["syx"], card_image=inputs["card"],
                      live=recorder, fast=False, realtime=False, panel_dwell=4)
clock["worker"] = worker
worker.pause.set(); worker.start()
deadline = time.monotonic() + 600
fingerprint = source_hashes()
report = {"status": "running", "condition": "off" if args.off else "up",
          "inputs": inputs, "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
          "source_sha256": fingerprint, "gestures": [], "stages": [],
          "scope": "Native ColdFire core with diagnostic context-call/clock adapter; prepared stock sampler; fixed 102 BPM; no permanent firmware/G control, hardware or DAC claim"}


def advance(n=2_000_000):
    target = worker.stats["instrs"] + n + gui.BUDGET
    require(target <= 600_000_000, "Arp instruction bound exceeded")
    clock["pause_after"] = target; worker.pause.clear()
    while worker.stats["status"] != "paused" or worker.stats["instrs"] < target:
        require(not worker.error and worker.is_alive(), f"CPU stopped: {worker.error}")
        require(time.monotonic() < deadline, "Arp wall-time bound exceeded")
        time.sleep(0.005)


def button(name, kind):
    matches = [k for k, v in worker.button_names.items() if v == name]
    require(len(matches) == 1, f"Unknown panel control {name}")
    report["gestures"].append([worker.stats["instrs"], kind, name])
    worker.inbox.append((kind, matches[0], None)); advance()


def tap(name):
    button(name, "press"); button(name, "release")


def chord(mod, name):
    button(mod, "press"); tap(name); button(mod, "release")


def stage(name):
    report["stages"].append({"name": name, "frame": len(recorder.frames),
                             "tick": arp.tick(), "instructions": worker.stats["instrs"]})
    if worker._panel_latch:
        panel.write_png(worker._panel_latch, str(out / (name + ".png")))
    print(name, worker.stats["instrs"], "frames", len(recorder.frames),
          "arp notes", len([e for e in arp.outputs if e["kind"] == "on"]), flush=True)


try:
    require(worker.ready.wait(60) and not worker.error, f"CPU startup failed: {worker.error}")
    while len(recorder.frames) < 32 and worker.stats["instrs"] < 220_000_000:
        advance(10_000_000)
    require(len(recorder.frames) >= 32, "Audio-link warmup did not complete")
    tap("STOP"); tap("STOP")
    chord("FUNC", "SRC")
    for _ in range(8): tap("UP")
    tap("YES"); tap("YES"); tap("TRIG 1")
    tap("RECORD"); chord("FUNC", "PLAY"); tap("RECORD")
    tap("KEYBOARD")
    arp.arm(); stage("armed")
    input_start, stock_start = len(arp.inputs), len(arp.stock_calls)
    report.update(input_start=input_start, stock_start=stock_start)
    first_frame = len(recorder.frames)
    for name in ("TRIG 13", "TRIG 11", "TRIG 9"):
        button(name, "press")
    stage("held-chord")
    tap("PLAY")
    if args.off:
        advance(130_000_000)
    else:
        while len([e for e in arp.outputs if e["kind"] == "on"]) < 8:
            advance(5_000_000)
        require([e["note"] for e in arp.outputs if e["kind"] == "on"] ==
                [60, 64, 67, 60, 64, 67, 60, 64], "UP order differs")
    stage("up-eight")
    middle_start = len(arp.outputs)
    button("TRIG 11", "release")
    if not args.off:
        while len([e for e in arp.outputs[middle_start:] if e["kind"] == "on"]) < 4:
            advance(5_000_000)
        require([e["note"] for e in arp.outputs[middle_start:] if e["kind"] == "on"] ==
                [67, 60, 67, 60], "Released middle note reappeared")
    button("TRIG 9", "release"); button("TRIG 13", "release")
    last = len(arp.outputs); advance(10_000_000)
    require(not arp.outputs[last:], "New arp events after last key release")
    tap("STOP"); stopped = len(arp.outputs); advance(10_000_000)
    require(not arp.outputs[stopped:], "New arp events after Stop")
    stage("released-stopped")
    require(arp.field("held") == arp.field("owned") == 0, "Input ownership remained")
    physical = [e for e in arp.inputs[input_start:] if e["kind"] == "on"]
    require([e["note"] for e in physical] == [67, 64, 60], "Unexpected mapped input")
    require(all(e["consumed"] != args.off for e in physical), "OFF/UP collection differs")
    if args.off:
        require(not arp.outputs, "OFF generated arp output")
        require([e["note"] for e in arp.stock_calls[stock_start:] if e["kind"] == "on" and e["track"] == 0] ==
                [67, 64, 60], "OFF did not preserve native key order")
    if args.stop_held:
        restart = len(arp.outputs)
        button("TRIG 9", "press"); tap("PLAY")
        while not any(e["kind"] == "on" for e in arp.outputs[restart:]):
            advance(1_000_000)
        require(arp.field("active") == 60 and arp.field("owned") == arp.field("held") == 1,
                "Stop check did not begin during an active held gate")
        stage("stop-held-active")
        before_stop = len(arp.outputs)
        button("STOP", "press")
        require(arp.outputs[before_stop:] == [
            {"kind": "off", "note": 60, "velocity": 0, "tick": arp.outputs[-1]["tick"]}],
                "Stop did not close exactly the active gate")
        require(arp.field("active") == 0xFFFFFFFF and arp.field("held") == 0
                and arp.field("owned") == 1, "Stop did not retain suppressed input ownership")
        button("STOP", "release")
        stopped = len(arp.outputs); advance(10_000_000)
        release_start = len(arp.stock_calls)
        button("TRIG 9", "release")
        advance(10_000_000)
        require(not arp.outputs[stopped:], "Stopped held note restarted")
        require(not arp.stock_calls[release_start:], "Old held-key release leaked into stock")
        require(arp.inputs[-1]["kind"] == "off" and arp.inputs[-1]["consumed"],
                "Stopped input release was not consumed")
        require(arp.field("owned") == arp.field("held") == 0, "Stopped input ownership remained")
        report["stop_held"] = {"status": "passed", "output_start": restart,
                               "stop_output": before_stop, "ownership_after_release": 0}
        stage("stop-held-released")
    unsupported_start = len(arp.stock_calls)
    chord("TRK", "TRIG 2")
    tap("TRIG 9")
    unsupported = arp.stock_calls[unsupported_start:]
    require(any(e["kind"] == "on" and e["track"] == 1 and e["note"] == 60
                and not e["generated"] for e in unsupported), "Other track was intercepted")
    require(any(e["kind"] == "off" and e["track"] == 1 and e["note"] == 60
                and not e["generated"] for e in unsupported), "Other track release was intercepted")
    stage("unsupported-track-stock")
    report["unsupported_calls"] = unsupported
    trigs = [{"frame": i, "tick": recorder.ticks[i],
              "note_word": int.from_bytes(f[2:4], "big")}
             for i, f in enumerate(recorder.frames) if i >= first_frame
             and int.from_bytes(f[0x22:0x24], "big") & 1]
    if not args.off:
        ons = [e for e in arp.outputs if e["kind"] == "on"]
        require([e["note_word"] for e in trigs] == [e["note"] * 256 for e in ons],
                "Native arp pitches did not reach the actual DSP control frames")
        lag = [t["tick"] - e["tick"] for t, e in zip(trigs, ons, strict=True)]
        require(all(0 <= n <= 64 for n in lag), "Control delivery exceeded two modeled blocks")
        report["control_delivery_samples"] = lag
        report["native_on_intervals_samples"] = [b["tick"] - a["tick"]
                                                   for a, b in zip(ons, ons[1:])]
    require(all((b-a) & 0xFFFFFFFF == 32 for a, b in zip(recorder.ticks, recorder.ticks[1:])),
            "Capture clock has missing or duplicate blocks")
    require(not worker.error and not worker._faulted_pages, "CPU error or fault pages")
    require(source_hashes() == fingerprint, "Source changed during capture")
    report.update(status="passed", render_start=first_frame, render_end=len(recorder.frames))
except BaseException as exc:
    report.update(status="failed", error=str(exc)); raise
finally:
    worker.stop_flag.set(); worker.pause.clear(); worker.join(timeout=30)
    require(not worker.is_alive(), "CPU worker did not stop")
    (out / "control.dtfr").write_bytes(b"DTFR" + struct.pack("<II", 1, len(recorder.frames)) +
        b"".join(struct.pack("<I", len(f)) + f for f in recorder.frames))
    (out / "state.bin").write_bytes(arp.raw() if arp.machine else b"")
    report.update(native_inputs=arp.inputs, native_outputs=arp.outputs, stock_calls=arp.stock_calls,
                  ticks=recorder.ticks, interrupts=dict(clock["interrupts"]),
                  faulted_pages=sorted(worker._faulted_pages), worker_error=worker.error,
                  capture_sha256=sha256(out / "control.dtfr"), transactions=arp.calls,
                  trigger_frames=[{"frame": i, "tick": recorder.ticks[i],
                                   "note_word": int.from_bytes(f[2:4], "big")}
                                  for i, f in enumerate(recorder.frames)
                                  if i >= report.get("render_start", 0) and int.from_bytes(f[0x22:0x24], "big") & 1])
    write_json(out / "arp.json", report)
print("PASS", report["condition"], len(arp.outputs), "native arp output edges")
