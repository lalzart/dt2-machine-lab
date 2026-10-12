"""DTII 1.16 sparse parameter metadata extension for the Plaits control experiment."""

import json
import struct

from lab.project import ROOT, require

BASE = 0x40000400
TABLE = 0x4020F18C
COUNT = 275
ROWS = 0x40311B80
CODE = 0x40311D30
LIMIT = 0x40312000


def word(n):
    return struct.pack(">H", n)


def long(n):
    return struct.pack(">I", n)


def resolver(source, scale, destination, operation="lea", field=0):
    """Preserve all registers and CCR except the displaced destination.

    ColdFire MOVEM and address-register ADDQ/SUBQ preserve CCR, allowing D7 to carry saved flags. No
    absolute scratch or current-track global is used: every call is reentrant.
    """
    src = int(source[1]) + (8 if source[0] == "a" else 0)
    dst = int(destination[1])
    b = bytearray.fromhex("518f 48d70080 40c7 3f470004")
    b += word(0x2E00 | src)  # move.l source,d7
    b += bytes.fromhex("0c87") + long(COUNT * scale)
    lower = len(b)
    b += b"\x65\x00"
    b += bytes.fromhex("0c87") + long((COUNT + 3) * scale)
    upper = len(b)
    b += b"\x64\x00"
    ext_base = ROWS - COUNT * 60 + field
    old_base = TABLE + field

    def assign(value):
        if operation == "lea":
            return word(0x41F9 | (dst << 9)) + long(value)
        if operation == "adda":
            return word(0xD1FC | (dst << 9)) + long(value)
        return word(0x0680 | dst) + long(value)

    b += assign(ext_base)
    skip = len(b)
    b += b"\x60\x00"
    fallback = len(b)
    b += assign(old_base)
    restore = len(b)
    if operation == "addi":
        b += bytes.fromhex("40c7 3f470004")
    b += bytes.fromhex("3e2f0004 44c7 4cd70080 508f 4e75")
    for at, target in ((lower, fallback), (upper, fallback), (skip, restore)):
        b[at + 1] = target - at - 2
    return bytes(b)


