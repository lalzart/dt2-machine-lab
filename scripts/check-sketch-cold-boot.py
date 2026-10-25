#!/usr/bin/env python3
"""CPU reset plus SHARC application entry with live native coupling.

No ready snapshot. DSP ROM and CPU-to-DSP boot upload remain outside the model.
The inspected native upstream is read-only; lab dependency pins stay unchanged.
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
p.add_argument("build", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--native-upstream", required=True, type=Path)
a = p.parse_args()
provenance = doctor()
upstream = a.native_upstream.resolve()
revision = "38dfbe4ae88263511eed95691c07fc07e17b6f26"
require(git(upstream, "rev-parse", "HEAD") == revision, "Unknown native upstream")
require(not git(upstream, "status", "--porcelain"), "Dirty native upstream")
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(exist_ok=False, parents=True)
os.environ["DT2_LAB_RUN_DIR"] = out.name
from lab.runtime import STOCK_BLOB, STOCK_MAIN
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit

device = DeviceBuild(a.build, STOCK_MAIN.read_bytes())
audit(device.blob)
inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(
    sha256(inputs["syx"])
    == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
    "Stock SYX drift",
)
require(
    sha256(inputs["card"])
    == "f0a30d418c256ad2d8a87c395a36ffbce2fb8ad0119d755927b442f77df28cea",
    "Stock card drift",
)
reset_proof = ROOT / "out/runs/sketch-dsp-startup-20261023-01/report.json"
require(
    sha256(reset_proof)
    == "86c599454f5d3dfbecf4e7ee5cd9da7f6b2b2da165caa79d480228738dc3c8e1",
    "Reset model drift",
)
write_json(
    out / "reset-values.json", json.loads(reset_proof.read_text())["reset_values"]
)
generation = upstream / "out/native/shared-core/gen"
names = ("core_i.rs", "core_g.rs", "syms.rs", "tables.rs", "CORE_FINGERPRINT")
generated = {name: sha256(generation / name) for name in names}
env = {
    k: v for k, v in os.environ.items() if not k.startswith(("SHARC_", "DSP_", "DIGI_"))
}
env["SHARC_GEN_DIR"] = str(generation)
report = dict(
    status="running",
    scope=__doc__,
    captures=0,
    hardware=False,
    dsp_rom_executed=False,
    boot_upload_emulated=False,
    native_upstream_revision=revision,
    generated_core=generated,
    source_hashes=provenance["source_hashes"],
    device=device.identity,
    input_hashes={k: sha256(inputs[k]) for k in ("syx", "card")},
    arms={},
)
try:
    for name in provenance["source_hashes"]:
        dest = out / "frozen-sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    helper = ROOT / "lab/native/sketch_cold_inputs.py"
    for label, blob in (("stock", STOCK_BLOB), ("device", device.blob_path)):
        cmd = [
            sys.executable,
            "-c",
            "import runpy,sys; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')",
            str(helper),
            str(blob),
            str(out / "reset-values.json"),
            str(out / f"{label}-inputs"),
        ]
        subprocess.run(cmd, cwd=upstream, env=env, check=True, timeout=120)
    spec = dict(
        output=str(out),
        syx=inputs["syx"],
        card=inputs["card"],
        main=str(device.folder / device.manifest["cpu"]["path"]),
        metadata=str(device.folder / "native-patches.json"),
        stock_inputs=str(out / "stock-inputs"),
        device_inputs=str(out / "device-inputs"),
    )
    write_json(out / "spec.json", spec)
    (out / "src").mkdir()
    shutil.copyfile(ROOT / "lab/native/sketch_cold_probe.rs", out / "src/main.rs")
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-sketch-cold-probe"\nversion="0.1.0"\nedition="2024"\n'
        '[dependencies]\nserde_json="1"\nsha2="0.10"\n'
        "elektron-native-boot={path="
        + json.dumps(str(upstream / "packages/emulator/boot"))
        + ',features=["sharc"]}\n'
        "sharc-native={path="
        + json.dumps(str(upstream / "packages/emulator/sharc"))
        + "}\n"
    )
    # Warm firmware-free cache; unique probe binary, no upstream source changes.
    target = upstream / "out/native/target/generic"
    print("Building bounded cold-start probe", flush=True)
    with (out / "build.log").open("w") as log:
        subprocess.run(
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
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=900,
        )
    binary = target / "release/dt2-sketch-cold-probe"
    report["runner_sha256"] = sha256(binary)
    report["cargo_lock_sha256"] = sha256(out / "Cargo.lock")
    for mode in ("stock", "device", "detached"):
        print("Starting " + mode + " from reset/application entry", flush=True)
        with (
            (out / f"{mode}.stdout.log").open("w") as stdout,
            (out / f"{mode}.stderr.log").open("w") as stderr,
        ):
            result = subprocess.run(
                [str(binary), str(out / "spec.json"), mode],
                cwd=upstream,
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=660,
            )
        if mode == "detached":
            require(
                result.returncode != 0
                and "Native DSP coupling absent after 8 CPU frames"
                in (out / f"{mode}.stderr.log").read_text(),
                "Disconnected-DSP negative was not detected",
            )
            report["disconnected_dsp_negative_detected"] = True
        else:
            require(
                result.returncode == 0, mode + " cold-start failure; inspect stderr"
            )
            report["arms"][mode] = json.loads((out / mode / "report.json").read_text())
        write_json(out / "report.json", report)
    require(
        source_hashes() == provenance["source_hashes"], "Source changed during check"
    )
    require(not git(upstream, "status", "--porcelain"), "Native source changed")
    require(
        {name: sha256(generation / name) for name in generated} == generated,
        "Generated core changed",
    )
    report["status"] = "passed-coupled-application-startup"
    print(report["status"], flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
