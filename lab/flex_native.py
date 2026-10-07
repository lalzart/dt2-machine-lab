"""Native ColdFire recorder primitives for OS 1.16.

This module emits device instructions, not emulator callbacks. It deliberately
does not expose an OS packager until resource, UI and persistence integration
are complete. Caller supplies owned, writable destination memory.
"""

import struct

from lab.coldfire import audit_code

LOCK = 0x40012542
UNLOCK = 0x40012552
RECORDER_CHUNK = 0x4001282E
MAX_FRAMES = 960000
FIRST_ID = 0x7FFE0001
LAST_ID = FIRST_ID + 31
RESOURCE_SITES = {
    "resolve": (0x4015B178, "4fefffe848d77c04"),
    "key": (0x4015ABE6, "2f02242f000c"),
    "open": (0x4015B2D0, "4e56fffc2f0a"),
    "size": (0x4015BA22, "2f0a2f024ab944f2bd68"),
    "read": (0x4015832E, "2f0a2f02242f000c"),
    "name": (0x401575F6, "4feffebc48d77cfc"),
    "close": (0x401585E4, "2f0a246f0008"),
}


USE_ERRORS = {
    "generic": "FLEX: CANNOT USE",
    "changed": "FLEX: TRACK CHANGED",
    "machine": "FLEX: USE ONESHOT",
    "settings": "FLEX: NO PROJECT",
    "slots": "FLEX: NO FREE SLOT",
    "short": "FLEX: TAKE TOO SHORT",
    "long": "FLEX: OVER 20 SEC",
    "format": "FLEX: INPUT FORMAT",
    "limit": "FLEX: 32 TAKE LIMIT",
    "memory": "FLEX: NO MEMORY",
    "copy": "FLEX: COPY FAILED",
    "load": "FLEX: LOAD FAILED",
    "assign": "FLEX: ASSIGN FAILED",
}


def error_stage(code, errors, name):
    """D1 scratch; A2 points at Flex state. Keep D0 return values intact."""
    code.emit(f"{0x7200 | errors[name]:04x}")
    code.emit("25410030")


def recorder_error_text(address, state, table):
    """Replace the original error PEA; preserve its one-pointer stack effect."""
    c = Code()
    c.imm("2039", state + 48)
    c.imm("0c80", len(USE_ERRORS))
    c.branch(5, "known")
    c.emit("7000")
    c.label("known")
    c.emit("d080 d080")
    c.imm("43f9", table)
    c.emit("d3c0 2f11")
    c.imm("4ef9", 0x4002198C)
    return c.finish(address)


class Code:
    """Small label assembler; only independently audited instructions emitted."""

    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.branches = []

    def emit(self, hex_bytes):
        self.data.extend(bytes.fromhex(hex_bytes))

    def imm(self, opcode, value):
        self.emit(opcode)
        self.data.extend(struct.pack(">I", value & 0xFFFFFFFF))

    def label(self, name):
        if name in self.labels:
            raise ValueError("Duplicate native label")
        self.labels[name] = len(self.data)

    def branch(self, condition, label):
        self.branches.append((len(self.data), label))
        self.data.extend(bytes((0x60 | condition, 0, 0, 0)))

    def finish(self, address):
        result = bytearray(self.data)
        for offset, label in self.branches:
            displacement = self.labels[label] - offset - 2
            result[offset + 2 : offset + 4] = struct.pack(">h", displacement)
        audit_code(result, address)
        return bytes(result)


