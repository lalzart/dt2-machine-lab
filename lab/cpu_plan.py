"""Relocate native payloads without pretending DDR is part of the stored image."""

from lab.coldfire import audit_code
from lab.dt2_116 import BASE
from lab.project import require


class Namespace:
    def __init__(self, allocator, owner):
        self.allocator, self.owner = allocator, owner
        self.allocations = {}

    def allocate(self, name, size, **options):
        start = self.allocator.allocate(self.owner + "/" + name, size, **options)
        self.allocations[name] = (start, start + size)
        return start


class NativePlan:
    """Stock writes have exact guards; payload writes must own an allocation."""

    def __init__(self, image, allocator):
        self.image, self.allocator = bytes(image), allocator
        self.writes = []
        self.metadata = {}

    def put(self, address, before, after, label, kind, *, payload=False):
        require(len(before) == len(after) and len(after) > 0, "Invalid patch size")
        end = address + len(after)
        if payload:
            require(
                (address, end) in self.allocator.allocations.values(),
                "Payload does not own its allocation: " + label,
            )
            require(not any(before), "Payload guard must be zero")
        if not payload or BASE <= address < BASE + len(self.image):
            off = address - BASE
            require(
                off >= 0
                and off + len(before) <= len(self.image)
                and self.image[off : off + len(before)] == before,
                "Native byte guard: " + label,
            )
        require(
            all(
                end <= w["address"]
                or address >= w["address"] + len(bytes.fromhex(w["after"]))
                for w in self.writes
            ),
            "Overlapping native write: " + label,
        )
        decoded = audit_code(after, address) if kind == "code" else []
        if kind == "stock-trampoline":
            require(after[-6:-4] == b"\x4e\xf9", "Invalid stock trampoline tail")
            audit_code(after[-6:], end - 6)
        self.writes.append(
            dict(
                address=address,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind=kind,
                payload=payload,
                instructions=decoded,
            )
        )

    def apply(self):
        data = bytearray(self.image)
        for w in self.writes:
            off = w["address"] - BASE
            code = bytes.fromhex(w["after"])
            require(
                off >= 0 and off + len(code) <= len(data),
                "External payload requires the extension loader",
            )
            data[off : off + len(code)] = code
        return bytes(data)
