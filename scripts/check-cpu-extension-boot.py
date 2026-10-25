#!/usr/bin/env python3
"""Bounded native ColdFire reset/ready check with explicit upstream adapter pin."""

# ruff: noqa: E402
import argparse
import json
import os
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
p.add_argument("package", type=Path)
p.add_argument("output", type=Path)
p.add_argument(
    "--native-upstream",
    required=True,
    type=Path,
    help="Clean inspected DigiKit ed57b475 checkout; does not replace lab pins",
)
args = p.parse_args()
provenance = doctor()
revision = "ed57b4758d45d435d07da37ce06b4090afab843b"
upstream = args.native_upstream.resolve()
require(
    git(upstream, "rev-parse", "HEAD") == revision, "Unknown native adapter revision"
)
require(not git(upstream, "status", "--porcelain"), "Dirty native adapter checkout")
package = args.package.resolve()
manifest = json.loads((package / "manifest.json").read_text())
require(manifest["status"] == "target-build-complete", "Build incomplete")
require(manifest["source_hashes"] == source_hashes(), "Package source drift")
candidate = package / manifest["candidate"]
image = package / manifest["cpu"]["path"]
meta = package / "native-patches.json"
require(sha256(candidate) == manifest["container"]["sha256"], "Package changed")
require(sha256(image) == manifest["cpu"]["sha256"], "MAIN changed")
require(
    json.loads(meta.read_text()) == manifest["cpu"]["native"], "Layout metadata changed"
)
inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
stock = Path(inputs["syx"])
require(
    sha256(stock) == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
    "Unknown stock SYX",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
(out / "src").mkdir()
(out / "src/main.rs").write_bytes(
    (ROOT / "lab/native/cpu_extension_probe.rs").read_bytes()
)
(out / "Cargo.toml").write_text(
    '[package]\nname = "dt2-cpu-extension-probe"\nversion = "0.1.0"\nedition = "2024"\n'
    "[dependencies]\nelektron-native-boot = { path = "
    + json.dumps(str(upstream / "packages/emulator/boot"))
    + ' }\nserde_json = "1"\nsha2 = "0.10"\n'
)
target = ROOT / "out/cache/cpu-extension-native" / revision
report = dict(
    status="running",
    hardware=False,
    coupled_dsp=False,
    firmware="Digitakt II OS1.16",
    candidate_sha256=sha256(candidate),
    main_sha256=sha256(image),
    upstream_revision=revision,
    source_hashes=provenance["source_hashes"],
    lab_dependencies=provenance["dependencies"],
    limits=[
        "ColdFire reset with modeled peripherals; no coupled DSP",
        "Emulator ready and instruction counts do not establish device timing or cache coherence",
    ],
)
try:
    with (out / "build.log").open("w") as log:
        subprocess.run(
            [
                "rustup",
                "run",
                "1.98.0",
                "cargo",
                "build",
                "--offline",
                "--release",
                "--manifest-path",
                str(out / "Cargo.toml"),
                "--target-dir",
                str(target),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=180,
        )
    binary = target / "release/dt2-cpu-extension-probe"
    with (
        (out / "native.json").open("w") as stdout,
        (out / "stderr.log").open("w") as stderr,
    ):
        subprocess.run(
            [str(binary), str(stock), str(image), str(meta)],
            stdout=stdout,
            stderr=stderr,
            check=True,
            timeout=180,
        )
    native = json.loads((out / "native.json").read_text())
    require(
        native["status"] == "passed" and native["main_sha256"] == sha256(image),
        "Native check failed",
    )
    # Causal negative: restore only the original reset calls. The same segment
    # comparison must fail before any main-task or UI execution can hide it.
    from lab.cpu_extension import RESET, RESET_BYTES
    from lab.dt2_116 import BASE

    disabled = bytearray(image.read_bytes())
    disabled[RESET - BASE : RESET - BASE + len(RESET_BYTES)] = RESET_BYTES
    negative_image = out / "NO_LOADER_MAIN.bin"
    negative_image.write_bytes(disabled)
    negative_meta = json.loads(meta.read_text())
    negative_meta["sha256"] = sha256(negative_image)
    write_json(out / "no-loader-metadata.json", negative_meta)
    with (
        (out / "no-loader.stdout.log").open("w") as stdout,
        (out / "no-loader.stderr.log").open("w") as stderr,
    ):
        failed = subprocess.run(
            [
                str(binary),
                str(stock),
                str(negative_image),
                str(out / "no-loader-metadata.json"),
            ],
            stdout=stdout,
            stderr=stderr,
            timeout=180,
        )
    require(
        failed.returncode != 0
        and "reset segment mismatch" in (out / "no-loader.stderr.log").read_text(),
        "Disabled-loader negative did not detect missing segment copy",
    )
    require(source_hashes() == provenance["source_hashes"], "Source drift")
    require(
        git(upstream, "rev-parse", "HEAD") == revision
        and not git(upstream, "status", "--porcelain"),
        "Native adapter source drift",
    )
    report.update(
        status="passed",
        native=native,
        runner_sha256=sha256(binary),
        runner_source_sha256=sha256(out / "src/main.rs"),
        cargo_lock_sha256=sha256(out / "Cargo.lock"),
        disabled_loader_negative_detected=True,
    )
    print(json.dumps(native, indent=2), flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
