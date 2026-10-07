# ruff: noqa: E402
"""Edit a prepared OS 1.16 pattern through panel inputs and capture normal PLAY."""

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
p.add_argument("--machine", choices=("stock", "plaits", "integration"), default="stock")
p.add_argument(
    "--no-sequencer-irqs",
    action="store_true",
    help="Negative control: retain the missing interrupt delivery",
)
p.add_argument(
    "--window",
    action="store_true",
    help="Prepare the example, then open an interactive panel with buffered capture",
)
p.add_argument(
    "--window-seconds",
    type=int,
    default=900,
    help="Window lifetime bound, 10..1800 seconds",
)
p.add_argument(
    "--integration-controls",
    action="store_true",
    help="Check R3 duration, LFO and track guard instead of the pattern sequence",
)
args = p.parse_args()
require(
    not args.integration_controls or args.machine == "integration",
    "R3 controls require --machine integration",
)
require(10 <= args.window_seconds <= 1800, "Window bound must be 10..1800 seconds")
require(
    not (args.window and args.no_sequencer_irqs), "Window requires sequencer interrupts"
)
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.pattern_clock import Recorder, install

# isort: off
from lab.runtime import REPO
from emu import gui, panel
# isort: on

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(
    sha256(inputs["main"])
    == "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830",
    "Unexpected inherited CPU image",
)
old = Path(inputs["main"]).read_bytes()
if args.machine in ("plaits", "integration"):
    from lab.plaits import build_cpu

    candidate = build_cpu(
        family="integration" if args.machine == "integration" else "controls"
    )
    new = (out / "PLAITS_MAIN_OS.bin").read_bytes()
else:
    # Keep the checkpoint's CPU integration; select the untouched stock sampler.
    # Reverting the image under live objects is not a stock cold-boot comparison.
    new = old
    candidate = {
        "sha256": sha256(inputs["main"]),
        "stock_machine_in_prepared_cpu": True,
    }
require(len(old) == len(new), "Image extent changed")
os.chdir(REPO)
os.environ.update(
    DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"], DT2_MAIN_IMG=inputs["main"]
)
recorder = Recorder()
runtime = install(gui, recorder, sequencer_irqs=not args.no_sequencer_irqs)
emu = gui.Emulator(
    inputs["snapshot"],
    syx=inputs["syx"],
    card_image=inputs["card"],
    live=recorder,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
runtime["worker"] = emu
emu.pause.set()
emu.start()
deadline = time.monotonic() + 1200
fingerprint = source_hashes()
report = {
    "inputs": inputs,
    "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
    "source_sha256": fingerprint,
    "cpu_candidate": candidate,
    "machine": args.machine,
    "sequencer_irqs": not args.no_sequencer_irqs,
    "gestures": [],
    "stages": [],
    "passes": [],
    "scope": "Prepared OS 1.16; real panel editing and PLAY; SSI clock assumption 96000 Hz; zero DSP replies; no project reload, final mixer or hardware claim.",
}


def advance(n=2_000_000):
    # Retain one chunk of panel dwell, but make its end independent of host
    # scheduling. The adapter pauses the worker before another chunk begins.
    target = emu.stats["instrs"] + n + gui.BUDGET
    runtime["pause_after"] = target
    emu.pause.clear()
    while emu.stats["status"] != "paused" or emu.stats["instrs"] < target:
        require(not emu.error and emu.is_alive(), f"CPU stopped: {emu.error}")
        require(time.monotonic() < deadline, "1200-second CPU bound exceeded")
        time.sleep(0.005)


def code(name, encoder=False):
    names = emu.encoder_names if encoder else emu.button_names
    hits = [k for k, v in names.items() if v.upper() == name]
    require(len(hits) == 1, f"Unknown control {name}")
    return hits[0]


def button(name, kind):
    report["gestures"].append([emu.stats["instrs"], kind, name])
    emu.inbox.append((kind, code(name), None))
    advance()


def tap(name):
    button(name, "press")
    button(name, "release")


def chord(modifier, name):
    button(modifier, "press")
    tap(name)
    button(modifier, "release")


def turn(encoder, delta, count):
    report["gestures"].append([emu.stats["instrs"], "turn", encoder, delta, count])
    emu._dwell_chunks = 0
    for _ in range(count):
        emu.inbox.append(("encoder", code("ENCODER " + encoder, True), delta))
        advance(200_000)
    emu._dwell_chunks = 4
    advance(4_000_000)


def values(f):
    return {
        k: int.from_bytes(f[o : o + 2], "big")
        for k, o in {
            "trig": 0x22,
            "type": 0x94,
            "note": 2,
            "tune": 0xDA,
            "harmonics": 0xDC,
            "model": 0xDE,
            "timbre": 0xE0,
            "morph": 0xE6,
            "length": 0xE8,
            "level": 0xEC,
        }.items()
    }


def triggers(start):
    return [
        {"frame": i, "tick": recorder.ticks[i], "values": values(recorder.frames[i])}
        for i in range(start, len(recorder.frames))
        if int.from_bytes(recorder.frames[i][0x22:0x24], "big") & 1
    ]


def stage(name):
    row = {
        "name": name,
        "frame": len(recorder.frames),
        "instructions": emu.stats["instrs"],
        "wire": values(recorder.frames[-1]),
    }
    report["stages"].append(row)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(out / (name + ".png")))
    print(json.dumps(row), flush=True)


