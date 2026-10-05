# ruff: noqa: E402
"""Prepared DTII window with buffered, emulated Plaits note audition.

Real CPU step previews supply controls. The native SHARC renders a complete
note before afplay plays its WAV at normal speed. This is not real-time audio
or the final DTII mixer. Close the window to stop; automatic limit 15 minutes.
"""

import argparse
import array
import dataclasses
import json
import math
import os
import queue
import struct
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--seconds", type=int, default=900)
args = p.parse_args()
require(30 <= args.seconds <= 1800, "Use 30..1800 seconds")
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.formats import read_frames
from lab.runtime import LIB, PACK, REPO, STOCK_MAIN

# lab.runtime installs the pinned DigiKit import paths before these imports.
import sharc_transpile_run as native
import sharcldr
from live_audio import LiveAudio
# isort: on

reference = ROOT / "out/runs/trio-final-01"
capture = ROOT / "out/runs/trio-model-capture-02"
checked = json.loads((reference / "report.json").read_text())
require(checked["status"] == "passed", "Prototype validation missing")
for name in ("PLAITS_MAIN_OS.bin", "firmware/PLAITS_BLOB.bin"):
    require(
        sha256(reference / name) == checked["outputs"][name], f"Image drift: {name}"
    )
meta = json.loads((capture / "capture.json").read_text())
require(
    meta["status"] == "passed"
    and sha256(capture / "models.dtfr") == meta["capture_sha256"],
    "Capture drift",
)
inputs = meta["inputs"]
for k in ("main", "syx", "card"):
    require(sha256(inputs[k]) == meta["input_sha256"][k], f"Input drift: {k}")
live_lib = ROOT / "out/cache/live-audio/release/liblive_audio.dylib"
require(live_lib.is_file(), "Build pinned native/live into out/cache/live-audio first")

# Preserve state/card/core provenance; replace only the actual program image
# and use the same runtime-decode options as the checked lab replay.
original = PACK.read_bytes()
pos = 8
require(original[:8] == b"SHFP\x01\0\0\0", "Wrong state pack")


def u32():
    global pos
    v = struct.unpack_from("<I", original, pos)[0]
    pos += 4
    return v


def blob():
    global pos
    n = u32()
    v = original[pos : pos + n]
    pos += n
    return v


blob()
state = blob()
options = {}
for _ in range(u32()):
    k = u32()
    v = struct.unpack_from("<q", original, pos)[0]
    pos += 8
    options[k] = v
host = original[pos : pos + 28]
pos += 28
first = u32()
require(u32() == 0, "Expected frameless pack")
require(original[pos : pos + 4] == b"SHLV", "Missing live trailer")
pos += 4
require(u32() == 3, "Need provenance trailer v3")
nv = u32()
voices = original[pos : pos + nv * 12]
pos += nv * 12
blob()
card = blob()
core = blob()
require(
    pos == len(original) and card.decode() == meta["input_sha256"]["card"],
    "Pack/card mismatch",
)
candidate = reference / "firmware/PLAITS_BLOB.bin"
image = native.pack_image(sharcldr.LoadedMemory.from_stream(candidate.read_bytes()))
options[native.OPT_BLOCKS] = 0
options[native.OPT_RUNTIME_DECODE] = 1


def sized(v):
    return struct.pack("<I", len(v)) + v


pack = (
    b"SHFP"
    + struct.pack("<I", 1)
    + sized(image)
    + sized(state)
    + struct.pack("<I", len(options))
    + b"".join(struct.pack("<Iq", k, v) for k, v in options.items())
    + host
    + struct.pack("<II", first, 0)
    + b"SHLV"
    + struct.pack("<II", 3, nv)
    + voices
    + sized(("trio-" + sha256(candidate)).encode())
    + sized(card)
    + sized(core)
)
(out / "live.pack").write_bytes(pack)
report = {
    "scope": __doc__,
    "source_sha256": source_hashes(),
    "base_pack_sha256": sha256(PACK),
    "dsp_sha256": sha256(candidate),
    "cpu_sha256": sha256(reference / "PLAITS_MAIN_OS.bin"),
    "snapshot_sha256": sha256(capture / "models-ready.snap"),
    "live_library_sha256": sha256(live_lib),
    "notes": [],
}
raw = read_frames(capture / "models.dtfr")
base = bytearray(raw[meta["preview_start"] - 1])


