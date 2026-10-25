#!/usr/bin/env python3
# ruff: noqa: E402
"""Opt-in dry SAMPLING prototype, with original UART input and stock GUI."""

import argparse
import hashlib
import os
import shutil
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import (
    doctor,
    git,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--dry-run", action="store_true", help="Opt in; otherwise stock gesture control"
)
p.add_argument("--destination", type=int, choices=range(5), default=1)
p.add_argument(
    "--source-main", action="store_true", help="Seed a cold MAIN-source project fixture"
)
p.add_argument("--compare-trigger", choices=("double", "chord", "both"))
p.add_argument("--buf-arm", choices=("stock", "next-bar"), default="next-bar")
p.add_argument(
    "--model-bars", action="store_true", help="Explicit TEST clock; never native bars"
)
p.add_argument(
    "--tap-ticks",
    type=int,
    default=6,
    help="First physical press duration, 1..63 native panel ticks",
)
p.add_argument(
    "--context",
    choices=(
        "performance",
        "playing",
        "ready",
        "armed",
        "recording",
        "background",
        "trim",
        "name",
    ),
    default="performance",
)
p.add_argument("--page", choices=("SRC", "AMP", "FLTR", "LFO"), default="SRC")
p.add_argument(
    "--case",
    choices=(
        "single",
        "double",
        "slow",
        "hold",
        "long-hold",
        "double-hold",
        "triple",
        "encoder-hold",
        "encoder-after-tap",
        "yes-after-tap",
        "chords",
        "late-arm",
        "func-first",
        "sampling-func",
        "c-first",
        "c-chord",
        "stop",
        "project",
        "destination",
        "busy",
        "arm-chord",
        "chord-encoder",
        "chord-then-hold",
        "repeat-chord",
        "repeat-double",
        "encoder-gap",
        "armed-stop",
        "armed-project",
        "armed-destination",
        "armed-busy",
        "unobserved-settings",
    ),
    default="double",
)
p.add_argument("--window", action="store_true")
p.add_argument("--window-seconds", type=int, default=600)
args = p.parse_args()
require(10 <= args.window_seconds <= 1800, "Window lifetime 10..1800 seconds")
require(1 <= args.tap_ticks < 64, "Tap duration 1..63 ticks")
provenance = doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.recorder_gesture_ui import DryRunUI
from lab.flex_recorder import Take
from lab.flex_session import Session
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
    arguments=vars(args) | {"output": str(out)},
    provenance=provenance,
    head=git(ROOT, "rev-parse", "HEAD"),
    source_manifest_sha256=sha256(out / "sources.json"),
    host_recognizer=True,
    host_oled_overlay=True,
    native_recorder_connected=False,
    native_freeze_connected=False,
    native_bar_clock_connected=False,
    shared_request_model=bool(args.compare_trigger),
    model_bar_events=args.model_bars,
    button_aliases={"LFO": "MOD"},
    constructed_events=[],
    recorder_calls=[],
    stages=[],
    panel_inputs=[],
    encoder_routes=[],
    recorder_draws=[],
)
session = None
stage_name = "setup"
try:
    waiting_model = args.context == "armed" or args.case in ("chords", "late-arm")
    waiting_model |= args.destination == 0 and args.case in (
        "arm-chord",
        "chord-encoder",
        "chord-then-hold",
        "repeat-chord",
    )
    waiting_model |= args.buf_arm == "stock" or args.compare_trigger == "double"
    waiting_model |= args.case in (
        "arm-chord",
        "chord-encoder",
        "chord-then-hold",
        "repeat-chord",
    )
    adapter = DryRunUI
    adapter_options = {}
    if args.compare_trigger:
        from lab.recorder_trigger_ui import TriggerComparisonUI

        adapter = TriggerComparisonUI
        adapter_options = dict(
            trigger_method=args.compare_trigger, buf_arm=args.buf_arm
        )
    session = Session(
        Take(bytes(480000 * 4), True),
        out,
        adapter_factory=partial(
            adapter,
            gestures_enabled=args.dry_run,
            model_armed_status=waiting_model,
            **adapter_options,
        ),
    )
    ui, fw = session.flex, session.flex.fw
    if args.source_main:
        require(args.compare_trigger, "MAIN source fixture requires comparison mode")
        source_seed = []
        require(
            fw.read(0x4004CC96, 4) == bytes.fromhex("202801ae"), "Source getter drift"
        )

        def seed_main(uc, *_):
            if not source_seed:
                address = uc.reg_read(k.UC_M68K_REG_A0) + 0x1AE
                require(fw.u32(address) == 18, "Expected initial IN source")
                fw.write(address, (16).to_bytes(4, "big"))
                source_seed.append(address)

        fw.uc.hook_add(UC_HOOK_CODE, seed_main, begin=0x4004CC96, end=0x4004CC96)
        ui._settings_data = ui._settings_owner = None
        report["source_fixture"] = (
            "MAIN seeded through original source getter before first sampler draw"
        )
    if args.compare_trigger:
        ui.gestures_enabled = False  # Establish stock recorder-state fixtures first.
    session.emu._dwell_chunks = 0
    ips = session.runtime["timers"].sources[0].ips
    report["timing"] = dict(
        pit_ips=ips,
        native_double_ticks=fw.u32(0x402B405C),
        native_panel_counter="0x47ddec1c",
        model_armed_status=waiting_model,
    )

    def observe(uc, pc, *_):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == 0x40114624:
            key, flags = fw.u32(sp + 8), fw.u32(sp + 12)
            report["constructed_events"].append(
                dict(
                    stage=stage_name,
                    tick=ui.now(),
                    key=key,
                    flags=flags,
                    pit_now=session.runtime["timers"].now,
                )
            )
        elif pc == 0x40021DE0:
            report["recorder_draws"].append(
                dict(
                    stage=stage_name,
                    tick=ui.now(),
                    pit_now=session.runtime["timers"].now,
                )
            )
        elif pc == 0x10300800:
            event = uc.reg_read(k.UC_M68K_REG_D2)
            report["encoder_routes"].append(
                dict(
                    stage=stage_name,
                    tick=ui.now(),
                    event=hex(event),
                    channel=fw.u32(event + 12),
                    destination=ui.destination,
                )
            )
        else:
            report["recorder_calls"].append(
                dict(
                    stage=stage_name, tick=ui.now(), pc=hex(pc), caller=hex(fw.u32(sp))
                )
            )

    for pc in (
        0x40114624,
        0x40015F9C,
        0x40015FDA,
        0x400161FE,
        0x40015FF8,
        0x40016020,
        0x4001603C,
        0x10300800,
        0x40021DE0,
    ):
        fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)

    def wait_ticks(count):
        target = ui.now() + count
        bound = session.emu.stats["instrs"] + max(40_000_000, count * 2_000_000)
        while ui.now() < target:
            require(session.emu.stats["instrs"] < bound, "Panel timer advance stalled")
            step = max(1, min(target - ui.now(), 4))
            session.advance(max(0, round(ips * step / 120) - session.gui.BUDGET))

    def edge(name, kind, ticks=6):
        native_name = report["button_aliases"].get(name, name)
        code = next(
            n
            for n, label in session.emu.button_names.items()
            if label.upper() == native_name
        )
        report["panel_inputs"].append(
            dict(stage=stage_name, tick=ui.now(), name=name, kind=kind)
        )
        session.emu.inbox.append((kind, code, None))
        session.advance(0)
        wait_ticks(ticks)

    def tap(name, ticks=6):
        edge(name, "press", ticks)
        edge(name, "release", ticks)

    def turn(name, delta=5):
        code = next(
            n
            for n, label in session.emu.encoder_names.items()
            if label == f"ENCODER {name}"
        )
        report["panel_inputs"].append(
            dict(
                stage=stage_name, tick=ui.now(), name=name, kind="encoder", delta=delta
            )
        )
        session.emu.inbox.append(("encoder", code, delta))
        session.advance()

    def chord(modifier, name):
        edge(modifier, "press")
        tap(name)
        edge(modifier, "release")

    def stage(name):
        global stage_name
        stage_name = name
        session.screenshot(name)
        raw = ui._raw_panel or session.emu._panel_latch
        completed = ui.input.completed
        report["stages"].append(
            dict(
                name=name,
                tick=ui.now(),
                instructions=session.emu.stats["instrs"],
                pit_now=session.runtime["timers"].now,
                destination=ui.destination,
                recorder_state=ui.context().recorder_state,
                mode=ui.gestures.mode,
                pending=ui.gestures.pending is not None,
                feedback=ui.feedback.kind if ui.feedback else None,
                raw_oled_sha256=hashlib.sha256(raw).hexdigest(),
                shown_oled_sha256=sha256(out / f"{name}.png"),
                captured=ui.input.captured,
                completed_pcm_sha256=hashlib.sha256(completed).hexdigest()
                if completed is not None
                else None,
                cpu_control_frames=session.emu.live_peer.frames,
            )
        )

    # Select the actual C destination before testing the performance shortcut.
    tap("SAMPLING")
    initial_destination = 0 if args.context == "name" else args.destination
    for _ in range(30):
        if ui.destination == initial_destination:
            break
        turn("C", 5 if ui.destination < initial_destination else -5)
    require(ui.destination == initial_destination, "C destination not reached")
    report["recorder_settings"] = fw.u32(ui.view + 0xA0)
    if args.context != "ready":
        tap("SRC")
    if args.page != "SRC":
        tap(args.page)
    if args.context == "playing":
        tap("PLAY")
    if args.context == "armed":
        chord("SAMPLING", "YES")
    elif args.context in ("recording", "background", "trim", "name"):
        tap("SAMPLING")
        tap("YES")
        require(ui.input.active, "Manual fixture did not start")
        if args.context == "background":
            tap("SRC")
        if args.context in ("trim", "name"):
            wait_ticks(12)
            tap("YES")
            require(ui.input.completed is not None, "Manual fixture did not stop")
            if args.context == "name":
                # Keep original NORMAL save/name path for this modal fixture.
                tap("YES")
                if args.destination:
                    from lab.flex_buffer_ui import STATE

                    fw.write(STATE, args.destination.to_bytes(4, "big"))
                    report["injected_modal_destination"] = True
    wait_ticks(80)
    if args.compare_trigger:
        ui.gestures_enabled = args.dry_run
        report["stock_fixture_setup"] = True
    ui.gesture_log.clear()
    ui.navigation.clear()
    report["setup_event_count"] = len(report["constructed_events"])
    report["setup_call_count"] = len(report["recorder_calls"])
    report["kit_before"] = fw.read(fw.u32(0x80004704), 16 * 0x450).hex()
    report["resources_before"] = dict(
        issued=ui.issued,
        sources=len(fw.sources),
        handles=len(fw.handles),
        pages=len(ui.pages),
    )
    report["slots_before"] = [
        fw.read(fw.u32(0x80004704) + n * 0x450 + 0x80, 2).hex() for n in range(16)
    ]
    stage("00-before")
    if args.model_bars:
        require(args.compare_trigger, "TEST bars require the comparison adapter")
        ui.test_bar(10)

    if args.window:
        from lab.recorder_gesture_window import open_window

        note = (
            f"{args.compare_trigger.upper()} trial; BUF chord {args.buf_arm}; DRY MODEL"
            if args.compare_trigger
            else ""
        )
        open_window(
            session,
            seconds=args.window_seconds,
            comparison_note=note,
            model_bar=ui.queue_test_bar
            if args.compare_trigger and args.model_bars
            else None,
        )
    elif args.case.startswith("armed-") or args.case == "unobserved-settings":
        require(args.compare_trigger, "Request controls require comparison mode")
        if args.case == "unobserved-settings":
            ui._settings_owner = None
        chord("SAMPLING", "YES")
        stage("01-request")
        if args.case == "armed-stop":
            tap("STOP")
        elif args.case == "armed-project":
            ui.invalidate_gesture("injected-project-epoch", project=True)
        elif args.case == "armed-destination":
            from lab.flex_buffer_ui import STATE

            fw.write(STATE, (2).to_bytes(4, "big"))
        elif args.case == "armed-busy":
            ui.pending = ("injected-publication",)
            ui.gesture_hook(fw.uc, 0x40033D00, 0, None)
            ui.pending = None
        wait_ticks(40)
        stage("02-request-control")
    elif args.case in ("arm-chord", "chord-encoder", "chord-then-hold", "repeat-chord"):
        edge("SAMPLING", "press")
        if args.case == "chord-encoder":
            for name, delta in (("A", 127), ("A", 127), ("C", -127), ("C", -127)):
                turn(name, delta)
        tap("YES")
        stage("01-chord")
        if args.case == "chord-then-hold":
            wait_ticks(80)
        edge("SAMPLING", "release")
        if args.case == "repeat-chord":
            chord("SAMPLING", "YES")
        wait_ticks(40)
        stage("02-chord-complete")
    elif args.case == "repeat-double":
        for _ in range(2):
            tap("SAMPLING")
            tap("SAMPLING")
            wait_ticks(40)
        stage("01-two-double-gestures")
    elif args.case == "encoder-gap":
        edge("SAMPLING", "press", 3)
        edge("SAMPLING", "release", 2)
        turn("C", 127)
        turn("C", 127)
        tap("SAMPLING")
        wait_ticks(40)
        stage("01-gap-complete")
    elif args.case in ("single", "double", "slow", "double-hold", "triple"):
        edge("SAMPLING", "press", args.tap_ticks)
        stage("01-held")
        edge("SAMPLING", "release")
        stage("02-first-release")
        if args.case == "single":
            wait_ticks(60)
        else:
            if args.case == "slow":
                wait_ticks(40)
            edge("SAMPLING", "press", 90 if args.case == "double-hold" else 6)
            stage("03-second-held")
            edge("SAMPLING", "release")
            if args.case == "triple":
                tap("SAMPLING")
            wait_ticks(40)
        stage("04-complete")
    elif args.case in ("hold", "long-hold", "encoder-hold"):
        edge("SAMPLING", "press")
        stage("01-held")
        if args.case == "encoder-hold":
            # Two turns survive the original scaler's initial filtering.
            # A and C exercise performance parameters without encoder pushes.
            for name, delta in (("A", 127), ("A", 127), ("C", -127), ("C", -127)):
                turn(name, delta)
        wait_ticks(260 if args.case == "long-hold" else 80)
        stage("02-still-held")
        edge("SAMPLING", "release")
        stage("03-released")
    elif args.case == "encoder-after-tap":
        edge("SAMPLING", "press", 3)
        edge("SAMPLING", "release", 2)
        stage("01-tap-pending")
        turn("C", 127)
        turn("C", 127)
        wait_ticks(40)
        stage("02-encoder-routed")
    elif args.case == "yes-after-tap":
        edge("SAMPLING", "press", 3)
        edge("SAMPLING", "release", 2)
        tap("YES")
        wait_ticks(20)
        stage("01-ordinary-manual-record")
    elif args.case == "chords":
        chord("SAMPLING", "YES")
        stage("01-stock-arm")
        chord("SAMPLING", "NO")
        stage("02-stock-cancel")
        chord("FUNC", "SAMPLING")
        stage("03-stock-browser")
    elif args.case == "late-arm":
        edge("SAMPLING", "press", 80)
        stage("01-held-milestone")
        tap("YES")
        edge("SAMPLING", "release")
        stage("02-late-arm")
    elif args.case == "func-first":
        chord("FUNC", "SAMPLING")
        stage("01-stock-browser")
    elif args.case == "sampling-func":
        edge("SAMPLING", "press")
        edge("FUNC", "press")
        edge("SAMPLING", "release")
        edge("FUNC", "release")
        stage("01-reverse-func")
    elif args.case == "c-first":
        edge("ENCODER C", "press")
        edge("SAMPLING", "press", 80)
        edge("SAMPLING", "release")
        edge("ENCODER C", "release")
        stage("01-preheld-c")
    elif args.case == "c-chord":
        chord("SAMPLING", "ENCODER C")
        stage("01-c-chord")
    else:
        edge("SAMPLING", "press", 3)
        if args.case == "stop":
            tap("STOP")
            tap("STOP")
        elif args.case == "project":
            ui.invalidate_gesture("injected-project-epoch", project=True)
        elif args.case == "destination":
            from lab.flex_buffer_ui import STATE

            fw.write(STATE, (2 if ui.destination == 1 else 1).to_bytes(4, "big"))
            report["injected_destination_change"] = True
        elif args.case == "busy":
            ui.pending = ("dry-test-admission",)
            # Poll the actual state contract without running a fake backend job.
            ui.effects(ui.gestures.poll(ui.now(), ui.context()), 0x40033D00)
            ui.pending = None
            report["injected_busy_state"] = True
        edge("SAMPLING", "release")
        wait_ticks(80)
        stage("01-canceled")
    if args.model_bars:
        ui.test_bar(10)  # A duplicate current-bar event must never start.
        stage("80-duplicate-bar")
        ui.test_bar(11)
        ui.test_bar(11)
        stage("81-next-test-bar")
    wait_ticks(12)
    stage("99-settled")
    report["gesture_log"] = ui.gesture_log
    report["navigation"] = ui.navigation
    report["encoder_log"] = ui.encoder_log
    report["recorder_ui_events"] = ui.events
    report["bridge_log"] = ui.bridge_log
    report["kit_after"] = fw.read(fw.u32(0x80004704), 16 * 0x450).hex()
    report["resources_after"] = dict(
        issued=ui.issued,
        sources=len(fw.sources),
        handles=len(fw.handles),
        pages=len(ui.pages),
    )
    report["status_model_reads"] = ui.status_model_reads
    if args.compare_trigger:
        report["request_log"] = ui.request_log
        report["request_state"] = ui.arm_requests.state
        report["request_serial"] = ui.arm_requests.serial
        report["arm_entry_log"] = ui.arm_entry_log
    report["slots_after"] = [
        fw.read(fw.u32(0x80004704) + n * 0x450 + 0x80, 2).hex() for n in range(16)
    ]
    require(
        report["slots_before"] == report["slots_after"],
        "Dry shortcut changed track sample assignments",
    )
    require(source_hashes() == sources, "Source drift")
    report["status"] = "observed"
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
