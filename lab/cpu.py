"""Build a hash-guarded SINE MAIN override using the pinned DigiKit planner."""

import hashlib

from lab.project import require, sha256, write_json
from lab.runtime import OUT, PROFILE, STOCK_MAIN


def build():
    import machinebuild
    import machinepatch
    import machineprofile

    require(sha256(STOCK_MAIN) == PROFILE["stock_main_sha256"], "Wrong stock MAIN")
    sha, profile = machineprofile.profile_for(STOCK_MAIN)
    require(profile is machineprofile.DT2_116, "Expected DTII 1.16 CPU profile")
    spec = machinepatch.MachineSpec(
        name="SINE",
        short="SIN",
        desc_name="SINE",
        desc_short="SIN",
        clone_of=6,
        fields=PROFILE["cpu"]["descriptor_fields"],
    )
    writes, patched = machinebuild.plan_and_verify(
        STOCK_MAIN, profile, spec, machinepatch.PARTS
    )
    (OUT / "SINE_MAIN_OS.bin").write_bytes(patched)
    report = {
        "original_sha256": sha,
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "writes": [
            {"address": hex(a), "old": old.hex(), "new": new.hex()}
            for a, old, new in writes
        ],
        "scope": "CPU image build only; no boot or hardware claim",
    }
    write_json(OUT / "cpu-patch-SINE.json", report)
    return report
