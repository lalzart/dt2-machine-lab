"""Guarded quality source generation, preserving the independently frozen core."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from lab.capicola_quality import STRETCH_SHA, prepare, transform
from lab.project import ROOT


class QualityOverlayTests(unittest.TestCase):
    def test_only_the_reviewed_splice_anchors_change(self):
        source = (ROOT / "machines/capicola/stretch.c").read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), STRETCH_SHA)
        changed = transform(source).decode()
        self.assertIn("quality_front(s)", changed)
        self.assertIn("quality_duration(s,duration)", changed)
        self.assertIn("quality_phase_step(c->increment,c->pitch)", changed)
        self.assertNotIn("if(duration>960.0f)", changed)
        with self.assertRaises(ValueError):
            transform(source + b"\n")

    def test_overlay_preserves_all_other_compiled_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "out/runs") as temp:
            out = prepare(Path(temp) / "overlay")
            changes = []
            for p in (out / "machines").rglob("*"):
                if (
                    p.is_file()
                    and p.read_bytes() != (ROOT / p.relative_to(out)).read_bytes()
                ):
                    changes.append(str(p.relative_to(out)))
            self.assertEqual(changes, ["machines/capicola/stretch.c"])
