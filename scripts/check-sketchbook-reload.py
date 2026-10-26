#!/usr/bin/env python3
"""Independently cold-boot stock OS1.16 and compare native saved/reloaded PCM."""

# ruff: noqa: E402
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, git, require, settings, sha256, write_json


def main():
    cfg = settings()
    if Path(sys.executable).resolve() != cfg["python"].resolve():
        os.execv(
            str(cfg["python"]), [str(cfg["python"]), "-B", __file__, *sys.argv[1:]]
        )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--native-upstream", type=Path, required=True)
    p.add_argument("--native-boot", type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
    out.mkdir(parents=True, exist_ok=False)
    os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
    doctor()
    # isort: off
    from lab import runtime as runtime
    import plusdrive_check as check
    # isort: on

    upstream = a.native_upstream.resolve()
    require(
        git(upstream, "rev-parse", "HEAD") == "38dfbe4ae88263511eed95691c07fc07e17b6f26"
        and not git(upstream, "status", "--porcelain"),
        "Native upstream drift",
    )
    capture = a.capture.resolve()
    spec = json.loads((capture / "spec.json").read_text())
    flow = json.loads((capture / "flow.json").read_text())
    require(flow["status"] == "passed", "Incomplete capture")
    require(
        sha256(spec["stock_syx"])
        == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
        "Stock SYX drift",
    )
    image = out / "durable.img"
    subprocess.run(["cp", "-c", spec["card"], str(image)], check=True)
    raw = (capture / "verified-card.overlay").read_bytes()
    require(len(raw) % 584 == 0, "Bad overlay size")
    with image.open("r+b") as f:
        for at in range(0, len(raw), 584):
            sector = struct.unpack_from("<Q", raw, at)[0]
            mask = raw[at + 8 : at + 72]
            data = raw[at + 72 : at + 584]
            f.seek(sector * 512)
            original = bytearray(f.read(512))
            for i in range(512):
                if mask[i // 8] >> (i % 8) & 1:
                    original[i] = data[i]
            f.seek(sector * 512)
            f.write(original)
    saves = json.loads((capture / "save-progress.json").read_text())
    files = []
    for i, name in enumerate(["A", "B"]):
        reference = bytes(saves[i]["reference"]["Ok"])
        record = int.from_bytes(reference[:4], "big")
        content = check.image_file_bytes(image, record)
        expected = (capture / f"expected-{name}.native").read_bytes()
        require(content == expected, "Durable native file mismatch")
        files.append(
            dict(sample=name, record=record, bytes=len(content), exact_native_file=True)
        )
    write_json(
        out / "spec.json",
        dict(card=str(image), stock_syx=spec["stock_syx"], saves=saves),
    )
    (out / "src").mkdir()
    shutil.copy(ROOT / "lab/native/sketchbook_reload_probe.rs", out / "src/main.rs")
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-sketchbook-stock-reload"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nserde_json="1"\nsha2="0.10"\nelektron-native-boot={path='
        + json.dumps(str(a.native_boot.resolve()))
        + ',features=["sharc"]}\nsharc-native={path='
        + json.dumps(str(upstream / "packages/emulator/sharc"))
        + "}\n"
    )
    env = dict(
        os.environ,
        SHARC_GEN_DIR=str(upstream / "out/native/shared-core/gen"),
        CARGO_TARGET_DIR=str(upstream / "out/native/target/generic"),
    )
    with (out / "native.log").open("w") as log:
        subprocess.run(
            [
                "rustup",
                "run",
                "1.98.1",
                "cargo",
                "run",
                "--release",
                "--offline",
                "--manifest-path",
                str(out / "Cargo.toml"),
                "--",
                str(out),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    result = json.loads((out / "reload.json").read_text())
    for i, name in enumerate(["A", "B"]):
        raw = (out / f"load-{i}.pages").read_bytes()
        require(len(raw) % 4104 == 0, "Bad loader page capture")
        pages = []
        headers = []
        for at in range(0, len(raw), 4104):
            tag, flag = struct.unpack_from(">II", raw, at)
            data = raw[at + 8 : at + 4104]
            if tag == 0xFFFFFFFF:
                headers.append(struct.unpack_from(">5I", data))
            else:
                pages.append((tag, data, flag))
        exact = check.sent_pcm_matches(
            dict(pages=pages, slot_headers=headers),
            (capture / f"expected-{name}.native").read_bytes(),
        )
        require(exact and all(exact), "Stock reloaded PCM mismatch")
        result["loads"][i]["exact_PCM_by_channel"] = exact
    result.update(
        status="passed",
        durable_files=files,
        overlay_sha256=sha256(capture / "verified-card.overlay"),
    )
    write_json(out / "reload.json", result)
    print("PASS exact durable files and independent stock loader PCM")


if __name__ == "__main__":
    main()