def recording_copy(address):
    """Emit int copy(dest, capacity, start, frames, stereo).

    Returns native-file byte length, or -1 before touching the destination.
    Arguments and nonvolatile registers follow the stock ColdFire stack ABI.
    Caller must keep the recorder stopped and destination alive throughout.
    No heap, filesystem, track or sample-table mutations occur here.
    """
    c = Code()
    # 36 bytes for D2-D7/A2-A4. Arguments now begin at SP+40.
    c.emit("4fef ffdc 48d7 1cfc")
    c.emit("246f0028 222f002c 242f0030 262f0034 202f0038")
    c.imm("0c80", 1)
    c.branch(2, "invalid")  # unsigned higher
    c.imm("b5fc", 0)  # CMPA.L #0,A2
    c.branch(7, "invalid")
    c.imm("0c83", 141)
    c.branch(5, "invalid")
    c.imm("0c83", MAX_FRAMES)
    c.branch(2, "invalid")
    c.imm("0c82", MAX_FRAMES)
    c.branch(2, "invalid")
    c.emit("2042 2003 d1c0")  # A0=start+frames, bounded operands cannot wrap
    c.imm("b1fc", MAX_FRAMES)
    c.branch(2, "invalid")
    c.emit("7e01 2803 2004 d080 2800 202f0038")
    c.imm("0c80", 0)
    c.branch(7, "size")
    c.emit("7e00 2004 d080 2800")  # D4=PCM bytes, D7=mono selector
    c.label("size")
    c.emit("2004")
    c.imm("0680", 80)
    c.emit("2840 b081")  # A4=total; CMP.L capacity,total
    c.branch(2, "invalid")

    # Zero header; MOVE immediate through a register respects ColdFire EA rules.
    c.emit("204a 7040 7200")
    c.label("zero_header")
    c.emit("10c1")
    c.imm("0680", -1)
    c.branch(6, "zero_header")
    c.emit("202f0038 15400001 25440004")
    c.imm("203c", 48000)
    c.emit("25400008 707f 15400014 47ea0040")

    c.label("chunk")
    c.imm("2a3c", 1024)
    c.imm("0c87", 0)
    c.branch(6, "limit")
    c.imm("2a3c", 512)
    c.label("limit")
    c.emit("ba83")  # CMP.L remaining,chunk
    c.branch(3, "bounded")  # unsigned lower or same
    c.emit("2a03")
    c.label("bounded")
    c.emit("2005 d080 2c00")
    c.imm("0c87", 0)
    c.branch(6, "locked_copy")
    c.emit("d080 2c00")
    c.label("locked_copy")
    c.imm("4eb9", LOCK)
    c.emit("2f07 2f05 2f02")
    c.imm("4eb9", RECORDER_CHUNK)
    c.emit("2040 224b 2006")
    c.label("copy_byte")
    c.emit("12d8")  # MOVE.B (A0)+,(A1)+
    c.imm("0680", -1)
    c.branch(6, "copy_byte")
    c.emit("2649")
    c.imm("4eb9", UNLOCK)
    c.emit("4fef000c 2042 2005 d1c0 2408 2003 2205 9081 2600")
    c.branch(6, "chunk")

    c.emit("204b 7010 7200")
    c.label("zero_trailer")
    c.emit("10c1")
    c.imm("0680", -1)
    c.branch(6, "zero_trailer")
    c.emit("200c")
    c.branch(0, "return")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd71cfc 4fef0024 4e75")
    return c.finish(address)


def resource_lookup(address, head_address):
    """D0 identity -> A0 node or NULL; clobbers D1/A1, bounds traversal to 32.

    Node layout: next pointer, 16-byte reference, native-file pointer. Nodes
    and their file buffers must remain owned while visible to a loader.
    """
    c = Code()
    c.imm("2079", head_address)
    c.imm("227c", 32)
    c.label("scan")
    c.imm("b1fc", 0)
    c.branch(7, "return")
    c.emit("22280004 b081")
    c.branch(7, "return")
    c.emit("2050")
    c.imm("d3fc", -1)
    c.imm("b3fc", 0)
    c.branch(6, "scan")
    c.imm("207c", 0)
    c.label("return")
    c.emit("4e75")
    return c.finish(address)


