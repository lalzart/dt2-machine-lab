#!/usr/bin/env python3
"""Build the opt-in volatile managed Sketch profile; no upload or hardware action."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="fresh directory below out/runs")
    parser.add_argument(
        "--assign-popup",
        action="store_true",
        help="try the optional track-assignment popup after recording",
    )
    parser.add_argument(
        "--buf-loading",
        action="store_true",
        help="show pending BUF rows and loading status",
    )
    parser.add_argument(
        "--early-buf-setup",
        action="store_true",
        help="try guarded slot setup before project sample loads",
    )
    args = parser.parse_args()
    profile = json.loads((ROOT / "profiles/sketch-managed.json").read_text())
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/build-sketch-device.py"),
            str((ROOT / args.output).resolve()),
            *("--" + name for name in profile["build_flags"]),
            *(["--assign-popup"] if args.assign_popup else []),
            *(["--buf-loading"] if args.buf_loading else []),
            *(["--early-buf-setup"] if args.early_buf_setup else []),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
