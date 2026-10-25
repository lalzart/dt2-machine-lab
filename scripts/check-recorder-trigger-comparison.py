#!/usr/bin/env python3
# ruff: noqa: E402
"""Fresh native-panel trials comparing two front ends and one dry request sink."""

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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--validate-only", action="store_true")
args = parser.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored output")
cases = []


def add(
    name,
    case,
    method="chord",
    *,
    enabled=True,
    dest=1,
    context="performance",
    buf_arm="next-bar",
    bars=False,
    ticks=6,
    source_main=False,
):
    cases.append(
        dict(
            name=name,
            case=case,
            method=method,
            enabled=enabled,
            dest=dest,
            context=context,
            buf_arm=buf_arm,
            bars=bars,
            ticks=ticks,
            source_main=source_main,
        )
    )


for method in ("double", "chord", "both"):
    for case in ("single", "double", "arm-chord", "hold"):
        add(f"{method}-{case}", case, method)
add("main-double", "double", "double", source_main=True)
add("main-chord", "arm-chord", "chord", source_main=True)
for method in ("chord", "both"):
    for case in ("chord-encoder", "encoder-gap"):
        add(f"{method}-{case}", case, method)
add("double-encoder-gap", "encoder-gap", "double")
for enabled in (False, True):
    for case in ("single", "double", "hold", "arm-chord"):
        add(f"normal-{int(enabled)}-{case}", case, "both", enabled=enabled, dest=0)
for enabled in (False, True):
    add(
        f"buf-stock-{int(enabled)}",
        "arm-chord",
        "both",
        enabled=enabled,
        buf_arm="stock",
    )
add("model-double", "double", "double", bars=True, context="playing")
add("model-chord", "arm-chord", "chord", bars=True, context="playing")
add("repeat-double", "repeat-double", "double")
add("repeat-chord", "repeat-chord", "chord")
for context in ("ready", "armed", "recording", "background", "trim", "name"):
    add(
        f"context-{context}",
        "hold" if context in ("trim", "name") else "arm-chord",
        context=context,
    )
for dest in (2, 3, 4):
    add(f"buf-{dest}", "arm-chord", dest=dest)
add("late-chord", "late-arm", "both")
add("chord-then-hold", "chord-then-hold")
for case in ("armed-stop", "armed-project", "armed-destination", "armed-busy"):
    add(case, case, bars=True)
for case in ("func-first", "sampling-func", "chords", "unobserved-settings"):
    add(case, case, "both")
for ticks in (24, 40):
    for method in ("double", "chord"):
        add(f"latency-{method}-{ticks}", "single", method, ticks=ticks)
for case in ("single", "double", "hold"):
    add(f"legacy-{case}", case, None)

if not args.validate_only:
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "sources.json", source_hashes())

    def run(cfg):
        command = [
            sys.executable,
            str(ROOT / "scripts/check-recorder-gesture-dry.py"),
            str(out / cfg["name"]),
            "--case",
            cfg["case"],
            "--destination",
            str(cfg["dest"]),
            "--context",
            cfg["context"],
            "--buf-arm",
            cfg["buf_arm"],
            "--tap-ticks",
            str(cfg["ticks"]),
        ]
        if cfg["method"]:
            command += ["--compare-trigger", cfg["method"]]
        if cfg["enabled"]:
            command += ["--dry-run"]
        if cfg["bars"]:
            command += ["--model-bars"]
        if cfg["source_main"]:
            command += ["--source-main"]
        with (out / f"{cfg['name']}.log").open("w") as stream:
            result = subprocess.run(
                command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT
            )
        path = out / cfg["name"] / "report.json"
        report = json.loads(path.read_text()) if path.exists() else {}
        item = dict(
            case=cfg,
            command=command,
            exit_code=result.returncode,
            status=report.get("status"),
            error=report.get("error"),
        )
        print(json.dumps(item), flush=True)
        return item

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, cases))
    write_json(out / "matrix.json", results)

results = json.loads((out / "matrix.json").read_text())
checks, reports = [], {}


def check(value, label):
    require(value, label)
    checks.append(label)


