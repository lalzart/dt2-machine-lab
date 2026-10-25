"""Native OS 1.16 Flex name -> project RAM bank -> save transaction.

The original slot stays valid for inactive patterns/locks. A different bank
gets a new stock-loaded alias; only the captured live track changes slot. No
unproven project-wide reference rewriting or old-slot reclamation is attempted.
All UI, validation, loading and saving below execute as ColdFire instructions.
"""

from lab.emit import Code
from lab.flex_native import sample_machine_guard

LOADED, LENGTHS, LIVE_KIT = 0x405B1368, 0x405BA768, 0x80004704
# Borrowed immutable node/pool, captured assignment, UI phase, bounded filename.
NODE, POOL, KIT, TRACK, ORIGINAL, BANK, PHASE, NAME = range(0, 32, 4)
STATE_BYTES = NAME + 64


def _reference(c, left, right, failed):
    """Compare all four identity words at address registers left/right."""
    for offset in range(0, 16, 4):
        c.emit(f"202{left}{offset:04x} 222{right}{offset:04x} b081")
        c.branch(6, failed)


def _slot(c, register, base):
    """D0 slot -> register address, stride 16; D0 is scratch."""
    c.emit("d080 d080 d080 d080")
    c.imm({"8": "41f9", "9": "43f9"}[register], base)
    c.emit({"8": "d1c0", "9": "d3c0"}[register])


def validate(address, pool, lookup):
    """int validate(flow*): exact live project, kit, track and sample identity."""
    c = Code()
    c.emit("4feffff4 48d70c04 246f0010 266a0000")
    c.imm("b7fc", 0)
    c.branch(7, "invalid")
    c.imm("4eb9", pool)
    c.emit("222a0004 b081 4a80")
    c.branch(7, "invalid")
    c.emit("b081")
    c.branch(6, "invalid")
    c.emit("202b0004")
    c.imm("4eb9", lookup)
    c.emit("2008 220b b081")
    c.branch(6, "invalid")
    for offset in (28, 56):
        c.emit(f"202b{offset:04x} 4a80")
        c.branch(6, "invalid")
    c.emit("202b0014 4a80")
    c.branch(7, "invalid")
    c.imm("2039", LIVE_KIT)
    c.emit("222a0008 b081")
    c.branch(6, "invalid")
    c.emit("202a000c")
    c.imm("0c80", 15)
    c.branch(2, "invalid")
    c.imm("223c", 0x450)
    c.emit("4c010800 206a0008 d1c0 7000 30280080 222a0010 b081")
    c.branch(6, "invalid")
    c.emit("7000 102800d6")
    sample_machine_guard(c, extended=True)
    c.emit("202a0010")
    c.imm("0c80", 1023)
    c.branch(2, "invalid")
    c.emit("727f c081")
    c.branch(7, "invalid")
    c.emit("202a0010 d080 d080")
    c.imm("41f9", LENGTHS)
    c.emit("d1c0 2010 4a80")
    c.branch(7, "invalid")
    c.emit("202a0010")
    _slot(c, "8", LOADED)
    c.emit("43eb0004")
    _reference(c, "8", "9", "invalid")
    c.emit("202a0010 d080 d080 d080 d080 206a0004 d1c0")
    _reference(c, "8", "9", "invalid")
    c.emit("7000")
    c.branch(0, "done")
    c.label("invalid")
    c.emit("70ff")
    c.label("done")
    c.emit("4cd70c04 4fef000c 4e75")
    return c.finish(address)