def patch_image():
    i = 0
    while i < len(old):
        if old[i] == new[i]:
            i += 1
            continue
        start = i
        while i < len(old) and old[i] != new[i]:
            i += 1
        address = 0x40000400 + start
        require(
            bytes(emu._uc.mem_read(address, i - start)) == old[start:i],
            f"Checkpoint image drift at {address:#x}",
        )
        emu._uc.mem_write(address, new[start:i])


def preview(step):
    button(f"TRIG {step}", "press")
    start = len(recorder.frames)
    tap("YES")
    advance(4_000_000)
    events = triggers(start)
    require(len(events) == 1, f"Expected one preview on {step}: {events}")
    button(f"TRIG {step}", "release")
    return events[0]["values"]


fields = ("type", "note", "tune", "length", "level")
if args.machine in ("plaits", "integration"):
    fields += ("model", "harmonics", "timbre", "morph")


def signature(v):
    return {k: v[k] for k in fields}


def play_pass(name, steps, expected, count=9):
    start = len(recorder.frames)
    tap("PLAY")
    limit = emu.stats["instrs"] + 800_000_000
    while len(triggers(start)) < count and emu.stats["instrs"] < limit:
        advance(10_000_000)
    events = triggers(start)
    stage(name)
    tap("STOP")
    tap("STOP")
    stopped = len(recorder.frames)
    advance(15_000_000)
    require(not triggers(stopped), "Stopped transport still emitted track-1 notes")
    result = {
        "name": name,
        "start": start,
        "end": stopped,
        "events": events,
        "steps": steps,
    }
    report["passes"].append(result)
    if args.no_sequencer_irqs:
        require(
            len(events) < count, "Negative control unexpectedly completed the pattern"
        )
        return
    require(len(events) >= count, f"PLAY stalled after {len(events)} notes")
    events = events[:count]
    for i, event in enumerate(events):
        step = steps[i % len(steps)]
        require(
            signature(event["values"]) == signature(expected[step]),
            f"PLAY step {step} controls differ: {event}, expected {expected[step]}",
        )
    # 102 BPM, 1x speed. Sixteenth-note spacing; at most one audio block of quantization.
    expected_intervals = [
        ((steps[(i + 1) % len(steps)] - steps[i % len(steps)]) % 16)
        * 1500
        * 60
        / (102 * 4)
        for i in range(count - 1)
    ]
    intervals = [events[i + 1]["frame"] - events[i]["frame"] for i in range(count - 1)]
    result.update(
        interval_frames=intervals, expected_interval_frames=expected_intervals
    )
    require(
        all(
            abs(a - b) <= 1.01
            for a, b in zip(intervals, expected_intervals, strict=True)
        ),
        f"Pattern timing differs: {intervals} vs {expected_intervals}",
    )
    result.update(render_start=events[0]["frame"], render_end=events[-1]["frame"])
    print("PASS", name, intervals, flush=True)


