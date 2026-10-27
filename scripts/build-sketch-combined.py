#!/usr/bin/env python3
"""Build a local OS1.16 with current Sketch, author Capicola R2 and selected-track ARP."""

# ruff: noqa: E402
import argparse
import json
import os
import sys
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

cfg = settings()
if Path(sys.executable).resolve() != cfg["python"].resolve():
    os.execv(str(cfg["python"]), [str(cfg["python"]), "-B", __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
a = p.parse_args()
out = a.output.resolve()
require(
    out.is_relative_to(ROOT / "out/runs") and not out.exists(),
    "Use a fresh ignored output",
)
out.mkdir(parents=True)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
from lab.runtime import STOCK_MAIN
from lab.sketch_combined import build_cpu
from lab.sketch_combined_dsp import build as combined_dsp
from lab.sketch_device import build as sketch_cpu
from lab.sketch_dsp_device import build as sketch_dsp
from lab.sketchbook_dsp import build as readback_dsp
from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

reference = ROOT / "out/references/elekloader-upload-audit"
require(
    git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION, "Codec revision drift"
)
require(not git(reference, "status", "--porcelain"), "Dirty codec reference")
sys.path[:0] = [str(cfg["digikit"]), str(reference)]
from elekloader.codec.aplib import pack_section
from elekloader.syx import Syx

report = dict(
    status="running",
    firmware="Digitakt II OS1.16",
    project_persistence=False,
    hardware=False,
    **provenance,
)
try:
    flags = {
        k.replace("-", "_"): True
        for k in json.loads((ROOT / "profiles/sketch-managed.json").read_text())[
            "build_flags"
        ]
    }
    flags.update(assign_popup=True, buf_loading=True, early_buf_setup=True)
    original = STOCK_MAIN.read_bytes()
    base, base_meta = sketch_cpu(original, **flags)
    image, meta = build_cpu(original, base, base_meta, out / "cpu")
    repeat, repeat_meta = build_cpu(original, base, base_meta, out / "cpu-repeat")
    require((image, meta) == (repeat, repeat_meta), "Combined CPU repeat differs")
    blob, dsp = sketch_dsp(out / "base-dsp")
    blob, dsp = readback_dsp(blob, dsp, out / "readback-dsp")
    blob, dsp = combined_dsp(blob, out / "firmware")
    stock_path = Path(json.loads((ROOT / ".local/cpu-inputs.json").read_text())["syx"])
    require(
        sha256(stock_path)
        == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
        "Unknown stock package",
    )
    stock = Syx(stock_path.read_bytes())
    packed = {3: pack_section(image), 7: pack_section(blob)}
    raw = assemble_container(stock, packed)
    facts = verify_candidate(raw, stock, {3: image, 7: blob})
    require(raw == assemble_container(stock, packed), "Container repeat differs")
    require(source_hashes() == provenance["source_hashes"], "Build source drift")
    name = "EXPERIMENTAL_SKETCH_CAPI_R2_ARP_OS1.16.syx"
    (out / name).write_bytes(raw)
    (out / "SKETCH_MAIN.bin").write_bytes(image)
    write_json(out / "native-patches.json", meta)
    report.update(
        status="target-build-complete",
        candidate=name,
        container=facts,
        cpu=dict(path="SKETCH_MAIN.bin", sha256=meta["sha256"]),
        dsp=dsp,
        capicola_reddit=True,
        combined=True,
        repeat_exact=True,
        includes=[
            "managed Sketch and explicit Sketchbook export",
            "assignment popup and early-buffer/loading UI",
            "author Capicola R2 STRETCH",
            "selected-track/stopped keyboard ARP",
        ],
        excludes=["Plaits", "legacy Flex", "buffer project persistence"],
    )
except BaseException as e:
    report.update(status="failed", error=f"{type(e).__name__}: {e}")
    raise
finally:
    write_json(out / "manifest.json", report)
print(json.dumps({k: report[k] for k in ("status", "candidate", "cpu")}, indent=2))