def find_slot(address):
    """int find(flow*): keep original in its bank, else first truly empty slot.

    Caller validates the flow. All eight reserved OFF slots are skipped, and
    both project ownership and CPU loader identity/length must be empty.
    """
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 202a0014")
    c.imm("0c80", 7)
    c.branch(2, "full")
    c.emit("222a0010 ee89 b081")
    c.branch(7, "original")
    c.imm("223c", 128)
    c.emit("4c010800 2400")
    c.imm("0682", 1)
    c.emit("2602")
    c.imm("0683", 127)
    c.label("slot")
    c.emit("2002 d080 d080")
    c.imm("41f9", LENGTHS)
    c.emit("d1c0 2010 4a80")
    c.branch(6, "next")
    c.emit("2002")
    _slot(c, "8", LOADED)
    c.emit("2010")
    c.imm("0c80", -1)
    c.branch(6, "next")
    c.emit("2002 d080 d080 d080 d080 206a0004 d1c0 2010")
    c.imm("0c80", -1)
    c.branch(7, "found")
    c.label("next")
    c.imm("0682", 1)
    c.emit("2002 b083")
    c.branch(5, "slot")
    c.label("full")
    c.emit("70ff")
    c.branch(0, "done")
    c.label("original")
    c.emit("242a0010")
    c.label("found")
    c.emit("2002")
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(address)


