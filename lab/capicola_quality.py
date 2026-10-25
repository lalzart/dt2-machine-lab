"""Guarded optional source overlay; frozen Capicola sources stay unchanged."""

import hashlib
import json
from pathlib import Path

from lab.project import ROOT, require, sha256, write_json

# Set from the reviewed, preserved STRETCH reader, never from a changed input.
STRETCH_SHA = "505e2a82107b89e727ecd76ffca4fa803f65b160965a9bd919d6eb6fd6fba067"


def transform(source):
    require(hashlib.sha256(source).hexdigest() == STRETCH_SHA, "Quality baseline drift")
    text = source.decode()
    replacements = (
        (
            "float cap_stretch_tick(CapStretch *s) {",
            '#include "quality_policy.h"\nfloat cap_stretch_tick(CapStretch *s) {',
        ),
        (
            "if(!c->splicing && lead>c->leash) {",
            "if(!c->splicing && (lead>c->leash || quality_front(s))) {",
        ),
        (
            "if(duration>960.0f) duration=960.0f;\n        if(duration<48.0f) duration=48.0f;",
            "duration=quality_duration(s,duration);",
        ),
        (
            "c->phase+=c->increment*c->pitch;",
            "c->phase+=quality_phase_step(c->increment,c->pitch);",
        ),
    )
    for before, after in replacements:
        require(text.count(before) == 1, "Ambiguous quality source anchor")
        text = text.replace(before, after)
    return text.encode()


def prepare(output):
    """Mirror C/H files so every existing relative include keeps its meaning."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads(
        (
            ROOT / "machines/capicola/quality-contract/implementation-contract.json"
        ).read_text()
    )
    require(
        contract["status"] == "ready"
        and contract["proposal"]["approval"]["state"] == "approved",
        "Quality profile not approved",
    )
    for record in (contract["proposal"], contract["technical_spec"]):
        require(
            sha256(ROOT / record["path"]) == record["sha256"], "Quality contract drift"
        )
    files = {}
    for path in sorted((ROOT / "machines").rglob("*")):
        if path.suffix not in (".c", ".h") or not path.is_file():
            continue
        name = path.relative_to(ROOT)
        data = path.read_bytes()
        generated = (
            transform(data) if name == Path("machines/capicola/stretch.c") else data
        )
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(generated)
        files[str(name)] = dict(
            source=hashlib.sha256(data).hexdigest(),
            compiled=hashlib.sha256(generated).hexdigest(),
        )
    write_json(
        output / "source-overlay.json",
        dict(
            policy="capicola-quality-v1",
            contract_sha256=sha256(
                ROOT / "machines/capicola/quality-contract/implementation-contract.json"
            ),
            files=files,
        ),
    )
    return output
