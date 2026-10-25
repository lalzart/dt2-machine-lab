"""Load authenticated package CPU bytes into an explicitly prepared fixture."""

import hashlib
import json
import struct
from pathlib import Path

from lab.cpu_extension import Segment, segment_chain
from lab.dt2_116 import BASE
from lab.project import require, sha256, source_hashes


def load_package(path):
    path = Path(path).resolve()
    m = json.loads((path / "manifest.json").read_text())
    require(m["status"] == "target-build-complete", "Package incomplete")
    require(m["source_hashes"] == source_hashes(), "Package source drift")
    require(
        sha256(path / m["candidate"]) == m["container"]["sha256"], "Candidate changed"
    )
    image = (path / m["cpu"]["path"]).read_bytes()
    require(
        hashlib.sha256(image).hexdigest() == m["cpu"]["sha256"], "CPU image changed"
    )
    meta = m["cpu"]["native"]
    require(meta["sha256"] == m["cpu"]["sha256"], "CPU layout identity changed")
    segments(image, meta)
    return image, meta, m


def segments(image, meta):
    start = meta.get("chain_address", 0x4031FF60) - BASE
    cursor, result = start, []
    for info in meta["segments"]:
        require(cursor + 12 <= len(image), "Truncated segment header")
        n, dest, bss = struct.unpack_from(">III", image, cursor)
        require(
            (n, dest, bss) == (info["data_bytes"], info["destination"], info["bss"]),
            "Segment metadata mismatch",
        )
        cursor += 12
        require(cursor + n <= len(image), "Truncated segment data")
        data = image[cursor : cursor + n]
        require(
            hashlib.sha256(data).hexdigest() == info["sha256"],
            "Segment content changed",
        )
        result.append(Segment(dest, data, bss))
        cursor += n
    require(image[start:] == segment_chain(tuple(result)), "Invalid segment chain")
    return tuple(result)


def install(write, image, meta, *, read=None):
    """No reset claim: install code/data directly and initialize runtime views.

    Appended CAPI source lives in stock BSS. Never write that source into an
    already running fixture; populate its SRAM destination instead.
    """
    for w in meta["writes"]:
        if w["payload"] or "runtime_address" in w:
            continue
        before, after = bytes.fromhex(w["before"]), bytes.fromhex(w["after"])
        if read is not None:
            require(
                read(w["address"], len(before)) == before,
                "Fixture byte guard " + w["label"],
            )
        write(w["address"], after)
    if meta.get("base"):
        for w in meta["base"]["runtime_initializers"]:
            write(w["address"], bytes.fromhex(w["after"]))
    for s in segments(image, meta):
        write(s.destination, s.data + bytes(s.bss))
