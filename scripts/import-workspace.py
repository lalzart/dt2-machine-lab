#!/usr/bin/env python3
"""Recreate this macOS replay setup from the preserved, verified experiment."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import git, read_json, require, sha256, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    old = workspace / "work/digikit"
    fixture = read_json(ROOT / "tests/fixtures/sine-1.16.json")
    lock = read_json(ROOT / "deps.lock.json")
    mapping = {
        "sections/section_3_MAIN_OS.bin": old
        / "out/sections/dt2-1.16/section_3_MAIN_OS.bin",
        "sections/section_7_BLOB.bin": old / "out/sections/dt2-1.16/section_7_BLOB.bin",
        "native/state.pack": old
        / "out/native/live/state-66912e66cfed237d2628f167.pack",
        "native/libsharc_native.dylib": old
        / "out/native/playground-116/target/release/libsharc_native.dylib",
    }
    for name in ("type-6.dtfr", "type-7.dtfr", "sine-type-7.dtfr"):
        mapping["captures/" + name] = old / "out/machine-test-116" / name
    for name, source in mapping.items():
        require(
            sha256(source) == fixture["files"][name],
            f"Source fixture mismatch: {source}",
        )
    for name, expected in fixture["selache_tools"].items():
        require(
            sha256(workspace / "work/selache" / name) == expected,
            f"Source tool mismatch: {name}",
        )
    python = old / ".venv/bin/python"
    require(python.is_file(), "Missing original Python environment")
    (ROOT / ".deps").mkdir(exist_ok=True)
    for name in ("digikit", "selache"):
        dest = ROOT / ".deps" / name
        if not dest.exists():
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(workspace / "work" / name),
                    str(dest),
                ],
                check=True,
                timeout=120,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(dest),
                    "checkout",
                    "--detach",
                    lock[name]["revision"],
                ],
                check=True,
                timeout=120,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(dest),
                    "remote",
                    "set-url",
                    "origin",
                    lock[name]["url"],
                ],
                check=True,
                timeout=30,
            )
        require(
            git(dest, "rev-parse", "HEAD") == lock[name]["revision"],
            f"Wrong {name} revision",
        )
        require(not git(dest, "status", "--porcelain"), f"Dirty {name} checkout")

    def copy_checked(source, dest, expected):
        if dest.exists():
            require(
                sha256(dest) == expected, f"Refusing to overwrite changed input: {dest}"
            )
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        require(sha256(dest) == expected, f"Copy verification failed: {dest}")

    for name, source in mapping.items():
        copy_checked(source, ROOT / ".local/fixture" / name, fixture["files"][name])
    for name, expected in fixture["selache_tools"].items():
        copy_checked(
            workspace / "work/selache" / name, ROOT / ".deps/selache" / name, expected
        )
    config = {
        "digikit": ".deps/digikit",
        "selache": ".deps/selache",
        "fixture": ".local/fixture",
        "python": str(python),
    }
    config_path = ROOT / ".local/config.json"
    if config_path.exists():
        require(
            read_json(config_path) == config,
            "Existing configuration differs; review it manually",
        )
    else:
        write_json(config_path, config)
    subprocess.run([str(ROOT / "labctl"), "doctor"], cwd=ROOT, check=True, timeout=60)


if __name__ == "__main__":
    main()
