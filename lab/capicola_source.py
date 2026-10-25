"""Source-playback runtime; preserved experiments retain their exact bytes."""

import hashlib
import json
from pathlib import Path

from lab.project import ROOT, require, sha256, write_json


def prepare(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    contract_path = (
        ROOT / "machines/capicola/source-contract/implementation-contract.json"
    )
    contract = json.loads(contract_path.read_text())
    require(contract["status"] == "ready", "Source playback contract is not ready")
    require(
        contract["proposal"]["approval"]["state"] == "approved",
        "Source port not approved",
    )
    for record in (contract["proposal"], contract["technical_spec"]):
        require(
            sha256(ROOT / record["path"]) == record["sha256"], "Source contract drift"
        )
    lock = json.loads((contract_path.parent / "source-equivalence.json").read_text())
    for record in lock["files"]:
        require(
            sha256(ROOT / ".local/sources/capicola" / record["path"])
            == record["sha256"],
            f"Capicola source drift: {record['path']}",
        )
    for name, digest in lock["integration_baseline_files"].items():
        if name.startswith("machines/"):
            require(sha256(ROOT / name) == digest, f"Source baseline drift: {name}")
    files = {}
    for path in sorted((ROOT / "machines").rglob("*")):
        if path.suffix not in (".c", ".h") or not path.is_file():
            continue
        name = path.relative_to(ROOT)
        data = path.read_bytes()
        generated = data
        if name == Path("machines/capicola/live.c"):
            generated = (ROOT / "machines/capicola/source-live.c").read_bytes()
        elif name == Path("machines/capicola/cache.h"):
            require(
                data.count(b"#define CAP_CACHE_SLOTS 16") == 1,
                "Cache slot anchor drift",
            )
            generated = data.replace(
                b"#define CAP_CACHE_SLOTS 16", b"#define CAP_CACHE_SLOTS 32"
            )
        elif name == Path("machines/plaits-capicola-stretch-live/machine.c"):
            text = generated.decode()
            begin = text.index("static unsigned stretch_selected(")
            end = text.index("/* Invalidate publication", begin)
            text = (
                text[:begin]
                + '#include "../capicola/source-selection.h"\nstatic unsigned stretch_selected(unsigned track,unsigned *source,unsigned *frames) {\n return source_select(track,0,source,frames);\n}\n'
                + text[end:]
            )
            text = text.replace("sizeof(CapCache)==1436", "sizeof(CapCache)==2844")
            begin = text.index(" /* Mark all existing selected banks")
            end = text.index("\n#endif", begin)
            text = (
                text[:begin]
                + """ /* Reference both planar channels before admitting any replacement. */
 for(unsigned item=0;item<32;item++) {
  unsigned source,frames;
  if(!source_select(item>>1,item&1u,&source,&frames))cap_cache_reference(CACHE,source,(int)frames);
 }
 for(unsigned item=0;item<32;item++) {
  unsigned source,frames;
  if(!source_select(item>>1,item&1u,&source,&frames))cap_cache_select(CACHE,(const short *)source,(int)frames,source);
 }"""
                + text[end:]
            )
            helper = """static int source_track_ready(unsigned track) {
 unsigned left,right,frames,n;
 return !source_select(track,0,&left,&frames) && !source_select(track,1,&right,&n)
  && n==frames && stretch_published(left,frames)>=0 && stretch_published(right,n)>=0;
}
"""
            text = text.replace(
                "static int stretch_integer_position",
                helper + "static int stretch_integer_position",
            )
            text = text.replace(
                "stretch_selected(lane/2u,&selected,&n)",
                "source_select(lane/2u,lane&1u,&selected,&n)",
            )
            text = text.replace(
                "if(!selection_error && selected==source",
                "if(!selection_error && source_track_ready(lane/2u) && selected==source",
            )
            text = text.replace(
                "if(selection_error || selected!=s->source",
                "if(selection_error || !source_track_ready(lane/2u) || selected!=s->source",
            )
            generated = text.encode()
            changes = {
                b"s->backend=0;cap_live_stop(&s->reader);": b"s->backend=0;",
                b"cap_live_start(&s->reader,": b"cap_live_retrigger(&s->reader,",
                b"if(!s->backend) return 0;": b"if(!s->backend) {cap_live_stop(&s->reader);return 0;}",
            }
            for before, after in changes.items():
                require(generated.count(before) == 1, "Ambiguous source adapter anchor")
                generated = generated.replace(before, after)
        elif name == Path("machines/plaits-capicola-stretch-toggle/machine.c"):
            require(
                data.count(b"stretch_published(source,frames)>=0") == 1,
                "Status readiness anchor drift",
            )
            generated = data.replace(
                b"stretch_published(source,frames)>=0", b"source_track_ready(track)"
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
            policy="capicola-source-playback-v1",
            contract_sha256=sha256(contract_path),
            files=files,
        ),
    )
    return output
