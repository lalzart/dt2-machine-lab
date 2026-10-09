"""OS 1.16 recorder-scoped explicit Flex save and stock filename dialog.

The closure borrows an owned Flex node (valid until reboot) and captures the
project pool. Dialog copies own only those two pointers. NO destroys the dialog
without calling the writer. All emitted instructions execute on the device.
"""

from lab.flex_native import Code


def current_pool(address):
    c = Code()
    c.imm("4eb9", 0x401988A2)
    c.emit("2f00")
    c.imm("4eb9", 0x40041D18)
    c.emit("588f 2040")
    c.imm("b1fc", 0)
    c.branch(7, "empty")
    c.emit("2250 22690028 2f08 4e91 588f")
    c.imm("0c80", 0)
    c.branch(7, "empty")
    c.imm("0680", 0x1D2)
    c.emit("4e75")
    c.label("empty")
    c.emit("7000 4e75")
    return c.finish(address)


def target(address, pool, lookup):
    """Return node in D0 and current project pool in D1, or D0=0."""
    c = Code()
    c.emit("4feffff4 48d70c04 246f0010")
    c.imm("4eb9", pool)
    c.emit("2640")
    c.imm("b7fc", 0)
    c.branch(7, "missing")
    c.emit("2f2a00a0")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f")
    c.imm("0c80", 15)
    c.branch(2, "missing")
    c.imm("223c", 0x450)
    c.emit("4c010800")
    c.imm("2079", 0x80004704)
    c.emit("d1c0 7200 122800d6")
    c.imm("0c81", 0)
    c.branch(6, "missing")
    c.emit("7000 30280080")
    c.imm("0c80", 1024)
    c.branch(4, "missing")
    c.emit("d080 d080 d080 d080")
    c.imm("43f9", 0x405B1368)
    c.emit("d3c0 2411 2002")
    c.imm("4eb9", lookup)
    c.emit("2008")
    c.branch(0, "done")
    c.label("missing")
    c.emit("7000")
    c.label("done")
    c.emit("220b 4cd70c04 4fef000c 4e75")
    return c.finish(address)


def push_dialog(address):
    """Consume one stock shared-control-block reference and push its view."""
    c = Code()
    c.emit("4feffff0 48d70404 246f0014")
    c.imm("b5fc", 0)
    c.branch(7, "failed")
    c.emit("41ea0010 2f480008 2f4a000c")
    c.emit("41ef0008 7000 2f00 2f08")
    c.imm("4eb9", 0x40198948)
    c.emit("2f00")
    c.imm("4eb9", 0x40031122)
    c.emit("4fef000c 2400 41ef000c 2f08")
    c.imm("4eb9", 0x40197A4A)
    c.emit("588f 2002")
    c.branch(0, "done")
    c.label("failed")
    c.emit("70ff")
    c.label("done")
    c.emit("4cd70404 4fef0010 4e75")
    return c.finish(address)


def message(address, push):
    """Open the stock message dialog for a static C string."""
    c = Code()
    c.emit("4feffff8 2f4a0000 246f000c 7000 2f400004")
    c.emit("41ef0004 2f0a 7000 2f00 2f00 2f00 2f08")
    c.imm("4eb9", 0x4019C08E)
    c.emit("4fef0014 2f2f0004")
    c.imm("4eb9", push)
    c.emit("588f 2457 4fef0008 4e75")
    return c.finish(address)


def manager(address):
    """Stock std::function manager ABI for an inline pair of borrowed pointers."""
    c = Code()
    c.emit("206f0004 226f0008 202f000c")
    c.imm("0c80", 2)
    c.branch(7, "copy")
    c.imm("0c80", 1)
    c.branch(7, "pointer")
    # Operation 0 queries RTTI; this private closure has no public target type.
    # Operation 3 destroys it; neither borrowed pointer owns an allocation.
    c.imm("0c80", 0)
    c.branch(6, "done")
    c.emit("7000 2080")
    c.branch(0, "done")
    c.label("copy")
    c.emit("20d9 20d9")
    c.branch(0, "done")
    c.label("pointer")
    c.emit("2089")
    c.label("done")
    c.emit("7000 4e75")
    return c.finish(address)


def open_name(address, manage, callback, push, title, initial):
    """Build the original filename editor, capture(node,pool), 60-char limit."""
    c = Code()
    # D2-D3/A2-A3, title/name strings, 16-byte function, allocator scratch.
    c.emit("4fefffd4 48d70c0c 264f 202b0030 27400018 202b0034 2740001c")
    c.imm("203c", manage)
    c.emit("27400020")
    c.imm("203c", callback)
    c.emit("27400024")
    c.imm("203c", 0xB0)
    c.emit("2f00")
    c.imm("4eb9", 0x4011E8F0)
    c.emit("588f 2440")
    c.imm("b5fc", 0)
    c.branch(7, "failed")
    c.emit("7001 25400004 25400008 41ea0010 2548000c 2608")
    c.imm("203c", 0x401EED80)
    c.emit("2480")
    for offset, text in ((0x10, title), (0x14, initial)):
        c.emit("41eb0028 2f08")
        c.imm("4879", text)
        c.emit(f"41eb{offset:04x} 2f08")
        c.imm("4eb9", 0x401E7A64)
        c.emit("4fef000c")
    c.emit("41eb0018 2f08 7000 2f00 703c 2f00 7000 2f00")
    c.emit("41eb0014 2f08 41eb0010 2f08 2f03")
    c.imm("4eb9", 0x40117990)
    c.emit("4fef001c")
    for offset in (0x10, 0x14):
        c.emit(f"41eb{offset:04x} 2f08")
        c.imm("4eb9", 0x401E5FB4)
        c.emit("588f")
    c.emit("2f0a")
    c.imm("4eb9", push)
    c.emit("588f")
    c.branch(0, "done")
    c.label("failed")
    c.emit("70ff")
    c.label("done")
    c.emit("4cd70c0c 4fef002c 4e75")
    return c.finish(address)


