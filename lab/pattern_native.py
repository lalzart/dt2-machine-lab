"""Private native copy with a resume-after-instruction ABI; unchanged semantics."""

import hashlib
import os
import shutil
import subprocess
import sys

from lab.project import ROOT, read_json, require, sha256, write_json
from lab.runtime import REPO

RESUME = """
// Lab-only ABI: called only after a successful replacement instruction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn sharc_native_resume_after_insn(handle: *mut Engine) -> i32 {
    if handle.is_null() { return -1; }
    let engine = unsafe { &mut *handle };
    engine.halt = None;
    engine.last_trap = None;
    0
}
"""


def library():
    revision = read_json(ROOT / "deps.lock.json")["digikit"]["revision"]
    key = hashlib.sha256((revision + RESUME).encode()).hexdigest()[:16]
    output = ROOT / "out/cache/pattern-native" / key
    manifest = output / "build.json"
    target = output / "target/release/libsharc_native.dylib"
    if manifest.is_file():
        require(
            sha256(target) == read_json(manifest)["sha256"],
            "Pattern native library drift",
        )
        return target
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(
        REPO / "native", output / "native", ignore=shutil.ignore_patterns("target")
    )
    source = output / "native/sharc/src/lib.rs"
    source.write_text(source.read_text() + RESUME)
    with (output / "build.log").open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(REPO / "tools/sharc_transpile.py"),
                "--out",
                str(output / "gen"),
                "--work",
                str(output / "transpile-work"),
            ],
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
        subprocess.run(
            [
                "cargo",
                "build",
                "--offline",
                "--locked",
                "--release",
                "--lib",
                "--manifest-path",
                str(output / "native/sharc/Cargo.toml"),
            ],
            env={
                **os.environ,
                "SHARC_GEN_DIR": str(output / "gen"),
                "CARGO_TARGET_DIR": str(output / "target"),
            },
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=900,
        )
    write_json(
        manifest,
        {
            "revision": revision,
            "resume_sha256": hashlib.sha256(RESUME.encode()).hexdigest(),
            "sha256": sha256(target),
            "semantics": "Unchanged pinned generated core",
        },
    )
    return target
