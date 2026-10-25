"""Typed SHARC hook contracts and shared ABI context generation for OS1.16."""

from dataclasses import dataclass

from lab.project import require

REGS = tuple(f"{kind}{i}" for kind in ("R", "I", "M", "L") for i in range(16))


@dataclass(frozen=True)
class Address:
    value: int
    space: str

    def in_space(self, space):
        require(self.space == space, f"Expected {space}, got {self.space}")
        return self.value


@dataclass(frozen=True)
class Hook:
    name: str
    site: Address
    continuation: Address
    scratch: Address
    stack: Address
    context: str
    frames: int | None = None
    sample_rate: int | None = None

    def __post_init__(self):
        self.site.in_space("dsp-sw")
        self.continuation.in_space("dsp-sw")
        self.scratch.in_space("dsp-byte")
        self.stack.in_space("dsp-byte")
        require(
            self.context in ("voice", "maintenance", "sample-event"),
            "Unknown hook context",
        )


def hook(name, site, resume, scratch, stack, context, frames=None, rate=None):
    return Hook(
        name,
        Address(site, "dsp-sw"),
        Address(resume, "dsp-sw"),
        Address(scratch, "dsp-byte"),
        Address(stack, "dsp-byte"),
        context,
        frames,
        rate,
    )


HOOKS = {
    "source": hook(
        "source", 0x1C4F15, 0x1C4F18, 0x200E0800, 0x200DFF00, "voice", 64, 96000
    ),
    "stretch": hook(
        "stretch", 0x1C6AEE, 0x1C6AF1, 0x200E0800, 0x200DFF00, "voice", 32, 48000
    ),
    "maintenance": hook(
        "maintenance", 0x1C75A2, 0x1C75A5, 0x200E0A00, 0x200DBF00, "maintenance"
    ),
    "sample-page": hook(
        "sample-page", 0x1C403C, 0x1C4040, 0x200E0C00, 0x200D9F00, "sample-event"
    ),
    "sample-guard": hook(
        "sample-guard", 0x1C400F, 0x1C4014, 0x200E0C00, 0x200D9F00, "sample-event"
    ),
    "sample-header": hook(
        "sample-header", 0x1C3FE5, 0x1C3FE8, 0x200E0C00, 0x200D9F00, "sample-event"
    ),
}


def context_stores(scratch):
    return f"DM({hex(scratch)})=R0;\n" + "".join(
        f"R0={reg}; DM({hex(scratch + i * 4)})=R0;\n"
        for i, reg in enumerate(REGS[1:], 1)
    )


def context_restores(scratch):
    return "".join(
        f"R0=DM({hex(scratch + i * 4)}); {reg}=R0;\n"
        for i, reg in reversed(list(enumerate(REGS[1:], 1)))
    )


def validate_preemption(hooks):
    """The sample callback can interrupt either audio context; it may not alias."""
    for event in (h for h in hooks if h.context == "sample-event"):
        for audio in (h for h in hooks if h.context != "sample-event"):
            require(
                abs(event.scratch.value - audio.scratch.value) >= 256,
                "Preempting hook scratch overlaps",
            )
            require(
                event.stack.value != audio.stack.value, "Preempting hook stack aliases"
            )
    return hooks


validate_preemption(tuple(HOOKS.values()))