def resource_handler(address, lookup, operation, fallback):
    """Emit a native RAM-source API boundary; fallback is a stock trampoline.

    Normal IDs are forwarded with the original arguments/registers. Reserved
    but unregistered IDs fail closed. There is no Python resource dictionary.
    Installation, ownership and project lifecycle are intentionally separate.
    """
    if operation not in ("resolve", "key", "open", "size", "read", "name", "close"):
        raise ValueError("Unknown resource operation")
    c = Code()
    c.emit("4fef fff4 48d7 0c04")  # D2/A2/A3; args at +16,+20,+24
    if operation in ("resolve", "open", "close"):
        c.emit("246f0010")
        c.imm("b5fc", 0)
        c.branch(7, "stock")
        c.emit("2012")
    elif operation == "read":
        c.emit("266f0018")
        c.imm("b7fc", 0)
        c.branch(7, "stock")
        c.emit("2013")
    else:
        c.emit("202f0010")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "stock")
    c.imm("0c80", LAST_ID)
    c.branch(2, "stock")
    c.imm("4eb9", lookup)
    c.imm("b1fc", 0)
    c.branch(7, "invalid")

    if operation in ("resolve", "open"):
        # Check the complete identity, not just its ID.
        for i in range(4):
            c.emit("202a" + struct.pack(">H", i * 4).hex())
            c.emit("2228" + struct.pack(">H", i * 4 + 4).hex())
            c.emit("b081")
            c.branch(6, "invalid")
        c.emit("226f0014 20280004 2280")
        if operation == "open":
            c.emit("7000 23400004 23400008")
    elif operation == "key":
        c.emit("226f0014 41e80004 22d8 22d8 22d8 22d8")
    elif operation == "size":
        c.emit("2028000c")
        c.branch(0, "return")
    elif operation == "name":
        # 32-byte buffer supplied by the original loader. Bounded constant name.
        c.emit("226f0018")
        for value in (0x2F54454D, 0x502F464C, 0x45580000, 0, 0, 0, 0, 0):
            c.imm("203c", value)
            c.emit("22c0")
        c.emit("202f0018")
        c.branch(0, "return")
    elif operation == "read":
        c.emit("242f0014 2028000c 222b0004 b081")
        c.branch(5, "invalid")  # position > size
        c.emit("9081 b480")  # available=size-position; requested > available?
        c.branch(3, "count")
        c.emit("2400")
        c.label("count")
        c.imm("0c82", 0)
        c.branch(7, "success")
        c.emit("20680014 2001 d1c0 2241 2002 d3c0 27490004 226f0010 2002")
        c.label("byte")
        c.emit("12d8")
        c.imm("0680", -1)
        c.branch(6, "byte")
        c.emit("2002")
        c.branch(0, "return")
    c.label("success")
    c.emit("7000")
    c.branch(0, "return")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c04 4fef000c 4e75")
    c.label("stock")
    c.emit("4cd70c04 4fef000c")
    c.imm("4ef9", fallback)
    return c.finish(address)


