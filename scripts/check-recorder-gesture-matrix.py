#!/usr/bin/env python3
# ruff: noqa: E402
"""Reproduce the isolated dry-SAMPLING matrix and compare NORMAL controls."""

import argparse
import concurrent.futures
import json
import os
import subprocess
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
p.add_argument("--validate-only", action="store_true")
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")

cases = []


def add(
    name,
    case,
    *,
    enabled=True,
    destination=1,
    context="performance",
    page="SRC",
    tap_ticks=6,
):
    cases.append(
        dict(
            name=name,
            case=case,
            enabled=enabled,
            destination=destination,
            context=context,
            page=page,
            tap_ticks=tap_ticks,
        )
    )


for case in (
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
    "c-chord",
    "c-first",
    "stop",
    "project",
    "destination",
    "busy",
):
    add(case, case)
for enabled in (False, True):
    for case in ("single", "double", "hold"):
        add(f"normal-{int(enabled)}-{case}", case, enabled=enabled, destination=0)
for context in ("ready", "armed", "recording", "background", "trim", "name"):
    for case in ("double", "hold"):
        add(f"{context}-{case}", case, context=context)
for page in ("AMP", "FLTR", "LFO"):
    add(f"page-{page}", "hold", page=page)
for case in ("single", "double", "hold", "encoder-hold"):
    add(f"playing-{case}", case, context="playing")
for destination in (2, 3, 4):
    add(f"buf-{destination}", "double", destination=destination)
for ticks in (6, 24, 40):
    add(f"latency-stock-{ticks}", "single", enabled=False, tap_ticks=ticks)
    if ticks != 6:
        add(f"latency-dry-{ticks}", "single", tap_ticks=ticks)
add("encoder-stock", "encoder-after-tap", enabled=False)
add("encoder-hold-stock", "encoder-hold", enabled=False)
add("reverse-func-stock", "sampling-func", enabled=False)

if not args.validate_only:
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "sources.json", source_hashes())

    def run(case):
        target = out / case["name"]
        command = [
            sys.executable,
            str(ROOT / "scripts/check-recorder-gesture-dry.py"),
            str(target),
            "--case",
            case["case"],
            "--destination",
            str(case["destination"]),
            "--context",
            case["context"],
            "--page",
            case["page"],
            "--tap-ticks",
            str(case["tap_ticks"]),
        ]
        if case["enabled"]:
            command.append("--dry-run")
        with (out / f"{case['name']}.log").open("w") as log:
            result = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
            )
        path = target / "report.json"
        report = json.loads(path.read_text()) if path.exists() else {}
        item = dict(
            case=case,
            command=command,
            exit_code=result.returncode,
            status=report.get("status"),
            report=str(path),
            error=report.get("error"),
        )
        print(json.dumps(item), flush=True)
        return item

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(run, cases))
    write_json(out / "matrix.json", results)

results = json.loads((out / "matrix.json").read_text())
checks = []


def check(value, label):
    require(value, label)
    checks.append(label)


reports = {}
check(len(results) == len(cases), "Complete case list")
for item in results:
    name, cfg = item["case"]["name"], item["case"]
    check(
        item["exit_code"] == 0 and item["status"] == "observed",
        f"{name}: completed ({item.get('error')})",
    )
    r = reports[name] = json.loads(Path(item["report"]).read_text())
    check(
        not any(
            r[k]
            for k in (
                "native_recorder_connected",
                "native_freeze_connected",
                "native_bar_clock_connected",
            )
        ),
        f"{name}: no backend connected",
    )
    check(r["slots_before"] == r["slots_after"], f"{name}: assignments preserved")
    check(
        r["resources_before"] == r["resources_after"],
        f"{name}: no resource publication",
    )
    check(
        r["stages"][-1]["cpu_control_frames"] > r["stages"][0]["cpu_control_frames"],
        f"{name}: control frames advance",
    )
    effects = [e for e in r["gesture_log"] if e["kind"].startswith("would-")]
    eligible = (
        cfg["enabled"]
        and cfg["destination"] > 0
        and cfg["context"] in ("performance", "playing")
    )
    expected = None
    if eligible and cfg["case"] in ("double", "double-hold", "triple"):
        expected = "would-arm"
    elif eligible and cfg["case"] in ("hold", "long-hold", "encoder-hold", "late-arm"):
        expected = "would-freeze"
    check(
        [e["kind"] for e in effects] == ([expected] if expected else []),
        f"{name}: expected intent only once",
    )
    if effects:
        check(
            effects[0]["destination"] == cfg["destination"],
            f"{name}: selected logical destination",
        )
    calls = r["recorder_calls"][r["setup_call_count"] :]
    if cfg["case"] not in ("chords", "late-arm", "yes-after-tap"):
        check(not calls, f"{name}: no recorder command from gestures")
    if expected and cfg["case"] != "late-arm":
        check(not r["navigation"], f"{name}: no recorder navigation")
    if cfg["context"] in ("trim", "name"):
        check(
            len({s["completed_pcm_sha256"] for s in r["stages"]}) == 1,
            f"{name}: completed PCM preserved",
        )
    if cfg["context"] == "name":
        check(
            len({s["raw_oled_sha256"] for s in r["stages"]}) == 1,
            f"{name}: name modal unchanged",
        )