def begin(address, state, valid, open_name, message, failure):
    """begin(node,pool,recorder_view): capture the exact live assignment."""
    c = Code()
    c.emit("4feffff8 48d70404")
    c.imm("45f9", state)
    c.emit("7000 25400018 202f000c 25400000 202f0010 25400004")
    c.imm("2039", LIVE_KIT)
    c.emit("25400008 206f0014 2f2800a0")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f 2540000c")
    c.imm("0c80", 15)
    c.branch(2, "failed")
    c.imm("223c", 0x450)
    c.emit("4c010800 206a0008 d1c0 7000 30280080 25400010 2200 ee89 25410014")
    c.emit("2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "failed")
    c.emit("2f2a0004 2f2a0000")
    c.imm("4eb9", open_name)
    c.emit("508f")
    c.branch(0, "done")
    c.label("failed")
    c.imm("4879", failure)
    c.imm("4eb9", message)
    c.emit("588f 70ff")
    c.label("done")
    c.emit("4cd70404 508f 4e75")
    return c.finish(address)


def capture_name(address, state, valid):
    """Stock name-editor closure callback; stage a bounded name, never save yet."""
    c = Code()
    c.emit("4feffff8 48d70404")
    c.imm("45f9", state)
    c.emit("206f000c 2010 222a0000 b081")
    c.branch(6, "done")
    c.emit("20280004 222a0004 b081")
    c.branch(6, "done")
    c.emit("2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "done")
    c.emit("206f0010 2050 43ea001c 7400")
    c.label("character")
    c.emit("7000 1018 12c0 4a80")
    c.branch(7, "ready")
    c.imm("0682", 1)
    c.imm("0c82", 61)
    c.branch(5, "character")
    c.branch(0, "done")
    c.label("ready")
    c.emit("7001 25400018")
    c.label("done")
    c.emit("7000 4cd70404 508f 4e75")
    return c.finish(address)


def active(address, state, valid):
    """active(view): invalidate a bank page after track/project/assignment change."""
    c = Code()
    c.emit("4feffff8 48d70404")
    c.imm("45f9", state)
    c.emit("202a0018")
    c.imm("0c80", 1)
    c.branch(6, "inactive")
    c.emit("206f000c 2f2800a0")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f 222a000c b081")
    c.branch(6, "reset")
    c.emit("2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "reset")
    c.emit("7001")
    c.branch(0, "done")
    c.label("reset")
    c.emit("7000 25400018")
    c.label("inactive")
    c.emit("7000")
    c.label("done")
    c.emit("4cd70404 508f 4e75")
    return c.finish(address)


def commit(address, valid, find, prepare, promote, *, pool):
    """int commit(flow*): load candidate, write, validate again, then publish.

    -2 means full bank. Failed loading/writing never changes project/track or
    retires the source. The candidate loader slot is unloaded on rollback.
    The original slot and its durable promoted reference remain valid.
    """
    c = Code()
    # D2-D4/A2-A5, prepared reference at SP+32 (16 bytes).
    c.emit("4fefffd0 48d73c1c 246f0034 7400 2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "failed")
    c.emit("2f0a")
    c.imm("4eb9", find)
    c.emit("588f 2600")
    c.imm("0c80", -1)
    c.branch(7, "full")
    c.emit("202a0010 b083")
    c.branch(7, "prepare")
    c.emit("266a0000 2f03 41eb0004 2f08")
    c.imm("4eb9", 0x40154540)
    c.emit("508f 7401 4a80")
    c.branch(6, "rollback")
    c.label("prepare")
    c.emit("2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "rollback")
    # Match stock assignment's readiness guard even if a loader reports
    # success without leaving a playable sample, or yields to slot teardown.
    c.emit("2003 d080 d080")
    c.imm("41f9", LENGTHS)
    c.emit("d1c0 2010 4a80")
    c.branch(7, "rollback")
    c.emit("41ef0020 2f08 41ea001c 2f08 2f2a0004 2f2a0000")
    c.imm("4eb9", prepare)
    c.emit("4fef0010 4a80")
    c.branch(6, "rollback")
    # Native save/loader calls can yield: recheck captured ownership afterwards.
    c.emit("2f0a")
    c.imm("4eb9", valid)
    c.emit("588f 4a80")
    c.branch(6, "rollback")
    c.emit("2003 d080 d080")
    c.imm("41f9", LENGTHS)
    c.emit("d1c0 2010 4a80")
    c.branch(7, "rollback")
    c.emit("2003")
    _slot(c, "8", LOADED)
    c.emit("266a0000 43eb0004")
    _reference(c, "8", "9", "rollback")
    c.emit("2003 d080 d080 d080 d080 286a0004 d9c0 4a82")
    c.branch(7, "publish")
    c.emit("2014")
    c.imm("0c80", -1)
    c.branch(6, "rollback")
    c.label("publish")
    c.emit("41ef0020 224c 22d8 22d8 22d8 22d8")
    c.emit("202a000c")
    c.imm("223c", 0x450)
    c.emit("4c010800 286a0008 d9c0 39430080 2f2a000c 41ec0034 2f08")
    c.imm("4eb9", 0x4002D438)
    c.emit("508f 41ef0020 2f08 2f2a0004 2f2a0000")
    c.imm("4eb9", promote)
    c.emit("4fef000c 7000 25400018 2003")
    c.branch(0, "done")
    c.label("rollback")
    c.emit("4a82")
    c.branch(7, "failed")
    # A project change transfers the loader table to stock ownership. Do not
    # unload anything from the replacement project, even if an ID matches.
    c.imm("4eb9", pool)
    c.emit("222a0004 b081")
    c.branch(6, "failed")
    # Never clear a different owner's slot after a re-entrant stock operation.
    c.emit("2003")
    _slot(c, "8", LOADED)
    c.emit("266a0000 43eb0004")
    _reference(c, "8", "9", "failed")
    c.emit("2003 d080 d080 d080 d080 206a0004 d1c0 2010")
    c.imm("0c80", -1)
    c.branch(6, "failed")
    c.emit("2f03")
    c.imm("4eb9", 0x401540C6)
    c.imm("4eb9", 0x40153BEA)
    c.emit("588f")
    c.label("failed")
    c.emit("70ff")
    c.branch(0, "done")
    c.label("full")
    c.emit("70fe")
    c.label("done")
    c.emit("4cd73c1c 4fef0030 4e75")
    return c.finish(address)


def keys(address, state, active_at, commit_at, message, strings, buffer):
    """keys(view,event): ordinary LEFT/RIGHT bank choice; YES save, NO back."""
    c = Code()
    c.emit("4feffff4 48d70c04 246f0010 266f0014 2f0a")
    c.imm("4eb9", active_at)
    c.emit("588f 4a80")
    c.branch(7, "inactive")
    c.emit("202b000c")
    # Let stock page/track navigation continue, discarding only the open dialog.
    for key in (1, 2, 3, 4, 5, 6, 16, 20, 21):
        c.imm("0c80", key)
        c.branch(7, "leave")
    c.imm("0c80", 25)
    c.branch(5, "button")
    c.imm("0c80", 40)
    c.branch(3, "leave")
    c.label("button")
    c.emit("202b0010")
    c.imm("0280", 27)
    c.imm("0c80", 16)
    c.branch(6, "consumed")
    c.imm("45f9", state)
    c.emit("202b000c")
    for key, label in (
        (10, "save"),
        (13, "left"),
        (15, "right"),
        (12, "back"),
        (50, "back"),
    ):
        c.imm("0c80", key)
        c.branch(7, label)
    c.branch(0, "consumed")
    c.label("left")
    c.emit("202a0014")
    c.imm("0680", 7)
    c.branch(0, "bank")
    c.label("right")
    c.emit("202a0014 5280")
    c.label("bank")
    c.imm("0280", 7)
    c.emit("25400014")
    c.branch(0, "consumed")
    c.label("back")
    c.emit("7000 25400018")
    c.branch(0, "consumed")
    c.label("save")
    c.emit("2f0a")
    c.imm("4eb9", commit_at)
    c.emit("588f")
    c.imm("0c80", -2)
    c.branch(7, "full")
    c.imm("0c80", -1)
    c.branch(7, "failed")
    c.emit("2200")
    c.imm("0280", 127)
    c.emit("2f00 ee89")
    c.imm("0681", ord("A"))
    c.emit("2f01")
    c.imm("4879", strings["bank_success"])
    c.imm("4879", buffer)
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef0010")
    c.imm("4879", buffer)
    c.branch(0, "show")
    c.label("full")
    c.imm("4879", strings["bank_full_message"])
    c.branch(0, "show")
    c.label("failed")
    c.imm("4879", strings["bank_failure"])
    c.label("show")
    c.imm("4eb9", message)
    c.emit("588f")
    c.branch(0, "consumed")
    c.label("leave")
    c.imm("41f9", state)
    c.emit("7000 21400018")
    c.label("inactive")
    c.emit("7000")
    c.branch(0, "done")
    c.label("consumed")
    c.emit("7001")
    c.label("done")
    c.emit("4cd70c04 4fef000c 4e75")
    return c.finish(address)


def draw(address, state, active_at, find, strings):
    """draw(view,raster): native framebuffer, familiar bank letters and slot."""
    from lab.flex_save_screen import FONT, TEXT

    c = Code()
    # D2/A2-A4 plus 32-byte text scratch at SP+16.
    c.emit("4fefffd0 48d71c04 246f0034 266f0038 2f0a")
    c.imm("4eb9", active_at)
    c.emit("588f 4a80")
    c.branch(7, "inactive")
    c.imm("45f9", state)
    c.emit("49ef0010")

    def rect(x0, y0, x1, y1, colour=1):
        for value in (colour, y1, x1, y0, x0):
            c.imm("4879", value)
        c.emit("2f0b")
        c.imm("4eb9", 0x40112ECE)
        c.emit("4fef0018")

    def text(name, x, y):
        if name is None:
            c.emit("2f0c")
        else:
            c.imm("4879", strings[name])
        for value in (0x20, y, x, FONT):
            c.imm("4879", value)
        c.emit("2f0b")
        c.imm("4eb9", TEXT)
        c.emit("4fef0018")

    rect(0, 0, 127, 63, 0)
    text("bank_title", 4, 54)
    rect(3, 49, 124, 49)
    c.emit("41ea001c 2f08")
    c.imm("4879", strings["bank_name_format"])
    c.emit("2f0c")
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef000c")
    text(None, 4, 40)
    text("bank_label", 4, 29)
    text("bank_letters", 32, 16)
    # Stock FONT advances four pixels per character; bank letters are eight
    # pixels apart including their separating space. Keep the box aligned.
    for dx0, y0, dx1, y1 in (
        (0, 13, 7, 13),
        (0, 22, 7, 22),
        (0, 13, 0, 22),
        (7, 13, 7, 22),
    ):
        c.emit("202a0014")
        c.imm("223c", 8)
        c.emit("4c010800")
        c.imm("0680", 30 + dx1)
        c.imm("4879", 1)
        c.imm("4879", y1)
        c.emit("2f00")
        c.imm("4879", y0)
        c.emit("202a0014")
        c.imm("223c", 8)
        c.emit("4c010800")
        c.imm("0680", 30 + dx0)
        c.emit("2f00 2f0b")
        c.imm("4eb9", 0x40112ECE)
        c.emit("4fef0018")
    c.emit("2f0a")
    c.imm("4eb9", find)
    c.emit("588f")
    c.imm("0c80", -1)
    c.branch(7, "full")
    c.emit("2200")
    c.imm("0280", 127)
    c.emit("2f00 ee89")
    c.imm("0681", ord("A"))
    c.emit("2f01")
    c.imm("4879", strings["bank_slot_format"])
    c.emit("2f0c")
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef0010")
    text(None, 4, 2)
    c.branch(0, "footer")
    c.label("full")
    text("bank_full", 4, 2)
    c.label("footer")
    text("bank_footer", 52, 2)
    c.emit("7001")
    c.branch(0, "done")
    c.label("inactive")
    c.emit("7000")
    c.label("done")
    c.emit("4cd71c04 4fef0030 4e75")
    return c.finish(address)


def payload(at):
    from lab import flex_native_save as named

    result = {
        name: (value.encode("ascii") + b"\0", "data")
        for name, value in {
            "bank_title": "SAVE TO +DRIVE",
            "bank_label": "PROJECT RAM BANK",
            "bank_letters": "A B C D E F G H",
            "bank_name_format": "%.20s",
            "bank_slot_format": "%c%03u",
            "bank_footer": "Y:SAVE N:BACK",
            "bank_full": "FULL",
            "bank_full_message": "RAM BANK FULL\nCHOOSE ANOTHER BANK",
            "bank_success": "FLEX SAMPLE SAVED\nPROJECT RAM: %c%03u",
            "bank_failure": "FLEX: SAVE FAILED\nTAKE KEPT IN RAM",
        }.items()
    }
    result["bank_state"] = (bytes(STATE_BYTES), "data")
    result["bank_message_buffer"] = (bytes(64), "data")
    result["bank_validate"] = (
        validate(at("bank_validate"), at("save_pool"), at("lookup")),
        "code",
    )
    result["bank_find"] = (find_slot(at("bank_find")), "code")
    result["bank_begin"] = (
        begin(
            at("bank_begin"),
            at("bank_state"),
            at("bank_validate"),
            at("save_open"),
            at("save_message"),
            at("bank_failure"),
        ),
        "code",
    )
    result["save_callback"] = (
        capture_name(at("save_callback"), at("bank_state"), at("bank_validate")),
        "code",
    )
    result["bank_active"] = (
        active(at("bank_active"), at("bank_state"), at("bank_validate")),
        "code",
    )
    result["bank_prepare"] = (
        named.write_named(
            at("bank_prepare"),
            at("save_pool"),
            at("save"),
            0,
            at("directory"),
            prepare_only=True,
        ),
        "code",
    )
    result["bank_commit"] = (
        commit(
            at("bank_commit"),
            at("bank_validate"),
            at("bank_find"),
            at("bank_prepare"),
            at("save_promote"),
            pool=at("save_pool"),
        ),
        "code",
    )
    strings = {name: at(name) for name in result}
    result["bank_keys"] = (
        keys(
            at("bank_keys"),
            at("bank_state"),
            at("bank_active"),
            at("bank_commit"),
            at("save_message"),
            strings,
            at("bank_message_buffer"),
        ),
        "code",
    )
    result["bank_draw"] = (
        draw(
            at("bank_draw"),
            at("bank_state"),
            at("bank_active"),
            at("bank_find"),
            strings,
        ),
        "code",
    )
    return result
