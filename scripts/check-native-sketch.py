#!/usr/bin/env python3
"""Opt-in native BUF/Sketch migration slice; preserve the active lab pin.

Authenticate stock service anchors, execute the complete candidate container,
and compare saved A/B/FREEZE replay against the unchanged old DSP runtime.
No recording, dependency replacement, hardware transfer or firmware changes.
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

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--native-upstream", type=Path, required=True)
p.add_argument(
    "--skip-boot", action="store_true", help="constructor and saved-page replay only"
)
p.add_argument("--build", type=Path, help="fresh sealed Sketch device build")
p.add_argument("--upload-proof", type=Path, help="matching passed boot-upload run")
p.add_argument(
    "--boot-only", action="store_true", help="constructors and startup; no saved replay"
)
p.add_argument(
    "--arm-diagnostics", action="store_true", help="bounded UI admission fault controls"
)
p.add_argument(
    "--operation-trace",
    action="store_true",
    help="read-only sample-operation trace from cold application reset",
)
a = p.parse_args()
require(not (a.boot_only and a.skip_boot), "Choose startup or replay-only")
require(not a.operation_trace or a.boot_only, "Operation trace requires startup-only")
require(
    not a.arm_diagnostics or a.boot_only, "Diagnostic controls require startup-only"
)
require(bool(a.build) == bool(a.upload_proof), "Supply both build and upload proof")
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(exist_ok=False, parents=True)
os.environ["DT2_LAB_RUN_DIR"] = out.name
provenance = doctor()
from lab.native_migration import REVISION, prepare_boot
from lab.runtime import STOCK_MAIN
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit

upstream = a.native_upstream.resolve()
device = DeviceBuild(
    a.build or ROOT / "out/runs/sketch-device-build-20261023-13",
    STOCK_MAIN.read_bytes(),
)
require(
    not a.arm_diagnostics or device.meta.get("arm_diagnostics"),
    "Not a diagnostic build",
)
upload = (a.upload_proof or ROOT / "out/runs/sketch-rom-upload-20261023-07").resolve()
proof = json.loads((upload / "report.json").read_text())
candidate = upload / "candidate-test-fixture.syx"
require(
    proof["status"] == "passed-stream-rules-and-native-cpu-upload",
    "Unproven candidate container",
)
require(
    sha256(candidate) == proof["test_container"]["sha256"], "Candidate container drift"
)
require(
    proof["device"]["main_sha256"] == device.meta["sha256"],
    "Candidate MAIN identity differs",
)
require(
    proof["device"]["dsp_sha256"] == sha256(device.blob_path),
    "Candidate DSP identity differs",
)
if a.upload_proof:
    require(
        proof["source_hashes"] == provenance["source_hashes"], "Upload source drift"
    )
audit(device.blob)
inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
for key, want in (
    ("syx", "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec"),
    ("card", "f0a30d418c256ad2d8a87c395a36ffbce2fb8ad0119d755927b442f77df28cea"),
):
    require(sha256(inputs[key]) == want, key + " drift")
fixture = ROOT / "out/runs/sketch-relocated-coupled-20261023-01"
if not a.boot_only:
    require(
        sha256(fixture / "report.json")
        == "baa03067c93cf61fa54a1a348bd08d9a6374a5a1dfa9665e4eebeea88e279790",
        "Saved A/B fixture drift",
    )
spec = dict(
    output=str(out),
    lab=str(ROOT),
    fixture=str(fixture),
    blob=str(device.blob_path),
    stock_syx=inputs["syx"],
    candidate=str(candidate),
    card=inputs["card"],
    main=str(device.folder / "SKETCH_MAIN.bin"),
    metadata=str(device.folder / "native-patches.json"),
    arm_diagnostics=a.arm_diagnostics,
    operation_trace=a.operation_trace,
)
write_json(out / "spec.json", spec)
generation = upstream / "out/native/shared-core/gen"
gen = {
    p: sha256(generation / p)
    for p in ("core_i.rs", "core_g.rs", "syms.rs", "tables.rs", "CORE_FINGERPRINT")
}
env = {
    k: v for k, v in os.environ.items() if not k.startswith(("SHARC_", "DSP_", "DIGI_"))
}
env["SHARC_GEN_DIR"] = str(generation)
report = dict(
    status="running",
    scope=(
        "Exact candidate container CPU application reset and independently initialized "
        "DSP application entry; modeled SSI/cadence, no DSP ROM or hardware"
        if a.boot_only
        else __doc__
    ),
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    native_upstream_revision=REVISION,
    generated_core=gen,
    device=device.identity,
    recordings=0,
    boot_only=a.boot_only,
    hardware=False,
    input_hashes={
        k: sha256(v)
        for k, v in spec.items()
        if k in ("candidate", "stock_syx", "main", "blob", "card")
    },
)


def helper(name, *args):
    code = "import runpy,sys;sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')"
    return [
        sys.executable,
        "-B",
        "-c",
        code,
        str(ROOT / "lab/native" / name),
        *map(str, args),
    ]


def run_logged(label, cmd, cwd=ROOT, timeout=600):
    print(label, flush=True)
    with (out / (label + ".log")).open("w") as log:
        subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=timeout,
        )


try:
    for name in provenance["source_hashes"]:
        dest = out / "frozen-sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    report["adapter"] = prepare_boot(upstream, out / "native-boot")
    if not a.boot_only:
        run_logged("legacy-oracle", helper("migration_legacy.py", out / "spec.json"))
        run_logged(
            "pack-current-inputs",
            helper("migration_inputs.py", out / "spec.json"),
            cwd=upstream,
        )
    reset = ROOT / "out/runs/sketch-dsp-startup-20261023-01/report.json"
    require(
        sha256(reset)
        == "86c599454f5d3dfbecf4e7ee5cd9da7f6b2b2da165caa79d480228738dc3c8e1",
        "Reset model drift",
    )
    write_json(out / "reset-values.json", json.loads(reset.read_text())["reset_values"])
    run_logged(
        "pack-reset-inputs",
        helper(
            "sketch_cold_inputs.py",
            device.blob_path,
            out / "reset-values.json",
            out / "reset-inputs",
        ),
        cwd=upstream,
    )
    (out / "src").mkdir()
    shutil.copyfile(ROOT / "lab/native/sketch_migration_probe.rs", out / "src/main.rs")
    shutil.copyfile(ROOT / "lab/native/buf_adapter.rs", out / "src/buf_adapter.rs")
    shutil.copyfile(
        ROOT / "lab/native/sketch_arm_diagnostic.rs",
        out / "src/sketch_arm_diagnostic.rs",
    )
    shutil.copyfile(
        ROOT / "lab/native/sketch_startup_operations.rs",
        out / "src/sketch_startup_operations.rs",
    )
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-native-sketch"\nversion="0.1.0"\nedition="2024"\n'
        '[dependencies]\nserde_json="1"\nsha2="0.10"\n'
        + "elektron-native-boot={path="
        + json.dumps(str(out / "native-boot"))
        + ',features=["sharc"]}\n'
        + "sharc-native={path="
        + json.dumps(str(upstream / "packages/emulator/sharc"))
        + "}\n"
    )
    target = upstream / "out/native/target/generic"
    run_logged(
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
        cwd=upstream,
        timeout=900,
    )
    shutil.copy2(target / "release/dt2-native-sketch", out / "runner")
    report["runner_sha256"] = sha256(out / "runner")
    report["cargo_lock_sha256"] = sha256(out / "Cargo.lock")
    modes = (
        ("constructors", "boot")
        if a.boot_only
        else ("constructors", "replay", *(() if a.skip_boot else ("boot",)))
    )
    for mode in modes:
        run_logged(
            mode, [str(out / "runner"), str(out / "spec.json"), mode], cwd=upstream
        )
        report[mode] = json.loads((out / (mode + ".json")).read_text())
        write_json(out / "report.json", report)
    require(
        source_hashes() == provenance["source_hashes"],
        "Source changed during native migration check",
    )
    if a.operation_trace:
        report["startup_operations"] = json.loads(
            (out / "startup-operations.json").read_text()
        )
    if a.arm_diagnostics:
        report["arm_diagnostics"] = json.loads(
            (out / "arm-diagnostics.json").read_text()
        )
        require(
            report["arm_diagnostics"]["status"] == "passed",
            "Diagnostic UI controls failed",
        )
    require(not git(upstream, "status", "--porcelain"), "Native upstream changed")
    require(gen == {p: sha256(generation / p) for p in gen}, "Generated core drift")
    report["reply_parity_qualified"] = (
        None if a.boot_only else report["replay"]["legacy_replies_exact"]
    )
    report["default_migration_ready"] = False
    report["unresolved"] = [
        "Default lab backend migration remains outside this run",
        "Physical timing, DSP ROM and hardware are unverified",
    ]
    if not a.boot_only and not report["reply_parity_qualified"]:
        report["unresolved"].insert(
            0,
            "Old/new DSP control replies differ; current stock and candidate replies are exact",
        )
    report["status"] = (
        "passed-native-candidate-application-startup"
        if a.boot_only
        else (
            (
                "native-constructor-and-voice-replay-validated-reply-parity-open"
                if a.skip_boot
                else "native-first-slice-validated-reply-parity-open"
            )
            if not report["reply_parity_qualified"]
            else (
                "passed-constructors-and-replay"
                if a.skip_boot
                else "passed-first-native-migration-slice"
            )
        )
    )
    print(report["status"], flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
