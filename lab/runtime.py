"""Single adapter boundary between lab paths and the pinned DigiKit modules."""

import os
import sys
from functools import cache

from lab.project import ROOT, inside, read_json, require, settings

CONFIG = settings()
REPO = CONFIG["digikit"]
SELACHE = CONFIG["selache"]
FIXTURE = CONFIG["fixture"]
PROFILE = read_json(ROOT / "profiles/dt2-1.16/profile.json")
run_dir = os.environ.get("DT2_LAB_RUN_DIR")
require(run_dir, "Use ./labctl to allocate a fresh run directory")
OUT = inside(ROOT / "out/runs", run_dir)
require(OUT.is_dir(), "Run directory was not prepared by labctl")
STOCK_BLOB = FIXTURE / "sections/section_7_BLOB.bin"
STOCK_MAIN = FIXTURE / "sections/section_3_MAIN_OS.bin"
PACK = FIXTURE / "native/state.pack"
LIB = FIXTURE / "native/libsharc_native.dylib"
ARENA = int(PROFILE["dsp"]["arena_byte"], 0)
sys.path[:0] = [str(REPO), str(REPO / "tools")]
os.environ["SHARC_NATIVE_LIB"] = str(LIB)


@cache
def sharc_profile():
    """Resolve the stock firmware using a lab-owned, versioned database cache."""
    import sharc
    import sharc_symbols
    import sharcdb

    lock = read_json(ROOT / "deps.lock.json")
    directory = (
        ROOT / "out/cache" / lock["digikit"]["revision"] / PROFILE["stock_blob_sha256"]
    )
    path = directory / "dt2-1.16.sqlite"
    sharcdb.build_database(str(STOCK_BLOB), str(path), name="dt2-1.16")
    image = sharc.Image("dt2-1.16", str(path), str(STOCK_BLOB))
    try:
        return sharc_symbols.resolve(image, device="dt2")
    finally:
        image.db.close()
