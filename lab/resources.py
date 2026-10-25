"""Deterministic placement and exclusive ownership checks, independent of a mod."""

from dataclasses import dataclass

from lab.project import require


class PaddingAllocator:
    """Best fit with stable input-order ties and optional branch reach limits."""

    def __init__(self, regions):
        self.gaps = [list(region) for region in regions]
        require(all(0 <= lo < hi for lo, hi in self.gaps), "Invalid allocation region")
        ordered = sorted(self.gaps)
        require(
            all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:], strict=False)),
            "Overlapping allocation regions",
        )
        self.allocations = {}

    def allocate(self, name, size, *, alignment=4, near=(), reach=None):
        require(
            name not in self.allocations and size > 0, "Invalid or duplicate payload"
        )
        require(alignment > 0 and not alignment & (alignment - 1), "Invalid alignment")
        starts = [(lo + alignment - 1) & -alignment for lo, _ in self.gaps]
        choices = [
            (hi - starts[i], i)
            for i, (_, hi) in enumerate(self.gaps)
            if hi - starts[i] >= size
            and (reach is None or all(abs(starts[i] - peer) < reach for peer in near))
        ]
        require(choices, f"Padding exhausted: {name}")
        _, index = min(choices)
        start = starts[index]
        self.gaps[index][0] = start + ((size + alignment - 1) & -alignment)
        self.allocations[name] = (start, start + size)
        return start


@dataclass(frozen=True)
class Region:
    owner: str
    space: str
    start: int
    end: int
    lifetime: str

    def __post_init__(self):
        require(
            self.space in ("cpu", "dsp-byte", "dsp-dm", "dsp-sw"),
            "Unknown address space",
        )
        require(
            bool(self.owner) and bool(self.lifetime) and 0 <= self.start < self.end,
            "Invalid region",
        )


def validate_regions(regions):
    for i, left in enumerate(regions):
        for right in regions[i + 1 :]:
            require(
                left.space != right.space
                or left.end <= right.start
                or right.end <= left.start,
                f"Resource overlap: {left.owner} / {right.owner} in {left.space}",
            )


def validate_names(claims):
    seen = {}
    for owner, names in claims:
        for name in names:
            require(
                name not in seen,
                f"Resource {name} claimed by {seen.get(name)} and {owner}",
            )
            seen[name] = owner
    return seen


def patch_conflicts(modules):
    """Report actual write intersections; metadata contains no firmware bytes."""
    conflicts = []
    for i, (name, writes) in enumerate(modules):
        for other, other_writes in modules[i + 1 :]:
            for left in writes:
                for right in other_writes:
                    lo = max(left["address"], right["address"])
                    hi = min(
                        left["address"] + len(bytes.fromhex(left["after"])),
                        right["address"] + len(bytes.fromhex(right["after"])),
                    )
                    if lo < hi:
                        conflicts.append(
                            dict(
                                owners=[name, other],
                                start=lo,
                                end=hi,
                                labels=[left["label"], right["label"]],
                            )
                        )
    return conflicts
