"""Source runtime must preserve existing experiments and reject baseline drift."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.capicola_source import prepare
from lab.project import ROOT, sha256


class SourceRuntimeTests(unittest.TestCase):
    def test_source_generation_preserves_every_other_compiled_input(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temp:
            out = prepare(Path(temp) / "source")
            changed = {
                str(p.relative_to(out))
                for p in (out / "machines").rglob("*")
                if p.is_file()
                and p.read_bytes() != (ROOT / p.relative_to(out)).read_bytes()
            }
            self.assertEqual(
                changed,
                {
                    "machines/capicola/live.c",
                    "machines/capicola/cache.h",
                    "machines/plaits-capicola-stretch-live/machine.c",
                    "machines/plaits-capicola-stretch-toggle/machine.c",
                },
            )

    def test_unknown_original_reader_fails_before_generation(self):
        def changed(path):
            return (
                "0" * 64
                if path == ROOT / "machines/capicola/stretch.c"
                else sha256(path)
            )

        with (
            tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temp,
            patch("lab.capicola_source.sha256", side_effect=changed),
            self.assertRaisesRegex(ValueError, "baseline drift"),
        ):
            prepare(Path(temp) / "source")
