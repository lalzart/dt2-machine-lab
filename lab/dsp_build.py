"""Shared DSP compilation, guarded loader patching and family build specifications."""

import hashlib
import json
import re
import struct
import subprocess

from lab import capicola_layout
from lab.context import BuildContext
from lab.families import family_spec
from lab.runtime import ROOT, SELACHE, STOCK_BLOB
from lab.sharc_hooks import HOOKS, context_restores, context_stores
from lab.sharc_tools import assemble, header

MACHINE = ROOT / "machines/plaits-va"
COMPILER = ROOT / "out/cache/selache-c99/release/selcc"
TOOLS = SELACHE / "target/release"


def build_context(output=None):
    if output is None:
        from lab.runtime import OUT

        output = OUT
    output.mkdir(parents=True, exist_ok=True)
    return BuildContext.configured(output)


def command(args):
    return subprocess.check_output([str(a) for a in args], text=True, timeout=120)


def checked_trio_tables(assembly, source):
    """Repair the pinned compiler's integer negation of float array literals.

    Accept only the exact IEEE bits or the observed negated-positive-bit bug;
    never guess a correction for other output. Host source stays upstream exact.
    """
    for name, body in re.findall(
        r"static const float (\w+)\[\] = \{(.*?)\};", source.read_text(), re.S
    ):
        values = [float(v.strip()) for v in body.split(",") if v.strip()]
        pattern = r"\.VAR " + name + r"\. = [^;]+;(?:\n\.VAR = [^;]+;)*"
        match = re.search(pattern, assembly)
        if not match:
            raise ValueError(f"Missing emitted table: {name}")
        emitted = re.findall(r"= (0x[0-9A-Fa-f]+);", match[0])
        if len(emitted) != len(values):
            raise ValueError(f"Unexpected table extent: {name}")
        corrected = []
        for value, word in zip(values, emitted, strict=True):
            expected = struct.unpack("<I", struct.pack("<f", value))[0]
            buggy = (-(expected & 0x7FFFFFFF)) & 0xFFFFFFFF
            if int(word, 16) != expected and not (value < 0 and int(word, 16) == buggy):
                raise ValueError(f"Unexpected emitted value in {name}: {word}")
            corrected.append(f"0x{expected:08X}")
        replacement = f".VAR {name}. = {corrected[0]};" + "".join(
            f"\n.VAR = {word};" for word in corrected[1:]
        )
        assembly = assembly[: match.start()] + replacement + assembly[match.end() :]
    return assembly