try:
    require(emu.ready.wait(60) and not emu.error, f"CPU startup failed: {emu.error}")
    if args.machine in ("plaits", "integration"):
        patch_image()
    # The original ready state intentionally suppresses its first 1500 frames.
    # Let the firmware count down naturally instead of clearing that counter.
    while len(recorder.frames) < 32 and emu.stats["instrs"] < 220_000_000:
        advance(10_000_000)
    require(len(recorder.frames) >= 32, "Audio-link warmup did not complete")
    tap("STOP")
    tap("STOP")
    chord("FUNC", "SRC")
    for _ in range(8):
        tap("UP")
    if args.machine in ("plaits", "integration"):
        for _ in range(7):
            tap("DOWN")
    tap("YES")
    tap("YES")
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    require(
        emu._uc.mem_read(ptr + 0xD6, 1)[0] == (7 if args.machine != "stock" else 0),
        "Machine selection failed",
    )
    # The prepared CPU refreshes the selected machine's active parameter row
    # on its first track trigger. Prime that row before editing it.
    tap("TRIG 1")
    advance(8_000_000)
    if args.machine in ("plaits", "integration"):
        tap("SRC")
        turn("C", -8, 6)
        turn("C", 3, 3)
        turn("B", 8, 12)
        turn("D", 8, 16)
        turn("E", 8, 6)
    if args.integration_controls:
        from lab.plaits_integration_panel import check

        check(emu, recorder, tap, chord, turn, advance, stage, values, report)
    else:
        tap("RECORD")
        chord("FUNC", "PLAY")  # clear the selected track's sequence
        advance(6_000_000)
        # Enter grid recording from the original ready fixture; initially 128/128.
        chord("FUNC", "PAGE")
        tap("PAGE")
        advance(4_000_000)
        stage("length-16")
        tap("NO")
        for step in (1, 5, 9, 13, 3, 3):  # add then remove step 3
            tap(f"TRIG {step}")
        tap("SRC")
        stage("grid-edited")
        for step, delta in ((5, -8), (13, 8)):
            button(f"TRIG {step}", "press")
            advance(30_000_000)
            lock_encoders = (
                ("A",)
                if args.machine == "stock"
                else ("B", "D", "E", "F")
                if args.machine == "integration"
                else ("B", "D", "E")
            )
            for encoder in lock_encoders:
                turn(encoder, delta, 16)
            tap("YES")
            advance(4_000_000)
            stage(f"stored-lock-{step}")
            button(f"TRIG {step}", "release")
        expected = {s: preview(s) for s in (1, 5, 9, 13)}
        require(
            signature(expected[1]) == signature(expected[9]), "Unlocked steps differ"
        )
        require(
            signature(expected[5]) != signature(expected[1]) != signature(expected[13]),
            "Locks must differ from base",
        )
        report["expected"] = expected
        if not args.window:
            play_pass("two-loops", [1, 5, 9, 13], expected)
        if not args.no_sequencer_irqs and not args.window:
            tap("TRIG 5")  # remove locked step 5
            tap("TRIG 7")  # add an unlocked step elsewhere
            turn("A" if args.machine == "stock" else "B", 8, 4)
            edited = {s: preview(s) for s in (1, 7, 9, 13)}
            require(
                signature(edited[1]) != signature(expected[1]),
                "Base edit did not persist",
            )
            require(
                signature(edited[13]) == signature(expected[13]),
                "Base edit damaged stored lock",
            )
            report["edited_expected"] = edited
            play_pass("edited-restart", [1, 7, 9, 13], edited, count=5)
    require(not emu.error and not emu._faulted_pages, "CPU error or faulted pages")
    require(
        all(
            (b - a) & 0xFFFFFFFF == 32
            for a, b in zip(recorder.ticks[:-1], recorder.ticks[1:], strict=True)
        ),
        "Missing or duplicate audio ticks",
    )
    require(source_hashes() == fingerprint, "Source changed during capture")
    report["status"] = "negative-control-passed" if args.no_sequencer_irqs else "passed"
    if args.window:
        from lab.pattern_window import open_window

        report["status"] = "prepared-for-window"
        write_json(out / "preparation.json", report)
        open_window(emu, recorder, out, report, seconds=args.window_seconds)
        require(
            not emu.error and not emu._faulted_pages, "Window CPU stopped or faulted"
        )
        require(source_hashes() == fingerprint, "Source changed while window was open")
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    if emu.is_alive():
        report.update(status="failed", error="CPU worker did not stop")
    (out / "pattern.dtfr").write_bytes(
        b"DTFR"
        + struct.pack("<II", 1, len(recorder.frames))
        + b"".join(struct.pack("<I", len(f)) + f for f in recorder.frames)
    )
    report.update(
        capture_sha256=sha256(out / "pattern.dtfr"),
        ticks=recorder.ticks,
        interrupts=dict(runtime["interrupts"]),
        worker_error=emu.error,
        faulted_pages=sorted(emu._faulted_pages),
    )
    write_json(out / "capture.json", report)
