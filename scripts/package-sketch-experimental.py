#!/usr/bin/env python3
"""Deliver a local Sketch-only OS1.16 SYX after exact-build validation.

Consumes fresh sealed build, upload and native startup reports. Reuses a
validated recorder flow only when its firmware/container bytes are identical.
No hardware, transfer, publication or previous Flex implementation is included.
"""

# ruff: noqa: E402
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

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("build", type=Path)
p.add_argument("upload", type=Path)
p.add_argument("startup", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--workflow-proof", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored output")
require(not out.exists(), "Output already exists")
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
from lab.runtime import STOCK_MAIN
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit
from lab.upload import REFERENCE_REVISION, verify_candidate

device = DeviceBuild(a.build, STOCK_MAIN.read_bytes())
require(
    device.manifest["source_hashes"] == provenance["source_hashes"],
    "Build source drift",
)
proofs = {}
for label, folder, status in (
    ("upload", a.upload, "passed-stream-rules-and-native-cpu-upload"),
    ("startup", a.startup, "passed-native-candidate-application-startup"),
):
    path = folder.resolve() / "report.json"
    proof = json.loads(path.read_text())
    require(proof["status"] == status, label + " did not pass")
    require(
        proof["source_hashes"] == provenance["source_hashes"], label + " source drift"
    )
    require(proof["device"] == device.identity, label + " build identity differs")
    proofs[label] = proof
upload, startup = proofs["upload"], proofs["startup"]
candidate = a.upload.resolve() / "candidate-test-fixture.syx"
candidate_sha = sha256(candidate)
require(candidate_sha == upload["test_container"]["sha256"], "Upload container drift")
require(
    startup["input_hashes"]["candidate"] == candidate_sha, "Startup container differs"
)
require(
    startup["boot"]["candidate_container_loaded"]
    and not startup["boot"]["host_MAIN_overlay"]
    and startup["boot"]["CPU_canaries_and_code_intact"]
    and startup["boot"]["Sketch_rendered"],
    "Incomplete native application startup",
)

workflow_path = a.workflow_proof.resolve()
workflow = json.loads(workflow_path.read_text())
require(
    workflow["status"] == "passed-bounded-native-BUF-recorder-connection",
    "Unqualified recorder workflow",
)
require(
    workflow["firmware"]["main_sha256"] == device.meta["sha256"]
    and workflow["firmware"]["blob_sha256"] == sha256(device.blob_path),
    "Recorder workflow firmware differs",
)
for name, digest in workflow["artifact_sha256"].items():
    require(sha256(ROOT / name) == digest, "Recorder evidence drift: " + name)
flow_container = Path(workflow["flow"]) / "candidate-test-fixture.syx"
require(sha256(flow_container) == candidate_sha, "Recorder workflow container differs")
changes = {
    name
    for name, digest in workflow["current_source_hashes"].items()
    if provenance["source_hashes"].get(name) != digest
}
require(
    changes
    <= {"scripts/check-native-sketch.py", "scripts/check-sketch-boot-upload.py"},
    "Recorder implementation changed: " + str(sorted(changes)),
)
extra = set(provenance["source_hashes"]) - set(workflow["current_source_hashes"])
require(extra <= {"scripts/package-sketch-experimental.py"}, "Unqualified new source")

