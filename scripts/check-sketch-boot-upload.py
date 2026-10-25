#!/usr/bin/env python3
"""Check device boot-stream rules and the native OS1.16 CPU upload handshake.

No ROM binary, SPI FIFO model, physical timing, recording or hardware access.
The full candidate container is checked separately. Native construction of it
hits a known signature-matching limit, so the sender fixture carries stock MAIN
and candidate DSP; sealed candidate MAIN is installed before instruction zero.
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
upstream = a.native_upstream.resolve()
revision = "38dfbe4ae88263511eed95691c07fc07e17b6f26"
require(git(upstream, "rev-parse", "HEAD") == revision, "Unknown native upstream")
require(not git(upstream, "status", "--porcelain"), "Dirty native upstream")
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(exist_ok=False, parents=True)
os.environ["DT2_LAB_RUN_DIR"] = out.name
provenance = doctor()
from lab.runtime import STOCK_BLOB, STOCK_MAIN
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit, blocks
from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

device = DeviceBuild(a.build, STOCK_MAIN.read_bytes())
report = dict(
    status="running",
    scope=__doc__,
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    device=device.identity,
    native_upstream_revision=revision,
    hardware=False,
    rom_executed=False,
)
try:
    for name in provenance["source_hashes"]:
        dest = out / "frozen-sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    report["stream"] = audit(device.blob)
    old = ROOT / "out/runs/sketch-device-build-20261023-09"
    old_blob = old / "dsp/RETIRE_BLOB.bin"
    require(
        sha256(old_blob)
        == "e5316478d6ac2544bb8eef7daac5256fe3e36122b2c1c96a52d2bb1fb9dfe13b",
        "Legacy identity drift",
    )
    # DeviceBuild already reproduces the complete sealed MAIN from current
    # emitters. UI/duration changes may differ from the historical DSP fix;
    # the complete stock upload routine must still be byte-exact.
    sender = slice(0x400CCF74 - 0x40000400, 0x400CD2A8 - 0x40000400)
    require(
        device.image[sender] == STOCK_MAIN.read_bytes()[sender],
        "Stock CPU upload routine changed",
    )
    # Compare every original loaded byte/FILL, independent of stream ordering.
    before, after = blocks(old_blob.read_bytes()), blocks(device.blob)
    n = len(blocks(STOCK_BLOB.read_bytes()))
    reordered = after[: n - 1] + [after[-1]] + after[n - 1 : -1]
    require(len(before) == len(reordered), "Block count changed")
    pads = []
    for b, c in zip(before, reordered, strict=True):
        require(b[:2] == c[:2], "DSP target/flags changed")
        if b[0] == 0x5001:
            require(b[2] == c[2] and b[4] == c[4], "FIRST payload changed")
        elif b[0] == 1:
            require(
                c[2] == b[2] + (-b[2]) % 4
                and c[3] == b[3]
                and c[4] == b[4] + bytes((-b[2]) % 4),
                "DSP code payload changed",
            )
            if c[2] != b[2]:
                pads.append(dict(target=b[1], original_bytes=b[2], padding=c[2] - b[2]))
        else:
            require(b == c, "DSP FILL/INIT/FINAL changed")
    report["equivalence"] = dict(
        current_cpu_rebuild_exact=True,
        cpu_matches_historical_baseline=device.image
        == (old / "SKETCH_MAIN.bin").read_bytes(),
        stock_upload_routine_byte_exact=True,
        stock_upload_routine=[0x400CCF74, 0x400CD2A8],
        all_prior_loaded_bytes_exact=True,
        padding=pads,
    )
    from lab.recorder_native_retirement import build as legacy_build

    default_blob, default_meta = legacy_build(out / "legacy-default")
    default_reference = (
        ROOT / "out/runs/sketch-memory-startup-20261023-01/legacy-default"
    )
    require(
        default_blob == (default_reference / "RETIRE_BLOB.bin").read_bytes()
        and default_meta == json.loads((default_reference / "build.json").read_text()),
        "Ordinary prepared-emulator DSP bytes/metadata changed",
    )
    report["legacy_default_bytes_and_metadata_exact"] = True
    # Separate implementation of the public-manual rules in inspected upstream.
    for label, path in (
        ("stock", STOCK_BLOB),
        ("device", device.blob_path),
        ("legacy", old_blob),
    ):
        code = (
            "import json,sys; from tools.sharc_dev.sharc_bootcheck import check; "
            "from pathlib import Path; r=check(Path(sys.argv[1]).read_bytes()); "
            "print(json.dumps(dict(ok=r.ok,blocks=len(r.blocks),errors=[str(x) for x in r.errors])))"
        )
        r = subprocess.run(
            [sys.executable, "-B", "-c", code, str(path)],
            cwd=upstream,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        result = json.loads(r.stdout)
        require(
            result["ok"] == (label != "legacy"),
            "Independent Python rules disagree: " + label,
        )
        report[label + "_independent_python"] = result
    ref = ROOT / "out/references/elekloader-upload-audit"
    require(
        git(ref, "rev-parse", "HEAD") == REFERENCE_REVISION
        and not git(ref, "status", "--porcelain"),
        "Codec identity drift",
    )
    sys.path[:0] = [str(config["digikit"]), str(ref)]
    from elekloader.codec.aplib import pack_section
    from elekloader.syx import Syx

    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    require(
        sha256(inputs["syx"])
        == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
        "Stock SYX drift",
    )
    stock = Syx(Path(inputs["syx"]).read_bytes())
    packed_dsp = pack_section(device.blob)
    raw = assemble_container(stock, {3: pack_section(device.image), 7: packed_dsp})
    report["test_container"] = verify_candidate(
        raw, stock, {3: device.image, 7: device.blob}
    )
    # Deliberately named a test fixture, kept in this ignored evidence folder.
    candidate_container = out / "candidate-test-fixture.syx"
    candidate_container.write_bytes(raw)
    runtime_raw = assemble_container(stock, {7: packed_dsp})
    report["native_input_container"] = verify_candidate(
        runtime_raw, stock, {7: device.blob}
    )
    test_container = out / "cpu-input-test-fixture.syx"
    test_container.write_bytes(runtime_raw)
    spec = dict(
        output=str(out),
        test_container=str(test_container),
        candidate_container=str(candidate_container),
        main=str(device.folder / "SKETCH_MAIN.bin"),
        blob=str(device.blob_path),
        legacy_blob=str(old_blob),
    )
    write_json(out / "spec.json", spec)
    (out / "src").mkdir()
    shutil.copyfile(ROOT / "lab/native/sketch_upload_probe.rs", out / "src/main.rs")
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-sketch-upload-probe"\nversion="0.1.0"\nedition="2024"\n'
        '[dependencies]\nserde_json="1"\nsha2="0.10"\n'
        + "elektron-native-boot={path="
        + json.dumps(str(upstream / "packages/emulator/boot"))
        + "}\n"
        + "patchkit={path="
        + json.dumps(str(upstream / "packages/patchkit"))
        + "}\n"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("SHARC_", "DSP_", "DIGI_"))
    }
    target = upstream / "out/native/target/generic"
    print("Building native CPU upload probe", flush=True)
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
    binary = target / "release/dt2-sketch-upload-probe"
    shutil.copy2(binary, out / "runner")
    report["runner_sha256"] = sha256(out / "runner")
    report["cargo_lock_sha256"] = sha256(out / "Cargo.lock")
    print("Executing OS1.16 CPU reset, depack and sender with busy holds", flush=True)
    with (
        (out / "native.stdout.log").open("w") as stdout,
        (out / "native.stderr.log").open("w") as stderr,
    ):
        subprocess.run(
            [str(out / "runner"), str(out / "spec.json")],
            cwd=upstream,
            env=env,
            stdout=stdout,
            stderr=stderr,
            check=True,
            timeout=600,
        )
    report["native"] = json.loads((out / "native.json").read_text())
    require(
        source_hashes() == provenance["source_hashes"], "Source changed during check"
    )
    require(not git(upstream, "status", "--porcelain"), "Native upstream changed")
    report["status"] = "passed-stream-rules-and-native-cpu-upload"
    print(report["status"], flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
