"""Real emulator panel with WAV input selection and buffered Flex audition."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lab.flex_recorder import Take
from lab.project import write_json


def open_window(session, *, seconds=900, input_name="Demo tone"):
    for key, directory in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        library = Path(sys.base_prefix) / "lib" / directory
        if library.is_dir():
            os.environ.setdefault(key, str(library))
    import tkinter as tk
    from tkinter import filedialog

    from emu import gui

    app = tk.Tk()
    app.title("Digitakt II — Flex sampling")
    app.configure(bg="#15181d")
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flex-panel")
    pending = []
    state = {
        "closed": False,
        "rendering": False,
        "audition": 0,
        "input": input_name,
        "player": None,
    }
    status = tk.StringVar(value="SAMPLING → YES record → YES stop → YES use")
    label = tk.StringVar()

    def submit(fn):
        if not state["closed"]:
            pending.append(pool.submit(fn))

    def send(kind, code, arg):
        if state["rendering"]:
            return

        def action():
            session.emu.inbox.append((kind, code, arg))
            session.advance()

        submit(action)

    panel = gui.Controls(
        app,
        session.emu.device,
        session.emu.button_names,
        session.emu.encoder_names,
        send,
        2,
    )
    panel.pack(padx=12, pady=12)
    tk.Label(app, textvariable=label, bg="#15181d", fg="#e6d59a", wraplength=850).pack(
        padx=12, pady=4
    )
    bar = tk.Frame(app, bg="#15181d")
    bar.pack(padx=12, pady=6, fill="x")

    def choose_input():
        if pending or session.flex.phase in ("recording", "trim"):
            status.set("Use or discard the current take before changing input.")
            return
        path = filedialog.askopenfilename(
            title="Choose simulated recorder input",
            filetypes=[("48 kHz PCM16 WAV", "*.wav")],
        )
        if not path:
            return
        try:
            source = Take.from_wav(path)
            session.flex.input.source = source
            state["input"] = Path(path).name
            status.set("Input ready. Open SAMPLING and press YES.")
        except (OSError, ValueError) as exc:
            status.set(str(exc))

    def retarget():
        if pending or session.flex.phase in ("recording", "trim"):
            status.set("Use or discard the current take first.")
            return
        session.flex.target = None
        status.set(
            "Select a track with TRK + its pad. The next recording will remember it."
        )

    def audition():
        if (
            pending
            or session.flex.current is None
            or session.flex.phase in ("recording", "trim")
        ):
            status.set("Accept a take before auditioning it.")
            return
        state["audition"] += 1
        state["rendering"] = True
        status.set(
            "Rendering the accepted track. Playback starts when its buffered audio is ready…"
        )

        def job():
            from lab.flex_audio import render_pad

            try:
                session.tap("SRC")
                capture = session.capture_pad(f"audition-{state['audition']:03d}")
                audio = render_pad(
                    capture,
                    session.inputs["lp0"],
                    session.flex.pages,
                    session.output / f"audition-{state['audition']:03d}",
                )
                write_json(
                    session.output / f"audition-{state['audition']:03d}.json", audio
                )
                if not state["closed"]:
                    state["player"] = subprocess.Popen(["afplay", audio["path"]])
                return (
                    "Buffered track audio ready. Continue recording whenever you like."
                )
            finally:
                state["rendering"] = False

        submit(job)

    tk.Button(bar, text="Input WAV…", command=choose_input).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(bar, text="Remember selected track next", command=retarget).pack(
        side="left", padx=8
    )
    tk.Button(bar, text="Render / listen to take", command=audition).pack(
        side="left", padx=8
    )
    tk.Label(app, textvariable=status, bg="#15181d", fg="#d5dbe3", wraplength=850).pack(
        padx=12, pady=6
    )
    tk.Label(
        app,
        text="WAV input model · ONESHOT · session only · audition up to 1 second · no live input or project save",
        bg="#15181d",
        fg="#9aa7b8",
    ).pack(padx=12, pady=(0, 10))

    def tap_key(name):
        if not state["rendering"]:
            submit(lambda: session.tap(name))
        return "break"

    app.bind("<Return>", lambda e: tap_key("YES"))
    app.bind("<Escape>", lambda e: tap_key("NO"))

    def close():
        state["closed"] = True
        if state["player"] and state["player"].poll() is None:
            state["player"].terminate()
        pool.shutdown(wait=False, cancel_futures=True)
        app.destroy()

    def tick():
        if state["closed"]:
            return
        panel.panel.draw(session.emu.fb)
        for future in list(pending):
            if future.done():
                pending.remove(future)
                try:
                    message = future.result()
                    if message:
                        status.set(message)
                except Exception as exc:
                    status.set(str(exc))
        flex = session.flex
        target = (
            f"T{flex.target + 1:02d}"
            if flex.target is not None
            else "selected track on next recording"
        )
        current = flex.current["name"] if flex.current else "no temporary take"
        label.set(
            f"Input: {state['input']}  |  Destination: {target}  |  {current}  |  {flex.phase.upper()}"
        )
        if flex.error:
            status.set(flex.error)
        if (
            session.emu.error
            or not session.emu.is_alive()
            or session.emu._faulted_pages
        ):
            status.set(
                f"CPU stopped; close this window and inspect its run log. {session.emu.error or ''}"
            )
            state["rendering"] = True
            app.after(100, tick)
            return
        if not pending and flex.phase == "recording":
            submit(lambda: session.advance(4_000_000))
        app.after(100, tick)

    app.protocol("WM_DELETE_WINDOW", close)
    app.after(seconds * 1000, close)
    tick()
    try:
        app.mainloop()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
