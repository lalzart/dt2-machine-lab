"""Bounded ColdFire gesture/state checks; all service stubs are explicit."""

import struct
import unittest

from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as frozen
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.emit import Code
from lab.runtime import STOCK_MAIN

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = r = None


@unittest.skipIf(u is None, "Configured native CPU runtime required")
class SketchTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (s.BASE, s.END - s.BASE),
            (nb.BASE, nb.END - nb.BASE),
            (bf.BASE, bf.END - bf.BASE),
            (bf.q.BASE, 4096),
            (0x200000, 0x10000),
            (0x40000000, 0x300000),
            (0x405B0000, 0x10000),
            (0x44F37000, 4096),
            (0x80004000, 4096),
            (w.BASE, 0x1000),
            (w.DEST, 4096),
            (frozen.BASE, 0x2000),
            (0x47DDE000, 4096),
        ):
            self.cpu.mem_map(at, size)
        for at, code in s.payload(STOCK_MAIN.read_bytes()).items():
            self.cpu.mem_write(at, code)
        self.put(s.STATE + s.BUF, 1)
        self.put(0x80004704, 0x204000)
        self.put(0x44F370A0, 0x203000)
        self.native_value(0x4019988A, 0x205000)
        self.native_value(0x40015F6C, 0)
        self.native_value(0x401988A2, 0x203000)
        self.native_value(0x40041D18, 0x206000)
        self.native_value(s.GETTERS[2], 4)
        self.native_value(0x4011DE70, 0)
        for at in (0x40114654, 0x4011AE46, 0x4011AEEA, s.OPEN):
            self.native_value(at, 0)
        self.put(s.STATE + s.VIEW, 0x200100)

    def put(self, at, *words):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(words), *words))

    def get(self, field):
        return int.from_bytes(self.cpu.mem_read(s.STATE + field, 4), "big")

    def native_value(self, at, value):
        c = Code()
        c.imm("203c", value)
        c.emit("4e75")
        self.cpu.mem_write(at, c.finish(at))
        self.cpu.ctl_remove_cache(at, at + len(c.data))

    def call(self, at, *args):
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, stop, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        self.cpu.emu_start(at, stop, count=100000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def event(self, key, flags):
        self.put(0x208400, 0, 0, 0, key, flags)
        return self.call(s.INPUT, 0x200100, 0x208400)

    def test_both_chord_orders_repeats_and_release_orders(self):
        for func_first in (False, True):
            for releases in ((17, 24), (24, 17)):
                with self.subTest(func_first=func_first, releases=releases):
                    self.setUp()
                    if func_first:
                        self.native_value(0x4011DE70, 1)
                        self.assertEqual(self.event(17, 1), 0)
                    self.assertEqual(self.event(24, 3 if func_first else 5), 1)
                    if not func_first:
                        self.assertEqual(self.event(17, 1), 1)
                    for flags in (9, 0x29, 5):
                        self.assertEqual(self.event(24, flags), 1)
                    for key in releases:
                        self.assertEqual(self.event(key, 0), 1)
                    self.assertEqual((self.get(s.ARMS), self.get(s.FREEZES)), (1, 0))
                    self.assertEqual((self.get(s.OWN), self.get(s.FUNC_OWN)), (0, 0))
                    self.assertEqual(self.get(s.ACTION), 1)

    def test_hold_is_once_and_empty_busy_refuse_without_jobs(self):
        for recorder_state, expected in ((0, 4), (1, 3), (2, 3), (3, 3), (4, 3)):
            with self.subTest(recorder_state=recorder_state):
                self.setUp()
                self.native_value(0x40015F6C, recorder_state)
                self.event(24, 1)
                for flags in (9, 9, 0x29, 9, 0x29):
                    self.event(24, flags)
                self.event(24, 16)
                self.assertEqual(self.get(s.FREEZES), 1)
                self.assertEqual(self.get(s.ACTION), expected)
                self.assertEqual(self.get(s.OWN), 0)
                self.assertEqual(self.get(s.VIEW), 0x200100)

    def test_real_arm_both_chord_orders_call_explicit_service_once(self):
        for func_first in (True, False):
            with self.subTest(func_first=func_first):
                self.setUp()
                self.cpu.mem_write(s.INPUT, s.input_event(arm_enabled=True))
                self.native_value(nb.ARM_ONLY, 0)
                calls = []

                def observe(uc, _pc, *_, calls=calls):
                    sp = uc.reg_read(r.UC_M68K_REG_A7)
                    calls.append(struct.unpack(">II", uc.mem_read(sp + 4, 8)))

                self.cpu.hook_add(
                    u.UC_HOOK_CODE, observe, begin=nb.ARM_ONLY, end=nb.ARM_ONLY
                )
                self.put(s.STATE + s.BUF, 3)
                if func_first:
                    self.native_value(0x4011DE70, 1)
                    self.event(17, 1)
                self.event(24, 3 if func_first else 1)
                if not func_first:
                    self.event(17, 1)
                for flags in (9, 0x29, 5):
                    self.event(24, flags)
                self.event(24, 0)
                self.event(17, 0)
                self.assertEqual(calls, [(0x205000, 3)])
                self.assertEqual(self.get(s.ACTION), 8)
                self.assertEqual(self.get(s.ARMS), 1)
                self.assertEqual(self.get(s.FREEZES), 0)
                self.assertEqual(int.from_bytes(self.cpu.mem_read(w.DEST, 4), "big"), 0)

    def test_real_freeze_calls_latched_buf_once_and_keeps_accepted_feedback(self):
        self.cpu.mem_write(s.INPUT, s.input_event(freeze_enabled=True))
        self.native_value(bf.SUBMIT, 0)
        calls = []

        def observe(uc, _pc, *_):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            calls.append(int.from_bytes(uc.mem_read(sp + 4, 4), "big"))

        self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=bf.SUBMIT, end=bf.SUBMIT)
        self.put(s.STATE + s.BUF, 2)
        self.event(24, 1)
        for flags in (9, 0x29, 9, 0x29):
            self.event(24, flags)
        self.put(s.STATE + s.BUF, 4)
        self.event(24, 0)
        self.assertEqual(calls, [2])
        self.assertEqual(self.get(s.FREEZES), 1)
        self.assertEqual(self.get(s.ACTION), 12)
        self.assertEqual(self.get(s.VIEW), 0x200100)
        self.assertEqual(self.get(s.OWN), 0)

    def test_real_freeze_refusal_and_async_completion_feedback(self):
        self.cpu.mem_write(s.INPUT, s.input_event(freeze_enabled=True))
        for result, action in ((-7, 14), (-2, 15), (-5, 16), (-1, 17), (-6, 18)):
            self.native_value(bf.SUBMIT, result)
            self.event(24, 1)
            self.event(24, 0x29)
            self.event(24, 0)
            self.assertEqual(self.get(s.ACTION), action)
        for result, action in ((312, 13), (-3, 19), (-4, 18)):
            self.put(s.STATE + s.ACTION, 12)
            self.put(s.STATE + s.FREEZE_DONE, 4)
            self.put(bf.q.STATE + 12, result & 0xFFFFFFFF)
            self.put(bf.q.STATE + 32, 4)
            self.call(s.FREEZE_FEEDBACK)
            self.assertEqual(self.get(s.ACTION), 12)  # Not an older completion.
            self.put(bf.q.STATE + 32, 5)
            self.call(s.FREEZE_FEEDBACK)
            self.assertEqual(self.get(s.ACTION), action)
            self.assertEqual(self.get(s.FREEZE_RESULT), result & 0xFFFFFFFF)

    def test_real_arm_refusal_feedback_and_hold_remains_dry(self):
        self.cpu.mem_write(s.INPUT, s.input_event(arm_enabled=True))
        for result, action in (
            (nb.ARM_BUSY, 9),
            (nb.ARM_REFUSED, 10),
            (nb.ARM_LENGTH, 11),
        ):
            self.native_value(nb.ARM_ONLY, result)
            self.event(24, 1)
            self.event(17, 1)
            self.event(24, 0)
            self.event(17, 0)
            self.assertEqual(self.get(s.ACTION), action)
            self.assertEqual(self.get(s.ARM_RESULT), result & 0xFFFFFFFF)
        self.event(24, 1)
        self.event(24, 0x29)
        self.event(24, 0)
        self.assertEqual(self.get(s.ACTION), 4)  # Empty BUF; no real FREEZE call.
        self.assertEqual(self.get(s.FREEZES), 1)

    def test_diagnostic_feedback_latches_and_draws_exact_admission_reason(self):
        cases = [
            (i, name, result, False, False)
            for i, (name, result) in enumerate(nb.ARM_DIAGNOSTICS, 1)
        ]
        cases += [
            (i, name, nb.ARM_REFUSED, True, False)
            for i, name in enumerate(nb.CLOCK_DIAGNOSTICS, len(nb.ARM_DIAGNOSTICS) + 1)
        ]
        cases += [
            (i, name, nb.ARM_BUSY, False, True)
            for i, name in enumerate(s.OP_DIAGNOSTICS, len(nb.ARM_DIAGNOSTICS) + 1)
        ]
        cases += [(4, "SAMPLE", nb.ARM_BUSY, False, True)]
        cases += [(4, "SAMPLE", nb.ARM_BUSY, True, False)]
        for index, reason, result, clock_fix, operation_diagnostics in cases:
            with self.subTest(reason=reason):
                self.setUp()
                parts = s.payload(
                    STOCK_MAIN.read_bytes(),
                    arm_enabled=True,
                    arm_diagnostics=True,
                    clock_fix=clock_fix,
                    operation_diagnostics=operation_diagnostics,
                )
                for at, code in parts.items():
                    self.cpu.mem_write(at, code)
                self.native_value(nb.ARM_ONLY, result)
                self.put(
                    nb.STATE + nb.ARM_DIAG,
                    4
                    if operation_diagnostics
                    else 11
                    if clock_fix and index > 15
                    else index,
                    42,
                )
                if operation_diagnostics:
                    op = index - len(nb.ARM_DIAGNOSTICS) - 1
                    words = [0] * len(s.freeze_jobs.OP_FIELDS)
                    words[0] = s.retirement.GUARDS + op * 256 + 14 if op >= 0 else 0
                    words[2] = words[3] = 42
                    self.put(nb.STATE + nb.OP_CONTEXT, *words)
                if clock_fix and index > 15:
                    self.put(
                        nb.STATE + nb.CLOCK_DIAG,
                        index - len(nb.ARM_DIAGNOSTICS) - 1,
                        42,
                    )
                self.call(s.ARM_SUBMIT)
                self.assertEqual(self.get(s.ARM_RESULT), result & 0xFFFFFFFF)
                self.assertEqual(self.get(s.ARM_DIAG), index)
                self.assertEqual(self.get(s.ARM_DIAG_VALUE), 42)
                if operation_diagnostics:
                    self.put(
                        nb.STATE + nb.OP_CONTEXT,
                        *([999] * len(s.freeze_jobs.OP_FIELDS)),
                    )
                self.put(
                    nb.STATE + nb.ARM_DIAG, 0, 999
                )  # Later backend state is irrelevant.
                self.call(s.ARM_FEEDBACK)
                for at in (
                    s.CLEAR,
                    s.TEXT,
                    s.PRINT,
                    *s.GETTERS,
                    0x4001FD88,
                    0x4001FDBE,
                    0x4001FDF4,
                ):
                    self.native_value(at, 1 if at == s.CLEAR else 0)
                seen = []

                def observe(uc, _pc, *_, seen=seen):
                    sp = uc.reg_read(r.UC_M68K_REG_A7)
                    pointer = int.from_bytes(uc.mem_read(sp + 8, 4), "big")
                    label = bytes(uc.mem_read(pointer, 64)).split(b"\0")[0]
                    if label.startswith((b"BUSY ", b"REF ", b"CLK ")):
                        seen.append(
                            (
                                label.decode(),
                                int.from_bytes(uc.mem_read(sp + 12, 4), "big"),
                            )
                        )

                self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=s.PRINT, end=s.PRINT)
                self.call(s.DRAW, 0x200100, 0x200500)
                category = (
                    "CLK"
                    if clock_fix and index > 15
                    else "BUSY"
                    if result == nb.ARM_BUSY
                    else "REF"
                )
                self.assertEqual(seen, [(f"{category} {reason} %u", 42)])

    def test_clock_profile_waits_visibly_without_requesting_or_hiding_errors(self):
        for count, loader, action, waiting in (
            (1, 0, 0, True),
            (0, 1, 0, True),
            (0, 0, 0, False),
            (1, 0, 10, False),
        ):
            with self.subTest(count=count, loader=loader, action=action):
                self.setUp()
                for at, raw in s.payload(
                    STOCK_MAIN.read_bytes(),
                    arm_enabled=True,
                    arm_diagnostics=True,
                    clock_fix=True,
                ).items():
                    self.cpu.mem_write(at, raw)
                for at in (
                    s.CLEAR,
                    s.TEXT,
                    s.PRINT,
                    *s.GETTERS,
                    0x4001FD88,
                    0x4001FDBE,
                    0x4001FDF4,
                ):
                    self.native_value(at, int(at == s.CLEAR))
                self.put(s.freeze_jobs.STATE + 56, count)
                self.put(s.freeze_jobs.STOCK_BUSY, loader)
                self.put(s.STATE + s.ACTION, action)
                seen = []

                def observe(uc, _pc, *_, seen=seen):
                    sp = uc.reg_read(r.UC_M68K_REG_A7)
                    ptr = int.from_bytes(uc.mem_read(sp + 24, 4), "big")
                    seen.append(bytes(uc.mem_read(ptr, 32)).split(b"\0")[0])

                self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=s.TEXT, end=s.TEXT)
                self.call(s.DRAW, 0x200100, 0x200500)
                self.assertEqual(b"WAIT SAMPLES" in seen, waiting)
                for at, value in (
                    (s.freeze_jobs.STATE + 56, count),
                    (s.freeze_jobs.STOCK_BUSY, loader),
                    (nb.STATE + nb.ARMS, 0),
                ):
                    self.assertEqual(
                        int.from_bytes(self.cpu.mem_read(at, 4), "big"), value
                    )
                self.assertEqual(self.get(s.ACTION), action)
                self.assertEqual((self.get(s.ARMS), self.get(s.FREEZES)), (0, 0))

    def admit_arm_feedback(self):
        # An explicit admission-service boundary, not a successful capture.
        self.native_value(nb.ARM_ONLY, 0)
        for field, value in (
            (nb.ARMS, 9),
            (nb.EPOCH, 7),
            (nb.KIT, 0x204000),
            (nb.DEST, 2),
            (nb.POOL, 0x206000),
            (nb.PHASE, 1),
        ):
            self.put(nb.STATE + field, value)
        self.put(frozen.STATE, 7)
        self.put(w.STATE + 68, 0x206000)
        self.put(s.STATE + s.LATCH, 2)
        self.call(s.ARM_SUBMIT)
        self.assertEqual(self.get(s.ARM_COUNT), 9)
        self.assertEqual(self.get(s.ARM_BUF), 2)

    def test_arm_feedback_follows_capture_and_requires_terminal_publication(self):
        self.admit_arm_feedback()
        for phase, action in (
            (1, s.ARM_WAITING),
            (2, s.ARM_RECORDING),
            (3, s.ARM_PROCESSING),
            (4, s.ARM_LOADING),
            (5, s.ARM_CANCELLING),
        ):
            with self.subTest(phase=phase):
                self.put(nb.STATE + nb.PHASE, phase)
                self.put(nb.STATE + nb.RESULT, 1)  # Cannot imply early readiness.
                before = bytes(self.cpu.mem_read(nb.BASE, 0x300))
                self.call(s.ARM_FEEDBACK)
                self.assertEqual(self.get(s.ACTION), action)
                self.assertEqual(bytes(self.cpu.mem_read(nb.BASE, 0x300)), before)
        for result, cancel, action in (
            (1, 0, s.ARM_READY),
            (-2, 1, s.ARM_CANCELLED),
            (-4, 0, s.ARM_FAILED),
            (-4, 1, s.ARM_CANCELLED),
            (-5, 1, s.ARM_STALE),
            (nb.CAPACITY_RESULT, 1, s.ARM_CAPACITY),
            (0, 0, s.ARM_FAILED),
        ):
            with self.subTest(result=result, cancel=cancel):
                self.put(s.STATE + s.ACTION, s.ARM_WAITING)
                self.put(nb.STATE + nb.PHASE, 0)
                self.put(nb.STATE + nb.RESULT, result & 0xFFFFFFFF)
                self.put(nb.STATE + nb.CANCEL, cancel)
                self.call(s.ARM_FEEDBACK)
                self.assertEqual(self.get(s.ACTION), action)
                self.assertEqual(self.get(s.ARM_RESULT), 0)  # Admission ABI intact.

    def test_arm_feedback_rejects_replacement_and_stale_project_context(self):
        for at in (
            nb.STATE + nb.ARMS,
            frozen.STATE,
            0x80004704,
            0x44F370A0,
            nb.STATE + nb.DEST,
            w.STATE + 68,
        ):
            with self.subTest(at=hex(at)):
                self.setUp()
                self.admit_arm_feedback()
                old = int.from_bytes(self.cpu.mem_read(at, 4), "big")
                self.put(at, old + 1)
                self.put(nb.STATE + nb.PHASE, 0)
                self.put(nb.STATE + nb.RESULT, 1)
                self.call(s.ARM_FEEDBACK)
                self.assertEqual(self.get(s.ACTION), s.ARM_STALE)
                self.assertEqual(
                    int.from_bytes(self.cpu.mem_read(at, 4), "big"), old + 1
                )

    def test_arm_feedback_does_not_replace_later_actions_or_terminal_messages(self):
        self.admit_arm_feedback()
        self.put(nb.STATE + nb.PHASE, 0)
        self.put(nb.STATE + nb.RESULT, 1)
        for action in (
            *range(8),
            *range(9, 20),
            *range(s.ARM_READY, s.ARM_CAPACITY + 1),
        ):
            with self.subTest(action=action):
                self.put(s.STATE + s.ACTION, action)
                self.call(s.ARM_FEEDBACK)
                self.assertEqual(self.get(s.ACTION), action)

    def test_arm_feedback_refresh_and_draw_keep_admitted_buf_after_selection_change(
        self,
    ):
        self.admit_arm_feedback()
        self.cpu.mem_write(s.UPDATE, s.update(arm_enabled=True))
        self.put(nb.STATE + nb.PHASE, 2)
        self.put(s.PANEL_TICK, 100)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.ACTION), s.ARM_RECORDING)
        # The dry profile does not observe a real transaction.
        self.put(nb.STATE + nb.PHASE, 3)
        self.cpu.mem_write(s.UPDATE, s.update())
        self.cpu.ctl_remove_cache(s.UPDATE, s.UPDATE + 0x100)
        self.put(s.PANEL_TICK, 112)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.ACTION), s.ARM_RECORDING)
        parts = s.payload(STOCK_MAIN.read_bytes(), arm_enabled=True)
        self.cpu.mem_write(s.DRAW, parts[s.DRAW])
        for at in (
            s.CLEAR,
            s.TEXT,
            s.PRINT,
            *s.GETTERS,
            0x4001FD88,
            0x4001FDBE,
            0x4001FDF4,
        ):
            self.native_value(at, 1 if at == s.CLEAR else 0)
        self.put(s.STATE + s.BUF, 4)
        self.put(s.STATE + s.LATCH, 4)  # A later navigation press can change this.
        seen = []

        def observe(uc, _pc, *_):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            fmt = int.from_bytes(uc.mem_read(sp + 8, 4), "big")
            label = bytes(uc.mem_read(fmt, 64)).split(b"\0")[0]
            if label.startswith(b"BUF %u:"):
                seen.append((label, int.from_bytes(uc.mem_read(sp + 12, 4), "big")))

        self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=s.PRINT, end=s.PRINT)
        self.call(s.DRAW, 0x200100, 0x200500)
        self.assertEqual(seen, [(b"BUF %u: PROCESSING", 2)])
        self.assertEqual(self.get(s.BUF), 4)
        self.assertEqual(self.get(s.ARM_BUF), 2)

    def test_context_change_and_stop_cancel_pending_cycle(self):
        for at in (s.STATE + s.BUF, w.DEST, frozen.STATE, 0x80004704, 0x44F370A0):
            with self.subTest(at=hex(at)):
                self.setUp()
                self.event(24, 1)
                self.put(at, 3)
                self.event(24, 0x29)
                self.event(24, 16)
                self.assertEqual(self.get(s.ACTION), 7)
                self.assertEqual((self.get(s.ARMS), self.get(s.FREEZES)), (0, 0))
        self.setUp()
        self.event(24, 1)
        self.assertEqual(self.event(21, 1), 0)
        self.event(24, 16)
        self.assertEqual(self.get(s.ACTION), 7)
        self.assertEqual(self.get(s.OWN), 0)
        self.assertEqual(self.event(12, 1), 0)

    def test_foreign_modal_route_cancels_recognition(self):
        self.event(24, 1)
        self.native_value(s.ROUTE_STOCK, 1)  # Modal consumes: no eligible view offered.
        self.assertEqual(self.call(s.ROUTE, 0x200100, 0x208400), 1)
        self.assertEqual(self.get(s.OWN), 4)
        self.event(24, 16)
        self.assertEqual((self.get(s.ARMS), self.get(s.FREEZES)), (0, 0))
        self.assertEqual(self.get(s.VIEW), 0x200100)

    def test_modal_owned_releases_clear_only_sketch_latches(self):
        self.event(24, 1)
        self.event(17, 1)
        self.native_value(s.ROUTE_STOCK, 1)
        for key in (17, 24):
            self.put(0x208400, 0, 0, 0, key, 0)
            self.assertEqual(self.call(s.ROUTE, 0x200100, 0x208400), 1)
        self.assertEqual((self.get(s.OWN), self.get(s.FUNC_OWN)), (0, 0))
        self.assertEqual(self.get(s.ARMS), 1)
        self.assertEqual(self.get(s.FREEZES), 0)

    def test_len_refusal_independent_selection_and_ready_cache(self):
        self.put(s.STATE + s.BUF, 4)
        self.native_value(s.GETTERS[2], 8)
        self.native_value(0x4011DE70, 1)
        self.event(24, 3)
        self.event(24, 18)
        self.event(17, 0)
        self.assertEqual(self.get(s.ACTION), 5)
        self.assertEqual(self.get(s.LATCH), 4)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(w.DEST, 4), "big"), 0)
        self.assertEqual(self.call(s.READY, 1), 0)
        self.put(w.STATE + 96, 300)
        self.put(0x405B1368 + 300 * 16, 123, 456, 1000, 1)
        self.assertEqual(self.call(s.READY, 1), 1)
        self.put(0x405B1368 + 300 * 16 + 8, 0)
        self.assertEqual(self.call(s.READY, 1), 0)

    def test_dry_arm_recognizes_each_supported_length_without_submitting_jobs(self):
        for raw in (4, 5, 6):
            with self.subTest(raw=raw):
                self.setUp()
                self.native_value(s.GETTERS[2], raw)
                self.native_value(0x4011DE70, 1)
                self.event(24, 3)
                self.event(24, 18)
                self.event(17, 0)
                self.assertEqual(self.get(s.ACTION), 1)
                self.assertEqual(self.get(s.ARMS), 1)
                self.assertEqual(
                    int.from_bytes(self.cpu.mem_read(nb.STATE + nb.ARMS, 4), "big"), 0
                )
                self.assertNotIn("!", s.LABELS[f"len{raw}"])
        self.assertIn("!", s.LABELS["len7"])
        self.assertIn("!", s.LABELS["len8"])

    def test_native_update_refreshes_without_input_and_skips_closed_views(self):
        self.put(s.PANEL_TICK, 100)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual((self.get(s.LAST_PAINT), self.get(s.UPDATES)), (100, 1))
        self.put(s.PANEL_TICK, 111)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.UPDATES), 1)
        self.put(s.PANEL_TICK, 112)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.UPDATES), 2)
        self.cpu.mem_write(0x200130, b"\1")
        self.put(s.PANEL_TICK, 200)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.UPDATES), 2)
        self.cpu.mem_write(0x200130, b"\0")
        self.put(s.STATE + s.LAST_PAINT, 0xFFFFFFFA)
        self.put(s.PANEL_TICK, 6)
        self.call(s.UPDATE, 0x200100)
        self.assertEqual(self.get(s.UPDATES), 3)

    def test_frozen_list_pages_and_cache_epoch_status_guards(self):
        self.native_value(s.CLEAR, 1)  # Raster service is separately checked below.
        self.native_value(s.TEXT, 0)
        self.native_value(s.PRINT, 0)
        self.put(s.STATE + s.PAGE, 1)
        self.put(frozen.STATE, 7, 5)
        association = (0x7FFB0001, 123, 640, 1)
        for index in range(5):
            record = frozen.SNAP + index * 64
            slot = 312 + index
            self.put(record, 1, 0x7FFC0001 + index, 7)
            self.put(record + 16, *association)
            self.put(record + 36, slot)
            self.put(0x405B1368 + slot * 16, *association)
            self.cpu.mem_write(0x405B6368 + slot * 16, f"BUF1-{index}".encode() + b"\0")
        rows = []
        labels = []

        def observe(uc, pc, *_):
            stack = uc.reg_read(r.UC_M68K_REG_A7)
            if pc == s.PRINT:
                pointer = int.from_bytes(uc.mem_read(stack + 8, 4), "big")
                if bytes(uc.mem_read(pointer, 10)).startswith(b"%03u %s"):
                    rows.append(int.from_bytes(uc.mem_read(stack + 12, 4), "big"))
            else:
                pointer = int.from_bytes(uc.mem_read(stack + 24, 4), "big")
                labels.append(bytes(uc.mem_read(pointer, 32)).split(b"\0")[0])

        self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=s.PRINT, end=s.PRINT)
        self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=s.TEXT, end=s.TEXT)
        self.call(s.DRAW, 0x200100, 0x200500)
        self.assertEqual(rows, [312, 313, 314, 315])
        rows.clear()
        labels.clear()
        self.put(s.STATE + s.FIRST, 4)
        self.call(s.DRAW, 0x200100, 0x200500)
        self.assertEqual(rows, [316])
        for word in range(4):
            with self.subTest(cache_word=word):
                rows.clear()
                labels.clear()
                self.put(0x405B1368 + 316 * 16, *association)
                self.put(0x405B1368 + 316 * 16 + word * 4, association[word] + 1)
                self.call(s.DRAW, 0x200100, 0x200500)
                self.assertEqual(rows, [])
                self.assertIn(b"NO READY TAKES", labels)
        self.put(0x405B1368 + 316 * 16, *association)
        for at, value in ((frozen.SNAP + 4 * 64 + 8, 6), (frozen.SNAP + 4 * 64, 2)):
            rows.clear()
            self.put(at, value)
            self.call(s.DRAW, 0x200100, 0x200500)
            self.assertEqual(rows, [])
            self.put(frozen.SNAP + 4 * 64, 1, 0x7FFC0005, 7)

    def test_canvas_clear_is_bounded_and_uses_native_memset(self):
        c = Code()
        c.emit("226f0004 203c00000100")
        c.label("zero")
        c.emit("4299 5380")
        c.branch(6, "zero")
        c.emit("4e75")
        self.cpu.mem_write(0x401360F4, c.finish(0x401360F4))
        self.put(0x200500, 0, 128, 64, 2, 0x209000)
        self.cpu.mem_write(0x208FFC, b"\xaa" * 1032)
        self.assertEqual(self.call(s.CLEAR, 0x200500), 1)
        self.assertEqual(bytes(self.cpu.mem_read(0x209000, 1024)), bytes(1024))
        self.assertEqual(bytes(self.cpu.mem_read(0x208FFC, 4)), b"\xaa" * 4)
        self.assertEqual(bytes(self.cpu.mem_read(0x209400, 4)), b"\xaa" * 4)
        self.put(0x200504, 256)
        self.assertEqual(self.call(s.CLEAR, 0x200500), 0)

    def test_native_input_preserves_callee_saved_registers(self):
        regs = [
            getattr(r, "UC_M68K_REG_" + name)
            for name in (
                "D2",
                "D3",
                "D4",
                "D5",
                "D6",
                "D7",
                "A2",
                "A3",
                "A4",
                "A5",
                "A6",
            )
        ]
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x210000 + i * 16)
        before = [self.cpu.reg_read(reg) for reg in regs]
        self.event(24, 1)
        self.assertEqual([self.cpu.reg_read(reg) for reg in regs], before)