def compile_target(
    integrated=False,
    *,
    variant="reference",
    output=None,
    family="va",
    layout="legacy",
    runtime_variant="reference",
    plaits_any_track=False,
):
    """No dependencies edited; inspect actual emitted/linked instruction extents."""
    from sharc_selache import compare_listing, find_elf_section, swap_parcels

    spec = family_spec(family)
    if runtime_variant not in (
        "reference",
        "trace-off",
        "cached",
        "cached-trace-off",
        "quality",
        "source",
    ):
        raise ValueError("Unknown runtime variant")
    if runtime_variant != "reference" and not spec.has("live"):
        raise ValueError("Runtime specialization requires live STRETCH")
    capicola_layout.validate_layout(layout, integrated, family)
    if variant not in ("reference", "main-only", "shared"):
        raise ValueError(f"Unknown Plaits variant: {variant}")
    if variant == "shared" and not integrated:
        raise ValueError("Lane sharing requires the firmware wrapper")
    if not spec.has("known") or (family != "va" and variant != "reference"):
        raise ValueError("Unknown family or unsupported multi-model optimization")
    out = build_context(output).output
    out.mkdir(parents=True, exist_ok=True)

    if not COMPILER.is_file():
        command(
            [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                SELACHE / "Cargo.toml",
                "--target-dir",
                ROOT / "out/cache/selache-c99",
                "-p",
                "selcc",
            ]
        )
    if spec.has("controls"):
        from lab.plaits_controls import validate_sources

        validate_sources()
    if spec.has("integration"):
        from lab.plaits_integration import validate_sources as validate_integration

        validate_integration()
    if spec.has("capicola"):
        contract = (
            "stretch-live-contract"
            if spec.has("live")
            else "stretch-multi-contract"
            if family == "capicola-stretch-multi"
            else "integration-contract"
        )
        lock = json.loads(
            (
                ROOT / "machines/capicola" / contract / "source-equivalence.json"
            ).read_text()
        )
        for relative, digest in lock["integration_baseline_files"].items():
            # These CPU-only tools are not inputs to the SHARC compiler. Their
            # newer Flex experiments must not block a frozen DSP comparison.
            # CPU overlays separately enforce exact MAIN image SHA/byte guards.
            if relative in (
                "lab/flex_native.py",
                "lab/flex_native_build.py",
                "lab/plaits_menu.py",
            ):
                continue
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Capicola integration baseline drift: {relative}")
    if spec.has("capicola") and not integrated:
        raise ValueError("Capicola family requires the combined voice wrapper")
    machine = ROOT / ("machines/plaits-" + family)
    source = machine / ("machine.c" if integrated else "target.c")
    if plaits_any_track:
        if not (integrated and family == "integration" and layout == "reserved-state"):
            raise ValueError("Any-track Plaits requires reserved integration")
        source = ROOT / "machines/plaits-any-track/machine.c"
    if runtime_variant == "quality":
        from lab.capicola_quality import prepare

        overlay = prepare(out / "quality-source")
        source = overlay / source.relative_to(ROOT)
    if runtime_variant == "source":
        from lab.capicola_source import prepare

        overlay = prepare(out / "source-playback")
        source = overlay / source.relative_to(ROOT)
    if variant != "reference" or runtime_variant != "reference":
        # A translation unit keeps compiler-specific -D handling out of this
        # experiment. The default source and build path remain the reference.
        defines = "#define PLAITS_MAIN_ONLY 1\n" if variant != "reference" else ""
        if "cached" in runtime_variant:
            defines += "#define CAP_CACHED_MAINTENANCE 1\n"
        if "trace-off" in runtime_variant:
            defines += "#define CAP_DISABLE_TRACE 1\n"
        if variant == "shared":
            defines += "#define PLAITS_SHARE_LANES 1\n"
        unit = out / "variant.c"
        unit.write_text(defines + f'#include "{source}"\n')
        source = unit
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            out / "kernel-original.s",
            source,
        ]
    )
    assembly = (out / "kernel-original.s").read_text()
    if spec.has("trio_tables"):
        assembly = checked_trio_tables(assembly, ROOT / "machines/plaits-trio/tables.h")
    if spec.has("bank_tables"):
        assembly = checked_trio_tables(assembly, ROOT / "machines/plaits-bank/tables.h")
    # Full-width RFRAME is not emitted correctly by the current assembler.
    # Only expand the known problematic stand-alone integer ADD instructions.
    assembly = re.sub(
        r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly
    )
    if layout == "reserved-state":
        assembly = capicola_layout.relocate_assembly(
            assembly,
            "kernel",
            family=family,
            trace="trace-off" not in runtime_variant,
            cached="cached" in runtime_variant,
        )
    (out / "kernel.s").write_text(assembly)
    wrapper = ".SECTION/PM seg_pmco;\n.GLOBAL start;\n"
    if integrated:
        wrapper += ".EXTERN machine.;\nstart:\nDM(-5,I6)=R0;\n"
        # Preserve the enclosing stock function's register context. A private
        # stack avoids depending on its local-frame capacity and C compiler ABI.
        # DM absolute stores accept universal registers through an R temporary.
        wrapper += context_stores(HOOKS["source"].scratch.in_space("dsp-byte"))
        wrapper += f"R4=I4;\nM5=0; M6=1; M7=-1; M14=1; L0=0; L1=0; L2=0; L3=0; L4=0; L5=0; L6=0; L7=0; L8=0; L9=0; L10=0; L11=0; L12=0; L13=0; L14=0; L15=0;\nI7={HOOKS['source'].stack.in_space('dsp-byte'):#x}; I6=I7; R2=I6;\nCJUMP machine. (DB);\nDM(I7,M7)=R2; DM(I7,M7)=returned-1;\nreturned:\nDM(0x200e0900)=R0;\n"
        wrapper += context_restores(HOOKS["source"].scratch.in_space("dsp-byte"))
        wrapper += f"R0=DM(0x200e0900); R1=0; COMP(R0,R1); IF EQ JUMP stock;\nR1=DM(0x200e0804); R0=DM(0x200e0800); JUMP 0x1c524a;\nstock:\nR1=DM(0x200e0804); R0=DM(0x200e0800);\nNOP; NOP; NOP;\nJUMP {HOOKS['source'].continuation.in_space('dsp-sw'):#x};\n"
    else:
        wrapper += (
            ".EXTERN kernel.;\nstart:\nM5=0; M6=1; M7=-1; M13=0; M14=1; M15=-1;\n"
        )
        wrapper += " ".join(f"L{i}=0;" for i in range(8))
        wrapper += "\nI7=0x200dff00; I6=I7; R4=0x200e0000;\nJUMP kernel. (DB);\nDM(I7,M7)=0; DM(I7,M7)=done-1;\ndone: RTS;\n"
    if spec.has("automatic"):
        from lab.capicola_automatic import assembly_wrappers

        wrapper += assembly_wrappers()
    if spec.has("stretch"):
        from lab.capicola_stretch import assembly_wrapper

        wrapper += assembly_wrapper()
    if layout == "reserved-state":
        wrapper = capicola_layout.relocate_assembly(wrapper, "wrapper", family=family)
    (out / "wrapper.s").write_text(wrapper)
    (out / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x20080000) END(0x200bffff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200c0000) END(0x200cffff) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(start)
 SECTIONS {
  code SW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco seg_l1_block0_swco seg_l1_block1_swco seg_l2_swco)) } > code
  data BW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) } > data
 }
}
""")
    if layout == "reserved-state":
        linker = out / "memory.ldf"
        linker.write_text(
            linker.read_text().replace(
                "START(0x200c0000) END(0x200cffff)",
                f"START({capicola_layout.STATE_BASE:#x}) END({capicola_layout.STATE_BASE + 0xFFFF:#x})",
            )
        )
    for stem in ("wrapper", "kernel"):
        command(
            [
                TOOLS / "selas",
                "-proc",
                "ADSP-21569",
                "-o",
                out / f"{stem}.doj",
                out / f"{stem}.s",
            ]
        )
    command(
        [
            TOOLS / "seld",
            "-proc",
            "ADSP-21569",
            "-T",
            out / "memory.ldf",
            "-o",
            out / "plaits.dxe",
            out / "wrapper.doj",
            out / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", out / "plaits.dxe"])
    (out / "listing.txt").write_text(listing)
    if not compare_listing(listing).all_extents_agree:
        raise ValueError("Plaits linked instruction width disagreement")
    code = swap_parcels(find_elf_section(out / "plaits.dxe", "code"))
    data = find_elf_section(out / "plaits.dxe", "data")
    return code, data


def build_blob(
    integrated=False,
    *,
    variant="reference",
    output=None,
    family="va",
    layout="legacy",
    runtime_variant="reference",
    plaits_any_track=False,
):
    import sharcldr

    from lab.runtime import PROFILE

    spec = family_spec(family)
    if runtime_variant not in (
        "reference",
        "trace-off",
        "cached",
        "cached-trace-off",
        "quality",
        "source",
    ):
        raise ValueError("Unknown runtime variant")
    if runtime_variant != "reference" and not spec.has("live"):
        raise ValueError("Runtime specialization requires live STRETCH")
    out = build_context(output).output
    code, data = compile_target(
        integrated,
        variant=variant,
        output=out,
        family=family,
        layout=layout,
        runtime_variant=runtime_variant,
        plaits_any_track=plaits_any_track,
    )
    if (
        family == "capicola-stretch-toggle"
        or runtime_variant != "reference"
        or (family == "integration" and layout == "reserved-state")
    ):
        # The byte-wide L2 loader is packed into 32-bit words by the native
        # core. Preserve a final short instruction by completing its word.
        # Older compile families retain their independently frozen images.
        code += bytes(-len(code) % 4)
    raw = bytearray(STOCK_BLOB.read_bytes())
    if hashlib.sha256(raw).hexdigest() != PROFILE["stock_blob_sha256"]:
        raise ValueError("Unexpected stock DSP image")
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in zip(memory._segments[0], memory._segments[1], strict=True):
        if lo < 0x200F2000 and hi > 0x20080000:
            raise ValueError("Experimental arena overlaps a stock loader segment")
    if layout == "reserved-state":
        capicola_layout.check_stock_disjoint(
            zip(memory._segments[0], memory._segments[1], strict=True)
        )
    if integrated:
        hook = sharcldr.offset_for_address(
            blocks, HOOKS["source"].site.in_space("dsp-sw")
        )
        displaced = bytes(raw[hook : hook + 6])
        if displaced.hex() != "5499a801408c":
            raise ValueError("Unexpected voice hook bytes")
        tail = assemble(
            f".section/pm seg_pmco;\nJUMP {HOOKS['source'].continuation.in_space('dsp-sw'):#x};\n"
        ).boot_bytes
        marker = bytes.fromhex("010001000100") + tail
        if code.count(marker) != 1:
            raise ValueError("Expected exactly one stock fallback placeholder")
        code = code.replace(marker, displaced + tail)
        raw[hook : hook + 6] = assemble(
            ".section/pm seg_pmco;\nJUMP 0xbc0000;\n"
        ).boot_bytes
        offset = sharcldr.offset_for_address(blocks, 0x1C2731)
        expected = assemble(".section/pm seg_pmco;\nI3=0x2567c0;\n").boot_bytes
        if raw[offset : offset + 6] != expected:
            raise ValueError("Unexpected remap pointer bytes")
        remap_address = (
            capicola_layout.address(0x200F0000)
            if layout == "reserved-state"
            else 0x200F0000
        )
        raw[offset : offset + 6] = assemble(
            f".section/pm seg_pmco;\nI3={remap_address:#x};\n"
        ).boot_bytes
    if spec.has("automatic"):
        from lab.capicola_automatic import patch_hooks

        code = patch_hooks(raw, blocks, code, out)
    if spec.has("stretch"):
        from lab.capicola_stretch import patch_hook

        patch_hook(raw, blocks, out)
    import struct

    arena = bytearray(0x72000)
    if len(code) > 0x40000 or len(data) > 0x10000:
        raise ValueError("Plaits placement overflow")
    arena[: len(code)] = code
    arena[0x40000 : 0x40000 + len(data)] = data
    remap = (0, 1, 2, 3, 4, 0, 5, 5) + ((5,) if spec.has("extra_selector") else ())
    arena[0x70000 : 0x70000 + len(remap) * 4] = struct.pack(
        "<" + str(len(remap)) + "I", *remap
    )
    split = blocks[-1]["offset"]
    if blocks[-1]["flags"] != ["bit0", "FINAL"] or blocks[-1]["byte_count"]:
        raise ValueError("Unexpected final loader block")
    result = (
        bytes(raw[:split]) + header(0x20080000, len(arena)) + arena + bytes(raw[split:])
    )
    if layout == "reserved-state":
        placement = capicola_layout.manifest(
            len(code), len(data), family=family, source=runtime_variant == "source"
        )
        if plaits_any_track:
            for region in placement['regions']:
                if region['name'] == 'plaits_lanes':
                    region['end'] = region['start'] + 32 * 352
            previous = 0
            for region in placement['regions']:
                if region['start'] < previous:
                    raise ValueError('Any-track Plaits state overlaps another owner')
                previous = region['end']
        state = bytearray(capicola_layout.STATE_BYTES)
        state[: len(data)] = data
        state[0x30000 : 0x30000 + len(remap) * 4] = struct.pack(
            "<" + str(len(remap)) + "I", *remap
        )
        result = (
            bytes(raw[:split])
            + header(capicola_layout.CODE_BASE, len(code))
            + code
            + header(capicola_layout.STATE_BASE, len(state))
            + state
            + bytes(raw[split:])
        )
        (out / "memory-layout.json").write_text(json.dumps(placement, indent=2) + "\n")
    parsed = sharcldr.parse_blocks(result)
    if parsed[-1]["payload_offset"] != len(result):
        raise ValueError("Bad candidate loader stream")
    (out / "PLAITS_BLOB.bin").write_bytes(result)
    (out / "build.json").write_text(
        json.dumps(
            {
                "code_bytes": len(code),
                "data_bytes": len(data),
                "arena_bytes": len(code) + len(state)
                if layout == "reserved-state"
                else len(arena),
                "compiler_sha256": hashlib.sha256(COMPILER.read_bytes()).hexdigest(),
                "integrated": integrated,
                "variant": variant,
                "runtime_variant": runtime_variant,
                "family": family,
                "lane_state_bytes": {
                    "va": (768 if integrated else 252),
                    "trio": (696 if integrated else 256),
                    "bank": (704 if integrated else 260),
                    "controls": (704 if integrated else 260),
                    "integration": (11264 if plaits_any_track else 704 if integrated else 260),
                    "capicola": 872,
                    "capicola-prep": 872,
                    "capicola-owned": 872,
                    "capicola-auto": 872,
                    "capicola-controls": 872,
                    "capicola-selection": 872,
                    "capicola-feedback": 872,
                    "capicola-live-feedback": 872,
                    "capicola-stretch": 4928,
                    "capicola-stretch-multi": 4928,
                    "capicola-stretch-live": 9536,
                    "capicola-stretch-toggle": 9536,
                }[family],
                "render_cache_bytes": 1036 if variant == "shared" else 0,
                "placement": (
                    "working data in reserved sample pool; L2 code ownership and hardware timing remain unverified"
                    if layout == "reserved-state"
                    else "emulator-only; stock loader disjointness is not runtime memory ownership"
                ),
                **({"layout": layout} if layout != "legacy" else {}),
            },
            indent=2,
        )
        + "\n"
    )
    return result