def patch_cpu(stock, candidate):
    controls = json.loads((ROOT / "machines/plaits-controls/controls.json").read_text())
    data = bytearray(candidate)
    writes = []

    def put(address, before, after, label):
        off = address - BASE
        require(len(before) == len(after), "Patch size changed")
        require(
            data[off : off + len(before)] == before,
            f"Patch guard: {label} {address:#x}",
        )
        data[off : off + len(after)] = after
        writes.append(
            {
                "address": address,
                "before": before.hex(),
                "after": after.hex(),
                "label": label,
            }
        )

    # Track restore validates (uint8_t)(machine + 1) < 8, rejecting type 7.
    # D2 is consumed only by this bound before being reloaded for the next
    # field. Preserve the stock handling of every other byte value.
    put(
        0x400DB2EA,
        bytes.fromhex("7408"),
        bytes.fromhex("7409"),
        "retain Plaits machine type during track restore",
    )

    # Three rows and strings occupy a verified zero gap after machinepatch's
    # payload and before the earlier MODEL label/shim; all remain below clear.
    labels = bytearray()
    rows = bytearray()
    for name, previous in (("harmonics", 0xF9), ("timbre", 0xFB), ("morph", 0xFC)):
        c = controls[name]
        row = bytearray(
            stock[TABLE - BASE + previous * 60 : TABLE - BASE + (previous + 1) * 60]
        )
        label = ROWS + 180 + len(labels)
        labels += name.title().encode() + b"\0" + c["label"].encode() + b"\0"
        for off, value in (
            (8, c["min_raw"]),
            (12, c["max_raw"]),
            (16, c["default_raw"]),
            (20, 0),
            (40, label),
            (48, label + len(name) + 1),
            (52, 0x400E1424),
        ):
            row[off : off + 4] = long(value)
        rows += row
    payload = bytes(rows + labels)
    require(ROWS + len(payload) <= 0x40311CC4, "Macro rows overlap MODEL")
    put(ROWS, bytes(len(payload)), payload, "dedicated macro rows and labels")

    # Each tuple is the index register/scale at an authenticated table reader.
    # Three constant-code branches and two stock-only iteration loops retain
    # the original table. Raising those loops would overwrite stock caches.
    sites = {}

    def add(addresses, src, scale=1, dst="a0", op="lea", field=0):
        for address in addresses:
            sites[address] = (src, scale, dst, op, field)

    add([0x4003A7E8, 0x40074488], "d1")
    add(
        [
            0x4003B530,
            0x4003B7CC,
            0x4003B86E,
            0x4003B922,
            0x4003CF94,
            0x4003D036,
            0x4003D0E2,
            0x4003D1B2,
            0x400C2E60,
            0x400C8804,
            0x400D9EE4,
            0x400D9F08,
            0x400DA07E,
            0x400DA0AA,
            0x400DA0D6,
            0x400DA16E,
            0x400DA1A2,
            0x400DA1DC,
            0x400DA49A,
            0x400DA4C4,
            0x400DA4E8,
            0x400DA50C,
            0x400DA530,
        ],
        "d0",
    )
    add([0x4006B164, 0x40073712, 0x40074172, 0x400C8B14, 0x400D3456, 0x4010406C], "d2")
    add([0x400682F4, 0x40074F8E], "d3")
    add(
        [
            0x4003B9D8,
            0x40048664,
            0x4006C996,
            0x4006D07E,
            0x400DA116,
            0x400DA440,
            0x40105A8E,
        ],
        "d0",
        64,
    )
    add([0x4006CB8A], "d0", 64, "a4")
    add([0x400D9F3A, 0x400D9FAA, 0x400DA018], "d1", 64)
    add([0x4006D9D4], "d2", 64)
    add([0x4003A8CA], "a2", 60, "a2", "adda")
    add([0x4003DC42], "a0", 60, "a0", "adda")
    add([0x400DA224], "d1", 60, "d1", "addi", 8)
    add([0x400DA344], "d0", 60, "d0", "addi", 32)

    cursor = CODE
    first_helper = (ROWS + len(payload) + 3) & ~3
    helpers = {}
    macro_shim = None
    bounds = set()
    for address, key in sorted(sites.items()):
        src, scale, dst, op, field = key
        if key not in helpers:
            code = resolver(*key)
            location = first_helper if not helpers else cursor
            require(
                location + len(code) <= (0x40311CC4 if not helpers else LIMIT),
                "Sparse helper cave overflow",
            )
            helpers[key] = location
            put(location, bytes(len(code)), code, "sparse resolver " + str(key))
            if location == cursor:
                cursor += len(code)
            else:
                macro_shim = location + len(code)
        off = address - BASE
        expected = word(
            (0x41F9 if op == "lea" else 0xD1FC if op == "adda" else 0x0680)
            | (int(dst[1]) << 9 if op != "addi" else int(dst[1]))
        ) + long(TABLE + field)
        put(
            address,
            expected,
            b"\x4e\xb9" + long(helpers[key]),
            "sparse table reference",
        )
        # A reader's adjacent unsigned clamp precedes its index multiply; a
        # few load the base first. Only known immediate comparison forms pass.
        candidates = []
        for delta in range(-40, 13, 2):
            pos = off + delta
            opcode = int.from_bytes(stock[pos : pos + 2], "big")
            value = int.from_bytes(stock[pos + 2 : pos + 6], "big")
            if (
                (opcode & 0xFFF8) == 0x0C80 or opcode in (0xBBFC, 0xBDFC)
            ) and value in (274, 275):
                candidates.append((abs(delta), pos, value))
        require(bool(candidates), f"Missing reader bound {address:#x}")
        _, pos, value = min(candidates)
        if pos not in bounds:
            put(BASE + pos + 2, long(value), long(value + 3), "parameter bound")
            bounds.add(pos)

    # The firmware also validates IDs before setters and looks up a 68-byte
    # UI behavior object. Reuse the existing numeric CFADE behavior object:
    # min/max/default and storage still come from the dedicated parameter ID.
    for address in (0x4003ACFC, 0x4003ADC4, 0x4003BC7E, 0x4006CD70, 0x4006D934):
        put(address + 2, long(274), long(277), "parameter operation bound")
    numeric = bytes.fromhex("202f0004 0c8000000113 650e 0c8000000116 6406 203c000000fa")
    numeric += bytes.fromhex("0c8000000113 4ef9400c87d4")
    put(0x40311CD0, bytes(len(numeric)), numeric, "numeric macro UI behavior")
    put(
        0x400C87CA,
        stock[0x400C87CA - BASE : 0x400C87CA - BASE + 6],
        bytes.fromhex("4ef940311cd0"),
        "macro UI object dispatch",
    )
    # Clear-selected-parameters caches the original table base in D5. Its
    # later dynamic lookup needs the same sparse selection as direct readers.
    reset = (
        b"\x4e\xb9"
        + long(helpers[("d0", 1, "a0", "lea", 0)])
        + bytes.fromhex("e589 ed88 4e75")
    )
    require(cursor + len(reset) <= LIMIT, "Clear helper cave overflow")
    put(cursor, bytes(len(reset)), reset, "macro default table lookup")
    put(
        0x4006D940,
        bytes.fromhex("2045 e589 ed88"),
        b"\x4e\xb9" + long(cursor),
        "macro clear default reader",
    )
    cursor += len(reset)

    # The sample slot is reduced to ten bits in stock transport (e.g. 5639
    # arrived as 519 in a real locked trigger). Reuse the existing type-7 /
    # track-1 guard; copy raw macros together with MODEL after stock filtering.
    # Engine interpolation handles continuous changes. Other types are untouched.
    copy = bytes.fromhex("203980003396 23c080005ba6 3039800033a0 33c080005bb0 4e75")
    require(
        macro_shim + len(copy) <= 0x40311CC4, "Macro transport overlaps MODEL label"
    )
    put(macro_shim, bytes(len(copy)), copy, "untruncated macro transport")
    put(
        0x40311D14,
        bytes.fromhex("303980003398 33c080005ba8"),
        b"\x4e\xb9" + long(macro_shim) + bytes.fromhex("4e71 4e71 4e71"),
        "guarded macro transport dispatch",
    )

    # SAMP is split/recombined after the smoother; its sentinel also skips a
    # repack branch. Restore TIMB once after that entire loop, so every value
    # reaches DSP. Preserve all registers/CCR except the displaced LEA's A5.
    sample_shim = cursor
    sample = bytes.fromhex(
        "518f 48d70080 40c7 3f470004 7fb980003cd0 0c8700000007 660c "
        "3e398000339a 33c780005baa 3e2f0004 44c7 4cd70080 508f 4bf98000483c 4e75"
    )
    require(cursor + len(sample) <= LIMIT, "Sample transport cave overflow")
    put(cursor, bytes(len(sample)), sample, "macro sample-slot final transport")
    put(
        0x4002E9A0,
        bytes.fromhex("4bf98000483c"),
        b"\x4e\xb9" + long(cursor),
        "post-sample-repack dispatch",
    )
    cursor += len(sample)

    return bytes(data), {
        "rows": ROWS,
        "code_end": cursor,
        "writes": writes,
        "helpers": [{"key": list(k), "address": v} for k, v in helpers.items()],
        "reader_sites": list(sites),
        "macro_shim": macro_shim,
        "sample_shim": sample_shim,
        "scope": "Sparse metadata and track-1/type-7 raw macro transport; requires prepared runtime verification",
    }


