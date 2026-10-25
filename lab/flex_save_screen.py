"""Opt-in native OS 1.16 save screen over the existing recorder view.

Identity and saved status belong to the accepted take. The original recorder
draws again after successful persistence or explicit discard. No host UI or DSP substitution.
"""

from lab.emit import Code

DRAW = 0x40021DE0
DRAW_PREFIX = bytes.fromhex("4fefffb848d77cfc")
MANUAL = 0x40015FDA
ARM = 0x40015F9C
TEXT = 0x40113AE8
FONT = 0x44D2E70C


def pending(address, target):
    """Same object argument as target; return unsaved node/pool or zero."""
    c = Code()
    c.emit("2f2f0004")
    c.imm("4eb9", target)
    c.emit("588f 4a80")
    c.branch(7, "done")
    c.emit("2040 22680038")
    c.imm("b3fc", 0)
    c.branch(6, "missing")
    c.emit("2268001c")
    c.imm("b3fc", 1)
    c.branch(6, "done")
    c.label("missing")
    c.emit("7000")
    c.label("done")
    c.emit("4e75")
    return c.finish(address)


def context(address, pending_at, state):
    """Selection belongs to this take/pool, never a sticky track-global dialog."""
    c = Code()
    c.emit("2f02 2f2f0008")
    c.imm("4eb9", pending_at)
    c.emit("588f")
    c.imm("41f9", state)
    c.emit("2410 b480")
    c.branch(6, "reset")
    c.emit("24280004 b481")
    c.branch(7, "done")
    c.label("reset")
    c.emit("2080 21410004 7400 21420008")
    c.label("done")
    c.emit("241f 4e75")
    return c.finish(address)


def keys(
    address,
    pending_at,
    open_name,
    fallback,
    *,
    state,
    discard_at,
    message,
    success,
    failure,
    bank_keys=0,
    bank_begin=0,
):
    """UP/DOWN selects, YES acts on release, NO goes back."""
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 266f0018 2f0a")
    c.imm("4eb9", pending_at)
    c.emit("588f 2400 4a80")
    c.branch(7, "stock")
    if bank_keys:
        c.emit("2f01 2f0b 2f0a")
        c.imm("4eb9", bank_keys)
        c.emit("508f 221f 4a80")
        c.branch(6, "consumed")
    c.emit("202b000c")
    for key in (20, 21, 16):
        c.imm("0c80", key)
        c.branch(7, "stock")
    c.imm("0c80", 6)
    c.branch(3, "stock")
    c.imm("0c80", 25)
    c.branch(5, "action")
    c.imm("0c80", 40)
    c.branch(3, "stock")
    c.label("action")
    c.emit("262b0010 2003")
    c.imm("0280", 27)
    c.imm("0c80", 16)
    c.branch(6, "consumed")
    c.imm("41f9", state)
    c.emit("202b000c")
    for key, label in (
        (10, "yes"),
        (11, "up"),
        (14, "down"),
        (12, "back"),
        (50, "back"),
    ):
        c.imm("0c80", key)
        c.branch(7, label)
    c.branch(0, "consumed")
    c.label("up")
    c.emit("7000 21400008")
    c.branch(0, "consumed")
    c.label("down")
    c.emit("7001 21400008")
    c.branch(0, "consumed")
    c.label("yes")
    c.emit("20280008 4a80")
    c.branch(7, "save")
    c.label("discard")
    c.emit("2f01 2f02")
    c.imm("4eb9", discard_at)
    c.emit("508f 2400")
    c.imm("41f9", state)
    c.emit("7000 21400008 4a82")
    c.branch(6, "failed")
    c.imm("4879", success)
    c.branch(0, "show")
    c.label("failed")
    c.imm("4879", failure)
    c.label("show")
    c.imm("4eb9", message)
    c.emit("588f")
    c.branch(0, "consumed")
    c.label("save")
    if bank_begin:
        c.emit("2f0a")
    c.emit("2f01 2f02")
    c.imm("4eb9", bank_begin or open_name)
    c.emit("4fef000c" if bank_begin else "508f")
    c.branch(0, "consumed")
    c.label("back")
    c.emit("7000 2080 2f0a")
    c.imm("4eb9", 0x4011AEEA)
    c.emit("588f")
    c.label("consumed")
    c.emit("7001 4cd70c0c 4fef0010 4e75")
    c.label("stock")
    c.emit("4cd70c0c 4fef0010")
    c.imm("4ef9", fallback)
    return c.finish(address)


