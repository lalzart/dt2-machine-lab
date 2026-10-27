"""Pinned author release-default STRETCH engine, composed with Plaits R3.

Original sources stay byte exact. Generated overlays change only static addresses,
our existing CAPI transport/feedback seam, and the STRETCH call site (OS 1.16).
"""

# ruff: noqa: I001 -- initialize the pinned runtime before deferred tool imports

import json
import os
import re
import shutil
import struct
import subprocess
import sys

from lab.capicola_layout import STATE_BASE, address
from lab.capicola_memory import BANK_BASE, BANK_END
from lab.project import ROOT, require, sha256, write_json

SOURCE = ROOT / "machines/capicola-reddit/upstream"
VOICE_BASE = 0x200E0000
VOICE_BYTES = 32 * 0x400
RING_BASE = (BANK_BASE + 15) & ~15
RING_BYTES = 32 * 0x5000
HOT_BASE = 0x2D7570
HOT_END = 0x2DF000
COLD_BASE = 0x200A0000
COLD_END = VOICE_BASE
FLAGS = [
    "-DCC_F32",
    "-DCC_ALIGN=8",
    "-DCC_LINK",
    "-DCC_CLEAN",
    "-DGEN_BLEND_FIXED=0.0f",
    "-DGEN_BLEND_ZERO",
    "-DGEN_WSOLA",
    "-DGEN_BUILD=0",
]


def validate_sources():
    lock = json.loads((SOURCE.parent / "source-manifest.json").read_text())
    for f in lock["files"]:
        require(
            sha256(SOURCE / f["path"]) == f["sha256"],
            "Author source drift: " + f["path"],
        )
    return lock


def replace_exact(text, before, after, count=1):
    require(text.count(before) == count, "Author overlay anchor drift: " + before)
    return text.replace(before, after)


def prepare(output, *, cold_base=COLD_BASE, cold_end=COLD_END):
    validate_sources()
    target = output / "source"
    shutil.copytree(SOURCE / "capicola_c99", target / "capicola_c99")
    sharc = target / "capicola_c99/sharc"
    require(COLD_BASE <= cold_base < cold_end <= COLD_END, "Cold code placement bounds")
    require(not (cold_base | cold_end) & 3, "Cold code placement alignment")
    if (cold_base, cold_end) != (COLD_BASE, COLD_END):
        linker = sharc / "l1l2.ldf"
        linker.write_text(replace_exact(
            linker.read_text(),
            "START(0x200A0000) END(0x200DFFFF)",
            f"START({cold_base:#x}) END({cold_end - 1:#x})",
        ))
    p = sharc / "dt2gen.c"
    c = replace_exact(
        p.read_text(),
        "#define STATE_BASE 0x9e000000u",
        f"#define STATE_BASE {RING_BASE:#x}u",
    )
    c = replace_exact(
        c,
        "#define VOICE_STATE(v) (0x20080000u +",
        f"#define VOICE_STATE(v) ({VOICE_BASE:#x}u +",
    )
    c += '\n#include "lab_status.h"\n'
    p.write_text(c)
    (
        sharc / "lab_status.h"
    ).write_text(f"""/* Existing CPU status protocol; no preparation/cache or DSP algorithm changes. */
void lab_capi_status(void) {{
 unsigned *counter=(unsigned *){STATE_BASE + 0x24600:#x}u;
 unsigned track=(*counter)++ & 15u, cap=0, stock=0, state=0;
 if((*(volatile unsigned *)(0x255970u+track*2u)&65535u)==2u) {{
  unsigned raw=*(volatile unsigned *)(0x2559bau+track*0x60u)&65535u;
  unsigned on=raw>=128u && raw<=256u;
  for(unsigned lane=track*2u;lane<track*2u+2u;lane++) {{
   if(*(volatile unsigned char *)(0x2412ccu+lane*0x1d8u+0x1b8u)) {{
    if(on) cap=1; else stock=1;
   }}
  }}
  state=cap && stock ? 5u : cap ? 3u : stock ? 4u : 2u;
 }}
 unsigned page=*(volatile unsigned *)0x261ca4u&1u;
 *(volatile unsigned short *)(0x26623au+(page<<12))=(unsigned short)(0xd000u|(track<<8)|state);
}}
""")
    p = sharc / "render.asm"
    p.write_text(
        replace_exact(p.read_text(), "R3 = 0x20080000;", f"R3 = {VOICE_BASE:#x};")
    )
    # Read our established raw switch threshold. Keep R2=v and all call arguments.
    p = sharc / "dt2entry.asm"
    a = p.read_text()
    start = a.index("      R1 = 0xDC;")
    end = a.index("      CALL .pf;", start)
    a = (
        a[:start]
        + """      R1 = -1;
      R0 = LSHIFT R0 BY R1;
      R1 = 0x60;
      R0 = R0 * R1 (SSI);
      R1 = 0x2559BA;
      R0 = R0 + R1;
      I4 = R0;
      R0 = DM(0, I4);
      R1 = 65535;
      R0 = R0 AND R1;
      R1 = 128;
      COMP(R0, R1);
      IF LT JUMP .st_stock;
      R1 = 256;
      COMP(R0, R1);
      IF GT JUMP .st_stock;
"""
        + a[end:]
    )
    from lab.capicola_automatic import wrapper
    from lab.sharc_hooks import HOOKS

    h = HOOKS["maintenance"]
    w = wrapper(
        "lab_capi_frame",
        "lab_capi_status",
        h.scratch,
        h.stack,
        "",
        "BIT CLR MODE1 0x200000;\n",
        h.continuation,
    )
    w = re.sub(r"0x200[cde][0-9a-f]+", lambda m: hex(address(int(m[0], 16))), w)
    a += "\n.SECTION/SW seg_cold;\n" + w
    p.write_text(a)
    require(
        RING_BASE + RING_BYTES <= STATE_BASE < BANK_END, "Ring/Plaits state overlap"
    )
    return sharc


