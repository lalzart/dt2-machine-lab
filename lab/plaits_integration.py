"""Guarded R3 integration overlay; R2 remains an independently reproducible baseline."""

import hashlib

from lab.coldfire import audit_code
from lab.plaits_controls import BASE, ROWS, TABLE, long
from lab.project import require

R2_MAIN = "4c226dfe863005324782f2931d2ad5e0c9142d8d8f85701c3e1a5065ed6fdc3f"
MODEL_NAMES = ("V-ANALOG", "2-OP FM", "BASSDRUM", "WAVESHAP", "HARMONIC", "GRANULAR")


def patch_cpu(image, metadata):
    require(
        hashlib.sha256(image).hexdigest() == R2_MAIN, "R3 requires exact audited R2"
    )
    data = bytearray(image)
    writes = []
    # Unused padding within the upstream fixed-slot layout, below reset clear.
    gaps = [
        [0x403117F4, 0x403118C4],
        [0x403118F0, 0x40311904],
        [0x40311918, 0x40311924],
        [0x40311934, 0x40311944],
        [0x4031198C, 0x403119C4],
        [0x40311A24, 0x40311A44],
        [0x40311A4C, 0x40311A54],
        [0x40311A58, 0x40311A64],
    ]
    for lo, hi in gaps:
        require(not any(data[lo - BASE : hi - BASE]), "Occupied R3 padding")

    def put(addr, before, after, label, kind="data"):
        off = addr - BASE
        require(
            len(before) == len(after) and data[off : off + len(before)] == before,
            f"R3 byte guard: {label} {addr:#x}",
        )
        instructions = audit_code(after, addr) if kind == "code" else []
        data[off : off + len(after)] = after
        writes.append(
            dict(
                address=addr,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind=kind,
                instructions=instructions,
            )
        )

    def alloc(payload, label, kind="data"):
        # Best fit keeps the one large gap available for the relocated resolver.
        choices = [
            (hi - lo, i) for i, (lo, hi) in enumerate(gaps) if hi - lo >= len(payload)
        ]
        require(bool(choices), f"R3 padding exhausted: {label}")
        _, i = min(choices)
        addr = gaps[i][0]
        put(addr, bytes(len(payload)), payload, label, kind)
        gaps[i][0] = (addr + len(payload) + 1) & ~1
        return addr

    def replace_code(addr, before, after, label):
        put(addr, before, after, label, "code")

    # Move the first resolver and macro copy out of the rows' expansion area.
    first = metadata["helpers"][0]["address"]
    first_bytes = image[first - BASE : first - BASE + 58]
    new_first_bytes = first_bytes.replace(long(278), long(279))
    new_first = alloc(new_first_bytes, "relocated four-row resolver", "code")
    old_copy = metadata["macro_shim"]
    copy = image[old_copy - BASE : old_copy - BASE + 24]
    copy += bytes.fromhex("30398000339a 33c080005baa 3039800033a2 33c080005bb2 4e75")
    new_copy = alloc(copy, "relocated full-width macro transport", "code")
    replace_code(
        0x40311D14,
        b"\x4e\xb9" + long(old_copy),
        b"\x4e\xb9" + long(new_copy),
        "macro transport relocation",
    )
    for w in metadata["writes"]:
        addr = w["address"]
        code = bytes.fromhex(w["after"])
        if w["label"] == "sparse table reference" and code == b"\x4e\xb9" + long(first):
            replace_code(
                addr, code, b"\x4e\xb9" + long(new_first), "resolver relocation"
            )
        elif w["label"].startswith("sparse resolver") and addr != first:
            key = next(h["key"] for h in metadata["helpers"] if h["address"] == addr)
            scale = key[1]
            replacement = code.replace(long(278 * scale), long(279 * scale))
            require(replacement != code, "Missing sparse upper bound")
            replace_code(addr, code, replacement, "four-row sparse resolver")
        elif w["label"] in ("parameter bound", "parameter operation bound"):
            old = bytes(data[addr - BASE - 2 : addr - BASE + 4])
            new = old[:2] + long(int.from_bytes(old[2:], "big") + 1)
            replace_code(addr - 2, old, new, "four-row parameter bound")
    numeric = bytes(data[0x40311CD0 - BASE : 0x40311CD0 - BASE + 38])
    replace_code(
        0x40311CD0,
        numeric,
        numeric.replace(long(278), long(279)),
        "duration numeric UI behavior",
    )

    # Named enum formatter: use the stock sprintf ABI (raw, destination).
    names = [alloc(n.encode() + b"\0", "model name " + n) for n in MODEL_NAMES]
    table = alloc(b"".join(map(long, names)), "model name pointers")
    fmt = bytes.fromhex("202f0004 e080 0c8000000006 6502 7000 e588 41f9") + long(table)
    fmt += bytes.fromhex("d1c0 2f10 487940240924 2f2f0010 4eb940000e82 4fef000c 4e75")
    model_formatter = alloc(fmt, "bounded model name formatter", "code")
    put(
        TABLE + 250 * 60 + 52,
        long(0x400E1424),
        long(model_formatter),
        "MODEL formatter",
    )

    # A dedicated duration row, in milliseconds; 100..12800 ms, default 1000.
    ms_string = alloc(b"%d ms\0", "duration format")
    fmt = bytes.fromhex("202f0004 e080 5280 7264 4c010800 2f00 4879") + long(ms_string)
    fmt += bytes.fromhex("2f2f0010 4eb940000e82 4fef000c 4e75")
    duration_formatter = alloc(fmt, "duration millisecond formatter", "code")
    rows = bytearray(image[ROWS - BASE : ROWS - BASE + 180])
    row = bytearray(image[TABLE - BASE + 253 * 60 : TABLE - BASE + 254 * 60])
    for off, value in (
        (8, 0),
        (12, 32512),
        (16, 2304),
        (20, 0),
        (52, duration_formatter),
    ):
        row[off : off + 4] = long(value)
    rows += row
    rows[60 + 36 : 60 + 40] = long(
        0x1E00
    )  # TIMB was the non-modulatable sample-slot row.
    for index in range(4):
        rows[index * 60 + 44 : index * 60 + 48] = long(
            0x40311A44
        )  # PLAITS owner caption
    labels = bytearray()
    for i, (full, short) in enumerate(
        (
            ("Harmonics", "HARM"),
            ("Timbre", "TIMB"),
            ("Morph", "MORP"),
            ("Duration", "LEN"),
        )
    ):
        pointer = ROWS + 240 + len(labels)
        labels += full.encode() + b"\0" + short.encode() + b"\0"
        rows[i * 60 + 40 : i * 60 + 44] = long(pointer)
        rows[i * 60 + 48 : i * 60 + 52] = long(pointer + len(full) + 1)
    payload = rows + labels
    require(ROWS + len(payload) <= 0x40311CC4, "Rows overlap MODEL")
    size = 0x40311CC4 - ROWS
    put(
        ROWS,
        bytes(data[ROWS - BASE : ROWS - BASE + size]),
        bytes(payload) + bytes(size - len(payload)),
        "four dedicated rows and labels",
    )
    put(0x403118C4 + 8 + 5 * 4, long(253), long(278), "descriptor duration ID")

    # High 16 bits are the track permission mask. Only bit 0 may select type 7.
    mask_addr = 0x40311964 + 7 * 4
    before = bytes(data[mask_addr - BASE : mask_addr - BASE + 4])
    require(before[:2] == b"\xff\xff", "Unexpected cloned track mask")
    put(mask_addr, before, b"\x00\x01" + before[2:], "Plaits track-1 permission")
    # Preserve LFO-modulated TIMB through the sampler's late slot repacking.
    # Skip only track 1/type 7 at the repack read; all stock branches remain.
    repack = 0x4002E978
    original = bytes.fromhex("716c005a0c8000000400")
    helper_code = bytes.fromhex("0c8600000000 6610 7000 103980003cd0 0c8000000007 6710")
    helper_code += original + bytes.fromhex("4ef94002e982 4ef94002e994")
    slot = metadata["sample_shim"]
    old = bytes(data[slot - BASE : slot - BASE + 58])
    require(len(helper_code) <= 58, "Repack helper overflow")
    helper_code += bytes.fromhex("4e71") * ((58 - len(helper_code)) // 2)
    replace_code(slot, old, helper_code, "preserve modulated TIMB through repack")
    replace_code(
        repack,
        original,
        b"\x4e\xf9" + long(slot) + bytes.fromhex("4e71 4e71"),
        "Plaits-only repack bypass",
    )
    replace_code(
        0x4002E9A0,
        b"\x4e\xb9" + long(slot),
        bytes.fromhex("4bf98000483c"),
        "remove post-LFO raw overwrite",
    )
    # LFO destinations enumerate physical mirrors, not the descriptor's IDs.
    # The stock per-machine reverse table has only seven rows. Supply the new
    # macros explicitly without extending that RAM cache or its initializers.
    gaps.append([(ROWS + len(payload) + 1) & ~1, 0x40311CC4])
    reverse = alloc(
        b"".join(
            int(v).to_bytes(2, "big") for v in (0, 275, 0, 276, 0, 0, 277, 278, 0, 0)
        ),
        "Plaits modulation mirror map",
    )
    fallback = alloc(
        bytes.fromhex("7206 b280 6406 4ef9400da274 4ef9400da284"),
        "stock mirror-map continuation",
        "code",
    )
    # Reserve the remaining 34-byte slot so the long conditional displacement
    # is calculated from its actual address, never from a guessed code layout.
    span = next((g for g in gaps if g[1] - g[0] >= 34), None)
    require(span is not None, "No modulation resolver slot")
    address = span[0]
    lookup = bytes.fromhex("0c8000000007 6600") + (fallback - (address + 8)).to_bytes(
        2, "big", signed=True
    )
    lookup += bytes.fromhex("2008 7219 9081 d080 43f9") + long(reverse)
    lookup += bytes.fromhex("d3c0 71d1 4ef9400da2c0")
    require(len(lookup) == 34, "Mirror resolver layout changed")
    where = alloc(lookup, "Plaits modulation reverse lookup", "code")
    require(where == address, "Mirror resolver allocation moved")
    replace_code(
        0x400DA26E,
        bytes.fromhex("7206 b280 6410"),
        b"\x4e\xf9" + long(where),
        "modulation mirror lookup dispatch",
    )
    covered = bytearray(len(data))
    for w in writes:
        off = w["address"] - BASE
        covered[off : off + len(bytes.fromhex(w["after"]))] = bytes([1]) * len(
            bytes.fromhex(w["after"])
        )
    require(
        all(
            a == b or covered[i]
            for i, (a, b) in enumerate(zip(image, data, strict=True))
        ),
        "Unaudited R3 delta",
    )
    return bytes(data), dict(
        baseline_sha256=R2_MAIN,
        sha256=hashlib.sha256(data).hexdigest(),
        writes=writes,
        first_helper=new_first,
        macro_shim=new_copy,
        model_formatter=model_formatter,
        duration_formatter=duration_formatter,
        unused_padding=gaps,
        hardware_verified=False,
    )


def validate_sources():
    import json

    from lab.project import ROOT, sha256

    lock = json.loads(
        (ROOT / "machines/plaits-integration/source-lock.json").read_text()
    )
    require(
        sha256(ROOT / "machines/plaits-controls/machine.c")
        == lock["baseline_adapter_sha256"],
        "R2 adapter drift",
    )
    require(
        sha256(ROOT / "docs/PLAITS-INTEGRATION-R3.md") == lock["contract_sha256"],
        "R3 contract drift",
    )
    return lock