def accept_recording(address, copier, errors):
    """Emit node* accept(state, start, frames, stereo, empty_slot), or -1.

    State is {head, successful_count}; caller serializes access and owns its
    lifetime. Uses the original heap and sample loader. A failed publication
    unlinks/frees its source and clears only the prechecked empty destination.
    Successful nodes stay owned, bounded to 32, to preserve sample references.
    Assignment and project persistence are separate from this worker primitive.
    """
    c = Code()
    c.emit("4fefffe0 48d73c3c 246f0024 262f0028 282f002c 2a2f0030 242f0034")
    error_stage(c, errors, "short")
    c.imm("0c84", 141)
    c.branch(5, "invalid")
    error_stage(c, errors, "long")
    c.imm("0c84", MAX_FRAMES)
    c.branch(2, "invalid")
    c.imm("0c83", MAX_FRAMES)
    c.branch(2, "invalid")
    c.emit("2043 2004 d1c0")
    c.imm("b1fc", MAX_FRAMES)
    c.branch(2, "invalid")
    error_stage(c, errors, "format")
    c.imm("0c85", 1)
    c.branch(2, "invalid")
    error_stage(c, errors, "limit")
    c.emit("202a0004")
    c.imm("0c80", 32)
    c.branch(4, "invalid")  # >=32 unsigned
    error_stage(c, errors, "slots")
    c.imm("0c82", 1023)
    c.branch(2, "invalid")
    c.emit("2002 727f c081")
    c.branch(7, "invalid")  # excludes zero and multiples of 128
    c.emit("2002 d080 d080")
    c.imm("41f9", 0x405BA768)
    c.emit("d1c0 2210")
    c.imm("0c81", 0)
    c.branch(6, "invalid")
    c.emit("d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "invalid")
    c.emit("2004 d080")
    c.imm("0c85", 0)
    c.branch(7, "size")
    c.emit("d080")
    c.label("size")
    c.imm("0680", 80)
    c.emit("2840")
    c.imm("0680", 64)
    error_stage(c, errors, "memory")
    c.emit("2f00")
    c.imm("4eb9", 0x4011E8F0)
    c.emit("588f 2640")
    c.imm("0c80", 0)
    c.branch(7, "invalid")
    error_stage(c, errors, "copy")
    c.emit("2f05 2f04 2f03 2f0c 41eb0040 2f08")
    c.imm("4eb9", copier)
    c.emit("4fef0014")
    c.imm("0c80", -1)
    c.branch(7, "free")
    c.emit("2692 202a0004")
    c.imm("0680", FIRST_ID)
    c.emit("27400004 274c000c 202a0004 5280 27400010")
    c.emit("41eb0040 27480014 27420018 7000")
    # Node +28 is the durable-reference cache flag, +32..47 the reference.
    # Keep the remainder of the 64-byte node header initialized as well.
    for offset in range(28, 64, 4):
        c.emit("2740" + struct.pack(">H", offset).hex())
    # Use the stock content hash, under the same filesystem mutex as stock
    # rehash. A made-up constant hash can alias different same-sized takes.
    c.imm("4879", 0x46F4DEB0)
    c.imm("4eb9", 0x400015A0)
    c.imm("203c", 0x43FA243A)
    for global_address in (0x40941D78, 0x40941D7C, 0x40941D80):
        c.imm("23c0", global_address)
    c.emit("7000")
    c.imm("23c0", 0x409418C4)
    c.emit("2f0c 41eb0040 2f08")
    c.imm("4eb9", 0x4015AA20)
    c.emit("508f")
    c.imm("4eb9", 0x4015A6DC)
    c.emit("7201 c280")
    c.branch(6, "odd_hash")
    c.emit("5280")
    c.label("odd_hash")
    c.emit("27400008")
    c.imm("4eb9", 0x400016D2)
    c.emit("588f 248b")
    error_stage(c, errors, "load")
    c.emit("2f02 41eb0004 2f08")
    c.imm("4eb9", 0x40154540)
    c.emit("508f 25400034")
    c.imm("0c80", 0)
    c.branch(7, "published")
    c.emit("2493 2f02")
    c.imm("4eb9", 0x401540C6)
    c.imm("4eb9", 0x40153BEA)
    c.emit("588f")
    c.label("free")
    c.emit("2f0b")
    c.imm("4eb9", 0x4011E8FC)
    c.emit("588f")
    c.label("invalid")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("published")
    c.emit("7200 25410030")
    c.emit("202a0004 5280 25400004 200b")
    c.label("return")
    c.emit("4cd73c3c 4fef0020 4e75")
    return c.finish(address)


def assign_recording(address):
    """Emit int assign(slot, track_index, expected_live_kit).

    UI-thread primitive, called after successful publication. Rejects project
    changes, unsupported track machines and empty/reserved slots before writing
    the track. Preserves all controls except its sample-slot field; invokes the
    original track refresh so the stock sampler receives the new assignment.
    """
    c = Code()
    c.emit("4feffff8 48d70404 242f000c 202f0010")  # D2/A2
    c.imm("0c80", 15)
    c.branch(2, "invalid")
    c.imm("0c82", 1023)
    c.branch(2, "invalid")
    c.emit("2002 727f c081")
    c.branch(7, "invalid")
    c.emit("2002 d080 d080")
    c.imm("41f9", 0x405BA768)
    c.emit("d1c0 2010")
    c.imm("0c80", 0)
    c.branch(7, "invalid")
    c.imm("2039", 0x80004704)
    c.emit("222f0014 b081")
    c.branch(6, "invalid")
    c.emit("2440 202f0010")
    c.imm("223c", 0x450)
    c.emit("4c010800 204a d1c0 2448 7000 102a00d6")
    c.imm("0c80", 0)
    c.branch(6, "invalid")
    # Mirror the original successful ProjectSettings sample load: copy the
    # loaded reference into the pool, not just the track's numeric slot.
    c.imm("4eb9", 0x401988A2)
    c.emit("2f00")
    c.imm("4eb9", 0x40041D18)
    c.emit("588f 2040 2250 22690028 2f08 4e91 588f")
    c.imm("0c80", 0)
    c.branch(7, "invalid")
    c.emit("2240 2002 d080 d080 d080 d080 d3c0")
    c.imm("d3fc", 0x1D2)
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 22d8 22d8 22d8 22d8")
    c.emit("35420080 2f2f0010 41ea0034 2f08")
    c.imm("4eb9", 0x4002D438)
    c.emit("508f 7000")
    c.branch(0, "return")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(address)


def exclusive_open_guard(address, caller_return):
    """Replace 0x401586b8's six bytes (6654 4a82 6724).

    Only the paired save routine may reject an existing writable file here.
    The decision executes while the original filesystem mutex is held, avoiding
    a separate existence-check/open race. Stock callers retain stock branches.
    """
    c = Code()
    c.branch(6, "missing")  # flags from original CMP at 0x401586b6
    c.emit("202e0004")
    c.imm("0c80", caller_return)
    c.branch(7, "exists")
    c.imm("0c82", 0)
    c.branch(7, "read_existing")
    c.imm("4ef9", 0x401586BE)
    c.label("read_existing")
    c.imm("4ef9", 0x401586E2)
    c.label("missing")
    c.imm("4ef9", 0x4015870E)
    c.label("exists")
    c.imm("4ef9", 0x40158758)
    return c.finish(address)


def save_recording(address):
    """Emit int save(node, new_absolute_path, output_reference).

    MUST install the paired exclusive_open_guard with the returned call site.
    This primitive writes via the stock filesystem, verifies the durable hash
    and length, then copies the reference to the caller. It never changes a
    project or frees the temporary recording. Failures remove only the file
    created by this call. The caller owns path selection and project commit.
    """
    c = Code()
    # D2-D4/A2-A5 (28 bytes), file handle (16), reference (16), padding.
    c.emit("4fefffc0 48d73c1c 246f0044 266f0048 286f004c")
    c.emit("41ef001c 2f08")
    c.imm("4879", 0x402423BB)  # original "w" mode string
    c.emit("2f0b")
    c.imm("4eb9", 0x40158626)
    after_open = address + len(c.data)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(6, "invalid")
    c.emit("262f001c 282a000c 2f04 7000 2f00 41ef0024 2f08")
    c.imm("4eb9", 0x40158534)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(6, "close_failed")
    c.emit("2a6a0014")
    c.label("chunk")
    c.imm("243c", 0x8000)
    c.emit("b484")
    c.branch(3, "bounded")
    c.emit("2404")
    c.label("bounded")
    c.emit("41ef001c 2f08 2f02 2f0d")
    c.imm("4eb9", 0x4015838E)
    c.emit("4fef000c b082")
    c.branch(6, "close_failed")
    c.emit("204d 2002 d1c0 2a48 2004 2202 9081 2800")
    c.branch(6, "chunk")
    c.emit("41ef001c 2f08")
    c.imm("4eb9", 0x4015B0CE)
    c.emit("588f 2400 41ef001c 2f08")
    c.imm("4eb9", 0x401585E4)
    c.emit("588f")
    c.imm("0c82", 0)
    c.branch(6, "delete_failed")
    c.emit("41ef002c 2f08 2f03")
    c.imm("4eb9", 0x4015ABE6)
    c.emit("508f")
    c.imm("0c80", 0)
    c.branch(6, "delete_failed")
    c.emit("202a0008 222f0030 b081")
    c.branch(6, "delete_failed")
    c.emit("202a000c 222f0034 b081")
    c.branch(6, "delete_failed")
    c.emit("41ef002c 224c 22d8 22d8 22d8 22d8 7000")
    c.branch(0, "return")
    c.label("close_failed")
    c.emit("41ef001c 2f08")
    c.imm("4eb9", 0x401585E4)
    c.emit("588f")
    c.label("delete_failed")
    c.emit("2f0b")
    c.imm("4eb9", 0x40156D9C)
    c.emit("588f")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd73c1c 4fef0040 4e75")
    return c.finish(address), after_open


def persist_project_pool(address, lookup, saver, path_format, directory):
    """Emit int persist(pool_reference_base), before project serialization.

    First save every temporary reference in the 1024-slot project pool. Cache
    durable refs in owned nodes so retries do not duplicate completed files.
    Only after all saves succeed does a second pass update project references.
    The caller must serialize project edits for the duration, as for saving.
    """
    c = Code()
    c.emit("4fefffa0 48d73c1c 246f0064 264a 2a4a")
    c.imm("dbfc", 0x4000)
    c.emit("7800")
    c.label("slot")
    c.emit("200b 220d b081")
    c.branch(7, "end_pass")
    c.emit("2013")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "advance")
    c.imm("0c80", LAST_ID)
    c.branch(2, "advance")
    c.imm("4eb9", lookup)
    c.imm("b1fc", 0)
    c.branch(7, "invalid")
    c.emit("2848")
    for offset in range(0, 16, 4):
        c.emit("202b" + struct.pack(">H", offset).hex())
        c.emit("222c" + struct.pack(">H", offset + 4).hex())
        c.emit("b081")
        c.branch(6, "invalid")
    c.imm("0c84", 0)
    c.branch(6, "commit")
    c.emit("202c001c")
    c.imm("0c80", 1)
    c.branch(7, "advance")
    c.imm("4879", directory)
    c.imm("4eb9", 0x40157192)
    c.emit("588f 7400")
    c.label("filename")
    c.emit("2f02 2f2c0008")
    c.imm("4879", path_format)
    c.emit("41ef0028 2f08")
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef0010 41ec0020 2f08 41ef0020 2f08 2f0c")
    c.imm("4eb9", saver)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(7, "saved")
    c.imm("0682", 1)
    c.imm("0c82", 64)
    c.branch(5, "filename")
    c.branch(0, "invalid")
    c.label("saved")
    c.emit("7001 2940001c")
    c.branch(0, "advance")
    c.label("commit")
    c.emit("202c001c")
    c.imm("0c80", 1)
    c.branch(6, "invalid")
    c.emit("41ec0020 224b 22d8 22d8 22d8 22d8")
    c.label("advance")
    c.emit("47eb0010")
    c.branch(0, "slot")
    c.label("end_pass")
    c.imm("0c84", 0)
    c.branch(6, "success")
    c.emit("7801 264a")
    c.branch(0, "slot")
    c.label("invalid")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("success")
    c.emit("7000")
    c.label("return")
    c.emit("4cd73c1c 4fef0060 4e75")
    return c.finish(address)


