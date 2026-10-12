# ruff: noqa: E402
"""Execute the hash-guarded OS 1.16 bootstrap depacker on candidate streams.

This runs the actual firmware routine under Unicorn, in scratch memory. It is
not a full boot, a flash test, or verification of the hardware memory map.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, git, require, settings, sha256, write_json
from lab.upload import REFERENCE_REVISION, digest

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=Path)
parser.add_argument("--elekloader-reference", required=True, type=Path)
args = parser.parse_args()
doctor()
reference = args.elekloader_reference.resolve()
require(
    git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION,
    "Wrong reference revision",
)
require(not git(reference, "status", "--porcelain"), "Dirty reference checkout")
sys.path[:0] = [str(config["digikit"]), str(reference)]
from elekloader.syx import Syx
from emu.extract import depack

run = args.run.resolve()
require(run.is_relative_to(ROOT / "out/runs"), "Expected lab run directory")
report_path = run / "device-depacker.json"
require(not report_path.exists(), "Refusing to overwrite previous evidence")
manifest = json.loads((run / "manifest.json").read_text())
candidate = run / manifest["candidate"]
require(sha256(candidate) == manifest["container"]["sha256"], "Candidate hash changed")
parsed = Syx(candidate.read_bytes())
bootstrap = parsed.section(2)
require(
    digest(bootstrap)
    == "79667563ab7d8da070f461fbaa888207fe7a457748e538386cbd172239bf8d43",
    "Unknown bootstrap; do not reuse depacker address",
)
report = {
    "candidate_sha256": sha256(candidate),
    "bootstrap_sha256": digest(bootstrap),
    "entry": "0x80000432",
    "scope": "Actual 1.16 routine under Unicorn, separate scratch input/output",
    "hardware_ready": False,
    "sections": {},
}
try:
    for sid in (8, 3, 7):
        started = time.monotonic()
        expected = parsed.section(sid)
        actual = depack(
            bootstrap[4:], parsed.stored[sid], at=0x80000432, limit=250_000_000
        )
        require(actual == expected, f"Device depacker mismatch for section {sid}")
        report["sections"][str(sid)] = {
            "sha256": digest(actual),
            "bytes": len(actual),
            "seconds": time.monotonic() - started,
            "exact": True,
        }
        print(
            f"Section {sid}: actual bootstrap depacker exact ({len(actual)} bytes)",
            flush=True,
        )
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(report_path, report)
