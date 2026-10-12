# ruff: noqa: E402
"""Build an OS 1.16 Plaits container for offline audit; never upload it."""

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
from lab.upload import (
    REFERENCE_REVISION,
    assemble_container,
    digest,
    verify_candidate,
)

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--elekloader-reference", required=True, type=Path)
parser.add_argument("--cpu-check", required=True, type=Path)
parser.add_argument("--pattern-check", required=True, type=Path)
args = parser.parse_args()
doctor()
reference = args.elekloader_reference.resolve()
require(
    git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION,
    "Wrong reference revision",
)
require(not git(reference, "status", "--porcelain"), "Dirty reference checkout")
sys.path.insert(0, str(reference))
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

from elekloader import syx
from elekloader.codec.aplib import pack_section

from lab.plaits import build_blob, build_cpu
from lab.runtime import PROFILE, STOCK_BLOB, STOCK_MAIN

sources = source_hashes()
report = {"hardware_ready": False, "status": "building", "sources": sources}
try:
    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    original = Path(inputs["syx"])
    require(sha256(original) == PROFILE["stock_syx_sha256"], "Unknown stock firmware")
    stock = syx.Syx(original.read_bytes())
    require(
        stock.section(3) == STOCK_MAIN.read_bytes(), "Stock MAIN differs from fixture"
    )
    require(
        stock.section(7) == STOCK_BLOB.read_bytes(), "Stock DSP differs from fixture"
    )
    require(
        assemble_container(stock, {}) == stock.raw,
        "Stock reconstruction is not byte exact",
    )
    verify_candidate(stock.raw, stock, {})
    cpu = build_cpu(family="controls")
    main = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    blob = build_blob(True, family="controls", output=out / "dsp")
    require(
        digest(main)
        == "4c226dfe863005324782f2931d2ad5e0c9142d8d8f85701c3e1a5065ed6fdc3f",
        "MAIN differs from reviewed ColdFire correction",
    )
    isa_report = json.loads((out / "coldfire-audit.json").read_text())
    require(
        isa_report["status"] == "passed" and isa_report["main_sha256"] == digest(main),
        "Missing independent instruction audit",
    )
    cpu_report = args.cpu_check.resolve()
    cpu_check = json.loads(cpu_report.read_text())
    require(
        cpu_check["status"] == "passed"
        and cpu_check["cpu"]["sha256"] == digest(main)
        and cpu_check["rank_abi_cases"] == 256
        and cpu_check["illegal_original_rejected"],
        "Missing corrected rank ABI / original illegal instruction rejection",
    )
    reload_report = args.pattern_check.resolve()
    reload_check = json.loads(reload_report.read_text())
    require(
        reload_check["status"] == "passed"
        and reload_check["cpu_candidate"]["sha256"] == digest(main)
        and bool(reload_check["temporary_pattern_reload"]),
        "Track-restore panel check has not passed for this MAIN",
    )
    tested_blob = ROOT / "out/runs/pattern-plaits-final-audio/firmware/PLAITS_BLOB.bin"
    require(
        blob == tested_blob.read_bytes(),
        "DSP no longer matches the tested audio candidate",
    )
    packed = {3: pack_section(main), 7: pack_section(blob)}
    raw = assemble_container(stock, packed)
    facts = verify_candidate(raw, stock, {3: main, 7: blob})
    require(raw == assemble_container(stock, packed), "Container repeat mismatch")
    negatives = {}
    bad_packet = bytearray(raw)
    bad_packet[16 + 126] ^= 1
    for name, action in (
        (
            "corrupted_packet_checksum",
            lambda: verify_candidate(bytes(bad_packet), stock, {3: main, 7: blob}),
        ),
        (
            "bootstrap_replacement",
            lambda: assemble_container(stock, {2: stock.stored[2]}),
        ),
        (
            "updater_replacement",
            lambda: assemble_container(stock, {4: stock.stored[4]}),
        ),
        ("unexpected_dsp_change", lambda: verify_candidate(raw, stock, {3: main})),
        (
            "wrong_expected_main",
            lambda: verify_candidate(raw, stock, {3: bytes(len(main)), 7: blob}),
        ),
    ):
        try:
            action()
        except ValueError as exc:
            negatives[name] = str(exc)
        else:
            raise ValueError(f"Negative control was accepted: {name}")
    require(source_hashes() == sources, "Sources changed during build")
    doctor()
    require(
        not git(reference, "status", "--porcelain"), "Reference changed during build"
    )
    name = "DO_NOT_FLASH-Digitakt_II_1.16-Plaits.syx.disabled"
    (out / name).write_bytes(raw)
    require(sha256(out / name) == facts["sha256"], "Written candidate hash mismatch")
    report.update(
        status="offline-container-checks-passed-release-blocked",
        candidate=name,
        stock_sha256=sha256(original),
        reference_revision=REFERENCE_REVISION,
        cpu=cpu,
        container=facts,
        negative_controls=negatives,
        stock_reconstruction_byte_exact=True,
        matches_tested_main_and_dsp=True,
        track_restore_report_sha256=sha256(reload_report),
        prior_main_difference="28-byte guarded rank slot correction; all other MAIN bytes identical to failed r1",
        cpu_check_sha256=sha256(cpu_report),
        instruction_audit_sha256=sha256(out / "coldfire-audit.json"),
        blockers=[
            "Run actual 1.16 firmware depacker on both changed streams",
            "Cold boot complete candidate without inherited snapshots",
            "Establish DSP arena ownership and wrapper ABI on full stock paths",
            "Verify downstream mixer, sample-free initialization and save/reload",
            "Measure physical DSP timing/headroom and validate recovery setup",
        ],
    )
    print(
        json.dumps(
            {k: report[k] for k in ("status", "candidate", "container")}, indent=2
        )
    )
except Exception as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "manifest.json", report)