def project_save_guard(address, persist):
    """Prepend persistence to OS 1.16 Project::saveProjectToMmc at 0x40043a30.

    Returns the original bool failure without entering the project writer when
    any temporary recording cannot be saved. On success, executes the exact
    displaced prologue and resumes the original writer with unchanged args.
    """
    c = Code()
    c.emit("2f2f0004")
    c.imm("4eb9", 0x40041D18)
    c.emit("588f 2040 2250 22690028 2f08 4e91 588f")
    c.imm("0c80", 0)
    c.branch(7, "failed")
    c.imm("0680", 0x1D2)
    c.emit("2f00")
    c.imm("4eb9", persist)
    c.emit("588f")
    c.imm("0c80", 0)
    c.branch(6, "failed")
    c.emit("4fefffcc 48d77c1c")
    c.imm("4ef9", 0x40043A38)
    c.label("failed")
    c.emit("7000 4e75")
    return c.finish(address)


def recorder_use_entry(address, state):
    """Capture the completed-trim action, then retain the stock queued-job UI."""
    c = Code()
    c.emit("4fefffd8 48d73cfc")
    c.imm("47f9", state)
    c.emit("202b000c")
    c.imm("0c80", 0)
    c.branch(6, "busy")
    c.emit("274a0008 202b0028")
    c.imm("0c80", 0)
    c.branch(7, "current_track")
    c.imm("0680", -1)
    c.branch(0, "track")
    c.label("current_track")
    c.emit("2f2a00a0")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f")
    c.label("track")
    c.emit("27400010")
    c.imm("2039", 0x80004704)
    c.emit("2740002c 202a09a0 27400018 2200 202a09a4 9081 2740001c 2f0a")
    c.imm("4eb9", 0x40020388)
    # The stock helper returns a byte bool. For mono, SNE.B / NEG.L leaves
    # D0 = 0xffffff01. Widen only its low byte before computing !mono.
    c.emit("588f 7200 1200 7001 9081 27400020 7001 2740000c")
    c.emit("4cd73cfc 4fef0028 487940229719 7e01")
    c.imm("4ef9", 0x40022FC6)
    c.label("busy")
    c.emit("4cd73cfc 4fef0028 7601")
    c.imm("4ef9", 0x400232D2)
    return c.finish(address)


