"""Build reset-only SHARC inputs with the inspected upstream's own format tools.

Executed in that checkout's Python import environment. No captured DSP state,
firmware edits, checkpoint execution or dependency modification occurs here.
"""

import argparse
import hashlib
import json
from pathlib import Path

from tools.sharc_dev import sharc_diff as sd
from tools.sharc_dev import sharc_run as sr
from tools.sharc_dev import sharc_transpile_run as nr
from tools.sharc_dev import sharcldr
from tools.sharc_dev.sharc_core.values import Const


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("blob", type=Path)
    p.add_argument("resets", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(exist_ok=False)
    raw = a.blob.read_bytes()
    memory = sharcldr.LoadedMemory.from_stream(raw)
    entries = sharcldr.entry_points(memory.blocks)
    if entries != [0x120230, 0x1C1338]:
        raise ValueError("Unknown OS1.16 loader entries")
    runner = sr.Runner(
        memory, entries[-1], explicit_memory_model=True, approx_recips=True
    )
    runner.state.bank_model = runner.state.stack_model = True
    resets = json.loads(a.resets.read_text())
    runner.state.mmrs.update({int(k, 16): Const(v) for k, v in resets.items()})
    fields = sd.export_state(runner.state, page_hash=False)
    fields["memory_ranges"] = nr._overlay_ranges(runner.state.overlay)
    (a.output / "image.bin").write_bytes(nr.pack_image(memory))
    (a.output / "reset.state").write_bytes(sd.pack_state(fields))
    code = []
    for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
        if 0x20080000 <= lo < 0x200E0000:
            data = memory.read(lo, hi - lo)
            code.append(
                dict(start=lo, size=hi - lo, sha256=hashlib.sha256(data).hexdigest())
            )
    (a.output / "inputs.json").write_text(
        json.dumps(
            dict(
                blob_sha256=hashlib.sha256(raw).hexdigest(),
                entry=entries[-1],
                instructions_executed=0,
                prepared_snapshot=False,
                code=code,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
