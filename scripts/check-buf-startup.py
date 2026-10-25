#!/usr/bin/env python3
"""Build and run one bounded native startup Sketch flow; no distributable OS."""

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

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--mode", choices=["publish", "cancel"], default="publish")
p.add_argument("--copy-shortcuts", action="store_true")
p.add_argument("--stopped-recording", action="store_true")
p.add_argument("--fixtures", type=Path, help="Preserved native fixture runs directory")
a = p.parse_args()
out = a.output.resolve()
require(out.parent == ROOT / "out/runs", "Fresh direct child of out/runs required")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = out.name
provenance = doctor()
from lab import buf_next_bar as nb
from lab import buf_startup as pending
from lab import buf_stopped as free
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_copy as clip
from lab.native_migration import prepare_recorder_boot
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build
from lab.sketch_device_validation import address
from lab.upload import assemble_container, verify_candidate

fixtures = a.fixtures.resolve() if a.fixtures else ROOT / "out/runs"
previous = fixtures / "fixed-h-native-01"
old = fixtures / "startup-retain-publish-01"
require(
    not a.copy_shortcuts or a.mode == "publish", "COPY flow requires a published take"
)
upstream = ROOT.parent.parent / "digikit-main"
report = dict(
    status="running",
    hardware=False,
    distributable_OS=False,
    source_hashes=provenance["source_hashes"],
)
try:
    main, meta = build(
        STOCK_MAIN.read_bytes(),
        arm_diagnostics=True,
        clock_fix=True,
        buf_selector=True,
        performance_controls=True,
        navigation_fixes=True,
        fixed_buf_slots=True,
        startup_capture=True,
        copy_shortcuts=a.copy_shortcuts,
        stopped_recording=a.stopped_recording,
    )
    (out / "SKETCH_MAIN.bin").write_bytes(main)
    write_json(out / "native-patches.json", meta)
    config = settings()
    ref = ROOT / "out/references/elekloader-upload-audit"
    sys.path[:0] = [str(config["digikit"]), str(ref)]
    from elekloader.codec.aplib import pack_section
    from elekloader.syx import Syx

    oldspec = json.loads((old / "spec.json").read_text())
    stock = Syx(Path(oldspec["stock_syx"]).read_bytes())
    blob = Path(oldspec["blob"]).read_bytes()
    raw = assemble_container(stock, {3: pack_section(main), 7: pack_section(blob)})
    report["container"] = verify_candidate(raw, stock, {3: main, 7: blob})
    (out / "candidate-test-fixture.syx").write_bytes(raw)
    report["adapter"] = prepare_recorder_boot(upstream, out / "native-boot")
    # Follow the authenticated native START trampoline after its new guard.
    # Observing the original entry would falsely begin modeled capture even
    # when the firmware refuses it. PCM/count/STOP/lock semantics stay exact.
    peer_file = out / "native-boot/src/runtime/recorder_peer.rs"
    original_peer = peer_file.read_text()
    start_pc = address(pending.START_STOCK)
    require(original_peer.count("0x4001_5fda") == 2, "Recorder START observer drift")
    peer_file.write_text(original_peer.replace("0x4001_5fda", f"0x{start_pc:08x}"))
    report["adapter"]["guarded_START_observer"] = dict(
        address=start_pc,
        original_sha256=provenance["source_hashes"]["lab/native/recorder_peer.rs"],
        derived_sha256=sha256(peer_file),
        original_peer_unchanged=True,
    )

    (out / "src").mkdir()
    for src, dst in [
        (
            "stopped_capture_probe.rs"
            if a.stopped_recording
            else "startup_capture_probe.rs",
            "main.rs",
        ),
        ("startup_capture_trace.rs", "startup_capture_trace.rs"),
    ]:
        shutil.copyfile(ROOT / "lab/native" / src, out / "src" / dst)
    if a.copy_shortcuts and not a.stopped_recording:
        driver = out / "src/main.rs"
        text = driver.read_text()
        anchor = " trace.checkpoint(&mut e,out,true);"
        require(text.count(anchor) == 1, "Native COPY extension anchor drift")
        driver.write_text(
            text.replace(
                "mod startup_capture_trace;",
                "mod sketch_copy_check;\nmod startup_capture_trace;",
            ).replace(
                anchor,
                " sketch_copy_check::run(&mut e,&mut trace,&shared,&spec);\n" + anchor,
            )
        )
        shutil.copyfile(
            ROOT / "lab/native/sketch_copy_check.rs", out / "src/sketch_copy_check.rs"
        )
    cargo = (
        (previous / "Cargo.toml")
        .read_text()
        .replace("dt2-native-buf-recording", "dt2-startup-capture")
        .replace(str(previous.resolve() / "native-boot"), str(out / "native-boot"))
    )
    (out / "Cargo.toml").write_text(cargo)
    symbols = {}
    for name, module in [
        ("nb", nb),
        ("w", w),
        ("s", s),
        ("pending", pending),
        ("clip", clip),
        ("free", free),
    ]:
        symbols[name] = {
            k: address(v) if 0x10000000 <= v < 0x11300000 else v
            for k, v in vars(module).items()
            if type(v) is int
        }
    spec = dict(
        oldspec,
        output=str(out),
        main=str(out / "SKETCH_MAIN.bin"),
        metadata=str(out / "native-patches.json"),
        candidate=str(out / "candidate-test-fixture.syx"),
        mode=a.mode,
        symbols=symbols,
    )
    spec["copy_return_pc"] = oldspec["copy_return_pc"]
    write_json(out / "spec.json", spec)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("SHARC_", "DSP_", "DIGI_"))
    }
    env["SHARC_GEN_DIR"] = str(upstream / "out/native/shared-core/gen")
    report["input_hashes"] = {
        key: sha256(spec[key])
        for key in ["stock_syx", "card", "candidate", "main", "metadata"]
    }
    report["input_hashes"].update(
        {
            name: sha256(Path(spec["reset_inputs"]) / name)
            for name in ("image.bin", "reset.state")
        }
    )
    report["generated_core"] = {
        f.name: sha256(f)
        for f in (upstream / "out/native/shared-core/gen").iterdir()
        if f.is_file()
    }
    target = upstream / "out/native/target/generic"
    for label, cmd in [
        (
            "build",
            [
                "rustup",
                "run",
                "1.98.1",
                "cargo",
                "build",
                "--offline",
                "--release",
                "--manifest-path",
                str(out / "Cargo.toml"),
                "--target-dir",
                str(target),
            ],
        ),
        ("flow", [str(out / "runner"), str(out / "spec.json")]),
    ]:
        if label == "flow":
            shutil.copy2(target / "release/dt2-startup-capture", out / "runner")
            report["runner_sha256"] = sha256(out / "runner")
        print(label, flush=True)
        with (out / (label + ".log")).open("w") as log:
            subprocess.run(
                cmd,
                cwd=upstream,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=720,
            )
    require(source_hashes() == provenance["source_hashes"], "Source drift")
    require(not git(upstream, "status", "--porcelain"), "Upstream changed")
    require(
        report["generated_core"]
        == {
            f.name: sha256(f)
            for f in (upstream / "out/native/shared-core/gen").iterdir()
            if f.is_file()
        },
        "Generated core changed",
    )
    report.update(status="passed", flow=json.loads((out / "flow.json").read_text()))
    if a.copy_shortcuts and not a.stopped_recording:
        report["copy_shortcuts"] = json.loads((out / "copy-flow.json").read_text())
except BaseException as e:
    report.update(status="failed", error=f"{type(e).__name__}: {e}")
    raise
finally:
    write_json(out / "report.json", report)
print(report["status"])
