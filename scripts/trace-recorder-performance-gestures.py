#!/usr/bin/env python3
# ruff: noqa: E402
"""Observe OS 1.16 SAMPLING gestures without installing a shortcut.

Input traverses DigiKit's UART8 panel model and the original event constructor.
Durations use the configured emulator PIT rate, with actual SSI ticks retained;
they are not physical button/debounce or audio-deadline measurements.
"""

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--model-armed-status",
    action="store_true",
    help="Model external recorder status as waiting while native controller state is armed",
)
p.add_argument(
    "--context",
    choices=(
        "performance",
        "playing",
        "ready",
        "armed",
        "recording",
        "background-recording",
        "trim",
        "name",
    ),
    default="performance",
)
p.add_argument(
    "--gesture",
    choices=(
        "single",
        "double",
        "slow-double",
        "hold",
        "encoder",
        "c-chord",
        "late-arm",
        "shortcuts",
    ),
    default="double",
)
args = p.parse_args()
provenance = doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.recorder_normal import StockRecorderPeer
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.runtime import STOCK_MAIN
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
report = dict(
    status="running",
    context=args.context,
    gesture=args.gesture,
    provenance=provenance,
    firmware="Digitakt II OS 1.16",
    binding_installed=False,
    modeled_armed_status=args.model_armed_status,
    modeled_status_returns=0,
    panel_inputs=[],
    constructed_events=[],
    dispatch=[],
    recorder_calls=[],
    stages=[],
    source_manifest_sha256=sha256(out / "sources.json"),
)
session = None
stage_name = "setup"
controller = None
settings_address = None