check(len(results) == len(cases), "Complete matrix")
for item in results:
    cfg, name = item["case"], item["case"]["name"]
    check(
        item["exit_code"] == 0 and item["status"] == "observed",
        f"{name}: execution ({item.get('error')})",
    )
    r = reports[name] = json.loads((out / name / "report.json").read_text())
    check(
        not any(
            r[k]
            for k in (
                "native_recorder_connected",
                "native_freeze_connected",
                "native_bar_clock_connected",
            )
        ),
        f"{name}: no native backend",
    )
    check(r["slots_before"] == r["slots_after"], f"{name}: assignments preserved")
    check(r["resources_before"] == r["resources_after"], f"{name}: resources preserved")
    check(
        r["stages"][-1]["cpu_control_frames"] > r["stages"][0]["cpu_control_frames"],
        f"{name}: original control frames advance",
    )
    check(
        json.loads((out / name / "sources.json").read_text())
        == json.loads((out / "sources.json").read_text()),
        f"{name}: identical source freeze",
    )
    log = r.get("request_log", [])
    requests = [e for e in log if e["trigger"] in ("double", "chord")]
    active = (
        cfg["enabled"]
        and cfg["dest"] > 0
        and cfg["context"] in ("performance", "playing")
    )
    expected = []
    if active and cfg["method"]:
        if cfg["case"] in ("double", "repeat-double") and cfg["method"] != "chord":
            expected = ["double"] * (2 if cfg["case"] == "repeat-double" else 1)
        chord_case = cfg["case"] in (
            "arm-chord",
            "chord-encoder",
            "chord-then-hold",
            "repeat-chord",
            "chords",
            "late-arm",
            "unobserved-settings",
        )
        if (
            (chord_case or cfg["case"].startswith("armed-"))
            and cfg["method"] != "double"
            and cfg["buf_arm"] == "next-bar"
        ):
            expected = ["chord"] * (2 if cfg["case"] == "repeat-chord" else 1)
    check(
        [e["trigger"] for e in requests] == expected, f"{name}: expected trigger only"
    )
    chord_requests = [e for e in requests if e["trigger"] == "chord"]
    suppressed = [e for e in r.get("arm_entry_log", []) if e["suppressed"]]
    check(
        len(suppressed) == len(chord_requests),
        f"{name}: only stock-detected global ARM is intercepted",
    )
    check(
        all(e["caller"] == "0x40016bae" for e in suppressed),
        f"{name}: authenticated ARM caller",
    )
    if requests and cfg["case"] != "unobserved-settings":
        if cfg["source_main"]:
            check(
                bytes.fromhex(requests[0]["plan"]["settings"])[:4]
                == (16).to_bytes(4, "big"),
                f"{name}: cold MAIN settings work without MON bootstrap",
            )
        check(
            requests[0]["plan"]["destination"] == cfg["dest"],
            f"{name}: latched destination",
        )
        check(
            len(bytes.fromhex(requests[0]["plan"]["settings"])) == 36,
            f"{name}: entire native recorder settings block latched",
        )
    if cfg["case"].startswith("repeat-"):
        check(
            [e["result"] for e in requests] == ["unclocked", "canceled"]
            and r["request_serial"] == 1,
            f"{name}: repeat cancels the same request",
        )
    starts = [e for e in log if e.get("would_start")]
    check(
        len(starts) == int(name in ("model-double", "model-chord")),
        f"{name}: only explicit next TEST bar can produce would-record",
    )
    if (
        expected
        and cfg["case"] not in ("chords", "late-arm", "unobserved-settings")
        and not cfg["case"].startswith("armed-")
    ):
        check(
            not [d for d in r["recorder_draws"] if d["stage"] != "setup"],
            f"{name}: request stays on performance page",
        )
        check(
            r["stages"][-1]["recorder_state"] == 0,
            f"{name}: original recorder never armed",
        )
    if cfg["context"] in ("trim", "name"):
        check(
            len({s["completed_pcm_sha256"] for s in r["stages"]}) == 1,
            f"{name}: candidate PCM preserved",
        )

for case in ("single", "double", "hold", "arm-chord"):
    a, b = reports[f"normal-0-{case}"], reports[f"normal-1-{case}"]
    check(
        a["constructed_events"] == b["constructed_events"],
        f"NORMAL {case}: exact native events/timing",
    )
    check(
        [s["raw_oled_sha256"] for s in a["stages"]]
        == [s["raw_oled_sha256"] for s in b["stages"]],
        f"NORMAL {case}: exact stock OLED",
    )
    check(not b["navigation"], f"NORMAL {case}: no delayed replay")
a, b = reports["buf-stock-0"], reports["buf-stock-1"]
check(
    a["constructed_events"] == b["constructed_events"]
    and [s["raw_oled_sha256"] for s in a["stages"]]
    == [s["raw_oled_sha256"] for s in b["stages"]],
    "BUF stock option retains original arming",
)


def first_plan(name):
    return next(
        e["plan"]
        for e in reports[name]["request_log"]
        if e["trigger"] in ("double", "chord")
    )


check(
    first_plan("both-double") == first_plan("both-arm-chord"),
    "Both inputs supply the exact same backend plan",
)
check(
    first_plan("model-double") == first_plan("model-chord"),
    "Same settings, clock and next-bar plan across trials",
)
check(
    reports["both-chord-encoder"]["kit_after"]
    == reports["chord-chord-encoder"]["kit_after"],
    "Chord encoder edits are identical with double recognition enabled/disabled",
)
check(
    reports["chord-chord-encoder"]["kit_before"]
    != reports["chord-chord-encoder"]["kit_after"],
    "Encoder edits actually change performance parameters",
)
check(
    [
        e["kind"]
        for e in reports["chord-then-hold"]["gesture_log"]
        if e["kind"].startswith("would-")
    ]
    == ["would-arm"],
    "Completed chord cannot later become a hold FREEZE",
)
check(
    [
        e["result"]
        for e in reports["unobserved-settings"]["request_log"]
        if e["trigger"] == "chord"
    ]
    == ["refused"],
    "Unobserved project settings refuse instead of falling through to native ARM",
)

latency = []
for ticks in (6, 24, 40):
    for method in ("double", "chord"):
        name = f"{method}-single" if ticks == 6 else f"latency-{method}-{ticks}"
        r = reports[name]
        up = next(
            e
            for e in r["constructed_events"][r["setup_event_count"] :]
            if e["key"] == 50 and e["flags"] == 16
        )
        draw = next(
            d
            for d in r["recorder_draws"]
            if d["stage"] != "setup" and d["tick"] >= up["tick"]
        )
        latency.append(
            dict(
                method=method,
                press_ticks=ticks,
                release_to_draw_ticks=draw["tick"] - up["tick"],
                model_ms=(draw["pit_now"] - up["pit_now"])
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
        cases=len(cases),
        assertion_count=len(checks),
        checks=checks,
        latency=latency,
        source_manifest_sha256=sha256(out / "sources.json"),
        reports={n: sha256(out / n / "report.json") for n in reports},
    ),
)
print(f"PASS: {len(cases)} cases, {len(checks)} assertions")
