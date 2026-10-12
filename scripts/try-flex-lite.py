#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the real prepared Digitakt II panel with the opt-in Flex emulator adapter."""

import argparse
import hashlib
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
from datetime import UTC, datetime

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", nargs="?", type=Path)
p.add_argument(
    "--input", type=Path, help="48 kHz PCM16 mono/stereo WAV, maximum 10 seconds"
)
p.add_argument(
    "--check",
    action="store_true",
    help="Run panel acceptance checks instead of opening a window",
)
p.add_argument("--mono", action="store_true", help="Use a mono demo input")
p.add_argument("--track", type=int, default=1, choices=range(1, 17))
p.add_argument(
    "--stock-save-control",
    action="store_true",
    help="Leave stock trim YES/save enabled; stop at its PLEASE WAIT view",
)
p.add_argument(
    "--skip-audio",
    action="store_true",
    help="CPU/UI check only; do not claim DSP validation",
)
p.add_argument("--window-seconds", type=int, default=900)
args = p.parse_args()
require(10 <= args.window_seconds <= 1800, "Window bound must be 10..1800 seconds")
require(
    not args.stock_save_control or args.check, "Save negative control is headless only"
)
preflight = doctor()
out = (
    args.output
    or ROOT / "out/runs" / datetime.now(UTC).strftime("flex-ui-%Y%m%dT%H%M%S%fZ")
).resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_recorder import Take
from lab.flex_session import Session


def demo(stereo, frequency=440):
    words = [
        round(9000 * math.sin(2 * math.pi * f * i / 48000))
        for i in range(12000)
        for f in ((frequency, frequency * 1.37) if stereo else (frequency,))
    ]
    return Take(struct.pack(f">{len(words)}h", *words), stereo)


source = Take.from_wav(args.input) if args.input else demo(not args.mono)
paths = [
    *sorted((ROOT / "lab").glob("flex_*.py")),
    Path(__file__),
    ROOT / "docs/FLEX-LITE-UI.md",
]
fingerprint = {str(f.relative_to(ROOT)): sha256(f) for f in paths}
for f in paths:
    dest = out / "frozen-sources" / f.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(f.read_bytes())
