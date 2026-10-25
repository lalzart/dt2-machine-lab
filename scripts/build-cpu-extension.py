#!/usr/bin/env python3
"""Build a private opt-in Arp + managed Flex DDR experiment for stock OS1.16."""

# ruff: noqa: E402
import argparse
import hashlib
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
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--elekloader-reference", required=True, type=Path)
parser.add_argument("--arp-stopped", action="store_true", help="Allow held keyboard arp notes at the current tempo while the sequencer is stopped")
parser.add_argument("--any-track", action="store_true", help="Selected-track arp and independent Plaits lanes on all tracks; includes stopped arp")
parser.add_argument("--flex-save-screen", action="store_true", help="Visible Flex save/discard screen, project RAM bank choice and recording guard")
parser.add_argument(
    "--all-features",
    action="store_true",
    help="Include reviewed Plaits R3, CAPI time stretch and OFF/ON control",
)
parser.add_argument(
    "--capicola-reddit",
    action="store_true",
    help="Author release-default WSOLA backend (default for --all-features)",
)
parser.add_argument(
    "--capicola-legacy",
    action="store_true",
    help="Reproduce the previous default analyzed-keyframe backend",
)
parser.add_argument(
    "--capicola-source",
    action="store_true",
    help="Full source playback and grain handoffs; requires --all-features",
)
parser.add_argument(
    "--capicola-switch",
    action="store_true",
    help="Use the stock binary switch graphic for CAPI; requires --all-features",
)
parser.add_argument(
    "--capicola-quality",
    action="store_true",
    help="Optional adaptive-fade correction; requires --all-features",
)
args = parser.parse_args()
require(not args.any_track or args.all_features, 'Any-track requires --all-features')
if args.any_track:
    args.arp_stopped = True
require(
    sum(
        (
            args.capicola_reddit,
            args.capicola_legacy,
            args.capicola_source,
            args.capicola_quality,
        )
    )
    <= 1,
    "Choose one CAPI runtime",
)
require(
    not (args.capicola_reddit or args.capicola_legacy) or args.all_features,
    "CAPI runtime requires all features",
)
args.capicola_reddit = args.all_features and not (
    args.capicola_legacy or args.capicola_source or args.capicola_quality
)
require(not args.any_track or args.capicola_reddit, "Any-track is scoped to the author Capicola backend")
if args.capicola_reddit:
    args.capicola_switch = True
require(
    not args.capicola_quality or args.all_features,
    "Quality profile requires all features",
)
require(
    not args.capicola_source or args.all_features, "Source port requires all features"
)
require(not (args.capicola_source and args.capicola_quality), "Choose one CAPI runtime")
require(
    not args.capicola_switch or args.all_features, "CAPI switch requires all features"
)
runtime_variant = (
    "source"
    if args.capicola_source
    else "quality"
    if args.capicola_quality
    else "reference"
)
provenance = doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.cpu_extension import build_cpu
from lab.runtime import PROFILE, STOCK_BLOB, STOCK_MAIN
from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

reference = args.elekloader_reference.resolve()
require(
    git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION, "Unknown codec revision"
)
require(not git(reference, "status", "--porcelain"), "Dirty codec reference")
sys.path.insert(0, str(reference))
from elekloader import syx
from elekloader.codec.aplib import pack_section

