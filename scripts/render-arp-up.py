"""Reuse the verified buffered stock-voice renderer for a passing arp capture."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("capture", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
capture, out = args.capture.resolve(), args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
meta = json.loads((capture / "arp.json").read_text())
require(meta["status"] == "passed" and meta["condition"] in ("up","order","random"), "Arp capture did not pass")
require(sha256(capture / "control.dtfr") == meta["capture_sha256"], "Capture changed")
compatible = out / "renderer-input"
compatible.mkdir()
shutil.copy2(capture / "control.dtfr", compatible / "pattern.dtfr")
write_json(compatible / "capture.json", {
    "status": "captured", "mode": "interactive", "machine": "stock",
    "capture_sha256": meta["capture_sha256"], "ticks": meta["ticks"],
    "passes": [{"render_start": meta["render_start"], "render_end": meta.get("record_end",meta["render_end"])}],
})
subprocess.run([sys.executable, str(ROOT / "scripts/render-pattern.py"),
                str(compatible), str(out / "replay")], check=True, timeout=600)
print(out / "replay/pattern.wav")
