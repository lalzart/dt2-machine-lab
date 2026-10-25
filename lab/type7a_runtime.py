"""Opt-in copied GPL-2.0 DigiKit runtime; pinned tools/fixtures stay intact."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from lab.project import ROOT, doctor, read_json, require, sha256, write_json

PATCH = ROOT / "patches/sharc-type7a-sisd.patch"
CONTRACT = ROOT / "machines/sharc-type7a/contract.json"


def contract():
    c = read_json(CONTRACT)
    require(c["status"] == "ready", "Type7a contract not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Plan drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Pin drift")
    return c


def source_map(directory):
    return {
        str(p.relative_to(directory)): sha256(p)
        for name in ("tools", "native", "tests")
        for p in sorted((directory / name).rglob("*"))
        if p.is_file() and not {"target", "__pycache__"}.intersection(p.parts)
        and p.suffix != ".pyc"
    }


def apply(directory):
    """Patch one known file in an explicit copy, never inside .deps."""
    c = contract()
    directory = Path(directory).resolve()
    require(not directory.is_relative_to(ROOT / ".deps"), "Refuse pinned edit")
    source = directory / c["source_equivalence"]["source"]
    require(sha256(source) == c["source_equivalence"]["sha256"], "Type7a source drift")
    subprocess.run(
        ["patch", "-t", "-N", "-p1", "-d", str(directory), "-i", str(PATCH)],
        check=True, capture_output=True, text=True,
    )
    return sha256(source)


def build(output):
    c, provenance = contract(), doctor()
    from lab.runtime import REPO

    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / "out"), "Use ignored output")
    output.mkdir(exist_ok=False, parents=True)
    before = source_map(REPO)
    copy = output / "runtime"
    copy.mkdir()
    shutil.copyfile(REPO / "LICENSE", copy / "LICENSE")
    for name in ("tools", "native", "tests"):
        shutil.copytree(REPO / name, copy / name,
                        ignore=shutil.ignore_patterns("target", "__pycache__", "*.pyc"))
    patched = apply(copy)
    copied = source_map(copy)
    changed = [n for n in before if before[n] != copied.get(n)]
    require(changed == [c["source_equivalence"]["source"]], "Unexpected copied edits")
    commands = [
        [sys.executable, str(copy / "tools/sharc_transpile.py"), "--strict",
         "--out", str(output / "gen"), "--work", str(output / "transpile-work")],
        ["cargo", "build", "--offline", "--locked", "--release", "--lib",
         "--manifest-path", str(copy / "native/sharc/Cargo.toml")],
    ]
    env = {**os.environ, "SHARC_GEN_DIR": str(output / "gen"),
           "CARGO_TARGET_DIR": str(output / "target")}
    write_json(output / "build-inputs.json", dict(provenance=provenance,
               contract_sha256=sha256(CONTRACT), patch_sha256=sha256(PATCH),
               upstream=before, copied=copied, commands=commands))
    with (output / "build.log").open("w") as log:
        for command in commands:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=900)
    require(source_map(REPO) == before, "Pinned source changed during build")
    generated = read_json(output / "gen/transpile-report.json")
    require(not generated["functions_not_translated"], "Incomplete generation")
    library = output / "target/release/libsharc_native.dylib"
    report = dict(status="built", contract_sha256=sha256(CONTRACT),
                  patch_sha256=sha256(PATCH), copied_sources=copied,
                  patched_sha256=patched, library=str(library.relative_to(output)),
                  library_sha256=sha256(library), core_sha256=generated["core_sha256"],
                  generator_report_sha256=sha256(output / "gen/transpile-report.json"),
                  provenance=provenance, license="runtime/LICENSE (GPL-2.0)")
    write_json(output / "build.json", report)
    return library


def activate(output):
    """Select matching sources and library before any SHARC import; no fallback."""
    contract()
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / "out"), "Use isolated lab output")
    meta = read_json(output / "build.json")
    require(meta["contract_sha256"] == sha256(CONTRACT), "Runtime contract drift")
    require(meta["patch_sha256"] == sha256(PATCH), "Runtime patch drift")
    require(source_map(output / "runtime") == meta["copied_sources"], "Copied source drift")
    library = output / meta["library"]
    require(sha256(library) == meta["library_sha256"], "Isolated library drift")
    require(not any(n == "sharc_core" or n.startswith("sharc_core.")
                    or n in ("sharc_trace", "sharc_transpile_run", "lab.dsp")
                    for n in sys.modules), "SHARC already imported; use a fresh process")
    from lab import runtime

    runtime.LIB = library
    os.environ["SHARC_NATIVE_LIB"] = str(library)
    os.environ.pop("SHARC_NATIVE_ALLOW_STALE", None)
    sys.path.insert(0, str(output / "runtime/tools"))
    import sharc_transpile

    require(sharc_transpile.core_hash() == meta["core_sha256"], "Core fingerprint mismatch")
    return meta