def control_header(controls):
    """Deterministic generated adapter constants from the locked control map."""
    text = "// Generated from controls.json; regenerate with the controls runner.\n"
    for name in (
        "model",
        "note",
        "tune",
        "harmonics",
        "timbre",
        "morph",
        "length",
        "level",
    ):
        text += f"#define BANK_{name.upper()}_DM {controls[name]['dm']}\n"
    for name in ("harmonics", "timbre", "morph", "level"):
        text += (
            f"#define BANK_{name.upper()}_FACTOR (1.0f/{controls[name]['scale']}.0f)\n"
        )
    text += f"#define BANK_MAX_MODEL {len(controls['model_names']) - 1}\n"
    return text


def validate_sources():
    from lab.project import git, sha256, verify_files

    machine = ROOT / "machines/plaits-controls"
    source = ROOT / ".local/sources/eurorack"
    lock = json.loads((machine / "source-lock.json").read_text())
    require(
        sha256(ROOT / lock["proposal"]) == lock["proposal_sha256"], "Contract drift"
    )
    require(
        sha256(machine / "controls.json") == lock["control_sha256"], "Control map drift"
    )
    controls = json.loads((machine / "controls.json").read_text())
    require(
        (machine / "controls.h").read_text() == control_header(controls),
        "Regenerate controls.h from controls.json",
    )
    verify_files(ROOT, lock["reuse_sha256"])
    verify_files(source, lock["files"])
    for path, revision in (
        (source, lock["revision"]),
        (source / "stmlib", lock["stmlib_revision"]),
    ):
        require(git(path, "rev-parse", "HEAD") == revision, "Wrong upstream revision")
        require(not git(path, "status", "--porcelain"), "Dirty upstream source")
    return lock
