"""Pack the exact candidate DSP with current upstream tools; no execution."""

import argparse
import json
import struct
from pathlib import Path

from tools.sharc_dev import sharc_diff as sd
from tools.sharc_dev import sharc_transpile_run as nr
from tools.sharc_dev import sharcldr


def main():
    p = argparse.ArgumentParser()
    p.add_argument("spec", type=Path)
    a = p.parse_args()
    spec = json.loads(a.spec.read_text())
    out = Path(spec["output"])
    memory = sharcldr.LoadedMemory.from_stream(Path(spec["blob"]).read_bytes())
    (out / "dsp.image").write_bytes(nr.pack_image(memory))
    stock = Path(spec["lab"]) / ".local/fixture/sections/section_7_BLOB.bin"
    (out / "stock-dsp.image").write_bytes(
        nr.pack_image(sharcldr.LoadedMemory.from_stream(stock.read_bytes()))
    )
    state = (out / "legacy/prepared.state").read_bytes()
    # Validate the documented canonical format; no register/state substitution.
    fields = sd.unpack_state(state)
    (out / "prepared.state").write_bytes(sd.pack_state(fields))
    pack = (Path(spec["lab"]) / ".local/fixture/native/state.pack").read_bytes()
    if pack[:8] != b"SHFP\x01\0\0\0":
        raise ValueError("Unknown prepared state-pack ABI")
    at = 12 + struct.unpack_from("<I", pack, 8)[0]
    at += 4 + struct.unpack_from("<I", pack, at)[0]
    count = struct.unpack_from("<I", pack, at)[0]
    at += 4
    if at + 12 * count > len(pack):
        raise ValueError("Incomplete prepared option table")
    options = dict(struct.unpack_from("<Iq", pack, at + 12 * i) for i in range(count))
    # Match the old Engine's explicit configuration, including its native
    # bank/stack/SEC models. Clock/interrupt defaults are part of this fixture.
    options.update({1: 0, 2: 1, 4: 1, 5: 0, 8: -1, 19: 1, 20: 1, 22: 1})
    (out / "prepared-options.json").write_text(json.dumps(sorted(options.items())))


if __name__ == "__main__":
    main()
