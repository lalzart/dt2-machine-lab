"""Local configuration, integrity checks, and run provenance; standard library only."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inside(base, relative):
    base = Path(base).resolve()
    result = (base / relative).resolve()
    require(result.is_relative_to(base), f"Path escapes {base}: {relative}")
    return result


def settings():
    path = ROOT / ".local/config.json"
    require(path.is_file(), "Missing .local/config.json; see README.md setup.")
    config = read_json(path)
    for name in ("digikit", "selache", "fixture", "python"):
        require(name in config, f"Missing configuration entry: {name}")
        config[name] = (ROOT / config[name]).absolute()
    return config


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, timeout=30
    ).strip()


def verify_files(base, expected):
    checked = {}
    for name, digest in expected.items():
        path = inside(base, name)
        require(path.is_file(), f"Missing fixture file: {path}")
        actual = sha256(path)
        require(actual == digest, f"Fixture hash mismatch: {name}")
        checked[name] = actual
    return checked


def source_hashes():
    paths = [ROOT / "labctl", ROOT / "deps.lock.json", ROOT / "pyproject.toml"]
    for name in ("lab", "machines", "profiles", "tests/fixtures", "scripts"):
        paths.extend(
            p
            for p in (ROOT / name).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(paths)}


def doctor():
    config = settings()
    lock = read_json(ROOT / "deps.lock.json")
    fixture = read_json(ROOT / "tests/fixtures/sine-1.16.json")
    dependencies = {}
    for name in ("digikit", "selache"):
        checkout = config[name]
        revision = git(checkout, "rev-parse", "HEAD")
        require(
            revision == lock[name]["revision"], f"Wrong {name} revision: {revision}"
        )
        require(not git(checkout, "status", "--porcelain"), f"Dirty {name} dependency")
        dependencies[name] = revision
    require(sys.version_info[:2] == (3, 12), "DigiKit runtime requires Python 3.12")
    packages = {}
    for name, expected in lock["python"]["packages"].items():
        actual = importlib.metadata.version(name)
        require(actual == expected, f"Wrong Python package {name}: {actual}")
        packages[name] = actual
    require(
        sys.byteorder == "little", "This native replay fixture requires little endian"
    )
    actual_host = {"system": platform.system(), "machine": platform.machine()}
    require(actual_host == fixture["native_host"], "Native fixture platform mismatch")
    unicorn_library = importlib.metadata.distribution("unicorn").locate_file(
        "unicorn/lib/libunicorn.2.dylib"
    )
    require(
        sha256(unicorn_library) == fixture["unicorn_native_sha256"],
        "Patched Unicorn native library differs from this fixture",
    )
    files = verify_files(config["fixture"], fixture["files"])
    tools = verify_files(config["selache"], fixture["selache_tools"])
    return {
        "ok": True,
        "dependencies": dependencies,
        "fixture_files": files,
        "selache_tools": tools,
        "python": sys.version,
        "python_packages": packages,
        "unicorn_native_sha256": fixture["unicorn_native_sha256"],
        "platform": actual_host,
        "source_hashes": source_hashes(),
        "scope": "Pinned offline replay fixture; clean CPU/DSP startup is a separate milestone",
    }
