#!/usr/bin/env python3
# ruff: noqa: E402
"""Build the explicit Plaits R3 + managed Flex + live Capicola OS 1.16 package.

Creates a fresh private experimental container and audit; never uploads.
"""

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

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--elekloader-reference", required=True, type=Path)
parser.add_argument(
    "--capi-toggle",
    action="store_true",
    help="Optional per-track stock/Capicola comparison control",
)
args = parser.parse_args()
provenance = doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

from lab.capicola_memory import MANAGED_BASE_SHA, SITES
from lab.capicola_memory import patch_cpu as reserve
from lab.coldfire import audit_code
from lab.flex_native_build import BASE
from lab.flex_native_build import patch_cpu as flex
from lab.plaits import build_blob, build_cpu
from lab.plaits_menu import patch_cpu as menu
from lab.runtime import PROFILE, STOCK_BLOB, STOCK_MAIN
from lab.upload import REFERENCE_REVISION, assemble_container, digest, verify_candidate

report = dict(
    status="building",
    firmware="Digitakt II OS 1.16",
    hardware_ready=False,
    hardware_uploaded=False,
    included=["Plaits R3", "managed streaming Flex", "Capicola live STRETCH R3"],
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    gaps=[
        "Physical timing and DSP headroom are unmeasured",
        "Coupled processor boot and hardware operation are unverified",
        "Permanent L2 instruction-code ownership is unresolved",
        "Full native STRETCH phase/progress bookkeeping is incomplete",
        "Flex identity recycling and full unsaved-source GC remain incomplete",
    ],
)
try:
    build_cpu(family="integration")
    plaits = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    stock = STOCK_MAIN.read_bytes()
    pre_menu, flex_report = flex(plaits, managed_sources=True)
    require(flex(plaits, managed_sources=True)[0] == pre_menu, "Flex repeat mismatch")
    require(
        all(pre_menu[i] == byte for i, byte in enumerate(plaits) if byte != stock[i]),
        "Flex changed a Plaits byte",
    )
    baseline, menu_report = menu(pre_menu)
    require(menu(pre_menu)[0] == baseline, "Menu repeat mismatch")
    require(digest(baseline) == MANAGED_BASE_SHA, "Managed Flex baseline drift")
    image, reservation = reserve(baseline, managed_flex=True)
    require(
        reserve(baseline, managed_flex=True)[0] == image, "Reservation repeat mismatch"
    )
    allowed = {a - BASE + i for a, *_ in SITES for i in range(2, 6)}
    require(
        all(
            a == b or i in allowed
            for i, (a, b) in enumerate(zip(baseline, image, strict=True))
        ),
        "Composition changed bytes outside pool bounds",
    )
    previous_writes = flex_report["writes"] + menu_report["writes"]
    for write in previous_writes:
        address, expected = write["address"], bytes.fromhex(write["after"])
        require(
            image[address - BASE : address - BASE + len(expected)] == expected,
            "Composition damaged " + write["label"],
        )
    require(
        image[0x40312000 - BASE :] == plaits[0x40312000 - BASE :],
        "Reset-copy data changed",
    )
    reservation["instruction_audit"] = [
        audit_code(bytes.fromhex(w["after"]), w["address"])
        for w in reservation["writes"]
    ]
    (out / "MANAGED_FLEX_MENU_MAIN_OS.bin").write_bytes(baseline)
    toggle_report = None
    if args.capi_toggle:
        from lab.capicola_toggle import patch_cpu as toggle

        image, toggle_report = toggle(image)
        require(
            toggle(reserve(baseline, managed_flex=True)[0])[0] == image,
            "CAPI CPU repeat mismatch",
        )
        report["included"].append("CAPI OFF/ON comparison toggle")
    else:
        require(
            digest(image)
            == "0bd3c2989665ec5151d5b14d9fbe3d55ee1810b3698fc2d34e7a1f9daaea5531",
            "Disabled CAPI MAIN drift",
        )
    main_name = "PLAITS_R3_FLEX_CAPICOLA_MAIN_OS.bin"
    (out / main_name).write_bytes(image)
    report["cpu"] = dict(
        path=main_name,
        sha256=digest(image),
        bytes=len(image),
        managed_flex_baseline_sha256=digest(baseline),
        flex=flex_report,
        menu=menu_report,
        reservation=reservation,
        previous_writes_preserved=len(previous_writes),
        only_six_pool_immediates_changed=True,
        reset_copy_data_preserved=True,
        capi_toggle=toggle_report,
    )
    print(
        "Combined MAIN preserves all Flex/menu patches and six guarded pool bounds",
        flush=True,
    )

    family = "capicola-stretch-toggle" if args.capi_toggle else "capicola-stretch-live"
    blob = build_blob(
        True,
        family=family,
        layout="reserved-state",
        output=out / "firmware",
    )
    require(
        args.capi_toggle
        or digest(blob)
        == "0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf",
        "Validated live STRETCH DSP changed",
    )
    repeat = build_blob(
        True,
        family=family,
        layout="reserved-state",
        output=out / "repeat",
    )
    require(blob == repeat, "DSP repeat mismatch")
    report["dsp"] = dict(
        path="firmware/PLAITS_BLOB.bin",
        sha256=digest(blob),
        bytes=len(blob),
        exact_validated_r3_image=not args.capi_toggle,
        build=json.loads((out / "firmware/build.json").read_text()),
        layout=json.loads((out / "firmware/memory-layout.json").read_text()),
    )

    reference = args.elekloader_reference.resolve()
    require(git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION, "Unknown codec")
    require(not git(reference, "status", "--porcelain"), "Dirty codec checkout")
    sys.path.insert(0, str(reference))
    from elekloader import syx
    from elekloader.codec.aplib import pack_section

    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    original = Path(inputs["syx"])
    require(sha256(original) == PROFILE["stock_syx_sha256"], "Unknown stock SYX")
    stock_container = syx.Syx(original.read_bytes())
    require(
        stock_container.section(3) == stock
        and stock_container.section(7) == STOCK_BLOB.read_bytes(),
        "Stock container differs from fixture",
    )
    require(
        assemble_container(stock_container, {}) == stock_container.raw,
        "Stock reconstruction mismatch",
    )
    images = {3: image, 7: blob}
    packed = {sid: pack_section(value) for sid, value in images.items()}
    raw = assemble_container(stock_container, packed)
    if not args.capi_toggle:
        require(
            digest(raw)
            == "cb57ee53d106b3bf05e3562d74e8d8f45889112da55043a1fb46976552a60229",
            "Disabled CAPI package drift",
        )
    facts = verify_candidate(raw, stock_container, images)
    require(
        raw == assemble_container(stock_container, packed), "Container repeat mismatch"
    )
    require(
        source_hashes() == provenance["source_hashes"], "Sources changed during build"
    )
    candidate = (
        "EXPERIMENTAL_PLAITS_R3_FLEX_CAPI_TOGGLE_OS1.16.syx"
        if args.capi_toggle
        else "EXPERIMENTAL_PLAITS_R3_FLEX_CAPICOLA_OS1.16.syx"
    )
    (out / candidate).write_bytes(raw)
    report.update(
        status="target-build-complete",
        candidate=candidate,
        container=facts,
        codec_revision=REFERENCE_REVISION,
        repeat_exact=True,
        source_fresh=True,
        capi_toggle=args.capi_toggle,
    )
    print(out / candidate, flush=True)
except Exception as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "manifest.json", report)
