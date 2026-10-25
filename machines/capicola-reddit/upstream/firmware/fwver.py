"""Which Digitakt II OS the firmware builders patch: DT2_FW=1.17 (default, the latest
release) or 1.16.

Section 7 (the SHARC image) is identical in 1.16 and 1.17, so the DSP code and its
addresses carry over as they are; MAIN OS (ColdFire) moved, so every MAIN OS
address the builders use goes through A(): itself on 1.16, on 1.17 its place in
addr_1.17.json (made by addrmap.py from the two stock images: each address found
by its surroundings, uniquely, RAM ones by all the references to them agreeing).
An address not in the table is an error, never a guess.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
WORKSPACE = pathlib.Path(os.environ.get("DT2_WORKSPACE") or REPO.parent)
DEPS = pathlib.Path(os.environ.get("DT2_DEPS") or REPO / "deps")   # ./build.sh's clones and Elektron's OS file
FW = os.environ.get("DT2_FW", "1.17")
KNOWN = {   # version: (stock .syx under the workspace, its sha256)
    "1.16": ("Digitakt_II_OS1.16_dist/Digitakt_II_OS1.16.syx",
             "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec"),
    "1.17": ("Digitakt_II_OS1.17_dist/Digitakt_II_OS1.17.syx",
             "26c22f6652625ac2cfd47f7ee970d388ed8b6427dae3563c0a6a2f2d334350d5"),
}
if FW not in KNOWN:
    raise SystemExit(f"DT2_FW={FW!r}: known are {', '.join(KNOWN)}")
STOCK_REL, STOCK_SHA256 = KNOWN[FW]
TAG = FW.replace(".", "")                       # "116", "117": file names

_MAP = None
if FW != "1.16":
    _MAP = {int(k, 16): int(v, 16) for k, v in json.loads((HERE / f"addr_{FW}.json").read_text())["map"].items()}


def stock_path(version: str = FW) -> pathlib.Path | None:
    """Elektron's OS file for `version`, the first of these that is that exact
    release (by sha256): DT2_STOCK_SYX, deps/stock/ (where ./build.sh puts it),
    the workspace's Elektron folder. None if there is none."""
    rel, sha = KNOWN[version]
    found = [pathlib.Path(os.environ["DT2_STOCK_SYX"])] if os.environ.get("DT2_STOCK_SYX") else []
    for p in found + [DEPS / "stock" / pathlib.PurePath(rel).name, WORKSPACE / rel]:
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == sha:
            return p
    return None


def stock() -> pathlib.Path:
    p = stock_path()
    if p is None:
        raise SystemExit(f"no Elektron Digitakt II OS {FW} file: run ./build.sh --stock FILE, or set DT2_STOCK_SYX "
                         f"(looked in {DEPS / 'stock'} and {WORKSPACE / STOCK_REL})")
    return p


def A(addr: int) -> int:
    """a 1.16 MAIN OS address on the chosen OS"""
    if _MAP is None:
        return addr
    if addr not in _MAP:
        raise SystemExit(f"{addr:#x} has no {FW} address in addr_{FW}.json (run addrmap.py on it)")
    return _MAP[addr]
