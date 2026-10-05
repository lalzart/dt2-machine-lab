"""Small command interface for the pinned local experiment."""

import argparse
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
    for name in ("build", "render", "profile", "test"):
        sub = commands.add_parser(name)
        sub.add_argument("machine", choices=["sine"])
        if name == "test":
            sub.add_argument(
                "--replay",
                action="store_true",
                required=True,
                help="run the prepared-fixture regression suite",
            )
    args = parser.parse_args()
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
        f"Running {args.command} sine; report: {output / 'manifest.json'}", flush=True
    )
    code = 1
    try:
        with (output / "run.log").open("w") as log:
            child = subprocess.run(
                [sys.executable, "-B", "-m", "lab.worker", args.command],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
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
