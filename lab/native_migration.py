"""Opt-in native adapter preparation; no pinned dependency or upstream edits."""

import re
import shutil
import subprocess
from pathlib import Path

from lab.project import ROOT, git, require, sha256, write_json

REVISION = "38dfbe4ae88263511eed95691c07fc07e17b6f26"
RUNTIME_SHA = "377627a94067103e41fa3c95ce6c6de5515b6fe860aadee83c3a9fe9b6423da4"
PATCH = ROOT / "lab/native/reference_main.patch"


def prepare_boot(upstream, output):
    """Copy only the boot crate and apply a reviewable constructor extension.

    Other native crates use their exact upstream sources. Existing constructors
    remain unchanged; the new API authenticates reference firmware before
    resolving service addresses from it. Candidate RAM/flash are not overlaid.
    """
    upstream, output = Path(upstream).resolve(), Path(output).resolve()
    require(git(upstream, "rev-parse", "HEAD") == REVISION, "Unknown native upstream")
    require(not git(upstream, "status", "--porcelain"), "Dirty native upstream")
    require(output.is_relative_to(ROOT / "out/runs"), "Use ignored local output")
    original = upstream / "packages/emulator/boot"
    require(
        sha256(original / "src/runtime.rs") == RUNTIME_SHA,
        "Native constructor source drift",
    )
    shutil.copytree(original, output)
    shutil.copyfile(upstream / "LICENSE", output / "LICENSE")
    manifest = (output / "Cargo.toml").read_text()
    manifest = manifest.replace(
        "license.workspace = true", 'license = "AGPL-3.0-or-later"'
    )
    manifest = manifest.replace(
        "repository.workspace = true",
        'repository = "https://github.com/ElekLabs/digikit"',
    )
    manifest = re.sub(
        r'path = "([^\"]+)"',
        lambda m: (
            'path = "' + str((original / m[1]).resolve()) + '"'
            if m[1].startswith("..")
            else m[0]
        ),
        manifest,
    )
    (output / "Cargo.toml").write_text(manifest)
    subprocess.run(
        ["patch", "-t", "-N", "-p1", "-d", str(output), "-i", str(PATCH)],
        check=True,
        capture_output=True,
        text=True,
    )
    changed = [
        str(p.relative_to(original))
        for p in original.rglob("*")
        if p.is_file() and sha256(p) != sha256(output / p.relative_to(original))
    ]
    require(
        sorted(changed) == ["Cargo.toml", "src/runtime.rs"],
        "Unexpected native copy changes",
    )
    metadata = dict(
        upstream_revision=REVISION,
        upstream_runtime_sha256=RUNTIME_SHA,
        patch_sha256=sha256(PATCH),
        runtime_sha256=sha256(output / "src/runtime.rs"),
        changed=sorted(changed),
        license="AGPL-3.0-or-later",
        default_constructors_unchanged=True,
        pinned_dependencies_changed=False,
    )
    write_json(output / "adapter.json", metadata)
    return metadata


def prepare_recorder_boot(upstream, output):
    """Add the legacy recorder-peer boundary to a separate native boot copy."""
    output = Path(output).resolve()
    metadata = prepare_boot(upstream, output)
    patch = ROOT / "lab/native/recorder_peer.patch"
    subprocess.run(
        ["patch", "-t", "-N", "-p1", "-d", str(output), "-i", str(patch)],
        check=True,
        capture_output=True,
        text=True,
    )
    peer = ROOT / "lab/native/recorder_peer.rs"
    shutil.copyfile(peer, output / "src/runtime/recorder_peer.rs")
    metadata.update(
        recorder_patch_sha256=sha256(patch),
        recorder_peer_sha256=sha256(peer),
        runtime_sha256=sha256(output / "src/runtime.rs"),
        lib_sha256=sha256(output / "src/lib.rs"),
        recorder_boundary="OS1.16 command/count peer; firmware jobs unchanged",
        changed=[
            "Cargo.toml",
            "src/lib.rs",
            "src/runtime.rs",
            "src/runtime/recorder_peer.rs",
        ],
    )
    write_json(output / "adapter.json", metadata)
    return metadata
