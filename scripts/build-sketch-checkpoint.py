#!/usr/bin/env python3
"""Build the accepted R8 profile and require identical MAIN/DSP output."""

# ruff: noqa: E402
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import read_json, require, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="fresh directory below out/runs")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    profile = read_json(ROOT / "profiles/sketch-buf-r8.json")
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/build-sketch-device.py"),
            str(output),
            *("--" + name for name in profile["build_flags"]),
        ],
        cwd=ROOT,
        check=True,
    )
    report = read_json(output / "manifest.json")
    require(report["status"] == "local-build-complete", "Incomplete R8 build")
    for label, actual in (
        ("MAIN_sha256", report["cpu"]["sha256"]),
        ("DSP_sha256", report["dsp"]["blob_sha256"]),
    ):
        require(actual == profile[label], f"Accepted R8 {label} differs")
    require(
        report["cpu"]["reservation_bytes"] == profile["reservation_bytes"],
        "R8 reservation changed",
    )
    require(
        report["cpu"]["buf_public_slots"] == profile["BUF_public_slots"],
        "R8 slot layout changed",
    )
    write_json(
        output / "checkpoint.json", dict(status="byte-exact-R8", profile=profile)
    )
    print(json.dumps(dict(status="byte-exact-R8", output=str(output))))


if __name__ == "__main__":
    main()
