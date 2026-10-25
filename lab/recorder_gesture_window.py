"""Interactive native panel for the emulator-only SAMPLING dry run."""

import os
import sys
import time
from pathlib import Path


def open_window(session, *, seconds=600, comparison_note="", model_bar=None):
    for key, directory in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        library = Path(sys.base_prefix) / "lib" / directory
        if library.is_dir():
            os.environ.setdefault(key, str(library))
    import tkinter as tk

    from emu import gui

    ui = session.flex
    app = tk.Tk()
    app.title(
        "Digitakt II — SAMPLING shortcut dry run"
        + (f" — {comparison_note}" if comparison_note else "")
    )
    app.configure(bg="#15181d")
    status = tk.StringVar()
    speed = tk.StringVar()
    held = set()

    def send(kind, code, arg):
        session.emu.inbox.append((kind, code, arg))

    panel = gui.Controls(
        app,
        session.emu.device,
        session.emu.button_names,
        session.emu.encoder_names,
        send,
        2,
    )
    panel.pack(padx=12, pady=12)
    for variable in (status, speed):
        tk.Label(
            app, textvariable=variable, bg="#15181d", fg="#e6d59a", wraplength=850
        ).pack(padx=12, pady=4)
    tk.Label(
        app,
        bg="#15181d",
        fg="#d5dbe3",
        wraplength=850,
        text=(
            "C on the recorder selects NORMAL / BUF 1–4. Return to SRC to try the shortcuts.\n"
            "S = SAMPLING (down/up), Return = YES, Escape = NO, F = FUNC.\n"
            "WOULD feedback is an emulator overlay. The shortcuts never record, freeze or assign samples."
        ),
    ).pack(padx=12, pady=6)
    if comparison_note:
        tk.Label(app, text=comparison_note, bg="#15181d", fg="#e6d59a").pack(pady=4)
    if model_bar:
        tk.Button(app, text="Advance TEST bar (no capture)", command=model_bar).pack(
            pady=4
        )

    names = {v.upper(): k for k, v in session.emu.button_names.items()}

    def keyboard(name, down):
        code = names[name]
        if down and code not in held:
            held.add(code)
            send("press", code, None)
        elif not down and code in held:
            held.remove(code)
            send("release", code, None)
        return "break"

    for key, name in (
        ("s", "SAMPLING"),
        ("Return", "YES"),
        ("Escape", "NO"),
        ("f", "FUNC"),
    ):
        app.bind(f"<KeyPress-{key}>", lambda e, n=name: keyboard(n, True))
        app.bind(f"<KeyRelease-{key}>", lambda e, n=name: keyboard(n, False))

    def close():
        session.emu.pause.set()
        app.destroy()

    mark = [time.monotonic(), session.emu.stats["instrs"]]

    def tick():
        panel.panel.draw(session.emu.fb)
        current = getattr(ui, "window_status", {})
        destination = current.get("destination", 0)
        label = f"BUF {destination}" if destination else "NORMAL"
        status.set(
            f"{label}  ·  {'DRY SHORTCUTS ON' if ui.gestures_enabled else 'STOCK GESTURE CONTROL'}  ·  "
            f"{current.get('mode', 'idle').upper()}"
            + ("  ·  waiting for second tap" if current.get("pending") else "")
        )
        now = time.monotonic()
        if now - mark[0] >= 1:
            rate = (session.emu.stats["instrs"] - mark[1]) / (now - mark[0])
            speed.set(
                f"Guest clock: {rate / 132000000:.1%} of configured model speed. "
                "Holds and tap waits stretch in wall time; use the report for latency measurements."
            )
            mark[:] = now, session.emu.stats["instrs"]
        if session.emu.error or not session.emu.is_alive():
            status.set(f"Emulator stopped: {session.emu.error or ui.error}")
        app.after(40, tick)

    session.runtime.pop("pause_after", None)
    session.emu.pause.clear()
    app.protocol("WM_DELETE_WINDOW", close)
    app.after(seconds * 1000, close)
    tick()
    try:
        app.mainloop()
    finally:
        session.emu.pause.set()
