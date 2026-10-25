#!/usr/bin/env python3
"""Exercise the real OS1.16 MAIN DSP depacker with its actual 1MiB allocation.

The failed build is a causal negative control. No hardware access is involved.
"""

# ruff: noqa: E402, I001
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
p.add_argument("--failed-package", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
sys.path[:0] = [str(config["digikit"]), str(config["digikit"] / "tools")]
from lab.upload import verify_dsp_staging, verify_stock_layout
from emu.harness import Machine, call
from unicorn import UC_HOOK_MEM_WRITE
import sharcldr

reference = ROOT / "out/references/elekloader-upload-audit"
sys.path.insert(0, str(reference))
from elekloader.syx import Syx

frozen = source_hashes()
report = dict(
    status="running",
    source_hashes=frozen,
    firmware="OS1.16",
    hardware=False,
    scope=__doc__,
    cases=[],
)
# Keep the precise CPU allocation layout: buffer[0]=command3, output=buffer+1.
SRC, BUFFER, ALLOCATION = 0x50000000, 0x60000000, 0x100000
OUTPUT = BUFFER + 1


def load(path):
    m = json.loads((path / "manifest.json").read_text())
    syx = path / m["candidate"]
    require(sha256(syx) == m["container"]["sha256"], "Candidate drift")
    s = Syx(syx.read_bytes())
    verify_stock_layout(s)
    return m, s


def execute(label, container, expected):
    main = container.section(3)
    # Authenticate all bytes around the exact MAIN entry used by this build.
    require(
        main[0x4013815C - 0x40000400 : 0x40138174 - 0x40000400].hex()
        == "4fefffec428148d7043c282f001c7601206f001822445088",
        "Unknown MAIN depacker",
    )
    stream = container.stored[7]
    m = Machine()
    m.install_isa_patches()
    m.load(main, 0x40000400)
    for at in range(SRC, SRC + len(stream) + 0x100000, 0x100000):
        m.ensure(at)
    for at in range(
        BUFFER, BUFFER + max(ALLOCATION + 0x100000, len(expected) + 0x100000), 0x100000
    ):
        m.ensure(at)
    m.uc.mem_write(SRC, stream)
    m.uc.mem_write(BUFFER, b"\x03" + b"\x5a" * (ALLOCATION - 1))
    canary = bytes.fromhex("c057a11c5afe1160") * 4
    m.uc.mem_write(BUFFER + ALLOCATION, canary)
    crossed = []

    def watch(uc, access, address, size, value, user):
        if address < BUFFER + ALLOCATION and address + size <= BUFFER + ALLOCATION:
            return
        if not crossed:
            crossed.append(dict(address=address, size=size, value=value))

    hook = m.uc.hook_add(
        UC_HOOK_MEM_WRITE,
        watch,
        begin=BUFFER + ALLOCATION,
        end=BUFFER + ALLOCATION + len(expected),
    )
    n = call(m, 0x4013815C, [SRC, OUTPUT], limit=250_000_000)
    m.uc.hook_del(hook)
    actual = bytes(m.uc.mem_read(OUTPUT, n))
    require(actual == expected, "Actual MAIN depacker output differs: " + label)
    require(bytes(m.uc.mem_read(BUFFER, 1)) == b"\x03", "Boot command overwritten")
    intact = bytes(m.uc.mem_read(BUFFER + ALLOCATION, len(canary))) == canary
    result = dict(
        label=label,
        entry="0x4013815c",
        decoded_bytes=n,
        command_bytes=1,
        allocation_bytes=ALLOCATION,
        overflow_bytes=max(0, n + 1 - ALLOCATION),
        crossed_allocation=bool(crossed),
        first_outside_write=crossed[:1],
        canary_intact=intact,
        decoded_exact=True,
        stored_sha256=hashlib.sha256(stream).hexdigest(),
    )
    report["cases"].append(result)
    write_json(out / "report.json", report)
    print(label, result, flush=True)
    return result


try:
    bad, bad_s = load(a.failed_package.resolve())
    good, good_s = load(a.package.resolve())
    require(
        bad["container"]["sha256"]
        == "a70f91d7998253b3baeda919dc2156ec3fd51a4e3532462eb92591913879505a",
        "Wrong hardware-failed build",
    )
    require(good["source_hashes"] == frozen, "New package source drift")
    require(good_s.section(3) == bad_s.section(3), "CPU changed during zero-fill fix")
    # Explicitly prove instruction/data and deterministic initialization identity.
    old_blob, new_blob = bad_s.section(7), good_s.section(7)
    old_mem, new_mem = [
        sharcldr.LoadedMemory.from_stream(b) for b in [old_blob, new_blob]
    ]
    require(
        old_mem._segments[:2] == new_mem._segments[:2], "Loaded region extents changed"
    )
    checked = 0
    for lo, hi in zip(old_mem._segments[0], old_mem._segments[1], strict=True):
        require(
            old_mem.read(lo, hi - lo) == new_mem.read(lo, hi - lo),
            f"Loaded bytes changed {lo:#x}",
        )
        checked += hi - lo
    require(
        sharcldr.entry_points(sharcldr.parse_blocks(old_blob))
        == sharcldr.entry_points(sharcldr.parse_blocks(new_blob)),
        "Entry points changed",
    )
    report["memory_equivalence"] = dict(
        exact=True,
        bytes=checked,
        regions=len(old_mem._segments[0]),
        cpu_exact=True,
        entries_exact=True,
    )
    negative = execute("hardware-failed-literal-zero-build", bad_s, old_blob)
    require(
        negative["crossed_allocation"]
        and not negative["canary_intact"]
        and negative["overflow_bytes"] > 0,
        "Negative did not expose real overflow",
    )
    try:
        verify_dsp_staging(len(bad_s.stored[7]), len(old_blob))
    except ValueError:
        report["old_rejected_by_package_guard"] = True
    else:
        raise ValueError("Package guard admitted old overflow")
    report["new_staging"] = verify_dsp_staging(len(good_s.stored[7]), len(new_blob))
    positive = execute("fixed-fill-build", good_s, new_blob)
    require(
        not positive["crossed_allocation"]
        and positive["canary_intact"]
        and positive["overflow_bytes"] == 0,
        "New allocation overflow",
    )
    require(source_hashes() == frozen, "Source drift during MAIN audit")
    report.update(
        status="passed",
        failed_candidate_sha256=bad["container"]["sha256"],
        fixed_candidate_sha256=good["container"]["sha256"],
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