report = dict(
    status="building",
    hardware_ready=False,
    hardware_uploaded=False,
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    codec_revision=REFERENCE_REVISION,
)
try:
    stock = STOCK_MAIN.read_bytes()
    options = dict(features="all", output=out / "cpu-base") if args.all_features else {}
    if args.arp_stopped:
        options['arp_stopped'] = True
    if args.any_track:
        options['any_tracks'] = True
    if args.flex_save_screen:
        options['flex_save_screen'] = True
    image, meta = build_cpu(stock, **options)
    if args.capicola_switch:
        from lab.capicola_ui import apply_switch

        image, meta = apply_switch(image, meta)
    repeat_options = (
        dict(features="all", output=out / "cpu-base-repeat")
        if args.all_features
        else {}
    )
    if args.arp_stopped:
        repeat_options['arp_stopped'] = True
    if args.any_track:
        repeat_options['any_tracks'] = True
    if args.flex_save_screen:
        repeat_options['flex_save_screen'] = True
    repeated = build_cpu(stock, **repeat_options)
    if args.capicola_switch:
        repeated = apply_switch(*repeated)
    require(repeated == (image, meta), "Extension build differs on repeat")
    if args.capicola_reddit and not args.arp_stopped and not args.flex_save_screen:
        require(
            meta["sha256"]
            == "574ba37b677c62a8cba8885652aa0ca25f4d3b7b93394e977739bb7c0e04e4cc",
            "Author backend must preserve the reviewed switch/Arp/Flex MAIN image",
        )
    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    original = Path(inputs["syx"])
    require(sha256(original) == PROFILE["stock_syx_sha256"], "Unknown stock SYX")
    container = syx.Syx(original.read_bytes())
    require(
        container.section(3) == stock
        and container.section(7) == STOCK_BLOB.read_bytes(),
        "Stock fixture mismatch",
    )
    require(assemble_container(container, {}) == container.raw, "Stock reconstruction")
    images = {3: image}
    dsp_report = None
    if args.all_features:
        from lab.dsp_build import build_blob

        def build_dsp(output):
            if args.capicola_reddit:
                from lab.capicola_reddit import build_blob as reddit_blob

                return reddit_blob(output, all_tracks=args.any_track)
            return build_blob(
                True,
                family="capicola-stretch-toggle",
                layout="reserved-state",
                output=output,
                runtime_variant=runtime_variant,
            )

        blob = build_dsp(out / "firmware")
        require(
            args.capicola_reddit
            or args.capicola_quality
            or args.capicola_source
            or hashlib.sha256(blob).hexdigest()
            == "cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7",
            "Reviewed Plaits/CAPI DSP drift",
        )
        require(
            build_dsp(out / "dsp-repeat") == blob,
            "DSP repeat mismatch",
        )
        images[7] = blob
        dsp_report = dict(
            path="firmware/PLAITS_BLOB.bin",
            sha256=hashlib.sha256(blob).hexdigest(),
            bytes=len(blob),
            build=json.loads((out / "firmware/build.json").read_text()),
            layout=json.loads((out / "firmware/memory-layout.json").read_text()),
        )
    packed = {sid: pack_section(content) for sid, content in images.items()}
    raw = assemble_container(container, packed)
    facts = verify_candidate(raw, container, images)
    require(raw == assemble_container(container, packed), "Container repeat differs")
    require(source_hashes() == provenance["source_hashes"], "Source drift")
    candidate = (
        "EXPERIMENTAL_ALL_FEATURES_CAPI_REDDIT_R2_OS1.16.syx"
        if args.capicola_reddit
        else "EXPERIMENTAL_ALL_FEATURES_CAPI_SOURCE_OS1.16.syx"
        if args.capicola_source
        else "EXPERIMENTAL_ALL_FEATURES_CAPI_QUALITY_OS1.16.syx"
        if args.capicola_quality
        else "EXPERIMENTAL_ALL_FEATURES_PLAITS_CAPI_ARP_FLEX_OS1.16.syx"
        if args.all_features
        else "EXPERIMENTAL_CPU_EXTENSION_ARP_FLEX_OS1.16.syx"
    )
    if args.capicola_switch and not args.capicola_reddit:
        candidate = candidate.replace("_OS1.16.syx", "_SWITCH_OS1.16.syx")
    if args.any_track:
        candidate = candidate.replace("_OS1.16.syx", "_ANY_TRACK_R1_OS1.16.syx")
    elif args.arp_stopped:
        candidate = candidate.replace("_OS1.16.syx", "_ARP_STOPPED_R1_OS1.16.syx")
    if args.flex_save_screen:
        candidate = candidate.replace("_OS1.16.syx", "_FLEX_SAVE_SCREEN_R5_BANK_OS1.16.syx")
    (out / candidate).write_bytes(raw)
    (out / "CPU_EXTENSION_MAIN.bin").write_bytes(image)
    write_json(out / "native-patches.json", meta)
    report.update(
        status="target-build-complete",
        candidate=candidate,
        container=facts,
        cpu=dict(path="CPU_EXTENSION_MAIN.bin", sha256=meta["sha256"], native=meta),
        repeat_exact=True,
        stock_dsp_unchanged=not args.all_features,
        included=(
            [
                "Plaits R3 six-model bank",
                "STRETCH CAPI OFF/ON",
                "Native Arp tempo/rates",
                "Managed Flex",
            ]
            if args.all_features
            else ["Native Arp tempo/rates", "Managed Flex"]
        ),
        flex_discard=args.flex_save_screen,
        flex_bank_choice=args.flex_save_screen,
        capi_toggle=args.all_features,
        capicola_quality=args.capicola_quality,
        capicola_source=args.capicola_source,
        capicola_reddit=args.capicola_reddit,
        capicola_switch=args.capicola_switch,
        arp_stopped=args.arp_stopped,
        any_tracks=args.any_track,
        flex_save_screen=args.flex_save_screen,
        limits=[
            "Experimental 64 KiB DDR reservation; physical ownership/timing unverified",
            "CPU-only emulator checks do not establish coupled DSP or device operation",
            ("Any-track Arp" if args.any_track else "Track-one Arp")
            + "; existing managed Flex lifetime/capacity limits remain",
        ],
    )
    if args.all_features:
        report["dsp"] = dsp_report
        report["cpu"]["capi_toggle"] = meta["base"]["capi_toggle"]
    print(out / candidate, flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "manifest.json", report)
