#!/usr/bin/env python3
"""Bounded native BUF selector check; private containers never authorize flashing."""

# ruff: noqa: E402
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import (
    doctor,
    git,
    read_json,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--clock-context",
    type=Path,
    required=True,
    help="preserved native clock recording run with native-boot and reset-inputs",
)
p.add_argument("--digikit-runtime", type=Path, required=True)
p.add_argument("--codec-reference", type=Path, required=True)
p.add_argument("--target-dir", type=Path)
a = p.parse_args()
config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored out/runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = out.name
report = dict(status="running", hardware=False, hardware_ready=False)


def run(command, name, **kwargs):
    with (out / (name + ".log")).open("w") as log:
        subprocess.run(
            [str(x) for x in command],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            **kwargs,
        )


try:
    provenance = doctor()
    report["source_hashes"] = provenance["source_hashes"]
    runtime = a.digikit_runtime.resolve()
    context = a.clock_context.resolve()
    reference = a.codec_reference.resolve()
    require(not git(runtime, "status", "--porcelain"), "Runtime source is dirty")
    report["runtime_revision"] = git(runtime, "rev-parse", "HEAD")
    boot = context / "native-boot"
    report["native_boot_source_hashes"] = {
        str(f.relative_to(boot)): sha256(f)
        for f in sorted(boot.rglob("*"))
        if f.is_file() and (f.suffix in (".rs", ".toml") or f.name == "Cargo.lock")
    }
    from lab.runtime import STOCK_MAIN
    from lab.sketch_device import build
    from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

    require(
        git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION
        and not git(reference, "status", "--porcelain"),
        "Codec reference drift",
    )
    rust = Path.home() / ".cargo/bin/rustup"
    run(
        [
            rust,
            "run",
            "1.98.1",
            "rustc",
            "--edition=2024",
            "--crate-name",
            "coldfire",
            "--crate-type",
            "rlib",
            "-O",
            runtime / "packages/emulator/coldfire/src/lib.rs",
            "-o",
            out / "libcoldfire.rlib",
        ],
        "build-core",
    )
    run(
        [
            rust,
            "run",
            "1.98.1",
            "rustc",
            "--edition=2024",
            "--crate-type",
            "cdylib",
            "-O",
            "--extern",
            f"coldfire={out / 'libcoldfire.rlib'}",
            ROOT / "lab/native/buf_selector_core.rs",
            "-o",
            out / "libcfselector.dylib",
        ],
        "build-bridge",
    )
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_buf_selector.py",
            "-v",
        ],
        "unit",
        env=dict(os.environ, DT2_BUF_SELECTOR_CORE=str(out / "libcfselector.dylib")),
    )
    stock_main = STOCK_MAIN.read_bytes()
    baseline, _ = build(stock_main, arm_diagnostics=True, clock_fix=True)
    import hashlib

    require(
        hashlib.sha256(baseline).hexdigest()
        == "4d2e6af70a1faf2593cfc3eab45d1b664f46f678038fc49ffb4dd555f6fa22f8",
        "Disabled selector changes working clock image",
    )
    main, meta = build(
        stock_main, arm_diagnostics=True, clock_fix=True, buf_selector=True
    )
    require(
        (main, meta)
        == build(stock_main, arm_diagnostics=True, clock_fix=True, buf_selector=True),
        "Selector build is not repeatable",
    )
    (out / "SKETCH_MAIN.bin").write_bytes(main)
    write_json(out / "native-patches.json", meta)
    report["main_sha256"] = meta["sha256"]
    report["reservation_bytes"] = meta["reservation_bytes"]
    spec = read_json(context / "spec.json")
    spec.update(
        output=str(out),
        main=str(out / "SKETCH_MAIN.bin"),
        candidate=str(out / "candidate-test-fixture.syx"),
        metadata=str(out / "native-patches.json"),
        reset_input=str(context / "reset-inputs"),
    )
    blob = (context / "dsp/RETIRE_BLOB.bin").read_bytes()
    require(
        hashlib.sha256(blob).hexdigest()
        == "2ede0c37df1374f19c0d88c3130c2db2d1fc42ba7a98bd9e52a96d0dd13eb53a",
        "Clock DSP baseline changed",
    )
    report["blob_sha256"] = hashlib.sha256(blob).hexdigest()
    sys.path.insert(0, str(reference))
    from elekloader.codec.aplib import pack_section
    from elekloader.syx import Syx

    stock = Syx(Path(spec["stock_syx"]).read_bytes())
    raw = assemble_container(stock, {3: pack_section(main), 7: pack_section(blob)})
    report["container_checks"] = verify_candidate(raw, stock, {3: main, 7: blob})
    (out / "candidate-test-fixture.syx").write_bytes(raw)
    write_json(out / "spec.json", spec)
    report["inputs"] = {
        k: dict(path=spec[k], sha256=sha256(spec[k]))
        for k in ("stock_syx", "card", "main", "candidate")
    }
    (out / "src").mkdir()
    (out / "src/main.rs").write_bytes(
        (ROOT / "lab/native/buf_selector_panel.rs").read_bytes()
    )
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-native-buf-selector-panel"\nversion="0.1.0"\nedition="2024"\n'
        '[dependencies]\nserde_json="1"\nsha2="0.10"\n'
        f'elektron-native-boot={{path="{boot}",features=["sharc"]}}\n'
        f'sharc-native={{path="{runtime / "packages/emulator/sharc"}"}}\n'
    )
    target = a.target_dir.resolve() if a.target_dir else out / "target"
    run(
        [
            rust,
            "run",
            "1.98.1",
            "cargo",
            "build",
            "--offline",
            "--release",
            "--manifest-path",
            out / "Cargo.toml",
            "--target-dir",
            target,
        ],
        "build-panel",
        env=dict(os.environ, SHARC_GEN_DIR=str(runtime / "out/native/shared-core/gen")),
    )
    run(
        [target / "release/dt2-native-buf-selector-panel", out / "spec.json"],
        "panel",
        timeout=600,
    )
    report["panel"] = read_json(out / "panel.json")
    require(
        source_hashes() == provenance["source_hashes"],
        "Source changed during selector check",
    )
    require(not git(runtime, "status", "--porcelain"), "Runtime source changed")
    report["status"] = "passed-bounded-native-selector"
except Exception as error:
    report.update(status="failed", error=str(error))
    raise
finally:
    write_json(out / "report.json", report)