def draw(address, pending_at, fallback, strings, state, *, bank_draw=0):
    """Stock raster/text, original waveform icon and aligned action menu."""
    c = Code()
    c.emit("4fefffc0 48d71c0c 246f0044 266f0048 2f0a")
    c.imm("4eb9", pending_at)
    c.emit("588f 4a80")
    c.branch(7, "stock")
    if bank_draw:
        c.emit("2f0b 2f0a")
        c.imm("4eb9", bank_draw)
        c.emit("508f 4a80")
        c.branch(6, "selected_done")
    c.emit("2f2a00a0")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f 5280 49ef0020 2f00")
    c.imm("4879", strings["screen_title"])
    c.emit("2f0c")
    c.imm("4eb9", 0x40000E82)
    c.emit("4fef000c")

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
    # Original sample waveform: compact, symmetrical bars, no borrowed asset.
    for i, height in enumerate((1, 3, 7, 3, 11, 5, 1)):
        rect(4 + i * 2, 57 - height // 2, 4 + i * 2, 57 + height // 2)
    text(None, 24, 54)
    rect(3, 49, 124, 49)
    text("screen_status", 4, 40)
    text("screen_yes", 13, 29)
    text("screen_discard", 13, 16)
    text("screen_nav", 4, 2)
    c.imm("41f9", state)
    c.emit("20280008 4a80")
    c.branch(6, "discard_selected")
    # Four thin edges avoid relying on an undocumented text inversion flag.
    for box, label in (
        ((2, 25, 125, 33), "selected_done"),
        ((2, 12, 125, 20), "discard_selected"),
    ):
        if label == "discard_selected":
            c.branch(0, "selected_done")
            c.label(label)
        x0, y0, x1, y1 = box
        for coords in (
            (x0, y0, x1, y0),
            (x0, y1, x1, y1),
            (x0, y0, x0, y1),
            (x1, y0, x1, y1),
        ):
            rect(*coords)
    c.label("selected_done")
    c.emit("4cd71c0c 4fef0040 4e75")
    c.label("stock")
    c.emit("4cd71c0c 4fef0040")
    c.imm("4ef9", fallback)
    return c.finish(address)


def start_guard(address, pending_at, original, mode):
    """Controller argument; refuse manual/armed recording of an unsaved track."""
    c = Code()
    c.emit("2f2f0004")
    c.imm("4eb9", pending_at)
    c.emit("588f 4a80")
    c.branch(7, "stock")
    c.emit("7000 4e75")
    c.label("stock")
    c.emit(f"487800{mode:02x} 206f0008")
    c.imm("4ef9", original + 8)
    return c.finish(address)


def payload(at):
    from lab import flex_native_save as named

    result = {
        name: (text.encode("ascii") + b"\0", "data")
        for name, text in {
            "screen_title": "FLEX TAKE  T%02u",
            "screen_status": "IN RAM / UNSAVED",
            "screen_discard": "DISCARD TAKE",
            "screen_nav": "YES:OK  NO:BACK",
            "discard_success": "FLEX TAKE DISCARDED",
            "discard_failure": "TAKE BUSY OR CHANGED\nPLEASE TRY AGAIN",
            "screen_yes": "SAVE TO +DRIVE",
        }.items()
    }
    result["screen_state"] = (bytes(12), "data")
    result["screen_context"] = (
        context(at("screen_context"), at("screen_pending"), at("screen_state")),
        "code",
    )
    from lab.flex_discard import discard

    result["screen_discard_take"] = (
        discard(
            at("screen_discard_take"),
            at("save_pool"),
            at("lookup"),
            at("abort_source"),
            at("state"),
        ),
        "code",
    )
    result["screen_start_target"] = (
        named.target(
            at("screen_start_target"),
            at("save_pool"),
            at("lookup"),
            sample_machines=True,
            settings_offset=0x10,
        ),
        "code",
    )
    result["screen_track_target"] = (
        named.target(
            at("screen_track_target"),
            at("save_pool"),
            at("lookup"),
            sample_machines=True,
            direct_track=True,
        ),
        "code",
    )
    for name, target_at in (
        ("screen_pending", at("save_target")),
        ("screen_start_pending", at("screen_start_target")),
        ("screen_track_pending", at("screen_track_target")),
    ):
        result[name] = (pending(at(name), target_at), "code")
    result["screen_draw_trampoline"] = (
        DRAW_PREFIX + bytes.fromhex("4ef9") + (DRAW + 8).to_bytes(4, "big"),
        "stock-trampoline",
    )
    result["screen_draw"] = (
        draw(
            at("screen_draw"),
            at("screen_context"),
            at("screen_draw_trampoline"),
            {name: at(name) for name in result},
            at("screen_state"),
            bank_draw=at("bank_draw") or 1,
        ),
        "code",
    )
    result["screen_manual"] = (
        start_guard(at("screen_manual"), at("screen_start_pending"), MANUAL, 2),
        "code",
    )
    result["screen_arm"] = (
        start_guard(at("screen_arm"), at("screen_start_pending"), ARM, 1),
        "code",
    )
    return result