def isolate(frame, event=True):
    f = bytearray(frame)
    for off in (0x22, 0x24, 0x26, 0x28):
        f[off : off + 2] = (
            (int.from_bytes(f[off : off + 2], "big") & 1) if event else 0
        ).to_bytes(2, "big")
    if not event:
        f[0x2A:0x2C] = b"\0\0"
    return bytes(f)


class BufferedAudio:
    period = 200_000

    def __init__(self):
        self.jobs = queue.Queue(maxsize=2)
        self.closed = threading.Event()
        self.pushed = 0
        self.trigs = 0
        self.rendered = 0
        self.rendered_stats = SimpleNamespace(
            frames=0, clean=0, stopped=0, nonzero_frames=0, median_us=0, p99_us=0
        )
        self.message = "Preparing emulated DSP…"
        self.last = None
        self.player = None

    def open(self):
        self.worker = threading.Thread(target=self.render_notes, daemon=True)
        self.worker.start()
        return self

    def close(self):
        self.closed.set()
        if self.player and self.player.poll() is None:
            self.player.terminate()

    def device_name(self):
        return "Buffered WAV audition on macOS default output"

    def stats(self):
        return SimpleNamespace(underruns=0)

    def frame_stats(self):
        return SimpleNamespace(
            pushed=self.pushed,
            trig_pushed=self.trigs,
            taken=self.rendered,
            repeats=0,
            max_depth=2,
            merged=0,
        )

    def render_stats(self):
        return self.rendered_stats

    def push_frame(self, f):
        self.pushed += 1
        if (
            int.from_bytes(f[0x22:0x24], "big") & 1
            and int.from_bytes(f[0x94:0x96], "big") == 7
        ):
            self.trigs += 1
            try:
                self.jobs.put_nowait(isolate(f))
            except queue.Full:
                self.message = "Audition queue full; wait for the current notes."

    def play(self, path):
        if self.player and self.player.poll() is None:
            self.player.terminate()
        self.player = subprocess.Popen(["/usr/bin/afplay", str(path)])
        self.message = "Playing " + path.stem + " — emulated voice buffers"

    def render_notes(self):
        try:
            with LiveAudio(
                frames_pack=out / "live.pack",
                library_path=live_lib,
                sharc_lib=LIB,
                card_sha256=card.decode(),
                device=False,
                gain=1,
            ) as audio:
                for _ in range(150):
                    if self.closed.is_set():
                        return
                    audio.push_frame(isolate(base, False))
                    audio.render(1)
                    self.rendered += 1
                self.rendered_stats = audio.render_stats()
                self.message = "Ready — use Preview VA / FM / BD below."
                while not self.closed.is_set():
                    try:
                        f = self.jobs.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    model = min(2, (int.from_bytes(f[0xDE:0xE0], "big") + 128) // 256)
                    name = ("VA", "FM", "BD")[model]
                    self.message = "Rendering " + name + "… about 10–25 seconds"
                    samples = array.array("f")
                    started = time.monotonic()
                    nonzero = False
                    quiet = 0
                    for i in range(780):
                        if self.closed.is_set():
                            return
                        audio.push_frame(f if i == 0 else isolate(f, False))
                        block = audio.render(1)
                        self.rendered += 1
                        require(
                            all(math.isfinite(v) and abs(v) < 0.5 for v in block),
                            "Invalid or unexpectedly loud PCM",
                        )
                        samples.extend(block)
                        if max(map(abs, block)) > 1e-7:
                            nonzero = True
                            quiet = 0
                        else:
                            quiet += 1
                        if nonzero and quiet >= 24:
                            break
                    require(
                        nonzero and quiet >= 24,
                        "Note silent or exceeds bounded duration",
                    )
                    self.rendered_stats = audio.render_stats()
                    stats = dataclasses.asdict(self.rendered_stats)
                    require(stats["stopped"] == 0, "Native SHARC stopped")
                    path = out / (f"{len(report['notes']) + 1:02d}-{name}.wav")
                    with wave.open(str(path), "wb") as w:
                        w.setnchannels(2)
                        w.setsampwidth(2)
                        w.setframerate(48000)
                        w.writeframes(
                            array.array(
                                "h", (round(v * 0.7 * 32767) for v in samples)
                            ).tobytes()
                        )
                    (path.with_suffix(".frame")).write_bytes(f)
                    report["notes"].append(
                        {
                            "model": name,
                            "path": str(path),
                            "render_seconds": time.monotonic() - started,
                            "audio_seconds": len(samples) / 96000,
                            "peak": max(map(abs, samples)),
                            "render_stats": stats,
                            "sha256": sha256(path),
                        }
                    )
                    write_json(out / "session.json", report)
                    print(json.dumps(report["notes"][-1]), flush=True)
                    self.last = path
                    self.play(path)
        except Exception as exc:
            self.message = "Audio stopped: " + str(exc)
            report["error"] = str(exc)
            write_json(out / "session.json", report)
            print(self.message, flush=True)


os.chdir(REPO)
os.environ.update(
    DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"], DT2_MAIN_IMG=inputs["main"]
)
# Relocated standalone Python needs explicit paths to its bundled Tcl/Tk.
for key, directory in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
    library = Path(sys.base_prefix) / "lib" / directory
    if library.is_dir():
        os.environ.setdefault(key, str(library))
import tkinter as tk

import framelink
from emu import gui

framelink.PROFILES[meta["input_sha256"]["main"]] = dict(
    framelink.PROFILES[sha256(STOCK_MAIN)]
)
old = Path(inputs["main"]).read_bytes()
new = (reference / "PLAITS_MAIN_OS.bin").read_bytes()
changed = [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
original_build = gui.build


def verified_build(*a, **kw):
    result = original_build(*a, **kw)
    # The checkpoint manifest names its inherited SINE image; its saved flash
    # must already contain every guarded candidate change from the capture.
    uc = result[0].uc
    for i in changed:
        require(
            bytes(uc.mem_read(0x40000400 + i, 1)) == new[i : i + 1],
            "Prepared checkpoint image drift",
        )
    return result


gui.build = verified_build
bridge = BufferedAudio()
app = gui.App(
    str(capture / "models-ready.snap"),
    syx=inputs["syx"],
    card_image=inputs["card"],
    live=bridge,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
app.title("Plaits machine lab — buffered emulator audition")
bar = tk.Frame(app, bg="#15181d")
bar.pack(fill="x", padx=16, pady=5)
label = tk.Label(app, text="", bg="#15181d", fg="#e6d59a")
label.pack(padx=16, pady=5)
control_lock = threading.Lock()


def preview(step):
    if not control_lock.acquire(blocking=False):
        return

    def send():
        try:
            e = app.emu
            require(e.ready.wait(60) and not e.error, "CPU not ready")

            def event(name, kind):
                code = next(k for k, v in e.button_names.items() if v.upper() == name)
                target = e.stats["instrs"] + 2_000_000
                e.inbox.append((kind, code, None))
                until = time.monotonic() + 30
                while e.inbox or e.stats["instrs"] < target:
                    if bridge.closed.is_set():
                        return
                    require(
                        not e.error and e.is_alive() and time.monotonic() < until,
                        "Panel event timed out",
                    )
                    time.sleep(0.02)

            event(f"TRIG {step}", "press")
            event("YES", "press")
            event("YES", "release")
            event(f"TRIG {step}", "release")
        except Exception as exc:
            bridge.message = str(exc)
        finally:
            control_lock.release()

    threading.Thread(target=send, daemon=True).start()


for name, step in (("Preview VA", 9), ("Preview FM", 1), ("Preview BD", 5)):
    tk.Button(bar, text=name, command=lambda s=step: preview(s)).pack(
        side="left", padx=4
    )
tk.Button(
    bar,
    text="Replay last",
    command=lambda: bridge.play(bridge.last) if bridge.last else None,
).pack(side="left", padx=4)


def poll():
    label.configure(text="Buffered DSP audition · " + bridge.message)
    app.after(200, poll)


poll()
app.after(7000, lambda: preview(9))
app.after(args.seconds * 1000, app.quit_all)
try:
    app.mainloop()
finally:
    bridge.close()
    report["cpu_worker_error"] = app.emu.error
    write_json(out / "session.json", report)
