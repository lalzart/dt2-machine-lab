"""OS1.16 Plaits CPU menu and parameter integration."""

import hashlib
import json
import struct

from lab.project import ROOT


def build_cpu(*, family="va", output=None):
    """A named type-7 CPU candidate. The current replay capture predates this label."""
    from lab.dsp_build import build_context

    OUT = build_context(output).output
    if family == "integration":
        from lab.plaits_integration import patch_cpu as integrate
        from lab.plaits_integration import validate_sources as validate_integration

        validate_integration()
        baseline = build_cpu(family="controls", output=OUT)
        data, integration = integrate(
            (OUT / "PLAITS_MAIN_OS.bin").read_bytes(),
            json.loads((OUT / "macro-cpu-patches.json").read_text()),
        )
        (OUT / "PLAITS_R2_MAIN_OS.bin").write_bytes(
            (OUT / "PLAITS_MAIN_OS.bin").read_bytes()
        )
        (OUT / "PLAITS_MAIN_OS.bin").write_bytes(data)
        (OUT / "integration-cpu-patches.json").write_text(
            json.dumps(integration, indent=2) + "\n"
        )
        return {
            **baseline,
            "sha256": integration["sha256"],
            "family": "integration",
            "baseline_sha256": baseline["sha256"],
            "writes": baseline["writes"] + len(integration["writes"]),
        }
    import machinebuild
    import machinepatch
    import machineprofile

    from lab.runtime import PROFILE, STOCK_MAIN

    digest, profile = machineprofile.profile_for(STOCK_MAIN)
    if digest != PROFILE["stock_main_sha256"] or profile is not machineprofile.DT2_116:
        raise ValueError("Unexpected CPU firmware")
    if family not in ("va", "trio", "bank", "controls"):
        raise ValueError("Unknown CPU machine family")
    name, short = ("P-VA", "PVA") if family == "va" else ("PLAITS", "PLT")
    fields = PROFILE["cpu"]["descriptor_fields"]
    if family in ("trio", "bank", "controls"):
        fields = (0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0, 0xFE, 0x0A)
    if family == "controls":
        fields = (0xF8, 275, 0xFA, 276, 277, 0xFD, 0, 0xFE, 0x0A)
    spec = machinepatch.MachineSpec(
        name=name,
        short=short,
        desc_name=name,
        desc_short=short,
        clone_of=6,
        fields=fields,
    )
    writes, data = machinebuild.plan_and_verify(
        STOCK_MAIN, profile, spec, machinepatch.PARTS
    )
    if family in ("trio", "bank", "controls"):
        # Dormant Manual Slice C row: no exposed stock descriptor uses 0xFA.
        # Keep shared PLAY/SAMP/SLICE metadata unchanged; only MODEL is dedicated.
        data = bytearray(data)
        base, row, label = 0x40000400, 0x40212C24, 0x40311CC4
        # MODEL is discrete. The stock one-pole mirror filter would turn a
        # model lock into an intermediate number at note-on. Bypass only
        # track 1 / type 7 / mirror 27 after the stock filter has completed.
        # D0 is caller-clobbered and restored to the displaced return value;
        # no other register or stock track/parameter is changed by this shim.
        shim = bytes.fromhex(
            "7000 103980003cd0 0c8000000007 660c "
            "303980003398 33c080005ba8 "
            "203c80005b50 4ef9400d934c"
        )
        controls = json.loads(
            (ROOT / f"machines/plaits-{family}/controls.json").read_text()
        )
        max_raw = controls["model"]["max_raw"]
        if max_raw != (len(controls["model_names"]) - 1) * 256:
            raise ValueError("MODEL range disagrees with control map")
        extra = [
            (row + 12, struct.pack(">I", 0x7F00), struct.pack(">I", max_raw)),
            (row + 40, struct.pack(">I", 0x40242AAC), struct.pack(">I", label)),
            (row + 48, struct.pack(">I", 0x40242AB6), struct.pack(">I", label + 6)),
            (label, bytes(12), b"Model\0MODEL\0"),
            (0x400D9346, bytes.fromhex("203c80005b50"), bytes.fromhex("4ef940311d04")),
            (0x40311D04, bytes(len(shim)), shim),
        ]
        for address, before, after in extra:
            off = address - base
            if data[off : off + len(before)] != before:
                raise ValueError(f"MODEL metadata guard failed at {address:#x}")
            data[off : off + len(after)] = after
    if family == "controls":
        from lab.plaits_controls import patch_cpu, validate_sources

        validate_sources()
        data, metadata = patch_cpu(STOCK_MAIN.read_bytes(), data)
        from lab.coldfire import audit_image, fix_rank

        data, correction = fix_rank(data)
        audit = audit_image(
            STOCK_MAIN.read_bytes(), data, writes, extra, metadata, correction
        )
        (OUT / "coldfire-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
        (OUT / "macro-cpu-patches.json").write_text(
            json.dumps(metadata, indent=2) + "\n"
        )
    (OUT / "PLAITS_MAIN_OS.bin").write_bytes(data)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "writes": len(writes)
        + (6 if family in ("trio", "bank", "controls") else 0)
        + (len(metadata["writes"]) if family == "controls" else 0),
        "machine_id": 7,
        "name": name,
        "scope": "Image construction; UI and control transport require a separate capture",
    }
