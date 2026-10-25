"""Small command interface for the pinned local experiment."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from lab.project import ROOT, doctor, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description="Digitakt II machine lab (offline)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor", help="verify dependency pins and private fixture hashes"
    )
    from lab.unit import add_arguments as unit_arguments
    from lab.unit import run as unit_run

    unit_arguments(commands.add_parser("unit", help="run scoped unit tests (default: BUF)"))
    from lab.diagnostics import add_arguments
    from lab.diagnostics import main as diagnostics_main

    add_arguments(
        commands.add_parser("diagnostics", help="show saved resource measurements")
    )
    for name in ("build", "render", "profile", "test"):
        sub = commands.add_parser(name)
        sub.add_argument(
            "machine",
            choices=["sine", "plaits", "flex", "capicola", "arp"]
            if name in ("build", "test")
            else ["sine"],
        )
        if name in ("build", "test"):
            sub.add_argument(
                "--shared-save",
                action="store_true",
                help="use typed native save phases (Arp/Flex)",
            )
            sub.add_argument(
                "--runtime-variant",
                choices=("reference", "trace-off", "cached", "cached-trace-off"),
                default="reference",
            )
        if name == "test":
            sub.add_argument(
                "--replay",
                action="store_true",
                required=True,
                help="run the prepared-fixture regression suite",
            )
    plan = commands.add_parser(
        "plan", help="check actual CPU writes and resource capacity before composition"
    )
    plan.add_argument(
        "--mods",
        nargs="+",
        required=True,
        choices=("sine", "plaits", "flex", "capicola", "arp"),
    )
    commands.add_parser(
        "resources",
        help="export per-owner declared bounds, separate from live measurements",
    )
    commands.add_parser(
        "compare-runtime",
        help="paired SHARC state/audio/instruction comparison for STRETCH variants",
    )
    args = parser.parse_args()
    if getattr(args, "shared_save", False) and getattr(args, "machine", None) not in (
        "arp",
        "flex",
    ):
        parser.error("--shared-save is supported for Arp and Flex")
    if (
        getattr(args, "runtime_variant", "reference") != "reference"
        and getattr(args, "machine", None) != "capicola"
    ):
        parser.error("--runtime-variant specializes Capicola only")
    if args.command == "diagnostics":
        return diagnostics_main(args)
    if args.command == "unit":
        return unit_run(args.suites or ["buf"], list_only=args.list_only, verbose=args.verbose)
    try:
        provenance = doctor()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.command == "doctor":
        print(
            f"PASS: pinned dependencies, {len(provenance['fixture_files'])} fixture files, "
            f"{len(provenance['selache_tools'])} tool binaries"
        )
        print(provenance["scope"])
        return 0
    name = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + args.command
        + "-"
        + uuid4().hex[:8]
    )
    output = ROOT / "out/runs" / name
    output.mkdir(parents=True)
    provenance.update(
        {
            "command": vars(args),
            "status": "running",
            "run": name,
            "started_utc": datetime.now(UTC).isoformat(),
        }
    )
    write_json(output / "manifest.json", provenance)
    environment = dict(os.environ, DT2_LAB_RUN_DIR=name, PYTHONDONTWRITEBYTECODE="1")
    print(
        f"Running {args.command} {getattr(args, 'machine', '')}; report: {output / 'manifest.json'}",
        flush=True,
    )
    code = 1
    try:
        with (output / "run.log").open("w") as log:
            child = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "lab.worker",
                    args.command,
                    json.dumps(vars(args)),
                ],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600 if getattr(args, "machine", None) == "sine" else 1800,
            )
        code = child.returncode
        if code == 0:
            result = read_json(output / "result.json")
            final_inputs = doctor()
            if (
                not result.get("ok")
                or final_inputs["source_hashes"] != provenance["source_hashes"]
            ):
                raise ValueError("Result failed or source changed during the run")
            provenance["result"] = result
            if (output / "sine-440.wav").is_file():
                print(f"Audio: {output / 'sine-440.wav'}")
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        provenance["error"] = str(exc)
        code = 1
    finally:
        provenance["status"] = "passed" if code == 0 else "failed"
        provenance["exit_code"] = code
        provenance["finished_utc"] = datetime.now(UTC).isoformat()
        write_json(output / "manifest.json", provenance)
        if code == 0:
            write_json(
                ROOT / "out/latest.json",
                {"run": name, "manifest": str(output / "manifest.json")},
            )
    print(f"{provenance['status'].upper()}: {output / 'manifest.json'}")
    if code:
        print(f"Details: {output / 'run.log'}", file=sys.stderr)
    return 0 if code == 0 else 1
