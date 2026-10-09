"""Fail-closed audit of the small ColdFire instruction subset emitted by Plaits.

Not a general disassembler or proof of hardware behavior. Rules are from NXP
CFPRM Rev. 3, integer instruction chapter (especially MOVE, pp. 4-47/4-48).
No Unicorn or generic 68000 decoder is used to decide instruction legality.
"""

import hashlib

BASE = 0x40000400
RANK = 0x40311A64
TABLE = 0x40311A84
INSERT = 0x401AAB60
FAILED_MAIN = "1b6dd1b8ec4d03156cb53a10d220badc91a59ea437dae6fa517cc6c5eb5d5f63"


def rank_shim():
    # Save A0 below SP; caller's begin/end consequently move to +12/+16.
    # MOVEA/LEA preserve CCR; the last MOVE sets CCR from end, as before.
    # 28 bytes fit the existing 32-byte slot. No global scratch or ABI guess.
    return bytes.fromhex(
        "2f08 41f940311a84 2f48000c 41e80040 2f480010 205f 4ef9401aab60"
    )


def fix_rank(image):
    data = bytearray(image)
    old = bytes.fromhex("2f7c40311a8400082f7c40311ac4000c4ef9401aab60")
    new = rank_shim()
    off = RANK - BASE
    expected = old + bytes(len(new) - len(old))
    if data[off : off + len(new)] != expected:
        raise ValueError("ColdFire rank shim byte guard failed")
    data[off : off + len(new)] = new
    return bytes(data), (RANK, expected, new)


def _ea(mode, reg, size):
    if mode <= 4:
        return 0
    if mode == 5:
        return 2
    # No indexed forms are currently emitted. Reject rather than accept
    # 68000 index extensions with ColdFire-incompatible index size/scale.
    if mode == 7 and reg in (0, 1, 2, 4):
        return 4 if reg == 1 or (reg == 4 and size == 4) else 2
    raise ValueError("Unreviewed effective-address form")


def audit_code(code, address):
    """Decode every byte; reject unsupported/unreviewed opcode and MOVE pairs."""
    decoded = []
    pos = 0
    while pos < len(code):
        if pos + 2 > len(code):
            raise ValueError(f"Truncated instruction at {address + pos:#x}")
        op = int.from_bytes(code[pos : pos + 2], "big")
        length, kind = 2, None
        if op >> 12 in (1, 2, 3):
            size = {1: 1, 2: 4, 3: 2}[op >> 12]
            sm, sr, dm, dr = (op >> 3) & 7, op & 7, (op >> 6) & 7, (op >> 9) & 7
            if dm == 1 and size != 4:
                raise ValueError(f"ColdFire MOVEA must be long at {address + pos:#x}")
            if dm == 7 and dr > 1 or size == 1 and sm == 1:
                raise ValueError(f"Invalid MOVE operand at {address + pos:#x}")
            if sm == 5 or (sm == 7 and sr == 2):
                forbidden = dm in (6, 7)
            elif sm == 6 or sm == 7 and sr in (0, 1, 3, 4):
                forbidden = dm in (5, 6, 7)
            else:
                forbidden = False
            if forbidden:
                raise ValueError(
                    f"ColdFire MOVE source/destination restriction at {address + pos:#x}"
                )
            length += _ea(sm, sr, size) + _ea(dm, dr, size)
            kind = "MOVEA.L" if dm == 1 else "MOVE"
        elif op & 0xF100 == 0x7000:
            kind = "MOVEQ"
        elif op & 0xF1FF == 0x71B9:
            # MVZ.B absolute-long,Dn: ColdFire ISA_B extension, not MOVEQ.
            length, kind = 6, "MVZ.B"
        elif op == 0x716C:
            length, kind = 4, "MVS.W d16(A4),D0"
        elif op & 0xF1C0 == 0x41C0:
            mode, reg = (op >> 3) & 7, op & 7
            if mode not in (2, 5) and not (mode == 7 and reg in (0, 1, 2)):
                raise ValueError("Unreviewed LEA")
            length, kind = 2 + _ea(mode, reg, 4), "LEA"
        elif op == 0x4878:
            length, kind = 4, "PEA absolute-short"
        elif op == 0x4879:
            length, kind = 6, "PEA absolute-long"
        elif op in (0x4EF9, 0x4EB9):
            length, kind = 6, "JMP" if op == 0x4EF9 else "JSR"
        elif op & 0xFFF8 == 0x4E90:
            # JSR (An), the stock OS virtual-call form (CFPRM JSR control EA).
            kind = "JSR (An)"
        elif op in (0x4E75, 0x4E71):
            kind = "RTS" if op == 0x4E75 else "NOP"
        elif op & 0xF000 == 0x6000:
            if (op >> 8) & 15 == 1 or op & 255 == 255:
                raise ValueError("Unreviewed branch form")
            length, kind = (4 if op & 255 == 0 else 2), "BRANCH"
        elif op & 0xFFF8 in (0x0C80, 0x0680):
            length, kind = 6, "CMPI.L" if op & 0xFFF8 == 0x0C80 else "ADDI.L"
        elif op in (0x0280, 0x0281):
            # CFPRM ANDI.L immediate,D0/D1; tagged informational reply decode.
            length, kind = 6, "ANDI.L"
        elif op in (0xEE89, 0xE889):
            # CFPRM LSR.L #7,D1: immediate count 1..8, register destination.
            kind = "LSR.L #7,D1" if op == 0xEE89 else "LSR.L #4,D1"
        elif op & 0xFFF8 == 0x0080:
            # CFPRM Rev. 3 ORI.L immediate,Dn; used to preserve SR mode bits.
            length, kind = 6, "ORI.L"
        elif op & 0xF1FF in (0xD1FC, 0xB1FC):
            length, kind = 6, "ADDA.L" if op & 0xF1FF == 0xD1FC else "CMPA.L"
        elif op & 0xF1F8 in (0xB080, 0xC080):
            kind = "CMP.L" if op & 0xF1F8 == 0xB080 else "AND.L"
        elif op & 0xF0F8 == 0x5088:
            kind = "ADDQ/SUBQ.L An"
        elif op in (0x48D7, 0x4CD7):
            length, kind = 4, "MOVEM.L (SP)"
        elif op & 0xFFF8 in (0x40C0, 0x44C0):
            kind = "MOVE SR,Dn" if op & 0xFFF8 == 0x40C0 else "MOVE Dn,CCR"
        elif op & 0xFFF8 == 0x46C0:
            # CFPRM supervisor ISA_A MOVE Dy,SR (register source only).
            kind = "MOVE Dn,SR"
        elif op in (0xE080, 0xE588, 0xE589, 0xED88):
            kind = "ASR/LSL.L immediate,Dn"
        elif op in (0xD1C0, 0xD3C0):
            kind = "ADDA.L D0,An"
        elif op == 0x71D1:
            kind = "MVZ.W (A1),D0"
        elif op == 0x9283:
            kind = "SUB.L D3,D1"
        elif op in (0x9081, 0xD080):
            kind = "SUB/ADD.L Dn,D0"
        elif op & 0xFFF8 == 0x4A80:
            kind = "TST.L Dn"
        elif op in (0x5380, 0x5382):
            kind = "SUBQ.L #1,D0/D2"
        elif op == 0x5280:
            kind = "ADDQ.L #1,D0"
        elif op == 0x57C0:
            kind = "SEQ.B D0"
        elif op == 0x4C01 and code[pos + 2 : pos + 4] == bytes.fromhex("0800"):
            length, kind = 4, "MULS.L D1,D0"
        if kind is None:
            raise ValueError(
                f"Unreviewed ColdFire opcode {op:04x} at {address + pos:#x}"
            )
        if pos + length > len(code):
            raise ValueError(f"Truncated {kind} at {address + pos:#x}")
        decoded.append(
            {
                "address": address + pos,
                "bytes": code[pos : pos + length].hex(),
                "kind": kind,
            }
        )
        pos += length
    return decoded


