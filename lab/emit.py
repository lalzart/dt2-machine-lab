"""Audited ColdFire label emission shared by native mods."""

import struct

from lab.coldfire import audit_code


class Code:
    """Small label assembler; only independently audited instructions emitted."""

    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.branches = []

    def emit(self, hex_bytes):
        self.data.extend(bytes.fromhex(hex_bytes))

    def imm(self, opcode, value):
        self.emit(opcode)
        self.data.extend(struct.pack(">I", value & 0xFFFFFFFF))

    def label(self, name):
        if name in self.labels:
            raise ValueError("Duplicate native label")
        self.labels[name] = len(self.data)

    def branch(self, condition, label):
        self.branches.append((len(self.data), label))
        self.data.extend(bytes((0x60 | condition, 0, 0, 0)))

    def finish(self, address):
        result = bytearray(self.data)
        for offset, label in self.branches:
            displacement = self.labels[label] - offset - 2
            result[offset + 2 : offset + 4] = struct.pack(">h", displacement)
        audit_code(result, address)
        return bytes(result)
