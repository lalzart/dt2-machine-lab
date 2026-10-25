#!/usr/bin/env python3
# ruff: noqa: E402
"""Read-only OS1.16 selector/loader survey; emits no firmware or patch."""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.dt2_116 import BASE, STOCK_SHA
from lab.project import ROOT, doctor, require, source_hashes

RANGES = {
    "project-load-worker": (0x4004E98A, 0x4004EAE4),
    "stock-loader": (0x40154540, 0x40154D48),
    "stock-unload": (0x401540C6, 0x40154214),
    "stock-clear": (0x40153BEA, 0x40153D70),
    "allocation-association": (0x401535BA, 0x401537A8),
    "quick-list-and-model": (0x4001DD9C, 0x4001F02C),
    "full-picker": (0x4001D1B0, 0x4001DD9C),
    "project-sample-access": (0x4004B710, 0x4004B794),
    "pool-directory": (0x400163B0, 0x40016576),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--main",
        type=Path,
        default=ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin",
    )
    parser.add_argument("--clock-build", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use ignored out/runs")
    out.mkdir(exist_ok=False)
    report = dict(
        status="running",
        firmware_version="Digitakt II OS 1.16",
        evidence="authenticated source bytes and RTTI; no runtime or device claim",
        new_firmware=False,
        recordings=0,
        hardware_access=False,
    )
    try:
        report["preflight"] = doctor()
        before = source_hashes()
        report["source_hashes"] = before
        blob = args.main.read_bytes()
        report["main_sha256"] = hashlib.sha256(blob).hexdigest()
        require(report["main_sha256"] == STOCK_SHA, "Unknown OS1.16 MAIN")
        config = json.loads((ROOT / ".local/config.json").read_text())
        dependency = ROOT / config["digikit"]
        sys.path[:0] = [str(dependency), str(dependency / "tools")]
        from dt2.coldfire import disasm
        from rttiscan import Image, demangle, find_typeinfos, find_vtables, kind_vptrs

        image = Image(blob, BASE)
        words = struct.unpack_from(f">{len(blob) // 4}I", blob)
        types = find_typeinfos(image, words, kind_vptrs(image, words), demangle)
        vtables = find_vtables(image, words, types, [(BASE, 0x401E8000)])
        classes = {
            "SampleListView",
            "SamplePicker",
            "SamplePoolDirectory",
            "SampleLoaderBgWorker",
        }
        selected = [v for v in vtables if v["class"] in classes]
        require({v["class"] for v in selected} == classes, "Missing stock RTTI")
        (out / "sample-vtables.json").write_text(json.dumps(selected, indent=2) + "\n")
        report["ranges"] = {}
        candidate = None
        if args.clock_build:
            metadata = json.loads((args.clock_build / "manifest.json").read_text())
            candidate = (args.clock_build / metadata["cpu"]["path"]).read_bytes()
            digest = hashlib.sha256(candidate).hexdigest()
            require(digest == metadata["cpu"]["sha256"], "Changed clock candidate")
            report["clock_main_sha256"] = digest
        for name, (start, end) in RANGES.items():
            raw = blob[start - BASE : end - BASE]
            info = dict(start=start, end=end, sha256=hashlib.sha256(raw).hexdigest())
            if candidate is not None and name in {
                "quick-list-and-model",
                "full-picker",
                "project-sample-access",
                "pool-directory",
            }:
                require(
                    raw == candidate[start - BASE : end - BASE],
                    "Changed selector range: " + name,
                )
                info["stock_equals_clock_candidate"] = True
            report["ranges"][name] = info
            (out / (name + ".txt")).write_text(
                "\n".join(
                    f"{pc:08x} {hx:<22} {mn:<9} {operands}"
                    for pc, hx, mn, operands in disasm(blob, BASE, start, end)
                )
                + "\n"
            )
        require(source_hashes() == before, "Source changed during survey")
        report["status"] = "passed-static-selector-loader-survey"
        print(report["status"])
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
