"""Explicit immutable paths for a build; importing this module has no run effects."""

from dataclasses import dataclass
from pathlib import Path

from lab.project import ROOT, read_json, require, settings


@dataclass(frozen=True)
class BuildContext:
    root: Path
    output: Path
    digikit: Path
    selache: Path
    fixture: Path

    @classmethod
    def configured(cls, output):
        output = Path(output).absolute()
        require(output.is_dir(), "Create a fresh build run before loading its context")
        require(
            output.is_relative_to(ROOT / "out/runs"),
            "Build output must be under out/runs",
        )
        config = settings()
        return cls(
            ROOT, output, config["digikit"], config["selache"], config["fixture"]
        )

    @property
    def profile(self):
        return read_json(self.root / "profiles/dt2-1.16/profile.json")

    @property
    def stock_main(self):
        return self.fixture / "sections/section_3_MAIN_OS.bin"

    @property
    def stock_blob(self):
        return self.fixture / "sections/section_7_BLOB.bin"
