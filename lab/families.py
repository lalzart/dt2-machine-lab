"""Declared DSP build features; historical family names remain stable."""

from dataclasses import dataclass

GROUPS = {
    "controls": frozenset(
        (
            "controls",
            "integration",
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "integration": frozenset(
        (
            "integration",
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "capicola": frozenset(
        (
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "trio_tables": frozenset(
        (
            "trio",
            "bank",
            "controls",
            "integration",
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "bank_tables": frozenset(
        (
            "bank",
            "controls",
            "integration",
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "automatic": frozenset(
        (
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "stretch": frozenset(
        (
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "known": frozenset(
        (
            "va",
            "trio",
            "bank",
            "controls",
            "integration",
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
            "capicola-stretch",
            "capicola-stretch-multi",
            "capicola-stretch-live",
            "capicola-stretch-toggle",
        )
    ),
    "live": frozenset(("capicola-stretch-live", "capicola-stretch-toggle")),
    "extra_selector": frozenset(
        (
            "capicola",
            "capicola-prep",
            "capicola-owned",
            "capicola-auto",
            "capicola-controls",
            "capicola-selection",
            "capicola-feedback",
            "capicola-live-feedback",
        )
    ),
}


@dataclass(frozen=True)
class FamilySpec:
    name: str

    def has(self, feature):
        return self.name in GROUPS[feature]


def family_spec(name):
    if name not in GROUPS["known"]:
        raise ValueError(f"Unknown DSP family: {name}")
    return FamilySpec(name)
