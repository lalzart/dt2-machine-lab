#!/usr/bin/env python3
# ruff: noqa: E402
"""Build guarded native Flex MAIN images, optionally composed with Plaits R3.

Creates local experimental binaries and audit manifests only; never uploads.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, git, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--plaits-r3", action="store_true")
parser.add_argument("--plaits-before-midi", action="store_true")
parser.add_argument(
    "--managed-sources",
    action="store_true",
    help="Experimental native saved-source retirement and failure cleanup",
)
parser.add_argument(
    "--memory-accounting",
    action="store_true",
    help="Add an optional read-only native diagnostic entry; no reclamation",
)
parser.add_argument(
    "--elekloader-reference",
    type=Path,
    help="Also package an experimental local SYX using the pinned codec",
)
args = parser.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_native_build import BASE, patch_cpu
from lab.runtime import STOCK_MAIN

baseline = STOCK_MAIN.read_bytes()
if args.plaits_r3:
    from lab.plaits import build_blob, build_cpu

    build_cpu(family="integration")
    baseline = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    blob = build_blob(True, family="integration", output=out / "firmware")
image, report = patch_cpu(baseline, managed_sources=args.managed_sources)
require(
    patch_cpu(baseline, managed_sources=args.managed_sources)[0] == image,
    "Non-deterministic native overlay",
)
# The native overlay must preserve every byte changed by the Plaits CPU build.
stock = STOCK_MAIN.read_bytes()
require(
    all(image[i] == value for i, value in enumerate(baseline) if value != stock[i]),
    "Flex changed a Plaits byte",
)
for start, end in ((0x40312000, BASE + len(image)),):
    require(
        image[start - BASE : end - BASE] == baseline[start - BASE : end - BASE],
        "Reset-copy data changed",
    )
if args.plaits_before_midi:
    require(args.plaits_r3, "Menu overlay requires Plaits R3")
    from lab.plaits_menu import patch_cpu as patch_menu

    original = image
    image, menu = patch_menu(original)
    require(patch_menu(original)[0] == image, "Non-deterministic menu overlay")
    report["menu_overlay"] = menu
    report["pre_menu_sha256"] = report["sha256"]
    report["sha256"] = hashlib.sha256(image).hexdigest()
    write_json(out / "menu-patches.json", menu)
if args.memory_accounting and not args.managed_sources:
    from lab.flex_memory import patch_cpu as patch_memory

    image, accounting = patch_memory(image)
    report["memory_accounting"] = accounting
    report["sha256"] = hashlib.sha256(image).hexdigest()
    write_json(out / "memory-accounting.json", accounting)
name = "PLAITS_R3_FLEX_MAIN_OS.bin" if args.plaits_r3 else "FLEX_MAIN_OS.bin"
(out / name).write_bytes(image)
report.update(
    plaits_r3=args.plaits_r3,
    repeat_exact=True,
    plaits_bytes_preserved=not args.plaits_before_midi,
    plaits_bytes_preserved_before_menu=True,
    hardware_ready=False,
    sources={
        p: sha256(ROOT / p)
        for p in (
            "lab/flex_native.py",
            "lab/flex_memory.py",
            "lab/flex_resources.py",
            "lab/flex_retirement.py",
            "lab/plaits_menu.py",
            "lab/flex_native_save.py",
            "lab/flex_native_build.py",
            "lab/coldfire.py",
            "scripts/build-flex-native.py",
        )
    },
)
if args.elekloader_reference:
    from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

    reference = args.elekloader_reference.resolve()
    require(
        git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION,
        "Unknown container codec revision",
    )
    require(not git(reference, "status", "--porcelain"), "Dirty codec checkout")
    sys.path.insert(0, str(reference))
    from elekloader import syx
    from elekloader.codec.aplib import pack_section

    from lab.runtime import PROFILE, STOCK_BLOB

    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    original = Path(inputs["syx"])
    require(sha256(original) == PROFILE["stock_syx_sha256"], "Unknown stock SYX")
    stock_container = syx.Syx(original.read_bytes())
    require(
        stock_container.section(3) == stock
        and stock_container.section(7) == STOCK_BLOB.read_bytes(),
        "Container differs from fixture",
    )
    require(
        assemble_container(stock_container, {}) == stock_container.raw,
        "Stock reconstruction mismatch",
    )
    replacements = {3: image}
    if args.plaits_r3:
        replacements[7] = blob
    packed = {key: pack_section(value) for key, value in replacements.items()}
    raw = assemble_container(stock_container, packed)
    facts = verify_candidate(raw, stock_container, replacements)
    require(raw == assemble_container(stock_container, packed), "SYX repeat mismatch")
    package = out / (
        "EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx"
        if args.plaits_r3
        else "EXPERIMENTAL_FLEX_OS1.16.syx"
    )
    package.write_bytes(raw)
    report["package"] = dict(path=str(package), sha256=sha256(package), checks=facts)
write_json(out / "native-patches.json", report)
print(out / name)
