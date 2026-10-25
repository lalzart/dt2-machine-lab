#!/usr/bin/env python3
"""Check isolated Sketch MAIN from reset using the pinned native CPU adapter."""

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
p.add_argument("build", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--native-upstream", type=Path, required=True)
a = p.parse_args()
provenance = doctor()
revision = "ed57b4758d45d435d07da37ce06b4090afab843b"
upstream = a.native_upstream.resolve()
require(
    git(upstream, "rev-parse", "HEAD") == revision, "Unknown native adapter revision"
)
require(not git(upstream, "status", "--porcelain"), "Dirty native adapter")
package = a.build.resolve()
manifest = json.loads((package / "manifest.json").read_text())
require(manifest["status"] == "local-build-complete", "Incomplete build")
require(manifest["source_hashes"] == source_hashes(), "Build source drift")
image = package / manifest["cpu"]["path"]
require(sha256(image) == manifest["cpu"]["sha256"], "MAIN changed")
metadata = package / "native-patches.json"
meta = json.loads(metadata.read_text())
require(
    meta == {k: v for k, v in manifest["cpu"].items() if k != "path"},
    "Metadata changed",
)
inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
stock = Path(inputs["syx"])
require(
    sha256(stock) == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
    "Unknown stock",
)
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
(out / "src").mkdir()
(out / "src/main.rs").write_bytes(
    (ROOT / "lab/native/sketch_device_probe.rs").read_bytes()
)
(out / "Cargo.toml").write_text(
    '[package]\nname="dt2-sketch-device-probe"\nversion="0.1.0"\nedition="2024"\n'
    "[dependencies]\nelektron-native-boot={path="
    + json.dumps(str(upstream / "packages/emulator/boot"))
    + '}\nserde_json="1"\nsha2="0.10"\n'
)
target = ROOT / "out/cache/cpu-extension-native" / revision
report = dict(
    status="running",
    hardware=False,
    coupled_dsp=False,
    source_hashes=provenance["source_hashes"],
    main_sha256=sha256(image),
    native_upstream_revision=revision,
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
    binary = target / "release/dt2-sketch-device-probe"
    with (
        (out / "native.json").open("w") as stdout,
        (out / "stderr.log").open("w") as stderr,
    ):
        subprocess.run(
            [str(binary), str(stock), str(image), str(metadata), str(out)],
            stdout=stdout,
            stderr=stderr,
            check=True,
            timeout=180,
        )
    native = json.loads((out / "native.json").read_text())
    require(native["status"] == "passed", "Native probe failed")
    # Causal control: all payload bytes remain, but the reset loader is disabled.
    from lab.cpu_extension import RESET, RESET_BYTES
    from lab.dt2_116 import BASE

    disabled = bytearray(image.read_bytes())
    disabled[RESET - BASE : RESET - BASE + len(RESET_BYTES)] = RESET_BYTES
    negative = out / "NO_LOADER_MAIN.bin"
    negative.write_bytes(disabled)
    write_json(out / "no-loader-metadata.json", dict(meta, sha256=sha256(negative)))
    with (
        (out / "negative.stdout.log").open("w") as stdout,
        (out / "negative.stderr.log").open("w") as stderr,
    ):
        result = subprocess.run(
            [
                str(binary),
                str(stock),
                str(negative),
                str(out / "no-loader-metadata.json"),
                str(out),
            ],
            stdout=stdout,
            stderr=stderr,
            timeout=180,
        )
    require(
        result.returncode != 0
        and "reset segment mismatch" in (out / "negative.stderr.log").read_text(),
        "Missing-loader control did not detect absent initialization",
    )
    require(source_hashes() == provenance["source_hashes"], "Check source drift")
    require(not git(upstream, "status", "--porcelain"), "Native adapter source drift")
    report.update(
        status="passed",
        native=native,
        disabled_loader_negative_detected=True,
        runner_sha256=sha256(binary),
        runner_source_sha256=sha256(out / "src/main.rs"),
        cargo_lock_sha256=sha256(out / "Cargo.lock"),
    )
    print(json.dumps(native, indent=2))
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
