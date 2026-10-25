"""Original bounded UP control core emitted as audited ColdFire instructions.

Caller owns state and supplies the clock. No firmware code is copied here.
This is not a firmware packager or a claim about permanent device RAM.
"""
import struct

from lab.emit import Code

SIZE = 1600
STEP = 2_880_000
GATE = STEP // 2
UNITS_PER_SAMPLE = 408  # 102 BPM * four sixteenth notes per beat.
CAPACITY = 16
COUNTS, OWNERS, VELOCITIES = 64, 576, 1088
FIELDS = {
    "enabled": 0, "playing": 4, "tick": 8, "phase": 12,
    "gate": 16, "active": 20, "last": 24, "velocity": 28,
    "owned": 32, "held": 36, "off": 40, "on": 44,
    "on_velocity": 48, "flags": 52,
}


def get(c, field, reg=0):
    c.emit(f"{0x202a | reg << 9:04x}{FIELDS[field]:04x}")


def put(c, field, reg=0):
    c.emit(f"{0x2540 | reg:04x}{FIELDS[field]:04x}")


def constant(c, field, value):
    if -128 <= value <= 127:
        c.emit(f"{0x7000 | (value & 255):04x}")
    else:
        c.imm("203c", value)
    put(c, field)


def prefix(c):
    # D2-D7/A2-A4 saved; stack arguments begin at +40.
    c.emit("4fefffdc 48d71cfc 246f0028")


def result(c):
    get(c, "flags")
    c.emit("4cd71cfc 4fef0024 4e75")


def invalid(c):
    c.label("invalid")
    c.emit("70ff 4cd71cfc 4fef0024 4e75")


def pointer(c, offset, index=2):
    # A0 = &state.table[index]. Use register-long address arithmetic;
    # no 68000-only immediate-to-displacement MOVE or indexed extension.
    c.emit(f"41ea{offset:04x} {0x2000 | index:04x} d080 d080 d1c0")


def close_gate(c, label):
    get(c, "active")
    c.imm("0c80", -1)
    c.branch(7, label)
    put(c, "off")
    constant(c, "flags", 1)
    constant(c, "active", -1)
    constant(c, "gate", 0)
    c.label(label)


def clear_active(c, label):
    c.emit(f"41ea{COUNTS:04x} 7200")
    c.imm("203c", 128)
    c.label(label)
    c.emit("20c1 5380")
    c.branch(6, label)
    for field in ("held", "phase", "playing"):
        constant(c, field, 0)
    constant(c, "last", -1)


