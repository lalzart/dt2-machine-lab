"""Check native captured PCM and load independent stock-file reference pages.

Runs in the old, pinned CPU tooling process. It records nothing, changes no
expected hashes and supplies no successful job callbacks to the native flow.
"""

import argparse
import hashlib
import json
import os
import struct
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    root, out = Path(spec["lab"]), Path(spec["output"])
    folder = out / "stock-oracle"
    folder.mkdir(exist_ok=False)
    os.environ["DT2_LAB_RUN_DIR"] = str(folder.relative_to(root / "out/runs"))
    from lab import runtime

    # Initialize pinned tool paths before importing their standalone modules.
    STOCK_MAIN = runtime.STOCK_MAIN
    import plusdrive_check as check
    import tools.plusdrive as pd

    from lab.flex_freeze_probe import payload, retarget
    from lab.flex_lite import publication_bytes
    from lab.project import require, sha256, write_json
    from lab.sketch_validation import pages

    first = pages(out / "flow/pages-A-frozen.bin")
    second = pages(out / "flow/pages-B.bin")
    require(second[: len(first)] == first, "Native publication prefix changed")
    source = folder / "wav"
    source.mkdir()
    metrics = []
    for number, history in ((1, first), (2, second)):
        captured = (out / f"flow/take-{number}.pcm").read_bytes()
        require(
            captured == payload(history, 300), "Native LP0 PCM differs from readback"
        )
        expected = b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(len(captured) // 4)
        )
        require(
            captured == expected and any(captured),
            "Nonzero recorder input qualification failed",
        )
        require(
            captured != bytes(len(captured)), "Zero-input negative control ineffective"
        )
        with wave.open(str(source / f"{number}.wav"), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(
                b"".join(captured[j : j + 2][::-1] for j in range(0, len(captured), 2))
            )
        metrics.append(
            dict(
                number=number,
                frames=len(captured) // 4,
                sha256=hashlib.sha256(captured).hexdigest(),
            )
        )
    (folder / "A.lp0").write_bytes(b"".join(publication_bytes(first)))
    (folder / "B.lp0").write_bytes(b"".join(publication_bytes(second[len(first) :])))
    entries = pd.build(
        str(source), str(folder / "reference.img"), main_os=STOCK_MAIN.read_bytes()
    )
    snapshot = (
        root.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Stock CPU snapshot drift",
    )
    cpu = check.Firmware(folder / "reference.img", snapshot, STOCK_MAIN)
    try:
        cpu.call(0x40154358, [])
        check.check_mount(cpu, entries[0]["ref"])
        for number, entry in enumerate(entries, 1):
            pcm = (out / f"flow/take-{number}.pcm").read_bytes()
            loaded = check.check_load(cpu, entry["ref"], 300 + number - 1)
            require(
                loaded["load_d0"] == 0
                and all(
                    check.sent_pcm_matches(loaded, pd.build_native_sample(pcm, True))
                ),
                "Stock file load differs",
            )
            (folder / f"reference-{number}.lp0").write_bytes(
                b"".join(publication_bytes(retarget(cpu.pages, 300)))
            )
    finally:
        cpu.close()
    write_json(
        folder / "report.json",
        dict(
            status="passed",
            captures=metrics,
            native_readback_equals_supplied_input=True,
            native_LP0_exact=True,
            stock_file_loader_exact=True,
            recordings=0,
            normalization="Existing peer acknowledges normalization without a gain pass",
        ),
    )


if __name__ == "__main__":
    main()