def promote(address, *, retire=0):
    """Promote only aliases of this take; retain unrelated temporary samples."""
    c = Code()
    c.emit("4feffff0 48d71c04 246f0014 266f0018 286f001c")
    c.emit("220b")
    c.imm("0681", 0x4000)
    c.label("slot")
    for base, mismatch in ((4, "cached"), (32, "next")):
        if base == 32:
            c.label("cached")
            c.emit("202a001c")
            c.imm("0c80", 1)
            c.branch(6, "next")
        for offset in range(0, 16, 4):
            c.emit(f"202a{base + offset:04x} 242b{offset:04x} b082")
            c.branch(6, mismatch)
        c.branch(0, "copy")
    c.label("copy")
    c.emit("204c 224b 22d8 22d8 22d8 22d8")
    c.label("next")
    c.emit("47eb0010 200b b081")
    c.branch(6, "slot")
    if retire:
        from lab.flex_retirement import mask

        mask(c)
    c.emit("204c 43ea0020 22d8 22d8 22d8 22d8 7001 2540001c")
    if retire:
        c.emit("46c1 2f0a")
        c.imm("4eb9", retire)
        c.emit("588f")
    c.emit("7000")
    c.emit("4cd71c04 4fef0010 4e75")
    return c.finish(address)


def write_named(address, pool, saver, promote_at, directory):
    """Write a new /recorded/name, then promote this node's references only."""
    c = Code()
    # Saved D2/A2-A4, new ref (16), 72-byte path, padding.
    c.emit("4fefff98 48d71c04 246f006c 266f0070 286f0074")
    c.imm("4eb9", pool)
    c.emit("220b b081")
    c.branch(6, "failed")
    # No leading space/dot, slash, backslash, control, non-ASCII or empty name.
    c.emit("7000 1014")
    c.imm("0c80", 33)
    c.branch(5, "failed")
    c.imm("0c80", 46)
    c.branch(7, "failed")
    c.emit("41ef0020")
    for word in (0x2F726563, 0x6F726465):
        c.imm("203c", word)
        c.emit("20c0")
    c.emit("7064 10c0 702f 10c0 7400")
    c.label("char")
    c.emit("7000 101c")
    c.imm("0c80", 0)
    c.branch(7, "terminated")
    c.imm("0c82", 60)
    c.branch(4, "failed")
    c.imm("0c80", 32)
    c.branch(5, "failed")
    c.imm("0c80", 126)
    c.branch(2, "failed")
    for character in (47, 92):
        c.imm("0c80", character)
        c.branch(7, "failed")
    c.emit("10c0")
    c.imm("0682", 1)
    c.branch(0, "char")
    c.label("terminated")
    c.emit("1080")
    c.imm("4879", directory)
    c.imm("4eb9", 0x40157192)
    c.emit("588f 41ef0010 2f08 41ef0024 2f08 2f0a")
    c.imm("4eb9", saver)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(6, "failed")
    c.emit("41ef0010 2f08 2f0b 2f0a")
    c.imm("4eb9", promote_at)
    c.emit("4fef000c")
    c.branch(0, "done")
    c.label("failed")
    c.emit("70ff")
    c.label("done")
    c.emit("4cd71c04 4fef0068 4e75")
    return c.finish(address)


def named_callback(
    address, writer, show_message, success, failure, *, success_callback=0
):
    c = Code()
    c.emit("206f0008 2f10 206f0008 2f280004 2f10")
    c.imm("4eb9", writer)
    c.emit("4fef000c")
    c.imm("0c80", 0)
    c.branch(6, "failed")
    if success_callback:
        c.imm("4ef9", success_callback)
    else:
        c.imm("4879", success)
        c.branch(0, "show")
    c.label("failed")
    c.imm("4879", failure)
    c.label("show")
    c.imm("4eb9", show_message)
    c.emit("588f 4e75")
    return c.finish(address)


def recorder_keys(
    address, target_at, open_at, show_message, missing, use_first, fallback
):
    """Consume FUNC+RECORD only in this recorder view; preserve other events."""
    c = Code()
    c.emit("4feffff4 48d70c04 246f0010 266f0014 202b000c")
    c.imm("0c80", 0x13)
    c.branch(6, "stock")
    c.emit("202b0010 7202 c081")
    c.imm("0c80", 2)
    c.branch(6, "stock")
    c.emit("202b0010 7209 c081")
    c.imm("0c80", 1)
    c.branch(6, "consumed")
    c.imm("4eb9", 0x4019988A)
    c.emit("2f00")
    c.imm("4eb9", 0x40015F6C)
    c.emit("588f")
    c.imm("0c80", 4)
    c.branch(7, "use_first")
    c.imm("0c80", 0)
    c.branch(6, "consumed")
    c.emit("2f0a")
    c.imm("4eb9", target_at)
    c.emit("588f")
    c.imm("0c80", 0)
    c.branch(7, "missing")
    c.emit("2f01 2f00")
    c.imm("4eb9", open_at)
    c.emit("508f")
    c.branch(0, "consumed")
    c.label("use_first")
    c.imm("4879", use_first)
    c.branch(0, "show")
    c.label("missing")
    c.imm("4879", missing)
    c.label("show")
    c.imm("4eb9", show_message)
    c.emit("588f")
    c.label("consumed")
    c.emit("7001 4cd70c04 4fef000c 4e75")
    c.label("stock")
    c.emit("4cd70c04 4fef000c")
    c.imm("4ef9", fallback)
    return c.finish(address)
