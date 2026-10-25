"""Freeze the old BUF runtime's saved-page oracle in a separate process."""

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("spec", type=Path)
    a = p.parse_args()
    spec = json.loads(a.spec.read_text())
    out = Path(spec["output"]) / "legacy"
    out.mkdir(exist_ok=False)
    os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(Path(spec["lab"]) / "out/runs"))
    from lab.sketch_validation import pages, runtime

    Engine, rt = runtime(out)
    from lab.flex_audio import baseline_pages
    from lab.flex_lite import publication_bytes
    from lab.flex_session import stock_inputs
    from lab.project import require, write_json
    from lab.voice_read import VoiceReader

    e = Engine(Path(spec["blob"]).read_bytes())
    e.publish(baseline_pages(stock_inputs()["lp0"]))
    (out / "prepared.state").write_bytes(e.state_bytes())
    reader = VoiceReader(out / "reader")
    fixture = Path(spec["fixture"])
    hist_a, hist_b = (
        pages(fixture / "pages-A-frozen.bin"),
        pages(fixture / "pages-B.bin"),
    )
    require(hist_b[: len(hist_a)] == hist_a, "Saved publication history drift")
    (out / "A.lp0").write_bytes(b"".join(publication_bytes(hist_a)))
    (out / "B.lp0").write_bytes(b"".join(publication_bytes(hist_b[len(hist_a) :])))
    e.publish(hist_a)
    descriptor = e.slot_record(312)
    require(e.slot_record(300) == descriptor, "Saved FREEZE does not alias A")
    wire = (fixture / "wire.bin").read_bytes()
    actions, observations = [], []
    for name, count, mask in (
        ("A", 12, 49),
        ("retained-A", 12, 0),
        ("B-frozen-A", 48, 49),
        ("late-frozen-A", 24, 32),
    ):
        if name == "retained-A":
            before = [e.core.peek(0x2412CC + v * 0x1D8) for v in (0, 1, 8, 9, 10, 11)]
            require(all(before), "No retained readers")
            e.publish(hist_b[len(hist_a) :])
            require(
                before
                == [e.core.peek(0x2412CC + v * 0x1D8) for v in (0, 1, 8, 9, 10, 11)],
                "Publication moved readers",
            )
            require(
                e.slot_record(312) == descriptor and e.slot_record(300) != descriptor,
                "Generation/frozen descriptor drift",
            )
        reply, pcm = bytearray(), bytearray()
        packets = bytearray()
        for i in range(count):
            b = bytearray(wire)
            for off in (0x22, 0x24, 0x26, 0x28, 0x2A):
                struct.pack_into(
                    ">H", b, off, mask if i == 0 and off in (0x22, 0x26) else 0
                )
            for track, slot in ((0, 300), (4, 300), (5, 312)):
                struct.pack_into(">H", b, 0xE0 + track * 0x60, slot)
            packets.extend(b)
            reply.extend(e.core.spi2_exchange(bytes(b)))
            e.block_after_exchange()
            pcm.extend(reader.read(e))
        for suffix, data in (("wire", packets), ("reply", reply), ("pcm", pcm)):
            (out / f"{name}.{suffix}").write_bytes(data)
        actions.append(dict(name=name, count=count, publish_b=name == "retained-A"))
        observations.append(
            dict(
                name=name,
                pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                reply_sha256=hashlib.sha256(reply).hexdigest(),
                pointers=[
                    e.core.peek(0x2412CC + v * 0x1D8) for v in (0, 1, 8, 9, 10, 11)
                ],
            )
        )
    write_json(
        out / "oracle.json",
        dict(
            status="passed",
            runtime=rt,
            actions=actions,
            observations=observations,
            frozen_descriptor=descriptor,
            recordings=0,
        ),
    )
    print("Saved-page legacy oracle: 96 native blocks, no recordings", flush=True)


if __name__ == "__main__":
    main()
