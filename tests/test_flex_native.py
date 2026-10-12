"""Execute emitted device code; mock only the three recorder-service calls.

These are CPU/ABI tests, not proof of RTOS scheduling or hardware recording.
"""

import struct
import unittest

from lab.coldfire import audit_code
from lab.flex_native import (
    FIRST_ID,
    LOCK,
    MAX_FRAMES,
    RECORDER_CHUNK,
    UNLOCK,
    recording_copy,
    resource_handler,
    resource_lookup,
)

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE = 0x100000
STACK = 0x20F000
DEST = 0x300100
RESPONSE = 0x800000
STOP = CODE + 0xF000


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class NativeRecorderTests(unittest.TestCase):
    def execute(self, start, frames, stereo, capacity=None):
        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, size in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x400000),
            (RESPONSE, 0x1000),
            (0x40012000, 0x1000),
        ):
            cpu.mem_map(address, size)
        cpu.mem_write(CODE, recording_copy(CODE))
        cpu.mem_write(STOP, bytes.fromhex("4e71"))
        width = 4 if stereo == 1 else 2
        total = frames * width + 80 if frames <= MAX_FRAMES + 1 else 80
        capacity = total if capacity is None else capacity
        cpu.mem_write(DEST - 16, b"\xa5" * (min(total, MAX_FRAMES * 4 + 80) + 32))
        cpu.mem_write(
            STACK, struct.pack(">6I", STOP, DEST, capacity, start, frames, stereo)
        )
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        saved = {}
        for i, reg in enumerate(
            (
                r.UC_M68K_REG_D2,
                r.UC_M68K_REG_D3,
                r.UC_M68K_REG_D4,
                r.UC_M68K_REG_D5,
                r.UC_M68K_REG_D6,
                r.UC_M68K_REG_D7,
                r.UC_M68K_REG_A2,
                r.UC_M68K_REG_A3,
                r.UC_M68K_REG_A4,
                r.UC_M68K_REG_A5,
                r.UC_M68K_REG_A6,
            )
        ):
            saved[reg] = 0x17001000 + i * 16
            cpu.reg_write(reg, saved[reg])
        requests, expected, locked = [], bytearray(), False

        def service(uc, address, _size, _data):
            nonlocal locked
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if address == LOCK:
                self.assertFalse(locked)
                locked = True
            elif address == UNLOCK:
                self.assertTrue(locked)
                locked = False
                uc.mem_write(RESPONSE, b"\xdd" * 2048)
            else:
                self.assertTrue(locked)
                offset, count, mono = struct.unpack(">3I", uc.mem_read(sp + 4, 12))
                self.assertEqual(mono, 1 - stereo)
                self.assertGreater(count, 0)
                self.assertLessEqual(count * width, 2048)
                self.assertEqual(offset, start + len(expected) // width)
                payload = bytes(
                    (offset * width + i) % 251 for i in range(count * width)
                )
                expected.extend(payload)
                requests.append((offset, count, mono))
                uc.mem_write(RESPONSE, payload)
                result = RESPONSE
            # All caller-saved registers may be destroyed by stock callees.
            for reg in (r.UC_M68K_REG_D1, r.UC_M68K_REG_A0, r.UC_M68K_REG_A1):
                uc.reg_write(reg, 0xDEAD0000)
            uc.reg_write(r.UC_M68K_REG_D0, result)
            uc.reg_write(r.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for address in (LOCK, UNLOCK, RECORDER_CHUNK):
            cpu.hook_add(u.UC_HOOK_CODE, service, begin=address, end=address)
        cpu.emu_start(CODE, STOP, count=15000000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        self.assertFalse(locked)
        for reg, value in saved.items():
            self.assertEqual(cpu.reg_read(reg), value)
        result = cpu.reg_read(r.UC_M68K_REG_D0)
        if result == 0xFFFFFFFF:
            self.assertFalse(requests)
            self.assertEqual(bytes(cpu.mem_read(DEST - 16, 112)), b"\xa5" * 112)
        else:
            self.assertEqual(result, total)
            header = bytearray(64)
            header[1] = stereo
            struct.pack_into(">II", header, 4, frames * width, 48000)
            header[20] = 127
            self.assertEqual(
                bytes(cpu.mem_read(DEST, total)), header + expected + bytes(16)
            )
            self.assertEqual(bytes(cpu.mem_read(DEST - 16, 16)), b"\xa5" * 16)
            self.assertEqual(bytes(cpu.mem_read(DEST + total, 16)), b"\xa5" * 16)
        return result, requests

    def test_native_mono_and_stereo_chunk_boundaries(self):
        for stereo in (0, 1):
            for frames in (141, 511, 512, 513, 1023, 1024, 1025, 2948):
                with self.subTest(stereo=stereo, frames=frames):
                    result, _ = self.execute(86, frames, stereo)
                    self.assertNotEqual(result, 0xFFFFFFFF)

    def test_native_maximum_and_last_valid_trim(self):
        for args in ((0, MAX_FRAMES, 0), (0, MAX_FRAMES, 1), (MAX_FRAMES - 141, 141, 0)):
            self.assertNotEqual(self.execute(*args)[0], 0xFFFFFFFF)

    def test_native_rejects_before_destination_or_recorder_access(self):
        for args in (
            (0, 140, 0),
            (0, MAX_FRAMES + 1, 1),
            (MAX_FRAMES, 141, 0),
            (MAX_FRAMES - 140, 141, 0),
            (0xFFFFFFFF, 141, 0),
            (0, 141, 2),
            (0, 141, 1, 643),
            (0, 141, 0, 361),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.execute(*args)[0], 0xFFFFFFFF)


class NativeEncodingTests(unittest.TestCase):
    def test_all_emitted_instructions_audited(self):
        code = recording_copy(CODE)
        self.assertGreater(len(audit_code(code, CODE)), 80)
        self.assertLess(len(code), 896)


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class NativeResourceTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        self.cpu.mem_map(CODE, 0x10000)
        self.cpu.mem_map(0x200000, 0x10000)
        self.cpu.mem_map(0x300000, 0x10000)
        self.cpu.mem_write(CODE, resource_lookup(CODE, 0x300000))
        self.cpu.mem_write(CODE + 0x100, bytes.fromhex("70634e75"))
        self.cpu.mem_write(STOP, bytes.fromhex("4e71"))
        self.entries = {}
        for i, op in enumerate(
            ("resolve", "key", "open", "size", "read", "name", "close")
        ):
            address = CODE + 0x200 + i * 0x200
            self.cpu.mem_write(
                address, resource_handler(address, CODE, op, CODE + 0x100)
            )
            self.entries[op] = address
        self.ref = struct.pack(">4I", FIRST_ID, 0x98765433, 3072, 1)
        self.cpu.mem_write(0x300000, struct.pack(">I", 0x300100))
        self.cpu.mem_write(0x300100, bytes(4) + self.ref + struct.pack(">I", 0x301000))
        self.payload = bytes(i % 251 for i in range(3072))
        self.cpu.mem_write(0x301000, self.payload)
        self.cpu.mem_write(0x300200, self.ref)

    def call(self, operation, *args):
        cpu = self.cpu
        cpu.mem_write(STACK, struct.pack(">" + "I" * (len(args) + 1), STOP, *args))
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        preserve = (
            r.UC_M68K_REG_D2,
            r.UC_M68K_REG_D3,
            r.UC_M68K_REG_D4,
            r.UC_M68K_REG_D5,
            r.UC_M68K_REG_D6,
            r.UC_M68K_REG_D7,
            r.UC_M68K_REG_A2,
            r.UC_M68K_REG_A3,
            r.UC_M68K_REG_A4,
            r.UC_M68K_REG_A5,
            r.UC_M68K_REG_A6,
        )
        for reg in preserve:
            cpu.reg_write(reg, 0xBAD000 + reg)
        cpu.emu_start(self.entries[operation], STOP, count=100000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        for reg in preserve:
            self.assertEqual(cpu.reg_read(reg), 0xBAD000 + reg)
        return cpu.reg_read(r.UC_M68K_REG_D0)

    def test_native_source_lifecycle_and_eof(self):
        self.assertEqual(self.call("resolve", 0x300200, 0x300300), 0)
        self.assertEqual(bytes(self.cpu.mem_read(0x300300, 4)), self.ref[:4])
        self.assertEqual(self.call("key", FIRST_ID, 0x300300), 0)
        self.assertEqual(bytes(self.cpu.mem_read(0x300300, 16)), self.ref)
        self.assertEqual(self.call("size", FIRST_ID), len(self.payload))
        self.assertEqual(self.call("open", 0x300200, 0x300300), 0)
        for position, requested, expected in (
            (0, 2048, 2048),
            (2048, 2048, 1024),
            (3072, 100, 0),
        ):
            self.assertEqual(self.call("read", 0x304000, requested, 0x300300), expected)
            self.assertEqual(
                bytes(self.cpu.mem_read(0x304000, expected)),
                self.payload[position : position + expected],
            )
        self.assertEqual(self.call("name", FIRST_ID, 0, 0x304000), 0x304000)
        self.assertEqual(
            bytes(self.cpu.mem_read(0x304000, 32)), b"/TEMP/FLEX".ljust(32, b"\0")
        )
        self.assertEqual(self.call("close", 0x300300), 0)

    def test_unregistered_and_mismatched_references_fail(self):
        self.assertEqual(self.call("size", FIRST_ID + 1), 0xFFFFFFFF)
        self.cpu.mem_write(0x300204, bytes(4))
        for op in ("open", "resolve"):
            self.assertEqual(self.call(op, 0x300200, 0x300300), 0xFFFFFFFF)

    def test_lookup_cycle_is_bounded(self):
        self.cpu.mem_write(0x300100, struct.pack(">I", 0x300100))
        self.assertEqual(self.call("size", FIRST_ID + 1), 0xFFFFFFFF)

    def test_stock_and_null_inputs_reach_stock_trampoline(self):
        for op, args in (
            ("size", (5,)),
            ("key", (5, 0x300300)),
            ("name", (5, 0, 0x304000)),
            ("resolve", (0, 0)),
            ("open", (0, 0)),
            ("close", (0,)),
            ("read", (0, 0, 0)),
        ):
            with self.subTest(op=op):
                self.assertEqual(self.call(op, *args), 99)


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class NativeRecorderFlagTests(unittest.TestCase):
    def capture_flag(self, channel, *, old_caller=False):
        from lab.flex_native import recorder_use_entry

        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, size in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x10000),
            (0x40000000, 0x50000),
            (0x80004000, 0x1000),
        ):
            cpu.mem_map(address, size)
        state, view, continuation = 0x300100, 0x301000, 0x40022FC6
        code = recorder_use_entry(CODE, state)
        if old_caller:
            # Retain branch offsets while recreating the original full-register
            # MOVE. NOP does not alter its value or flags.
            code = code.replace(
                bytes.fromhex("7200120070019081"), bytes.fromhex("22004e7170019081")
            )
        cpu.mem_write(CODE, code)
        # Exact OS 1.16 helper: SNE.B followed by NEG.L returns a byte bool;
        # upper bits are not a valid part of the return value. Only its
        # ProjectSettings enum getter is modeled below.
        cpu.mem_write(
            0x40020388,
            bytes.fromhex("206f00042f2800a04eb94004cca2588f4a8056c044804e75"),
        )
        cpu.mem_write(view + 0x9A0, struct.pack(">II", 0, 1000))
        cpu.mem_write(0x80004704, struct.pack(">I", 0x302000))
        cpu.mem_write(STACK, struct.pack(">I", STOP))
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        cpu.reg_write(r.UC_M68K_REG_A2, view)
        raw_returns = []

        def service(uc, address, _size, _data):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            value = channel if address == 0x4004CCA2 else 0
            uc.reg_write(r.UC_M68K_REG_D0, value)
            uc.reg_write(r.UC_M68K_REG_PC, int.from_bytes(uc.mem_read(sp, 4), "big"))
            uc.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for address in (0x4004ABE8, 0x4004CCA2):
            cpu.hook_add(u.UC_HOOK_CODE, service, begin=address, end=address)
        cpu.hook_add(
            u.UC_HOOK_CODE,
            lambda uc, *_: raw_returns.append(uc.reg_read(r.UC_M68K_REG_D0)),
            begin=0x4002039E,
            end=0x4002039E,
        )
        cpu.emu_start(CODE, continuation, count=2000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), continuation)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A2), view)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), STACK - 4)
        stereo = int.from_bytes(cpu.mem_read(state + 32, 4), "big")
        return raw_returns[0], stereo

    def test_native_entry_respects_byte_boolean_return(self):
        for channel in (0, 1, 2, 3):
            with self.subTest(channel=channel):
                raw, stereo = self.capture_flag(channel)
                self.assertEqual(raw, 0 if channel == 0 else 0xFFFFFF01)
                self.assertEqual(stereo, int(channel == 0))

    def test_old_full_register_caller_reproduces_input_format_rejection(self):
        raw, stereo = self.capture_flag(1, old_caller=True)
        self.assertEqual(raw, 0xFFFFFF01)
        self.assertEqual(stereo, 0x100)