def command(args, *, env=None):
    return subprocess.check_output(
        [str(x) for x in args],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=180,
        env=env,
    )


def widen_adds(source):
    # Same semantics; this pinned DigiKit decoder lacks Selache's compact 2b ADD.
    return re.sub(
        r"(?m)^(\s*R\d+\s*=\s*R\d+\s*\+\s*R\d+;)([^\n]*)$",
        r".NOCOMPRESS;\n\1\2\n.COMPRESS;",
        source,
    )


def compile_author(output, *, cold_base=COLD_BASE, cold_end=COLD_END):
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    from lab.dsp_build import COMPILER, TOOLS
    from lab.runtime import SELACHE

    output.mkdir(parents=True, exist_ok=True)
    c = prepare(output, cold_base=cold_base, cold_end=cold_end)
    common = [
        "-proc",
        "ADSP-21569",
        "-char-size-8",
        "-I",
        SELACHE / "libsel/include",
        "-I",
        c.parent,
        *FLAGS,
        "-DCC_ASM",
        "-DCC_SOURCE_ONLY",
    ]
    logs = []
    logs.append(
        command([COMPILER, *common, "-S", c / "dt2gen.c", "-o", output / "release.s"])
    )
    logs.append(
        command(
            [
                "clang",
                "--target=i386-none-elf",
                "-ffreestanding",
                "-fsyntax-only",
                "-DGEN_LAYOUT_CHECK",
                "-I",
                SELACHE / "libsel/include",
                "-I",
                c.parent,
                *FLAGS,
                "-DCC_ASM",
                "-DCC_SOURCE_ONLY",
                c / "dt2gen.c",
            ]
        )
    )
    logs.append(
        command(
            [
                sys.executable,
                SOURCE / "tools/cold_split.py",
                output / "release.s",
                output / "split.s",
            ],
            env=dict(os.environ, WSOLA="1", BLEND_ZERO="1"),
        )
    )
    logs.append(
        command(
            [
                COMPILER,
                "-proc",
                "ADSP-21569",
                "-char-size-8",
                "-S",
                "-I",
                SELACHE / "libsel/include",
                "-DRT_NO_TANF",
                "-DRT_MEMSET_WORDS",
                c / "rt.c",
                "-o",
                output / "rt.s",
            ]
        )
    )
    logs.append(
        command(
            [
                sys.executable,
                SOURCE / "tools/labelcheck.py",
                c / "render.asm",
                c / "dt2entry.asm",
                c / "feed.asm",
            ]
        )
    )
    for name, path, flags in [
        ("release", output / "split.s", []),
        ("rt", output / "rt.s", []),
        ("render", c / "render.asm", [*FLAGS, "-DGEN_NO_DIAG"]),
        ("entry", c / "dt2entry.asm", [*FLAGS, "-DGEN_NO_DIAG"]),
        ("feed", c / "feed.asm", FLAGS),
    ]:
        widened = output / (name + "-wide.s")
        widened.write_text(widen_adds(path.read_text()))
        path = widened
        logs.append(
            command(
                [
                    TOOLS / "selas",
                    "-proc",
                    "ADSP-21569",
                    *flags,
                    "-o",
                    output / (name + ".doj"),
                    path,
                ]
            )
        )
    logs.append(
        command(
            [
                TOOLS / "seld",
                "-proc",
                "ADSP-21569",
                "-T",
                c / "l1l2.ldf",
                "-o",
                output / "author.dxe",
                *[
                    output / (s + ".doj")
                    for s in ["release", "rt", "render", "entry", "feed"]
                ],
            ]
        )
    )
    (output / "compile.log").write_text("\n".join(logs))
    listings = {}
    for section in ["code", "cold"]:
        listing = command([TOOLS / "seldump", "-ns", section, output / "author.dxe"])
        require(
            compare_listing(listing).all_extents_agree,
            "Author instruction extent disagreement",
        )
        listings[section] = listing
    listing = "\n".join(listings.values())
    (output / "listing.txt").write_text(listing)
    symbols = {
        n: int(pc, 16)
        for n, pc in re.findall(r"(?m)^([\w.]+):\n\s+([0-9a-f]+)", listing)
    }
    hot = swap_parcels(find_elf_section(output / "author.dxe", "code"))
    cold = swap_parcels(find_elf_section(output / "author.dxe", "cold"))
    elf = (output / "author.dxe").read_bytes()
    phoff = struct.unpack_from("<I", elf, 0x1C)[0]
    entsize, count = struct.unpack_from("<HH", elf, 0x2A)
    segments = [
        struct.unpack_from("<8I", elf, phoff + i * entsize) for i in range(count)
    ]
    loaded = [s for s in segments if s[0] == 1 and s[5]]
    require(
        len(loaded) == 2
        and all(
            s[2] in (HOT_BASE // 2, 0xBD0000 + (cold_base - COLD_BASE) // 2)
            and s[4] == s[5] for s in loaded
        ),
        "Unexpected author ELF segment",
    )
    require(len(hot) <= 0x2DE9B0 - HOT_BASE, "Hot code overlaps author scratch")
    require(len(cold) <= cold_end - cold_base, "Cold code overflow")
    return hot, cold, symbols


def build_blob(output, *, all_tracks=False):
    from lab.dsp_build import build_blob as plaits_blob
    from lab.sharc_tools import assemble, header
    import sharcldr

    output.mkdir(parents=True, exist_ok=True)
    base = plaits_blob(
        True, family="integration", layout="reserved-state", output=output, plaits_any_track=all_tracks
    )
    base_meta = json.loads((output / "build.json").read_text())
    require(
        base_meta["code_bytes"] < COLD_BASE - 0x20080000,
        "Plaits overlaps author cold code",
    )
    hot, cold, symbols = compile_author(output / "author")
    raw = bytearray(base)
    blocks = sharcldr.parse_blocks(raw)
    patches = []
    for site, before, after in [
        (
            0x1C6AF1,
            "CJUMP 0x1c5576 (DB);",
            f"CJUMP {symbols['cc_dt2_entry.']:#x} (DB);",
        ),
        (0x1C75A2, "BIT CLR MODE1 0x200000;", f"JUMP {symbols['lab_capi_frame.']:#x};"),
    ]:
        b = assemble(".SECTION/PM seg_pmco;\n" + before + "\n").boot_bytes
        a = assemble(".SECTION/PM seg_pmco;\n" + after + "\n").boot_bytes
        off = sharcldr.offset_for_address(blocks, site)
        require(
            raw[off : off + len(b)] == b and len(a) == len(b),
            f"Author hook guard {site:#x}",
        )
        raw[off : off + len(a)] = a
        patches.append(dict(site=site, before=b.hex(), after=a.hex()))
    # L1's boot-load alias normalizes to byte address HOT_BASE.
    segments = [
        (
            "author-hot-and-scratch",
            0x28000000 + HOT_BASE,
            hot + bytes(HOT_END - HOT_BASE - len(hot)),
        ),
        ("author-cold", COLD_BASE, cold + bytes(-len(cold) % 4)),
        ("author-voices", VOICE_BASE, bytes(VOICE_BYTES)),
        ("author-rings", RING_BASE, bytes(RING_BYTES)),
    ]
    memory = sharcldr.LoadedMemory.from_stream(base)

    def physical(at):
        return at - 0x28000000 if 0x28000000 <= at < 0x30000000 else at

    existing = [
        (physical(lo), physical(lo) + hi - lo)
        for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True)
    ]
    for name, at, payload in segments:
        norm = physical(at)
        require(
            not any(lo < norm + len(payload) and hi > norm for lo, hi in existing),
            "Loader overlap: " + name,
        )
    split = blocks[-1]["offset"]
    result = (
        bytes(raw[:split])
        + b"".join(
            header(at, len(data)) + data if any(data) else header(at, len(data), fill=0)
            for _, at, data in segments
        )
        + bytes(raw[split:])
    )
    require(
        sharcldr.parse_blocks(result)[-1]["payload_offset"] == len(result),
        "Author loader stream invalid",
    )
    (output / "PLAITS_BLOB.bin").write_bytes(result)
    metadata = dict(
        base_meta,
        runtime_variant="reddit-release",
        family="integration+reddit-stretch",
        author_source=validate_sources()["sha256"],
        author_hot_bytes=len(hot),
        author_cold_bytes=len(cold),
        zero_state_encoding="ADI FILL; identical final loaded memory",
        custom_code_bytes=base_meta["code_bytes"] + len(hot) + len(cold),
        total_added_arena_bytes=base_meta["arena_bytes"]
        + sum(len(d) for _, _, d in segments),
        patches=patches,
        symbols=symbols,
    )
    write_json(output / "build.json", metadata)
    write_json(
        output / "memory-layout.json",
        dict(
            layout="author-release+reserved-plaits",
            plaits_code_bytes=base_meta["code_bytes"],
            plaits_state=STATE_BASE,
            regions=[dict(name=n, start=a, bytes=len(d)) for n, a, d in segments],
            author_voice_state_bytes=VOICE_BYTES,
            author_ring_bytes=RING_BYTES,
            algorithms_changed=False,
            hardware_verified=False,
        ),
    )
    return result
