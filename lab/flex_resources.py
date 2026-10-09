"""Optional shared native resource dispatch, preserving the original RAM ABI.

Code-space prerequisite for ownership work. No release or reference reuse.
"""

import struct

from lab.coldfire import audit_code
from lab.flex_native import FIRST_ID, LAST_ID, Code

OPERATIONS = ("resolve", "open", "close", "read", "key", "size", "name")


def entry(address, operation, dispatcher):
    c = Code()
    c.emit("4feffff4 48d70c04")
    c.emit(f"{0x7400 | OPERATIONS.index(operation):04x}")
    c.imm("4ef9", dispatcher)
    return c.finish(address)


def dispatch(
    address, lookup, fallbacks, *, durable_reader=0, source_pin=0, source_unpin=0
):
    c = Code()
    c.imm("0c82", 3)
    c.branch(5, "pointer")
    c.branch(7, "read_handle")
    c.emit("202f0010")
    c.branch(0, "lookup")
    c.label("pointer")
    c.emit("246f0010")
    c.imm("b5fc", 0)
    c.branch(7, "stock")
    c.emit("2012")
    c.branch(0, "lookup")
    c.label("read_handle")
    c.emit("266f0018")
    c.imm("b7fc", 0)
    c.branch(7, "stock")
    c.emit("2013")
    c.label("lookup")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "stock")
    c.imm("0c80", LAST_ID)
    c.branch(2, "stock")
    c.imm("4eb9", lookup)
    c.imm("b1fc", 0)
    c.branch(7, "invalid")
    if source_pin:
        c.emit("22280038")
        c.imm("0c81", 0)
        c.branch(6, "invalid")
    c.imm("0c82", 2)
    c.branch(5, "identity")
    c.branch(7, "success")
    for operation in ("read", "key", "size"):
        c.imm("0c82", OPERATIONS.index(operation))
        c.branch(7, operation)
    # Name retains the original 32-byte output contract.
    c.emit("226f0018")
    for value in (0x2F54454D, 0x502F464C, 0x45580000, 0, 0, 0, 0, 0):
        c.imm("203c", value)
        c.emit("22c0")
    c.emit("202f0018")
    c.branch(0, "return")
    c.label("identity")
    for i in range(4):
        c.emit("202a" + struct.pack(">H", i * 4).hex())
        c.emit("2228" + struct.pack(">H", i * 4 + 4).hex())
        c.emit("b081")
        c.branch(6, "invalid")
    c.emit("226f0014 20280004 2280")
    c.imm("0c82", 0)
    c.branch(7, "success")
    c.emit("7000 23400004 23400008")
    c.branch(0, "success")
    c.label("key")
    c.emit("226f0014 41e80004 22d8 22d8 22d8 22d8")
    c.branch(0, "success")
    c.label("size")
    c.emit("2028000c")
    c.branch(0, "return")
    c.label("read")
    c.emit("242f0014 2028000c 222b0004 b081")
    c.branch(5, "invalid")
    c.emit("9081 b480")
    c.branch(3, "count")
    c.emit("2400")
    c.label("count")
    c.imm("0c82", 0)
    c.branch(7, "success")
    if source_pin:
        c.emit("2448 2f0a")
        c.imm("4eb9", source_pin)
        c.emit("588f")
        c.imm("0c80", -1)
        c.branch(7, "invalid")
        c.imm("0c80", 0)
        c.branch(7, "durable")
        c.emit("2040 222b0004")
    elif durable_reader:
        c.emit("2448 202a0014")
        c.imm("0c80", 0)
        c.branch(7, "durable")
    if not source_pin:
        c.emit("20680014")
    c.emit("2001 d1c0 2241 2002 d3c0 27490004 226f0010 2002")
    c.label("byte")
    c.emit("12d8")
    c.imm("0680", -1)
    c.branch(6, "byte")
    if source_pin:
        c.emit("2f0a")
        c.imm("4eb9", source_unpin)
        c.emit("588f")
    c.emit("2002")
    c.branch(0, "return")
    if durable_reader:
        c.label("durable")
        c.emit("2f2b0004 2f02 2f2f0018 2f0a")
        c.imm("4eb9", durable_reader)
        c.emit("4fef0010")
        c.imm("0c80", 0)
        c.branch(11, "return")
        c.emit("206b0004 d1c0 27480004")
        c.branch(0, "return")
    c.label("success")
    c.emit("7000")
    c.branch(0, "return")
    c.label("invalid")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c04 4fef000c 4e75")
    c.label("stock")
    c.emit("2002 d080 d080")
    c.imm("43f9", fallbacks)
    c.emit("d3c0 2051 4cd70c04 4fef000c 2f08 4e75")
    return c.finish(address)


def parts(
    addresses, lookup, fallbacks, *, durable_reader=0, source_pin=0, source_unpin=0
):
    """Split at audited instruction boundaries; relocate every local branch.

    Two short parts fit the pre-existing small asset-padding gaps. Absolute
    calls remain untouched; explicit jumps replace cross-part fallthrough.
    No new instruction forms or unverified memory reservation are introduced.
    """
    return split_native(
        dispatch(
            0,
            lookup,
            fallbacks,
            durable_reader=durable_reader,
            source_pin=source_pin,
            source_unpin=source_unpin,
        ),
        addresses,
    )


def split_native(original, addresses):
    """Partition position-independent native code with local word branches."""
    instructions = audit_code(original, 0)
    groups = [[]]
    start = 0
    for ins in instructions:
        if ins["address"] + len(bytes.fromhex(ins["bytes"])) - start > 234:
            groups.append([])
            start = ins["address"]
        groups[-1].append(ins)
    if len(addresses) != len(groups):
        raise ValueError("Unexpected resource partition count")
    targets = {
        ins["address"]: addresses[i] + ins["address"] - group[0]["address"]
        for i, group in enumerate(groups)
        for ins in group
    }
    result = []
    for i, group in enumerate(groups):
        data = bytearray()
        for ins in group:
            encoded = bytes.fromhex(ins["bytes"])
            if ins["kind"] == "BRANCH":
                if len(encoded) != 4:
                    raise ValueError("Expected word-displacement branch")
                old_target = ins["address"] + 2 + struct.unpack(">h", encoded[2:])[0]
                displacement = targets[old_target] - targets[ins["address"]] - 2
                encoded = encoded[:2] + struct.pack(">h", displacement)
            data.extend(encoded)
        if i + 1 < len(groups):
            data.extend(bytes.fromhex("4ef9") + struct.pack(">I", addresses[i + 1]))
        audit_code(data, addresses[i])
        result.append(bytes(data))
    return result