for case in ("single", "double", "hold"):
    a, b = reports[f"normal-0-{case}"], reports[f"normal-1-{case}"]
    check(
        [s["raw_oled_sha256"] for s in a["stages"]]
        == [s["raw_oled_sha256"] for s in b["stages"]],
        f"NORMAL {case}: exact stock OLED sequence",
    )
    check(
        a["constructed_events"] == b["constructed_events"],
        f"NORMAL {case}: exact native events and timing",
    )
    check(not b["navigation"], f"NORMAL {case}: no delayed replay")

reverse = reports["sampling-func"]
stock = reports["reverse-func-stock"]
check(
    [s["raw_oled_sha256"] for s in reverse["stages"]]
    == [s["raw_oled_sha256"] for s in stock["stages"]],
    "Reverse FUNC order matches stock",
)
enc = reports["encoder-after-tap"]
check(
    enc["encoder_log"]
    and len([e for e in enc["encoder_log"] if e["kind"] == "defer"])
    == len([e for e in enc["encoder_log"] if e["kind"] == "apply"]),
    "Encoder queue delivered all inputs",
)
check(
    enc["kit_before"] == enc["kit_after"],
    "Post-tap encoders leave playback parameters intact",
)
check(
    enc["stages"][-1]["destination"]
    == reports["encoder-stock"]["stages"][-1]["destination"],
    "Post-tap C selection matches stock",
)
check(
    any(e["stage"] != "setup" for e in enc["encoder_routes"]),
    "Post-tap turn reached original recorder rotation",
)
held = reports["encoder-hold"]
check(
    held["kit_before"] != held["kit_after"],
    "Encoder turns during hold actually change performance parameters",
)
check(
    held["kit_before"] == reports["encoder-hold-stock"]["kit_before"]
    and held["kit_after"] == reports["encoder-hold-stock"]["kit_after"],
    "Encoder changes during hold exactly match stock",
)
check(not held["encoder_log"], "Held encoder turns are neither deferred nor replayed")
yes = reports["yes-after-tap"]
check(
    yes["stages"][-1]["recorder_state"] == 2
    and not [e for e in yes["gesture_log"] if e["kind"].startswith("would-")],
    "Quick released tap then YES uses original manual recorder",
)
latency = []
for ticks in (6, 24, 40):
    for mode in ("stock", "dry"):
        name = f"latency-{mode}-{ticks}" if mode == "stock" or ticks != 6 else "single"
        r = reports[name]
        events = [
            e
            for e in r["constructed_events"][r["setup_event_count"] :]
            if e["key"] == 50
        ]
        release = next(e for e in events if e["flags"] == 16)
        draws = [
            d
            for d in r["recorder_draws"]
            if d["tick"] >= release["tick"] and d["stage"] != "setup"
        ]
        check(bool(draws), f"{name}: recorder eventually draws")
        draw = draws[0]
        latency.append(
            dict(
                name=name,
                requested_press_ticks=ticks,
                release_tick=release["tick"],
                draw_tick=draw["tick"],
                release_to_draw_ticks=draw["tick"] - release["tick"],
                release_to_draw_model_ms=(draw["pit_now"] - release["pit_now"])
                / r["timing"]["pit_ips"]
                * 1000,
            )
        )
check(
    source_hashes() == json.loads((out / "sources.json").read_text()),
    "Source freeze unchanged",
)
write_json(
    out / "verification.json",
    dict(
        status="passed",
        cases=len(results),
        assertion_count=len(checks),
        checks=checks,
        latency=latency,
        source_manifest_sha256=sha256(out / "sources.json"),
        reports={name: sha256(out / name / "report.json") for name in reports},
    ),
)
print(f"PASS: {len(results)} cases, {len(checks)} assertions", flush=True)
