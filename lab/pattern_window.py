"""Small buffered audition window attached to an already prepared CPU worker."""

import os
import struct
import subprocess
import sys
from pathlib import Path

from lab.project import ROOT, require, sha256, write_json


def open_window(emu, recorder, output, capture_meta, *, seconds=900):
    for key, directory in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        library = Path(sys.base_prefix) / "lib" / directory
        if library.is_dir():
            os.environ.setdefault(key, str(library))
    import tkinter as tk

    from emu import gui

    require(emu.stats["status"] == "paused", "Window requires paused CPU")
    app = tk.Tk()
    app.title("DTII pattern lab — edit, capture, listen")
    app.configure(bg="#15181d")
    state = {
        "phase": "editing",
        "take": 0,
        "process": None,
        "last": None,
        "closed": False,
        "log": None,
    }
    names = {v.upper(): k for k, v in emu.button_names.items()}
    recorder.recording = False
    recorder.frames.clear()
    recorder.ticks.clear()

    def tap(name):
        emu.inbox.extend([("press", names[name], None), ("release", names[name], None)])

    def send(kind, code, arg):
        if state["phase"] in ("editing", "capturing"):
            emu.inbox.append((kind, code, arg))

    controls = gui.Controls(
        app, emu.device, emu.button_names, emu.encoder_names, send, 2
    )
    controls.pack(padx=12, pady=12)
    bar = tk.Frame(app, bg="#15181d")
    bar.pack(fill="x", padx=12)
    message = tk.StringVar(
        value="Edit track 1 with the panel. Capture runs PLAY, then renders a WAV."
    )
    duration = tk.IntVar(value=4)
    tk.Label(bar, text="Capture seconds:", bg="#15181d", fg="white").pack(side="left")
    tk.Spinbox(bar, from_=1, to=8, textvariable=duration, width=3).pack(side="left")

    def record():
        if state["phase"] != "editing":
            return
        try:
            n = duration.get()
            require(1 <= n <= 8, "Choose 1–8 seconds")
        except (ValueError, tk.TclError):
            message.set("Choose 1–8 seconds")
            return
        state.update(
            phase="stopping", duration=n, target_instr=emu.stats["instrs"] + 10_000_000
        )
        emu.inbox.append(("release_all", 0, None))
        tap("STOP")
        tap("STOP")
        message.set("Stopping transport before capture…")

    def listen():
        if state["last"]:
            subprocess.Popen(["afplay", str(state["last"])])

    tk.Button(bar, text="Capture & render", command=record).pack(side="left", padx=8)
    tk.Button(bar, text="Listen again", command=listen).pack(side="left", padx=4)
    tk.Label(
        app, textvariable=message, bg="#15181d", fg="#e6d59a", wraplength=800
    ).pack(padx=12, pady=8)
    tk.Label(
        app,
        text="Buffered voice audio · no live sound · track 1 · OS 1.16",
        bg="#15181d",
        fg="#9aa7b8",
    ).pack(pady=(0, 8))

    def editing(message_text):
        recorder.recording = False
        state["phase"] = "editing"
        message.set(message_text)
        emu.pause.clear()

    def close():
        state["closed"] = True
        process = state["process"]
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if state["log"]:
            state["log"].close()
        emu.stop_flag.set()
        emu.pause.clear()
        emu.join(timeout=30)
        app.destroy()

    def tick():
        if state["closed"]:
            return
        try:
            if emu.error or not emu.is_alive() or emu._faulted_pages:
                message.set(
                    "CPU stopped or faulted; close this window and inspect its run log."
                )
                state["phase"] = "failed"
            controls.panel.draw(emu.fb)
            phase = state["phase"]
            if (
                phase == "stopping"
                and not emu.inbox
                and emu.stats["instrs"] >= state["target_instr"]
            ):
                emu.pause.set()
                state["phase"] = "arming"
            elif phase == "arming" and emu.stats["status"] == "paused":
                recorder.frames.clear()
                recorder.ticks.clear()
                recorder.recording = True
                tap("PLAY")
                state["phase"] = "capturing"
                emu.pause.clear()
                message.set(
                    "Capturing firmware PLAY (the emulator runs slower than real time)…"
                )
            elif (
                phase == "capturing"
                and len(recorder.frames) >= state["duration"] * 1500
            ):
                state["end"] = state["duration"] * 1500
                tap("STOP")
                state["target_instr"] = emu.stats["instrs"] + 6_000_000
                state["phase"] = "finishing"
            elif (
                phase == "finishing"
                and not emu.inbox
                and emu.stats["instrs"] >= state["target_instr"]
            ):
                emu.pause.set()
                state["phase"] = "saving"
            elif phase == "saving" and emu.stats["status"] == "paused":
                state["take"] += 1
                take = output / f"take-{state['take']:03d}"
                take.mkdir()
                raw = recorder.frames
                events = [
                    i
                    for i, f in enumerate(raw[: state["end"]])
                    if int.from_bytes(f[0x22:0x24], "big") & 1
                ]
                require(
                    events and events[0] > 0,
                    "No track-1 notes captured; add a trig and try again",
                )
                require(
                    all(
                        (b - a) & 0xFFFFFFFF == 32
                        for a, b in zip(
                            recorder.ticks[:-1], recorder.ticks[1:], strict=True
                        )
                    ),
                    "Capture clock discontinuity",
                )
                (take / "pattern.dtfr").write_bytes(
                    b"DTFR"
                    + struct.pack("<II", 1, len(raw))
                    + b"".join(struct.pack("<I", len(f)) + f for f in raw)
                )
                meta = {
                    **capture_meta,
                    "status": "captured",
                    "mode": "interactive",
                    "ticks": list(recorder.ticks),
                    "capture_sha256": sha256(take / "pattern.dtfr"),
                    "passes": [
                        {
                            "name": "interactive",
                            "render_start": events[0],
                            "render_end": state["end"],
                        }
                    ],
                }
                write_json(take / "capture.json", meta)
                target = output / f"take-{state['take']:03d}-audio"
                state["log"] = (take / "render.log").open("w")
                state["process"] = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts/render-pattern.py"),
                        str(take),
                        str(target),
                        "--play",
                    ],
                    stdout=state["log"],
                    stderr=subprocess.STDOUT,
                )
                state.update(phase="rendering", audio=target / "pattern.wav")
                message.set(
                    "Rendering SHARC audio and checking an exact repeat. This takes several minutes."
                )
            elif phase == "rendering" and state["process"].poll() is not None:
                success = state["process"].returncode == 0
                state["log"].close()
                state["log"] = None
                if success:
                    state["last"] = state["audio"]
                editing(
                    "Ready. WAV played; edit and capture again."
                    if success
                    else "Render failed; inspect this take’s render.log. Editing can continue."
                )
        except Exception as exc:
            editing(str(exc))
        app.after(100, tick)

    app.protocol("WM_DELETE_WINDOW", close)
    app.after(seconds * 1000, close)
    emu.pause.clear()
    tick()
    try:
        app.mainloop()
    finally:
        write_json(
            output / "window.json",
            {
                "takes": state["take"],
                "last_wav": str(state["last"]) if state["last"] else None,
                "worker_error": emu.error,
                "faulted_pages": sorted(emu._faulted_pages),
            },
        )