try:
    session = Session(
        Take(bytes(480000 * 4), True), out, adapter_factory=StockRecorderPeer
    )
    fw = session.flex.fw
    main = STOCK_MAIN.read_bytes()
    code_sites = (0x40114624, 0x4011E038, 0x4011DC68, 0x40016B3A, 0x40064C3E)
    code_before = {hex(pc): fw.read(pc, 16).hex() for pc in code_sites}
    require(
        all(
            fw.read(pc, 16) == main[pc - 0x40000400 : pc - 0x40000400 + 16]
            for pc in code_sites
        ),
        "Observed stock key code is patched",
    )
    ips = session.runtime["timers"].sources[0].ips
    report["timing"] = dict(
        pit_instructions_per_second=ips,
        ssi_request_hz=96000,
        original_gui_dwell_chunks=session.emu._dwell_chunks,
        probe_gui_dwell_chunks=0,
        chunk_instructions=session.gui.BUDGET,
        native_panel_timer_pc="0x4011dc68",
        native_panel_tick_start=fw.u32(0x47DDEC1C),
        native_repeat_divisor=fw.u32(0x402B4058),
        native_double_window_ticks=fw.u32(0x402B405C),
        unsupported_dtim_timestamp=fw.u32(0xFC07000C),
    )
    # Separate, paused advances keep each physical edge distinct. Disable only
    # frontend queue pacing; leave firmware edge/tap/chord logic untouched.
    session.emu._dwell_chunks = 0

    def observe(uc, pc, *_):
        global controller, settings_address
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        now = session.flex.tick()
        if pc == 0x40114624:
            values = [fw.u32(sp + 4 + i * 4) for i in range(5)]
            if values[1] in (10, 12, 17, 20, 21, 43, 50):
                report["constructed_events"].append(
                    dict(
                        stage=stage_name,
                        tick=now,
                        panel_tick=fw.u32(0x47DDEC1C),
                        args=values,
                        caller=hex(fw.u32(sp)),
                    )
                )
        elif pc == 0x401146A4:
            event = fw.u32(sp + 4)
            key = fw.u32(event + 12)
            if key in (43, 50):
                report["dispatch"].append(
                    dict(
                        stage=stage_name,
                        tick=now,
                        key=key,
                        flags=fw.u32(event + 16),
                        caller=hex(fw.u32(sp)),
                    )
                )
        elif pc == 0x4004CD26:
            settings_address = uc.reg_read(k.UC_M68K_REG_A0)
        elif pc == 0x400CD702:
            # The generic SSI peer supplies zero (capture has started). A quiet
            # armed-state fixture needs the external status to remain nonzero.
            # This models that input boundary only; it neither seeds native
            # controller state nor implements capture/threshold detection.
            if (
                args.model_armed_status
                and controller
                and fw.u32(fw.u32(controller + 16) + 0xA4) == 1
            ):
                uc.reg_write(k.UC_M68K_REG_D0, 1)
                uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
                uc.reg_write(k.UC_M68K_REG_A7, sp + 4)
                report["modeled_status_returns"] += 1
        else:
            controller = fw.u32(sp + 4)
            if pc != 0x40015F6C:
                report["recorder_calls"].append(
                    dict(
                        stage=stage_name,
                        tick=now,
                        pc=hex(pc),
                        controller=hex(controller),
                        caller=hex(fw.u32(sp)),
                    )
                )

    for pc in (
        0x40114624,
        0x401146A4,
        0x40015F6C,
        0x40015F9C,
        0x40015FBC,
        0x40015FDA,
        0x40015FF8,
        0x40016020,
        0x4001603C,
        0x400161FE,
        0x400162C0,
        0x400CD702,
        0x4004CD26,
    ):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def wait_ms(ms):
        # Session.advance adds one budget; count the observed tick delta below.
        session.advance(max(0, round(ips * ms / 1000) - session.gui.BUDGET))

    def edge(name, kind, ms=55):
        code = next(
            n for n, label in session.emu.button_names.items() if label.upper() == name
        )
        report["panel_inputs"].append(
            dict(
                stage=stage_name,
                tick=session.flex.tick(),
                name=name,
                kind=kind,
                wait_ms=ms,
            )
        )
        session.emu.inbox.append((kind, code, None))
        wait_ms(ms)

    def tap(name, ms=55):
        edge(name, "press", ms)
        edge(name, "release", ms)

    def chord(modifier, name):
        edge(modifier, "press")
        tap(name)
        edge(modifier, "release")

    def stage(name):
        global stage_name
        stage_name = name
        session.screenshot(name)
        state = None
        if controller:
            state = fw.u32(fw.u32(controller + 16) + 0xA4)
        report["stages"].append(
            dict(
                name=name,
                tick=session.flex.tick(),
                panel_tick=fw.u32(0x47DDEC1C),
                instructions=session.emu.stats["instrs"],
                cpu_control_frames=session.emu.live_peer.frames,
                recorder_state=state,
                peer_phase=session.flex.phase,
                captured=session.flex.input.captured,
                completed_sha256=(
                    hashlib.sha256(session.flex.input.completed).hexdigest()
                    if session.flex.input.completed is not None
                    else None
                ),
                oled_sha256=sha256(out / f"{name}.png"),
            )
        )

    if args.context == "playing":
        tap("PLAY")
    elif args.context == "armed":
        # The global shortcut arms from SRC. On the recorder's own ready
        # page, YES reaches its manual-start handler before the global hook.
        chord("SAMPLING", "YES")
    elif args.context != "performance":
        tap("SAMPLING")
        if args.context in ("recording", "background-recording", "trim", "name"):
            tap("YES")
            require(session.flex.phase == "recording", "Manual capture did not start")
            if args.context == "background-recording":
                tap("SRC")
            if args.context in ("trim", "name"):
                wait_ms(100)
                tap("YES")
                require(session.flex.phase == "trim", "Manual capture did not finish")
                if args.context == "name":
                    tap("YES")
    wait_ms(650)  # Isolate setup taps from the observed gesture.
    stage("00-before")
    if args.context == "armed":
        require(
            report["stages"][-1]["recorder_state"] == 1,
            "Fixture did not reach native armed state",
        )
    report["setup_event_count"] = len(report["constructed_events"])

    if args.gesture in ("single", "double", "slow-double"):
        edge("SAMPLING", "press")
        stage("01-held")
        edge("SAMPLING", "release")
        stage("02-first-release")
        if args.gesture != "single":
            if args.gesture == "slow-double":
                wait_ms(600)
            edge("SAMPLING", "press")
            stage("03-second-held")
            edge("SAMPLING", "release")
            stage("04-second-release")
    elif args.gesture in ("hold", "encoder"):
        edge("SAMPLING", "press", 80)
        stage("01-held-80ms")
        if args.gesture == "encoder":
            code = next(
                n
                for n, label in session.emu.encoder_names.items()
                if label == "ENCODER C"
            )
            session.emu.inbox.append(("encoder", code, 5))
            report["panel_inputs"].append(
                dict(
                    stage=stage_name,
                    tick=session.flex.tick(),
                    name="ENCODER C",
                    kind="turn",
                    delta=5,
                )
            )
        for ms, name in (
            (320, "02-held-400ms"),
            (400, "03-held-800ms"),
            (400, "04-held-1200ms"),
        ):
            wait_ms(ms)
            stage(name)
        edge("SAMPLING", "release")
        stage("05-release")
    elif args.gesture == "c-chord":
        edge("SAMPLING", "press")
        tap("ENCODER C")
        stage("01-c-pushed")
        edge("SAMPLING", "release")
        stage("02-release")
    elif args.gesture == "late-arm":
        edge("SAMPLING", "press", 800)
        stage("01-held-before-late-yes")
        tap("YES")
        stage("02-late-yes")
        edge("SAMPLING", "release")
        stage("03-release")
    else:
        chord("SAMPLING", "YES")
        stage("01-stock-arm")
        chord("SAMPLING", "NO")
        stage("02-stock-cancel")
        chord("FUNC", "SAMPLING")
        stage("03-stock-browser")
        tap("NO")
        tap("SRC")
        tap("STOP")
        tap("STOP")
        stage("04-double-stop")
    wait_ms(500)
    stage("99-settled")
    report["recorder_settings_address"] = (
        hex(settings_address) if settings_address else None
    )
    require(
        {hex(pc): fw.read(pc, 16).hex() for pc in code_sites} == code_before,
        "Stock key code changed",
    )
    report["unmodified_key_code"] = code_before
    require(source_hashes() == sources, "Source drift")
    report["status"] = "observed"
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