def recorder_use_worker(address, state, accept, errors):
    """Replacement for the recorder's initial directory-scan worker."""
    c = Code()
    c.emit("4feffff4 48d70c04")
    c.imm("45f9", state)
    error_stage(c, errors, "changed")
    c.emit("202a002c")
    c.imm("2239", 0x80004704)
    c.emit("b081")
    c.branch(6, "invalid")
    c.emit("202a0010")
    c.imm("0c80", 15)
    c.branch(2, "invalid")
    error_stage(c, errors, "machine")
    c.imm("223c", 0x450)
    c.emit("4c010800 206a002c d1c0 7000 102800d6")
    c.imm("0c80", 0)
    c.branch(6, "invalid")
    # A CPU-empty slot may still belong to an unloaded project sample.
    # Reserve only a slot that is empty in both representations.
    error_stage(c, errors, "settings")
    c.imm("4eb9", 0x401988A2)
    c.emit("2f00")
    c.imm("4eb9", 0x40041D18)
    c.emit("588f 2040 2250 22690028 2f08 4e91 588f")
    c.imm("0c80", 0)
    c.branch(7, "invalid")
    c.emit("2640")
    c.imm("d7fc", 0x1D2)
    error_stage(c, errors, "slots")
    c.emit("7401")
    c.label("slot")
    c.imm("0c82", 1024)
    c.branch(4, "invalid")
    c.emit("2002 727f c081")
    c.branch(7, "advance")
    c.emit("2002 d080 d080")
    c.imm("41f9", 0x405BA768)
    c.emit("d1c0 2210")
    c.imm("0c81", 0)
    c.branch(6, "advance")
    c.emit("d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "advance")
    c.emit("2002 d080 d080 d080 d080 204b d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "advance")
    c.emit("2f02 2f2a0020 2f2a001c 2f2a0018 2f0a")
    c.imm("4eb9", accept)
    c.emit("4fef0014")
    c.imm("0c80", -1)
    c.branch(7, "invalid")
    c.emit("25420024 7000")
    c.branch(0, "return")
    c.label("advance")
    c.imm("0682", 1)
    c.branch(0, "slot")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c04 4fef000c 4e75")
    return c.finish(address)


def recorder_use_finish(address, state, assign, original_error, errors):
    """Commit on the UI thread, close progress/recorder, preserve trim on error."""
    c = Code()
    c.emit("4feffff4 48d70c04")
    c.imm("45f9", state)
    c.emit("7000 2540000c 202f0014")
    c.imm("0c80", 0)
    c.branch(6, "failed")
    error_stage(c, errors, "assign")
    c.emit("2f2a002c 2f2a0010 2f2a0024")
    c.imm("4eb9", assign)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(6, "failed")
    c.emit("7200 25410030")
    c.emit("202a0010 5280 25400028")
    c.imm("4eb9", 0x4019988A)
    c.emit("2f00")
    c.imm("4eb9", 0x40016020)
    c.emit("588f 266f0010 2053 2050 2250 22690028 2f08 4e91 588f")
    c.emit("206a0008 2250 22690028 2f08 4e91 588f 7000 25400008")
    c.emit("4cd70c04 4fef000c 4e75")
    c.label("failed")
    c.emit("70ff 2f400014 4cd70c04 4fef000c")
    c.imm("4ef9", original_error)
    return c.finish(address)
