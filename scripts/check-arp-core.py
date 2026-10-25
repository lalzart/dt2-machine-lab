"""Build and audit the original ColdFire arp instruction routines."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.arp_native import SIZE, build
from lab.arp_ui import collector
from lab.arp_emulation import CODE
from lab.coldfire import audit_code
from lab.project import require

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
rows = []
entries = build()
for name, (address, code) in entries.items():
    (out / (name + ".bin")).write_bytes(code)
    rows.append({"name": name, "address": hex(address), "bytes": len(code),
                 "sha256": hashlib.sha256(code).hexdigest(),
                 "instructions": len(audit_code(code, address))})
wrappers = []
for name, address, release in (("press", CODE + 0x1800, False),
                               ("release", CODE + 0x1C00, True)):
    code = collector(address, entries[name][0], release)
    (out / (name + "-collector.bin")).write_bytes(code)
    wrappers.append({"name": name, "address": hex(address), "bytes": len(code),
                     "sha256": hashlib.sha256(code).hexdigest(),
                     "instructions": len(audit_code(code, address))})
(out / "core.json").write_text(json.dumps({"status": "passed", "state_bytes": SIZE,
                                             "routines": rows, "collectors": wrappers}, indent=2) + "\n")
print("PASS", sum(r["bytes"] for r in rows + wrappers), "audited native bytes;", SIZE, "state bytes")
