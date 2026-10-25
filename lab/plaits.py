"""Compatibility exports for the shared DSP builder and Plaits CPU adapter."""

from lab.dsp_build import (
    COMPILER,
    MACHINE,
    TOOLS,
    build_blob,
    checked_trio_tables,
    command,
    compile_target,
)
from lab.plaits_cpu import build_cpu

__all__ = [
    "COMPILER",
    "MACHINE",
    "TOOLS",
    "build_blob",
    "build_cpu",
    "checked_trio_tables",
    "command",
    "compile_target",
]
