"""Pack stock DSP for native BUF compatibility; no execution or source edits."""

import argparse
import json
from pathlib import Path

from tools.sharc_dev import sharc_transpile_run as nr
from tools.sharc_dev import sharcldr

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("spec", type=Path)
a = p.parse_args()
spec = json.loads(a.spec.read_text())
stock = Path(spec["lab"]) / ".local/fixture/sections/section_7_BLOB.bin"
(Path(spec["output"]) / "stock-dsp.image").write_bytes(
    nr.pack_image(sharcldr.LoadedMemory.from_stream(stock.read_bytes()))
)