ref = ROOT / "out/references/elekloader-upload-audit"
require(
    git(ref, "rev-parse", "HEAD") == REFERENCE_REVISION
    and not git(ref, "status", "--porcelain"),
    "Codec identity drift",
)
sys.path[:0] = [str(config["digikit"]), str(ref)]
from elekloader.syx import Syx

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
stock_path = Path(inputs["syx"])
require(
    sha256(stock_path)
    == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
    "Stock OS1.16 identity drift",
)
raw = candidate.read_bytes()
container = verify_candidate(
    raw, Syx(stock_path.read_bytes()), {3: device.image, 7: device.blob}
)
require(container == upload["test_container"], "Package verification changed")
stream = audit(device.blob)
require(
    source_hashes() == provenance["source_hashes"], "Source changed during packaging"
)
out.mkdir(parents=True, exist_ok=False)
filename = "EXPERIMENTAL_SKETCH_BUF_OS1.16.syx"
(out / filename).write_bytes(raw)
require(sha256(out / filename) == candidate_sha, "Delivered package copy differs")
report = dict(
    status="local-experimental-package-validated",
    firmware="Digitakt II OS 1.16",
    profile="Sketch/BUF only; previous Flex and other custom features excluded",
    future_combined_os="BUF/Sketch replaces previous Flex; preserve old profiles as reference",
    package=filename,
    package_sha256=candidate_sha,
    stock_sha256=sha256(stock_path),
    device=device.identity,
    container=container,
    stream=stream,
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    proofs={
        label: dict(
            path=str(folder.resolve() / "report.json"),
            sha256=sha256(folder / "report.json"),
        )
        for label, folder in (("upload", a.upload), ("startup", a.startup))
    },
    recorder_workflow=dict(
        index=str(workflow_path),
        index_sha256=sha256(workflow_path),
        package_byte_exact=True,
        validation_only_source_changes=sorted(changes),
        new_sources=sorted(extra),
        new_recordings=0,
    ),
    hardware_transferred=False,
    hardware_validated=False,
    limitations=[
        "DSP ROM and physical SPI FIFO/ready-tail acceptance are unverified",
        "Physical memory/cache/DMA/stack ownership and real-time timing are unverified",
        "Native recorder input is modeled stereo; normalization gain is not simulated",
        "New-core recorder flow qualifies LEN16; mono and LEN32/64 lack that native flow",
        "Ten-second cap and normal 16-step clock; publication may miss the next first trigger",
        "ONESHOT is the proven playback path; retirement guards remain conservative",
        "No BUF/FREEZE project persistence or +Drive saving; no listening/device trial",
    ],
)
write_json(out / "manifest.json", report)
(out / "SHA256SUMS").write_text(f"{candidate_sha}  {filename}\n")
(out / "README.md").write_text(
    "# Sketch/BUF experimental firmware — Digitakt II OS 1.16\n\n"
    "Local experimental build; not hardware-qualified. No firmware has been sent to a device.\n\n"
    f"Package: `{filename}`\n\nSHA-256: `{candidate_sha}`\n\n"
    "This standalone OS1.16 profile includes Sketch/BUF only. It does not include the previous "
    "Flex implementation, Arp, Plaits, Capicola or the DigiKit OS1.17 runtime. In a future combined "
    "OS, BUF/Sketch replaces the previous Flex implementation.\n\n"
    "SONG tap opens/closes Sketch; FUNC+SONG arms the selected BUF for the next bar; held SONG "
    "creates a separately selectable FREEZE. BUF1–4 are global; publication preserves track "
    "assignments and retained readers. R.LEN16/32/64 uses the normal 16-step clock and ten-second cap. "
    "NORMAL keeps the stock recorder workflow.\n\n"
    "The delivered bytes pass container/seal/checksum, depack/staging, boot-stream and native "
    "CPU upload/backpressure checks. Full-container CPU application startup and independently "
    "initialized DSP application startup render Sketch with intact CPU code/canaries. The same "
    "package bytes passed native A/FREEZE/B/cancel and saved stock final-output comparisons. "
    "Application startup does not execute the physical bootstrap or DSP ROM.\n\n"
    "Remaining limits:\n\n"
    + "".join(f"- {v}.\n" for v in report["limitations"])
    + "\nKeep the known-good stock firmware and backups available for any separately authorized "
    "device trial. This folder performs no transfer or installation. See manifest.json for exact "
    "sources, input hashes and evidence paths.\n"
)
print(
    json.dumps(
        dict(status=report["status"], package=str(out / filename), sha256=candidate_sha)
    )
)
