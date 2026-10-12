"""Matched, explicitly adapted STRETCH controls for resource experiments."""

import struct

from lab.project import require
from lab.resource_workloads import EVENTS


def put(wire, offset, value):
    wire[offset : offset + 2] = value.to_bytes(2, "big")


def controls(template, tracks, *, fast=False, mixed=False):
    require(tracks in (0, 1, 4, 16), "Unsupported track count")
    require(len(template) >= 0xDA + 16 * 0x60, "Incomplete 16-track wire")
    wire = bytearray(template)
    for offset in EVENTS:
        put(wire, offset, 0)
    params = bytes(wire[0xDA:0x13A])
    for track in range(16):
        put(wire, 0x94 + track * 2, 2 if track < tracks else 0)
        put(wire, 2 + track * 2, 60 * 256)
        put(wire, 0x34 + track * 2, 100 * 256)
        base = 0xDA + track * 0x60
        wire[base : base + 0x60] = params
        tune = 16384 + ((track % 3) - 1) * 3072 if mixed else 19456 if fast else 16384
        play = (256, 512)[track % 2] if mixed else 512
        bars = (track % 4) * 256 if mixed else 0 if fast else 512
        for offset, value in (
            (0, tune),
            (2, play),
            (4, 0),
            (6, 7),
            (12, 0),
            (14, 30720),
            (16, bars),
            (18, 25600),
        ):
            put(wire, base + offset, value)
    return bytes(wire)


def measured_frames(wire, tracks, count, *, trigger):
    require(8 <= count <= 256 and 0 <= tracks <= 16, "Replay outside bounds")
    first = bytearray(wire)
    if trigger:
        put(first, 0x22, (1 << tracks) - 1)
    return [bytes(first)] + [wire] * (count - 1)


def pcm_extent(raw):
    require(raw and len(raw) % 4100 == 0, "Malformed LP0 capture")
    pages = [struct.unpack_from("<I", raw, pos)[0] for pos in range(0, len(raw), 4100)]
    pages = [p for p in pages if p < 0x19200]
    require(pages, "No PCM pages")
    extent = (max(pages) + 2) * 4096 + 1024
    require(extent <= 16 * 1024 * 1024, "PCM allocation bound")
    return extent