def initialize(address):
    """init(state, tick, enabled): overwrite exactly SIZE bytes."""
    c = Code(); prefix(c)
    c.emit("242f002c 262f0030")
    c.imm("0c83", 1); c.branch(2, "invalid")
    c.emit("204a 7200")
    c.imm("203c", SIZE // 4)
    c.label("zero"); c.emit("20c1 5380"); c.branch(6, "zero")
    put(c, "tick", 2); put(c, "enabled", 3)
    constant(c, "active", -1); constant(c, "last", -1)
    result(c); invalid(c)
    return c.finish(address)


def press(address):
    """press(state, pitch, velocity): accept at most 16 contributions."""
    c = Code(); prefix(c)
    c.emit("242f002c 262f0030")
    c.imm("0c82", 127); c.branch(2, "invalid")
    c.imm("0c83", 127); c.branch(2, "invalid")
    c.emit("4a83"); c.branch(7, "invalid")
    get(c, "enabled"); c.emit("4a80"); c.branch(7, "ignored")
    get(c, "owned"); c.imm("0c80", CAPACITY); c.branch(4, "invalid")
    c.emit("5280"); put(c, "owned")
    pointer(c, OWNERS); c.emit("2210"); c.imm("0681", 1); c.emit("2081")
    pointer(c, COUNTS); c.emit("2210"); c.imm("0681", 1); c.emit("2081")
    pointer(c, VELOCITIES); c.emit("2083")
    get(c, "held"); c.emit("4a80"); c.branch(6, "already-held")
    constant(c, "last", -1)
    c.label("already-held"); get(c, "held"); c.emit("5280"); put(c, "held")
    c.label("ignored"); constant(c, "flags", 0); result(c); invalid(c)
    return c.finish(address)


def release(address):
    """release(state, pitch): consume ownership even after Stop/disable."""
    c = Code(); prefix(c); c.emit("242f002c")
    c.imm("0c82", 127); c.branch(2, "invalid")
    constant(c, "flags", 0)
    pointer(c, OWNERS); c.emit("2210 4a81"); c.branch(7, "done")
    c.imm("0681", -1); c.emit("2081")
    get(c, "owned"); c.emit("5380"); put(c, "owned")
    pointer(c, COUNTS); c.emit("2210 4a81"); c.branch(7, "done")
    c.imm("0681", -1); c.emit("2081")
    # D3 retains remaining contributions at this pitch.
    c.emit("2601")
    get(c, "held"); c.emit("5380"); put(c, "held")
    c.emit("4a80"); c.branch(7, "last-release")
    c.emit("4a83"); c.branch(6, "done")
    get(c, "active"); c.emit("b082"); c.branch(6, "done")
    close_gate(c, "release-closed"); c.branch(0, "done")
    c.label("last-release"); close_gate(c, "last-closed")
    constant(c, "last", -1)
    c.label("done"); result(c); invalid(c)
    return c.finish(address)


def panic(address):
    """panic(state): release output, clear active set; keep input owners."""
    c = Code(); prefix(c); constant(c, "flags", 0)
    close_gate(c, "closed"); clear_active(c, "clear")
    result(c)
    return c.finish(address)


def mode(address):
    """mode(state, OFF=0/UP=1): disable flushes; reselecting UP is inert."""
    c = Code(); prefix(c); c.emit("242f002c")
    c.imm("0c82", 1); c.branch(2, "invalid")
    constant(c, "flags", 0)
    get(c, "enabled"); c.emit("b082"); c.branch(7, "done")
    close_gate(c, "closed"); clear_active(c, "clear"); put(c, "enabled", 2)
    c.label("done"); result(c); invalid(c)
    return c.finish(address)


def clock(address):
    """clock(state, sample_tick, playing): at most off+on; preserve phase."""
    c = Code(); prefix(c); c.emit("242f002c 262f0030")
    c.imm("0c83", 1); c.branch(2, "invalid")
    constant(c, "flags", 0)
    get(c, "tick", 1); c.emit("2002 9081")  # unsigned elapsed samples
    put(c, "tick", 2); c.emit("2a00")  # D5 = elapsed
    get(c, "enabled"); c.emit("4a80"); c.branch(7, "done")
    c.emit("4a83"); c.branch(6, "play")
    get(c, "playing"); c.emit("4a80"); c.branch(7, "done")
    c.branch(0, "flush")
    c.label("play"); get(c, "playing"); c.emit("4a80")
    c.branch(6, "running")
    constant(c, "playing", 1); constant(c, "phase", 0)
    c.branch(0, "done")
    c.label("running"); c.emit("2005"); c.imm("0c80", 48000)
    c.branch(2, "flush")
    c.imm("223c", UNITS_PER_SAMPLE); c.emit("4c010800 2a00")
    get(c, "active"); c.imm("0c80", -1); c.branch(7, "phase")
    get(c, "gate"); c.emit("2205 9081")
    c.branch(15, "gate-expired"); put(c, "gate"); c.branch(0, "phase")
    c.label("gate-expired"); close_gate(c, "gate-closed")
    c.label("phase")
    get(c, "phase", 1); c.emit("2005 2041 d1c0 2008")
    c.imm("0c80", STEP); c.branch(5, "store-phase")
    # Skip excess deadlines rather than emitting a late catch-up burst.
    c.label("modulo"); c.imm("0680", -STEP)
    c.imm("0c80", STEP); c.branch(4, "modulo")
    put(c, "phase")
    get(c, "held"); c.emit("4a80"); c.branch(7, "done")
    close_gate(c, "step-closed")
    get(c, "last", 2); c.imm("0682", 1)
    c.imm("263c", 128)
    c.label("scan"); c.imm("0c82", 128); c.branch(5, "in-range")
    c.emit("7400")
    c.label("in-range"); pointer(c, COUNTS); c.emit("2210 4a81")
    c.branch(6, "found")
    c.imm("0682", 1); c.imm("0683", -1); c.emit("4a83")
    c.branch(6, "scan"); c.branch(0, "flush")
    c.label("found")
    put(c, "last", 2); put(c, "active", 2); put(c, "on", 2)
    pointer(c, VELOCITIES); c.emit("2010")
    put(c, "velocity"); put(c, "on_velocity")
    constant(c, "gate", GATE)
    get(c, "flags"); c.imm("0080", 2); put(c, "flags")
    c.branch(0, "done")
    c.label("store-phase"); put(c, "phase"); c.branch(0, "done")
    c.label("flush"); close_gate(c, "panic-closed"); clear_active(c, "clear")
    c.label("done"); result(c); invalid(c)
    return c.finish(address)


GENERATORS = dict(init=initialize, press=press, release=release,
                  panic=panic, mode=mode, clock=clock)


def build(base=0x60000000):
    """Aligned separate routines, each smaller than its guarded 1 KiB slot."""
    rows = {}
    for i, (name, generator) in enumerate(GENERATORS.items()):
        address = base + i * 1024
        code = generator(address)
        if len(code) > 1024:
            raise ValueError("Native arp code exceeds its slot")
        rows[name] = (address, code)
    return rows


def commands(raw):
    """Decode a completed native result; never chooses or schedules a note."""
    flags = struct.unpack_from(">I", raw, FIELDS["flags"])[0]
    events = []
    if flags & 1:
        events.append(("off", struct.unpack_from(">I", raw, FIELDS["off"])[0], 0))
    if flags & 2:
        events.append(("on", struct.unpack_from(">I", raw, FIELDS["on"])[0],
                       struct.unpack_from(">I", raw, FIELDS["on_velocity"])[0]))
    return events
