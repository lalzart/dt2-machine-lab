#!/usr/bin/env python3
"""Cold-boot Sketchbook backend proof; modeled recorder/card/CPU-DSP cadence.

The host selects a public slot/name and observes bytes. DSP readback, native
queue execution, file writing and durable reference verification run in target
instructions. This does not install firmware, prove physical timing or audition.
"""

# ruff: noqa: E402
import argparse
import json
import os
import shutil
import subprocess
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


def main():
    cfg = settings()
    if Path(sys.executable).resolve() != cfg["python"].resolve():
        os.execv(
            str(cfg["python"]), [str(cfg["python"]), "-B", __file__, *sys.argv[1:]]
        )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument(
        "--reference-spec",
        type=Path,
        required=True,
        help="R10 cold-boot input/card/panel symbols",
    )
    p.add_argument(
        "--dsp-build",
        type=Path,
        required=True,
        help="fresh readback build with build.json",
    )
    p.add_argument(
        "--reset-inputs",
        type=Path,
        required=True,
        help="zero-execution inputs for that exact DSP",
    )
    p.add_argument("--native-upstream", type=Path, required=True)
    p.add_argument(
        "--native-boot",
        type=Path,
        required=True,
        help="existing prepared native recorder/boot adapter",
    )
    a = p.parse_args()
    out = a.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use ignored out/runs")
    out.mkdir(parents=True, exist_ok=False)
    os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
    provenance = doctor()
    upstream = a.native_upstream.resolve()
    require(
        git(upstream, "rev-parse", "HEAD") == "38dfbe4ae88263511eed95691c07fc07e17b6f26"
        and not git(upstream, "status", "--porcelain"),
        "Native upstream drift",
    )
    from lab import sketchbook_preview as preview
    from lab import sketchbook_save as book
    from lab import sketchbook_ui as ui
    from lab.runtime import STOCK_MAIN
    from lab.sketch_device import build
    from lab.sketch_device_validation import address
    from lab.upload import assemble_container, verify_candidate

    sys.path[:0] = [
        str(cfg["digikit"]),
        str(ROOT / "out/references/elekloader-upload-audit"),
    ]
    from elekloader.codec.aplib import pack_section
    from elekloader.syx import Syx

    source = source_hashes()
    write_json(out / "sources.json", source)
    report = dict(
        status="running",
        scope=__doc__,
        dependencies=provenance["dependencies"],
        hardware=False,
    )
    try:
        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
            startup_capture=True,
            copy_shortcuts=True,
            stopped_recording=True,
            recording_led=True,
            monitor_labels=True,
            freeze_h_slots=True,
            sketchbook_save=True,
        )
        image, meta = build(STOCK_MAIN.read_bytes(), **flags)
        require(
            build(STOCK_MAIN.read_bytes(), **flags) == (image, meta),
            "CPU repeat differs",
        )
        (out / "SKETCH_MAIN.bin").write_bytes(image)
        write_json(out / "native-patches.json", meta)
        dsp_build = a.dsp_build.resolve()
        blob = (dsp_build / "SKETCHBOOK_BLOB.bin").read_bytes()
        dsp = json.loads((dsp_build / "build.json").read_text())
        require(
            sha256(dsp_build / "SKETCHBOOK_BLOB.bin") == dsp["blob_sha256"],
            "DSP build drift",
        )
        inputs = json.loads((a.reset_inputs / "inputs.json").read_text())
        require(
            inputs["blob_sha256"] == dsp["blob_sha256"]
            and inputs["instructions_executed"] == 0,
            "DSP reset inputs drift",
        )
        spec = json.loads(a.reference_spec.read_text())
        stock = Syx(Path(spec["stock_syx"]).read_bytes())
        require(
            sha256(spec["stock_syx"])
            == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
            "Stock SYX drift",
        )
        raw = assemble_container(stock, {3: pack_section(image), 7: pack_section(blob)})
        report["container"] = verify_candidate(raw, stock, {3: image, 7: blob})
        (out / "candidate-test-fixture.syx").write_bytes(raw)
        spec.update(
            output=str(out),
            candidate=str(out / "candidate-test-fixture.syx"),
            main=str(out / "SKETCH_MAIN.bin"),
            blob=str(dsp_build / "SKETCHBOOK_BLOB.bin"),
            metadata=str(out / "native-patches.json"),
            reset_inputs=str(a.reset_inputs.resolve()),
        )
        spec["symbols"]["book"] = {
            n: address(getattr(book, n))
            for n in [
                "STATE",
                "META",
                "NODE",
                "SUBMIT",
                "PHASE",
                "JOB",
                "RESULT",
                "COMPLETIONS",
                "CONTEXT",
                "TOKEN",
                "OWNER",
                "AGE",
                "ERROR",
                "POSITION",
                "COUNT",
                "RECEIVED",
                "CANCEL",
                "COMMAND",
                "HANDLED",
                "COMMAND_SLOT",
                "COMMAND_RESULT",
                "COMMAND_NAME",
                "CLOSED",
            ]
        }
        spec["symbols"]["ui"] = {
            n: address(getattr(ui, n)) for n in ["STATE", "MODE", "ROW", "VIEW", "LINE"]
        }
        spec["symbols"]["preview"] = {"STATE": address(preview.STATE)}
        write_json(out / "spec.json", spec)
        (out / "src").mkdir()
        shutil.copy(ROOT / "lab/native/sketchbook_save_probe.rs", out / "src/main.rs")
        shutil.copy(
            ROOT / "lab/native/startup_capture_trace.rs",
            out / "src/startup_capture_trace.rs",
        )
        (out / "Cargo.toml").write_text(
            '[package]\nname="dt2-sketchbook-save"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nserde_json="1"\nsha2="0.10"\nelektron-native-boot={path='
            + json.dumps(str(a.native_boot.resolve()))
            + ',features=["sharc"]}\nsharc-native={path='
            + json.dumps(str(upstream / "packages/emulator/sharc"))
            + "}\n"
        )
        env = dict(
            os.environ,
            SHARC_GEN_DIR=str(upstream / "out/native/shared-core/gen"),
            CARGO_TARGET_DIR=str(upstream / "out/native/target/generic"),
        )
        print("Starting native cold-boot/record/freeze/save proof:", out, flush=True)
        with (out / "native.log").open("w") as log:
            subprocess.run(
                [
                    "rustup",
                    "run",
                    "1.98.1",
                    "cargo",
                    "run",
                    "--release",
                    "--offline",
                    "--manifest-path",
                    str(out / "Cargo.toml"),
                    "--",
                    str(out / "spec.json"),
                ],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        flow = json.loads((out / "flow.json").read_text())
        require(flow["status"] == "passed", "Native backend flow failed")
        require(source_hashes() == source, "Source drift during native proof")
        report.update(
            status="passed",
            flow=flow,
            cpu_sha256=meta["sha256"],
            dsp_sha256=dsp["blob_sha256"],
        )
        print("PASS native backend flow", flush=True)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(out / "report.json", report)


if __name__ == "__main__":
    main()