report = {
    "status": "running",
    "preflight": preflight,
    "source_sha256": fingerprint,
    "input_pcm_sha256": hashlib.sha256(source.pcm).hexdigest(),
    "input": str(args.input) if args.input else "generated WAV-source model",
    "scope": "Original OS 1.16 panel and CPU routines, modeled WAV recorder service, optional buffered original SHARC replay; no microphone, physical inputs, project persistence, final mixer or real-time claim",
    "checks": {},
}
session = None
try:
    session = Session(source, out, enabled=not args.stock_save_control)
    report["inputs"] = session.inputs
    report["frame_gate_before"] = session.frame_gate_before
    report["input_sha256"] = {
        k: sha256(v) for k, v in session.inputs.items() if k != "sections"
    }
    if args.track != 1:
        session.chord("TRK", f"TRIG {args.track}")
    if args.check:
        track_pointer = session.flex.fw.u32(0x80004704) + (args.track - 1) * 0x450
        machine = session.flex.fw.read(track_pointer + 0xD6, 1)[0]
        if machine and not args.stock_save_control:
            original_track = session.flex.fw.read(track_pointer, 0x450)
            session.record()
            session.tap("YES")
            require(
                session.flex.error == "Destination must use ONESHOT"
                and session.flex.current is None
                and not session.flex.fw.sources
                and session.flex.input.completed is not None
                and session.flex.fw.read(track_pointer, 0x450) == original_track,
                "Unsupported machine failure changed the sound or candidate",
            )
            report["checks"]["unsupported_machine_preserves_take"] = True
            session.chord("FUNC", "NO")
            session.tap("SRC")
            # This is deliberate test setup through the stock selector. The
            # interactive launcher never silently changes a track's machine.
            require(
                machine in (1, 2, 3, 4), "Use the prepared ONESHOT/STRETCH test tracks"
            )
            session.chord("FUNC", "SRC")
            for _ in range(machine):
                session.tap("UP")
            session.tap("YES")
            session.tap("YES")
            require(
                session.flex.fw.read(track_pointer + 0xD6, 1) == b"\0",
                "Panel did not select ONESHOT",
            )
        session.record()
        if not args.stock_save_control:
            original_frames = session.flex.input.captured
            # Native encoder acceleration has a direction-change deadband.
            # Deliver bounded repeated gestures, and inspect actual trim RAM.
            for _ in range(12):
                session.turn("E", 5)
                if session.flex.fw.u32(session.flex.view + 0x9A0) > 0:
                    break
            for _ in range(12):
                session.turn("H", -5)
                if session.flex.fw.u32(session.flex.view + 0x9A4) < original_frames:
                    break
            trim = [session.flex.fw.u32(session.flex.view + o) for o in (0x9A0, 0x9A4)]
            require(
                0 < trim[0] < trim[1] < original_frames,
                "Panel trim did not move both boundaries",
            )
            report["trim"] = {
                "recorded": original_frames,
                "start": trim[0],
                "end": trim[1],
            }
        session.screenshot("01-trim-use")
        if args.stock_save_control:
            session.tap("YES")
            session.advance()
            session.screenshot("02-stock-save-progress")
            require(
                session.flex.current is None
                and not session.flex.retained
                and not session.flex.fw.sources,
                "Disabled USE hook assigned a temporary sample",
            )
            require(
                any(
                    e["event"] == "stock-save-progress-opened"
                    for e in session.flex.events
                ),
                "Stock save progress view was not opened",
            )
            report["checks"]["disabled_use_hook"] = True
        else:
            session.accept()
            session.screenshot("02-temp-assigned")
            first = dict(session.flex.current)
            require(
                first["frames"] == trim[1] - trim[0],
                "Accepted duration differs from panel trim",
            )
            require(first["track"] == args.track - 1, "Target not selected track")
            capture_a = session.capture_pad("take-a")
            # Change the selected track before rerecording: remembered target
            # must survive, and the second take must not replace it on cancel.
            other = 2 if args.track != 2 else 3
            session.chord("TRK", f"TRIG {other}")
            session.flex.input.source = demo(source.stereo, 659)
            session.record()
            session.screenshot("03-new-take")
            session.chord("FUNC", "NO")
            session.advance()
            require(
                session.flex.current == first and session.flex.input.completed is None,
                "Discard changed the assigned take",
            )
            session.screenshot("04-discarded")
            # Native discard returns to the ready recorder page, so one YES
            # starts again without closing and reopening it.
            session.tap("YES")
            session.advance(8_000_000)
            session.tap("YES")
            session.accept()
            session.screenshot("05-replaced")
            require(
                session.flex.current["track"] == first["track"]
                and session.flex.current["slot"] != first["slot"],
                "Remembered target or immutable replacement failed",
            )
            require(
                not session.flex.fw.slot(first["slot"])["empty"],
                "Old sample storage was recycled",
            )
            capture_c = session.capture_pad("take-c")
            # Resource exhaustion is injected before allocation. The candidate
            # and assignment must remain intact, and retry stays possible.
            import lab.flex_ui as ui

            session.record()
            old_limit = ui.MAX_TAKES
            ui.MAX_TAKES = len(session.flex.fw.sources)
            try:
                before = dict(session.flex.current)
                session.tap("YES")
                session.advance()
                require(
                    session.flex.current == before
                    and session.flex.error
                    and session.flex.input.completed is not None,
                    "Capacity failure lost assignment or candidate",
                )
                session.screenshot("06-capacity-keeps-take")
            finally:
                ui.MAX_TAKES = old_limit
            session.accept()
            require(
                session.flex.current["slot"] != before["slot"],
                "Retry did not accept retained candidate",
            )
            session.screenshot("07-capacity-retry")
            report["checks"].update(
                record_stop_use=True,
                remembered_target=True,
                discard_preserves_assignment=True,
                old_allocation_retained=True,
                capacity_failure_preserves_candidate=True,
                track_data_preserved=True,
                panel_trim=True,
                capacity_retry=True,
                sources_closed=True,
            )
            report["captures"] = [capture_a, capture_c]
            if not args.skip_audio:
                from lab.flex_audio import render_pad

                report["audio"] = [
                    render_pad(
                        c, session.inputs["lp0"], session.flex.pages, out / f"audio-{i}"
                    )
                    for i, c in enumerate(report["captures"])
                ]
                require(
                    report["audio"][0]["sha256"] != report["audio"][1]["sha256"],
                    "New take did not change voice output",
                )
                report["checks"]["changed_audio_and_exact_repeat"] = True
            require(
                session.flex.fw.card.reads == [] and session.flex.fw.card.writes == [],
                "Temporary handoff touched storage",
            )
            require(
                session.flex.fw.recorder_lock_depth == 0
                and session.flex.fw.poisoned_responses > 0,
                "Recorder lock/lifetime checks absent",
            )
            report["checks"].update(
                no_temporary_storage_operations=True, copy_before_unlock=True
            )
    else:
        from lab.flex_window import open_window

        open_window(
            session,
            seconds=args.window_seconds,
            input_name=args.input.name if args.input else "Demo tone",
        )
        require(
            not session.emu.error
            and session.emu.is_alive()
            and not session.emu._faulted_pages,
            "Window CPU stopped or faulted",
        )
    require(
        {str(f.relative_to(ROOT)): sha256(f) for f in paths} == fingerprint,
        "Source changed during run",
    )
    report["status"] = "passed" if args.check else "window-closed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    if session:
        if report["status"] == "failed":
            session.screenshot("failure")
        session.dump_pages()
        report.update(
            events=session.flex.events,
            retained=session.flex.retained,
            cpu_fault_pages=sorted(session.emu._faulted_pages),
            source_requests=session.flex.input.requests,
            storage_reads=len(session.flex.fw.card.reads),
            storage_writes=len(session.flex.fw.card.writes),
            poisoned_responses=session.flex.fw.poisoned_responses,
        )
        session.close()
    write_json(out / "report.json", report)
print(f"{report['status']}: {out / 'report.json'}", flush=True)
