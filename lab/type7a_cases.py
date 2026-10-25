"""Independent expected instruction states for the bounded Type7a extension."""

import random


def cases():
    result = []
    fields = {"w": 1, "l": 0, "g": 0, "cond[4:0]": 0,
              "is[2:2]": 1, "is[1:0]": 0, "m[2:0]": 4,
              "idis[2:0]": 0, "compute[22:16]": 0, "compute[15:0]": 0}
    regs = {f"{kind}{i}": (0x84230000 if kind in ("I", "B") else
                            4 if kind == "M" else 0)
            for kind in ("I", "M", "L", "B") for i in range(16)}
    regs.update(MODE1=0, ASTATX=1, ASTATY=0, R1=7, R2=5, R3=0x999)

    def add(name, *, f=None, r=None, writes=None, stop=None):
        initial = regs | (r or {})
        result.append(dict(name=name, fields=fields | (f or {}), regs=initial,
                           expected=initial | (writes or {}), stop=stop))

    add("eq-true", writes={"I4": 0x84230010})
    add("eq-false", r={"ASTATX": 0})
    add("ne-true", f={"cond[4:0]": 0x10}, r={"ASTATX": 0}, writes={"I4": 0x84230010})
    add("ne-false", f={"cond[4:0]": 0x10})
    for cond, bit in ((3, 3), (4, 1), (5, 7), (7, 11), (8, 12), (13, 18)):
        for flag in (0, 1):
            add(f"predicate-{cond}-{flag}", f={"cond[4:0]": cond},
                r={"ASTATX": flag << bit}, writes={"I4": 0x84230010} if flag else {})
    add("source-destination-alias", f={"idis[2:0]": 4}, writes={"I0": 0x84230010})
    add("dag-bank-two", f={"g": 1, "idis[2:0]": 4}, writes={"I8": 0x84230010})
    add("negative-modifier", r={"M4": 0xFFFFFFFF}, writes={"I4": 0x8422FFFC})
    add("plain-scale", f={"w": 0}, writes={"I4": 0x84230004})
    add("short-scale", f={"w": 0, "l": 1}, writes={"I4": 0x84230008})
    add("normal-word-space", r={"I4": 0xE0000}, writes={"I4": 0xE0004})
    add("circular-forward-cbufen-off", r={"L4": 16, "I4": 0x8423000C, "M4": 2},
        writes={"I4": 0x84230004})
    add("circular-backward", r={"L4": 16, "I4": 0x84230004, "M4": 0xFFFFFFFE},
        writes={"I4": 0x8423000C})
    add("circular-exact-length", r={"L4": 16, "I4": 0x84230004})
    add("circular-oversize", r={"L4": 16, "M4": 5},
        stop="circular modifier is not smaller")
    add("unknown-length", r={"L4": None}, stop="unsupported Type7a circular modify")
    add("unknown-predicate", r={"ASTATX": None}, stop="unknown Type7a SISD predicate")
    add("unknown-mode", r={"MODE1": None}, stop="unsupported Type7a conditional SIMD/mode")
    add("simd-rejected", r={"MODE1": 1 << 21}, stop="unsupported Type7a conditional SIMD/mode")
    # Full compute ALU add: R3 = R1 + R2. True EQ uses pre-compute AZ=1;
    # the add yields 12 and clears AZ. Both effects must still occur.
    compute = {"compute[15:0]": 0x1312}
    add("parallel-compute-true", f=compute, writes={"I4": 0x84230010, "R3": 12, "ASTATX": 0})
    add("parallel-compute-false", f=compute, r={"ASTATX": 0})
    invalid = {"compute[22:16]": 0x30, "compute[15:0]": 0x0312}
    add("invalid-compute-true", f=invalid, stop="unsupported full compute")
    add("skipped-invalid-operands", f=invalid, r={"ASTATX": 0, "L4": None})
    add("legacy-unconditional", f={"cond[4:0]": 31}, writes={"I4": 0x84230010})
    add("legacy-not-sv-true", f={"cond[4:0]": 23}, writes={"I4": 0x84230010})
    add("legacy-not-sv-false", f={"cond[4:0]": 23}, r={"ASTATX": 1 << 11})
    add("legacy-conditional-compute-stop", f=compute | {"cond[4:0]": 23},
        stop="unsupported Type7a conditional compute")
    rng = random.Random(0)
    for i in range(64):
        source, destination, modifier = rng.randrange(8), rng.randrange(8), rng.randrange(8)
        bank, mode, delta = rng.randrange(2), rng.randrange(3), rng.randint(-8, 8)
        cond, az = rng.choice((0, 16)), rng.randrange(2)
        index, scale = 0x84230100 + i * 64, (1, 2, 4)[mode]
        change = az == (1 if cond == 0 else 0)
        add(f"seed0-{i}", f={"w": int(mode == 2), "l": int(mode == 1), "g": bank,
             "is[2:2]": source >> 2, "is[1:0]": source & 3,
             "idis[2:0]": source ^ destination, "m[2:0]": modifier, "cond[4:0]": cond},
            r={f"I{source + bank * 8}": index,
               f"M{modifier + bank * 8}": delta & 0xFFFFFFFF, "ASTATX": az},
            writes={f"I{destination + bank * 8}": (index + delta * scale) & 0xFFFFFFFF}
            if change else {})
    return result


def state(case, trace):
    return trace.State(0x100, {trace.UREG_CODES[n]: trace.Const(v) if v is not None
                       else trace.Unknown("fixture") for n, v in case["regs"].items()},
                       assume_nw32=True)


def check(case, actual, trace, *, reason=True):
    """Check all supplied registers, flags and progress against explicit values."""
    for name, expected in case["expected"].items():
        value = actual.uregs[trace.UREG_CODES[name]]
        if expected is None:
            assert isinstance(value, trace.Unknown), (case["name"], name, value)
        else:
            assert value == trace.Const(expected), (case["name"], name, value, expected)
    if case["stop"]:
        assert actual.stopped, case["name"]
        if reason:
            assert case["stop"] in actual.stopped, (case["name"], actual.stopped)
        assert actual.pc_sw == 0x100
    else:
        assert actual.stopped is None, (case["name"], actual.stopped)
        assert actual.pc_sw == 0x103