def audit_image(stock, image, upstream, extra, metadata, correction):
    """Classify all patch writes as code/data; require full changed-byte coverage.

    Fixed version-specific locations are intentional: a new patch site or kind
    requires explicit review. Partial immediate writes include their opcode.
    """
    data_starts = {
        0x403118C4,
        0x40311904,
        0x40311924,
        0x40311944,
        0x403119C4,
        0x40311A18,
        0x40311A44,
        0x40311A54,
        0x40311A84,
        0x40311964,
        0x40311A20,
        0x40311984,
    }
    regions = []
    for addr, _old, new in upstream:
        if addr == RANK:
            regions.append((addr, len(rank_shim()), "code", "rank shim"))
        elif addr in data_starts:
            regions.append((addr, len(new), "data", "machine tables/strings"))
        elif addr < 0x403117C4 and len(new) in (1, 4):
            back = 1 if len(new) == 1 else 2
            regions.append((addr - back, len(new) + back, "code", "inline operand"))
        else:
            regions.append((addr, len(new), "code", "machine patch"))
    for addr, _old, new in extra:
        typ = (
            "data"
            if addr in (0x40212C30, 0x40212C4C, 0x40212C54, 0x40311CC4)
            else "code"
        )
        regions.append((addr, len(new), typ, "MODEL patch"))
    for write in metadata["writes"]:
        addr, length, label = (
            write["address"],
            len(bytes.fromhex(write["after"])),
            write["label"],
        )
        typ = "data" if label == "dedicated macro rows and labels" else "code"
        if label in ("parameter bound", "parameter operation bound"):
            addr, length = addr - 2, length + 2
        regions.append((addr, length, typ, label))
    covered = bytearray(len(image))
    reports = []
    for addr, length, typ, label in regions:
        off = addr - BASE
        if off < 0 or off + length > len(image):
            raise ValueError("Audit region outside image")
        covered[off : off + length] = bytes([1]) * length
        code = image[off : off + length]
        reports.append(
            {
                "address": addr,
                "length": length,
                "type": typ,
                "label": label,
                "instructions": audit_code(code, addr) if typ == "code" else [],
            }
        )
    if len(stock) != len(image) or any(
        a != b and not covered[i]
        for i, (a, b) in enumerate(zip(stock, image, strict=True))
    ):
        raise ValueError("Image change outside audited code/data regions")
    # Reverse only the explicitly guarded correction. This proves the new
    # candidate differs from the hardware-failed one solely at that slot.
    previous = bytearray(image)
    addr, before, after = correction
    off = addr - BASE
    if previous[off : off + len(after)] != after:
        raise ValueError("Rank correction changed after application")
    previous[off : off + len(before)] = before
    if hashlib.sha256(previous).hexdigest() != FAILED_MAIN:
        raise ValueError("Unexpected change beyond the reviewed rank correction")
    return {
        "status": "passed",
        "main_sha256": hashlib.sha256(image).hexdigest(),
        "scope": "All changed bytes classified; emitted CPU instruction subset audited, not whole stock OS or hardware proof",
        "reference": "https://www.nxp.com/docs/en/reference-manual/CFPRM.pdf",
        "regions": reports,
        "instruction_count": sum(len(r["instructions"]) for r in reports),
        "failed_main_sha256": FAILED_MAIN,
        "correction_only": True,
    }
