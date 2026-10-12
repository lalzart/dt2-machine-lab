#!/usr/bin/env python3
"""Measure actual OS1.16 buddy allocations and a fragmentation negative control."""

# ruff: noqa: E402
import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--snapshot",
    type=Path,
    default=ROOT.parent
    / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap",
)
args = p.parse_args()
doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown CPU fixture",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.runtime import STOCK_MAIN  # isort: skip
import plusdrive_check as check

from lab.flex_heap import (
    EXPECTED_BASE,
    EXPECTED_HEADS,
    FREE,
    MALLOC,
    block_bytes,
    inspect_heap,
)

card = out / "unused-card.img"
card.write_bytes(b"")
fw = check.Firmware(card, args.snapshot, STOCK_MAIN)
report = dict(
    status="running",
    scope=__doc__,
    firmware="DTII OS1.16",
    snapshot=sha256(args.snapshot),
    main=sha256(STOCK_MAIN),
    sources={
        str(p.relative_to(ROOT)): sha256(p)
        for p in (ROOT / "lab/flex_heap.py", Path(__file__))
    },
)
try:
    initial = inspect_heap(fw.read)
    report["initial"] = initial.report()
    probes = []
    for requested in (1, 16, 17, 64, 362, 2130, 1920080, 3840080):
        before = inspect_heap(fw.read)
        ptr = fw.call(MALLOC, [requested])
        require(ptr != 0, "Probe allocation failed")
        after = inspect_heap(fw.read)
        expected = block_bytes(requested)
        require(
            before.free_bytes - after.free_bytes == expected
            and after.allocation_counter == before.allocation_counter + 1,
            "Native allocation disagrees with buddy model",
        )
        require((ptr - EXPECTED_BASE) % expected == 0, "Native block alignment differs")
        fw.call(FREE, [ptr])
        restored = inspect_heap(fw.read)
        require(restored == before, "Probe free failed to restore heap")
        probes.append(dict(requested=requested, occupied=expected, ptr=hex(ptr)))
    report["allocations"] = probes
    # Fill available 1 MiB blocks, then free alternating buddy blocks. Plenty of
    # total bytes return, but adjacent free buddies cannot coalesce to 4 MiB.
    owned = []
    while True:
        ptr = fw.call(MALLOC, [1 << 20])
        if not ptr:
            break
        owned.append(ptr)
        require(len(owned) <= 32, "Unexpected arena capacity")
    full = inspect_heap(fw.read)
    require(full.largest_block < 1 << 20, "Failure despite a suitable block")
    kept, released = [], []
    for ptr in owned:
        if ((ptr - EXPECTED_BASE) >> 20) % 2 == 0:
            fw.call(FREE, [ptr])
            released.append(ptr)
        else:
            kept.append(ptr)
    fragmented = inspect_heap(fw.read)
    require(
        fragmented.free_bytes > 4 << 20 and fragmented.largest_block < 4 << 20,
        "Fixture did not create fragmentation",
    )
    failed = fw.call(MALLOC, [3840080])
    require(
        failed == 0
        and inspect_heap(fw.read).blocks == fragmented.blocks
        and inspect_heap(fw.read).allocation_counter
        == fragmented.allocation_counter + 1,
        "Fragmentation rejection mutated heap",
    )
    report["fragmentation"] = dict(
        filled_blocks=len(owned),
        released_blocks=len(released),
        kept_blocks=len(kept),
        free_bytes=fragmented.free_bytes,
        largest_block=fragmented.largest_block,
        request=3840080,
        request_failed=True,
    )
    for ptr in kept:
        fw.call(FREE, [ptr])
    require(
        inspect_heap(fw.read).blocks == initial.blocks,
        "Stress did not restore original heap",
    )
    # A malformed head must never turn into a capacity estimate.
    old = fw.read(EXPECTED_HEADS, 88)
    fw.write(EXPECTED_HEADS, struct.pack(">i", 1))
    try:
        inspect_heap(fw.read)
    except ValueError:
        report["corrupt_list_rejected"] = True
    else:
        raise ValueError("Corrupt heap list accepted")
    finally:
        fw.write(EXPECTED_HEADS, old)
    require(
        inspect_heap(fw.read).blocks == initial.blocks,
        "Negative fixture restore changed heap",
    )
    report["all_allocations_returned"] = True
    report["failed_malloc_counter_drift"] = (
        inspect_heap(fw.read).allocation_counter - initial.allocation_counter
    )
    require(
        report["failed_malloc_counter_drift"] == 2, "Unexpected stock counter drift"
    )
    report["status"] = "PASS"
except Exception as exc:
    report.update(status="FAIL", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    fw.close()
print(json.dumps(report, indent=2))
