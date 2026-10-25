"""Execute next-bar ColdFire code with explicitly prepared service boundaries."""

import struct
import unittest

from buf_native_support import PerformanceFixture, r, u

from lab import buf_next_bar as b
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code


@unittest.skipIf(u is None, "Requires configured native CPU runtime")
class NextBarTests(PerformanceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for at, size in (
            (b.BASE, b.END - b.BASE),
            (0x400D8000, 4096),
            (0x40016000, 4096),
            (0x4002F000, 4096),
            (0x402A1000, 4096),
            (0x40138000, 4096),
            (0x4004C000, 4096),
            (0x400F0000, 4096),
            (0x40023000, 4096),
            (0x210000, 0x20000),
        ):
            self.cpu.mem_map(at, size)
        for at, code in b.payload(
            clock_fix=getattr(self, "clock_profile", False),
            arm_diagnostics=getattr(self, "clock_profile", False),
        ).items():
            self.cpu.mem_write(at, code)
        self.cpu.mem_write(b.CLOCK_SITE + 8, bytes.fromhex("4e75"))
        self.cpu.mem_write(b.ARM_CALLER, bytes.fromhex("4ef90020ff00"))
        # Original short controller bodies; only normalization/job boundaries
        # below are native stubs. No host callback chooses a musical event.
        originals = {
            b.ARM_SITE + 8: "2f2800104eb94004d9e0508f70012f4000044ef94002f47a",
            b.START: "48780002206f00082f2800104eb94004d9e0508f42af00044ef94002f47a",
            0x4004D9E0: "206f0004216f000800a44e75",
            0x4002F47A: "41ef000423d0402a14904e75",
            b.DISCARD: "2f0a246f000842a72f2a00104eb94004d9e0487800024eb94002f47a42aa00384fef000c245f4e75",
            b.READY: "2f0a246f000842a72f2a00104eb94004d9e042aa0038508f245f4e75",
            b.COUNT: "206f0004202800384e75",
        }
        for at, code in originals.items():
            self.cpu.mem_write(at, bytes.fromhex(code))
        self.native_value(b.CLOCK_MODE, b.CLOCK_VALUE)
        c = Code()
        c.imm("2039", 0x209000 - 24)
        c.emit("4e75")
        self.cpu.mem_write(b.RLEN_GET, c.finish(b.RLEN_GET))
        self.native_value(b.CHANNEL, 0)
        c = Code()
        c.imm("203c", 3)
        c.imm("23c0", 0x2071A4)
        c.emit("7000 4e75")
        self.cpu.mem_write(b.STOP, c.finish(b.STOP))
        for at, field, value in (
            (0x400F0AB8, 0x207618, 1),
            (w.WORKER, 0x20760C, 0),
            (w.ASSIGN, 0x207610, 0),
        ):
            self.put(field, value)
            c = Code()
            c.imm("2039", field)
            c.emit("4e75")
            self.cpu.mem_write(at, c.finish(at))
        self.native_value(0x40198A16, 0x207700)
        c = Code()
        c.imm("2039", 0x207614)
        c.emit("5280")
        c.imm("23c0", 0x207614)
        c.emit("7000 4e75")
        self.cpu.mem_write(w.ABORT, c.finish(w.ABORT))
        self.put(w.DEST, 1)
        self.put(0x209000 - 24, b.RLEN)
        self.put(0x4316501C, 0x210000)
        self.cpu.mem_write(0x210000 + 0x1DB74, b.MASTER)
        self.put(b.STATE + b.ENABLED, 1)
        self.put(0x207038, 56464)
        self.clock(3)

    def native_value(self, at, value):
        c = Code()
        c.imm("203c", value)
        c.emit("4e75")
        self.cpu.mem_write(at, c.finish(at))

    def clock(self, step):
        self.cpu.mem_write(0x43164F98, struct.pack(">H", step))
        stack, stop = 0x20E000, 0x20FF00
        self.cpu.mem_write(stack, bytes(148))
        self.put(stack + 148, stop)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        self.cpu.emu_start(b.IRQ, stop, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 152)

    def arm(self, caller=None):
        caller = b.ARM_CALLER if caller is None else caller
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, caller, 0x207000)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        self.cpu.emu_start(b.ARM, stop, count=100000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def edge(self):
        last = self.get(b.STATE + b.LAST_STEP)
        for step in range(last + 1, 16):
            self.clock(step)
        self.put(b.TICK, self.get(b.TICK) + 1000)
        self.clock(0)
        self.clock(1)

    def test_real_wrap_only_duplicate_disabled_jump_and_transport(self):
        self.assertEqual(self.get(b.STATE + b.SERIAL), 0)
        self.clock(3)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 0)
        self.clock(0)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 0)
        epoch = self.get(b.STATE + b.CEPOCH)
        for step in range(1, 16):
            self.clock(step)
        self.clock(0)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 0)
        self.clock(1)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 1)
        self.clock(1)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 1)
        self.put(0x43164F94, 0)
        self.clock(0)
        self.assertEqual(self.get(b.STATE + b.VALID), 0)
        self.assertGreater(self.get(b.STATE + b.CEPOCH), epoch)
        self.put(b.STATE + b.ENABLED, 0)
        self.put(0x43164F94, 1)
        self.clock(15)
        self.clock(0)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 1)

    def test_unsupported_master_never_arms(self):
        self.cpu.mem_write(0x210000 + 0x1DB74, b"\0\x20")
        self.clock(4)
        self.assertEqual(self.get(b.STATE + b.VALID), 0)
        self.assertEqual(self.arm(), 0xFFFFFFFF)

    def clock_fix(self):
        for at, code in b.payload(arm_diagnostics=True, clock_fix=True).items():
            self.cpu.mem_write(at, code)
        # setUp already executed the ordinary IRQ. Discard translated blocks
        # before exercising a different opt-in image at the same addresses.
        self.cpu.ctl_remove_cache(b.BASE, b.END)
        self.put(b.STATE + b.VALID, 0)

    def test_clock_fix_matches_stock_transport_and_ignores_fixture_only_bytes(self):
        for flags in ((1, 1), (1, 0), (0, 1)):
            with self.subTest(flags=flags):
                self.setUp()
                self.clock_fix()
                self.put(0x43164F94, flags[0])
                self.put(0x43165010, flags[1])
                header = bytearray(b.MASTER)
                for i in (2, 3, 4, 7, 8, 9, 10, 11):
                    header[i] ^= 0x55
                self.cpu.mem_write(0x210000 + 0x1DB74, bytes(header))
                self.clock(4)
                self.assertEqual(self.get(b.STATE + b.VALID), 1)
                self.assertEqual(self.arm(), 0)
                self.assertEqual(self.call(b.CHECK), 0)
                self.assertEqual(self.get(b.STATE + b.STARTS), 0)
                self.edge()
                self.assertEqual(self.get(b.STATE + b.SERIAL), 1)

    def test_clock_fix_refusals_and_mid_request_invalidation(self):
        for field, value, reason in ((0, 32, 3), (5, 1, 4), (6, 1, 5), (6, 3, 5)):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.clock_fix()
                self.clock(4)
                self.assertEqual(self.arm(), 0)
                at = 0x210000 + 0x1DB74 + field
                self.cpu.mem_write(
                    at, struct.pack(">H", value) if field == 0 else bytes([value])
                )
                # CHECK must reject a changed context even before the next IRQ.
                self.assertEqual(self.call(b.CHECK), 0xFFFFFFFF)
                self.clock(5)
                self.assertEqual(self.get(b.STATE + b.VALID), 0)
                self.assertEqual(self.get(b.STATE + b.CLOCK_DIAG), reason)
                self.assertEqual(self.get(b.STATE + b.CLOCK_DIAG_VALUE), value)
                self.call(b.STEP)
                self.assertEqual(self.get(b.STATE + b.STARTS), 0)
                self.assertEqual(self.get(b.STATE + b.USES), 0)
        for flags in ((0, 0), (2, 0), (1, 2)):
            self.setUp()
            self.clock_fix()
            self.put(0x43164F94, flags[0])
            self.put(0x43165010, flags[1])
            self.clock(4)
            self.assertEqual(self.get(b.STATE + b.VALID), 0)
            self.assertEqual(self.get(b.STATE + b.CLOCK_DIAG), 1)
            self.assertEqual(
                self.get(b.STATE + b.CLOCK_DIAG_VALUE), flags[0] | flags[1]
            )
        for at, value, reason in ((0x4316501C, 0, 2), (0x43164F98, 16 << 16, 6)):
            self.setUp()
            self.clock_fix()
            self.put(at, value)
            self.clock(16 if reason == 6 else 4)
            self.assertEqual(self.get(b.STATE + b.VALID), 0)
            self.assertEqual(self.get(b.STATE + b.CLOCK_DIAG), reason)

    def test_clock_fix_retains_wrap_jump_and_missing_clock_guards(self):
        self.clock_fix()
        self.assertEqual(self.arm(), 0xFFFFFFFF)
        self.assertEqual(self.get(b.STATE + b.ARM_DIAG), 11)
        self.clock(3)
        self.assertEqual(self.arm(), 0)
        self.clock(0)  # A jump is not a bar edge.
        self.clock(1)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)
        self.assertEqual(self.get(b.STATE + b.USES), 0)
        self.assertEqual(self.get(b.STATE + b.SERIAL), 0)

    def test_clock_fix_keeps_duration_late_edge_and_cancellation_guards(self):
        self.clock_profile = True
        for name in (
            "test_one_bar_start_stop_normalize_and_native_completion",
            "test_late_or_missed_boundary_cancels",
            "test_supported_lengths_stop_and_publish_after_the_exact_native_bar_count",
            "test_multibar_missed_receipt_and_late_final_edge_cancel_without_publication",
        ):
            with self.subTest(case=name):
                self.setUp()
                getattr(self, name)()
        self.clock_profile = False

    def test_operation_busy_snapshot_is_diagnostic_only_and_atomic_with_count(self):
        for at, code in b.payload(
            arm_diagnostics=True, operation_diagnostics=True
        ).items():
            self.cpu.mem_write(at, code)
        self.cpu.ctl_remove_cache(b.BASE, b.END)
        words = tuple(range(101, 101 + len(q.OP_FIELDS)))
        self.put(q.STATE + q.OP_SITE, *words)
        self.put(q.STATE + 56, 1)
        before = bytes(self.cpu.mem_read(b.STATE, b.OP_CONTEXT))
        self.assertEqual(self.call(b.ARM_ONLY, 0x207000, 1), 0xFFFFFFF9)
        self.assertEqual(self.get(b.STATE + b.ARM_DIAG), 4)
        self.assertEqual(self.get(b.STATE + b.ARM_DIAG_VALUE), 1)
        self.assertEqual(
            tuple(self.get(b.STATE + b.OP_CONTEXT + i * 4) for i in range(len(words))),
            words,
        )
        self.assertEqual(self.get(q.STATE + 56), 1)
        self.assertEqual(self.get(w.STATE + 12), 0)
        # Only the existing two diagnostic words change below OP_CONTEXT.
        after = bytes(self.cpu.mem_read(b.STATE, b.OP_CONTEXT))
        self.assertEqual(before[: b.ARM_DIAG], after[: b.ARM_DIAG])
        self.assertEqual(before[b.ARM_DIAG_VALUE + 4 :], after[b.ARM_DIAG_VALUE + 4 :])
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0x2700, 0x2000)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)

    def test_unobserved_clock_selector_refuses(self):
        self.native_value(b.CLOCK_MODE, 1)
        self.assertEqual(self.arm(), 0xFFFFFFFF)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)

    def test_one_bar_start_stop_normalize_and_native_completion(self):
        self.assertEqual(self.arm(), 0)
        self.assertEqual(self.get(b.STATE + b.PHASE), 1)
        self.assertEqual(self.get(w.STATE + 12), 1)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)
        self.edge()
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 1)
        self.assertEqual(self.get(0x2071A4), 2)
        self.assertEqual(self.get(0x402A1490), 0)
        self.edge()
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STOPS), 1)
        self.assertEqual(self.get(b.STATE + b.PHASE), 3)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 3)
        self.put(0x2071A4, 4)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 4)
        self.assertEqual(self.get(w.STATE + 28), 56464)
        self.assertEqual(self.get(w.STATE + 24), 0)
        self.assertEqual(self.get(w.STATE + 32), 1)
        self.assertEqual(self.call(b.WORKER), 0)
        self.call(b.DONE, 0x207700, 0)
        self.assertEqual(self.get(b.STATE + b.USES), 1)
        self.assertEqual(self.get(b.STATE + b.RESULT), 1)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(0x2071A4), 0)

    def test_cancel_second_chord_and_stop_before_edge_do_not_capture(self):
        self.arm()
        self.arm()
        self.assertEqual(self.get(b.STATE + b.CANCELS), 1)
        self.edge()
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)
        self.arm()
        self.put(b.STATE + b.CANCEL, 1)
        self.call(b.STEP)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)

    def test_late_or_missed_boundary_cancels(self):
        self.arm()
        self.edge()
        self.put(b.TICK, self.get(b.TICK) + b.LATENCY + 1)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)
        self.arm()
        self.edge()
        self.edge()
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STARTS), 0)

    def test_changes_cancel_without_publication(self):
        for at in (
            b.STATE + b.KIT,
            b.STATE + b.EPOCH,
            b.STATE + b.CLOCK_EPOCH,
            b.SETTINGS,
            w.DEST,
        ):
            self.setUp()
            self.arm()
            old = self.get(at)
            self.put(at, old + 1)
            self.call(b.STEP)
            self.assertEqual(self.get(b.STATE + b.USES), 0)
            self.assertEqual(self.get(b.STATE + b.PHASE), 0)

    def test_empty_destination_does_not_follow_selected_sample_or_machine(self):
        self.put(w.STATE + 80, 0)
        self.put(w.DEST, 2)
        self.slot(5, 44)
        self.cpu.mem_write(0x204000 + 5 * 0x450 + 0xD6, b"\x02")
        self.assertEqual(self.arm(), 0)
        self.assertEqual(self.get(b.STATE + b.DEST), 2)
        self.assertEqual(self.get(b.STATE + b.TRACK), 5)  # Diagnostic only.
        self.assertEqual(self.call(b.CHECK), 0)

    def test_track_selection_and_performance_edits_do_not_cancel(self):
        self.arm()
        for stage in ("armed", "capturing"):
            with self.subTest(stage=stage):
                self.slot(5, 44)
                for off in (0x40, 0x58, 0xA0):
                    self.put(0x204000 + 5 * 0x450 + off, 123)
                self.cpu.mem_write(0x204000 + 2 * 0x450 + 0xD6, b"\x02")
                self.put(0x209000 - 28, 99)  # Monitor is not capture identity.
                self.assertEqual(self.call(b.CHECK), 0)
                self.assertEqual(self.get(w.DEST), 1)
                self.edge()
                self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.STOPS), 1)

    def test_other_lengths_and_max_refuse_instead_of_recording_one_bar(self):
        for raw in (0, 1, 2, 3, 7, 8, 0xFFFFFFFF):
            with self.subTest(raw=raw):
                self.put(0x209000 - 24, raw)
                self.assertEqual(self.arm(), 0xFFFFFFFF)
                self.assertEqual(self.get(b.STATE + b.RESULT), 0xFFFFFFFA)
                self.assertEqual(self.get(b.STATE + b.PHASE), 0)
                self.assertEqual(self.get(w.STATE + 12), 0)

    def test_supported_lengths_stop_and_publish_after_the_exact_native_bar_count(self):
        for raw, bars in b.RLEN_BARS.items():
            for explicit in (False, True):
                with self.subTest(raw=raw, bars=bars, explicit=explicit):
                    self.setUp()
                    self.put(0x209000 - 24, raw)
                    frames = 56464 * bars
                    self.put(0x207038, frames)
                    result = (
                        self.call(b.ARM_ONLY, 0x207000, 2) if explicit else self.arm()
                    )
                    self.assertEqual(result, 0)
                    self.assertEqual(self.get(b.STATE + b.DURATION_BARS), bars)
                    self.edge()
                    self.call(b.STEP)
                    start = self.get(b.STATE + b.START_BAR)
                    for elapsed in range(1, bars + 1):
                        self.call(
                            b.STEP
                        )  # Polls/duplicate receipts cannot advance duration.
                        self.assertEqual(self.get(b.STATE + b.STOPS), 0)
                        self.edge()
                        self.call(b.STEP)
                        self.assertEqual(
                            self.get(b.STATE + b.LAST_BAR), start + elapsed
                        )
                        self.assertEqual(
                            self.get(b.STATE + b.STOPS), int(elapsed == bars)
                        )
                        if elapsed < bars:
                            self.assertEqual(self.get(b.STATE + b.PHASE), 2)
                    self.assertEqual(self.get(b.STATE + b.PHASE), 3)
                    self.put(0x2071A4, 4)
                    self.call(b.STEP)
                    self.assertEqual(self.get(w.STATE + 28), frames)
                    self.assertEqual(self.call(b.WORKER), 0)
                    self.call(b.DONE, 0x207700, 0)
                    self.assertEqual(self.get(b.STATE + b.USES), 1)
                    self.assertEqual(self.get(b.STATE + b.RESULT), 1)

    def test_multibar_missed_receipt_and_late_final_edge_cancel_without_publication(
        self,
    ):
        for raw, bars in ((5, 2), (6, 4)):
            for missed in (False, True):
                with self.subTest(raw=raw, missed=missed):
                    self.setUp()
                    self.put(0x209000 - 24, raw)
                    self.arm()
                    self.edge()
                    self.call(b.STEP)
                    if missed:
                        self.edge()
                        self.edge()
                    else:
                        for _ in range(bars - 1):
                            self.edge()
                            self.call(b.STEP)
                        self.edge()
                        self.put(b.TICK, self.get(b.TICK) + b.LATENCY + 1)
                    self.call(b.STEP)
                    self.assertEqual(self.get(b.STATE + b.PHASE), 0)
                    self.assertEqual(self.get(b.STATE + b.STOPS), 0)
                    self.assertEqual(self.get(b.STATE + b.USES), 0)
                    self.assertEqual(self.get(w.STATE + 12), 0)

    def test_multibar_cancel_and_capture_setting_change_keep_committed_generations(
        self,
    ):
        for raw in (5, 6):
            for changed in (False, True):
                with self.subTest(raw=raw, changed=changed):
                    self.setUp()
                    self.put(0x209000 - 24, raw)
                    self.arm()
                    self.edge()
                    self.call(b.STEP)
                    self.edge()
                    if raw == 6:
                        self.call(b.STEP)
                    committed = bytes(self.cpu.mem_read(n.GEN, 8 * 64))
                    if changed:
                        self.put(0x209000 - 24, 4)
                    else:
                        self.put(b.STATE + b.CANCEL, 1)
                    self.call(b.STEP)
                    self.assertEqual(self.get(b.STATE + b.PHASE), 0)
                    self.assertEqual(self.get(b.STATE + b.USES), 0)
                    self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 8 * 64)), committed)

    def test_multibar_capacity_uses_native_sample_clock_even_when_input_count_saturates(
        self,
    ):
        self.put(0x209000 - 24, 6)
        self.put(b.TICK, 0xFFFF0000)
        self.arm()
        self.edge()
        self.call(b.STEP)
        start = self.get(b.STATE + b.START_TICK)
        self.put(0x207038, b.MAX_CAPTURE_FRAMES)
        committed = bytes(self.cpu.mem_read(n.GEN, 8 * 64))
        self.put(b.TICK, (start + b.MAX_CAPTURE_FRAMES) & 0xFFFFFFFF)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 2)
        self.put(b.TICK, (start + b.MAX_CAPTURE_FRAMES + 1) & 0xFFFFFFFF)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)
        self.assertEqual(self.get(b.STATE + b.RESULT), b.CAPACITY_RESULT & 0xFFFFFFFF)
        self.assertEqual(self.get(b.STATE + b.USES), 0)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(0x2071A4), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 8 * 64)), committed)

    def test_explicit_arm_latches_argument_at_normal_or_different_dest_and_never_toggles(
        self,
    ):
        for normal in (0, 3):
            with self.subTest(normal=normal):
                self.setUp()
                self.put(w.DEST, normal)
                self.put(w.STATE + 80, 0)  # Empty capture needs no seed take.
                self.slot(5, 44)
                self.assertEqual(self.call(b.ARM_ONLY, 0x207000, 2), 0)
                self.assertEqual(self.get(w.DEST), normal)
                self.assertEqual(self.get(b.STATE + b.DEST), 2)
                self.assertEqual(self.get(b.STATE + b.NORMAL_DEST), normal)
                snapshot = bytes(self.cpu.mem_read(b.STATE, 0x240))
                self.assertEqual(
                    self.call(b.ARM_ONLY, 0x207000, 4), b.ARM_BUSY & 0xFFFFFFFF
                )
                self.assertEqual(bytes(self.cpu.mem_read(b.STATE, 0x240)), snapshot)
                self.assertEqual(self.get(b.STATE + b.CANCELS), 0)
                self.assertEqual(self.call(b.CHECK), 0)
                self.edge()
                self.call(b.STEP)
                self.edge()
                self.call(b.STEP)
                self.put(0x2071A4, 4)
                self.call(b.STEP)
                self.assertEqual(self.get(w.STATE + 56), 2)
                self.assertEqual(self.call(b.WORKER), 0)
                self.call(b.DONE, 0x207700, 0)
                self.assertEqual(self.get(b.STATE + b.USES), 1)
                self.assertEqual(self.get(w.DEST), normal)

    def test_explicit_refusal_and_changed_normal_destination_preserve_ownership(self):
        for buf in (0, 5, 0xFFFFFFFF):
            self.assertEqual(self.call(b.ARM_ONLY, 0x207000, buf), 0xFFFFFFFF)
            self.assertEqual(self.get(w.STATE + 12), 0)
        for at, value, expected in (
            (0x209000 - 24, 8, b.ARM_LENGTH),
            (b.STATE + b.VALID, 0, b.ARM_REFUSED),
            (0x2071A4, 2, b.ARM_BUSY),
            (w.STATE + 12, 3, b.ARM_BUSY),
        ):
            with self.subTest(at=hex(at)):
                self.setUp()
                self.put(w.DEST, 0)
                self.put(at, value)
                before = bytes(self.cpu.mem_read(b.STATE, 0x240))
                self.assertEqual(
                    self.call(b.ARM_ONLY, 0x207000, 2), expected & 0xFFFFFFFF
                )
                self.assertEqual(bytes(self.cpu.mem_read(b.STATE, 0x240)), before)
                self.assertEqual(self.get(w.DEST), 0)
                self.assertEqual(
                    self.get(w.STATE + 12), value if at == w.STATE + 12 else 0
                )
        self.setUp()
        self.put(w.DEST, 0)
        self.call(b.ARM_ONLY, 0x207000, 2)
        self.put(w.DEST, 3)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)
        self.assertEqual(self.get(b.STATE + b.USES), 0)
        self.assertEqual(self.get(w.DEST), 3)

    def test_diagnostic_admission_identifies_first_guard_without_changing_context(self):
        cases = (
            ("REQUEST", b.STATE + b.PHASE, 4, 0x207000, 1),
            ("BUF", None, 5, 0x207000, 5),
            ("WORKER", w.STATE + 12, 3, 0x207000, 1),
            ("FREEZE", q.STATE + 56, 2, 0x207000, 1),
            ("LOCK", n.STATE + 24, 7, 0x207000, 1),
            ("LOADER", q.STOCK_BUSY, 1, 0x207000, 1),
            ("PLAY", 0x43164F94, 0, 0x207000, 1),
            ("CTRL", None, 0, 0, 1),
            ("RECORDER", 0x2071A4, 4, 0x207000, 1),
            ("LENGTH", 0x209000 - 24, 8, 0x207000, 1),
            ("CLOCK", b.STATE + b.VALID, 0, 0x207000, 1),
            ("MODE", None, 3, 0x207000, 1),
            ("SETUP", w.STATE + 64, 0, 0x207000, 1),
            ("POOL", w.STATE + 68, 0, 0x207000, 1),
            ("KIT", 0x80004704, 0, 0x207000, 1),
        )
        for index, (reason, at, value, controller, buf) in enumerate(cases, 1):
            with self.subTest(reason=reason):
                self.setUp()
                self.cpu.mem_write(b.ARM_ONLY, b.arm_only(diagnostics=True))
                self.native_value(b.INIT_BODY, 0)
                if at is not None:
                    self.put(at, value)
                if reason == "MODE":
                    self.native_value(b.CLOCK_MODE, value)
                if reason == "PLAY":
                    self.put(0x43165010, 0)
                if reason == "REQUEST":
                    self.put(
                        w.STATE + 12, 3
                    )  # First failure wins over another busy flag.
                before = bytes(self.cpu.mem_read(b.STATE, 0x240))
                worker = bytes(self.cpu.mem_read(w.STATE, 0x100))
                result = self.call(b.ARM_ONLY, controller, buf)
                self.assertEqual(result, b.ARM_DIAGNOSTICS[index - 1][1] & 0xFFFFFFFF)
                self.assertEqual(self.get(b.STATE + b.ARM_DIAG), index)
                self.assertEqual(self.get(b.STATE + b.ARM_DIAG_VALUE), value)
                after = bytes(self.cpu.mem_read(b.STATE, 0x240))
                self.assertEqual(after[: b.ARM_DIAG], before[: b.ARM_DIAG])
                self.assertEqual(
                    after[b.ARM_DIAG_VALUE + 4 :], before[b.ARM_DIAG_VALUE + 4 :]
                )
                self.assertEqual(bytes(self.cpu.mem_read(w.STATE, 0x100)), worker)

    def test_diagnostic_success_matches_original_admission_and_clears_old_diagnostic(
        self,
    ):
        outcomes = []
        for enabled in (False, True):
            self.setUp()
            self.cpu.mem_write(b.ARM_ONLY, b.arm_only(diagnostics=enabled))
            if enabled:
                self.put(b.STATE + b.ARM_DIAG, 999, 123)
            self.assertEqual(self.call(b.ARM_ONLY, 0x207000, 1), 0)
            self.assertEqual(self.get(b.STATE + b.ARM_DIAG), 0)
            self.assertEqual(self.get(b.STATE + b.ARM_DIAG_VALUE), 0)
            outcomes.append(
                (
                    bytes(self.cpu.mem_read(b.STATE, 0x240)),
                    bytes(self.cpu.mem_read(w.STATE, 0x100)),
                )
            )
        self.assertEqual(outcomes[0], outcomes[1])

    def test_normal_use_honors_buf_lease_without_mutating_worker_context(self):
        self.native_value(b.USE_STOCK, 123)
        self.cpu.mem_write(0x400232D2, bytes.fromhex("70004e75"))
        self.put(w.DEST, 0)
        self.assertEqual(self.call(b.USE_GATE), 123)
        for lease in (1, 3):
            self.put(w.STATE + 12, lease)
            before = bytes(self.cpu.mem_read(w.STATE, 256))
            self.assertEqual(self.call(b.USE_GATE), 0)
            self.assertEqual(bytes(self.cpu.mem_read(w.STATE, 256)), before)
            self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D3), 1)

    def test_publication_primitive_does_not_write_any_track_assignment(self):
        # Execute the publication primitive itself. Loader/registry/free/LP0
        # service boundaries are prepared native RTS bodies in this unit case.
        self.cpu.mem_map(0x40153000, 4096)
        self.cpu.mem_write(w.ASSIGN, w.assign(assign_track=False))
        for at in (n.UNLOAD, n.CLEAR, 0x40154540, n.REGISTER, w.RETIRE, w.FLUSH):
            self.cpu.mem_write(at, bytes.fromhex("70004e75"))
        self.put(w.STATE + 20, 0x207A00)
        self.put(w.STATE + 36, 300)
        self.put(w.STATE + 44, 0x204000)
        self.put(w.STATE + 72, 304)
        self.put(w.STATE + 56, 1)
        self.put(w.STATE + 60, self.get(n.STATE))
        self.put(w.STATE + 160, 1)
        self.put(w.STATE + 80, 0)
        self.slot(0, 300)
        self.slot(4, 300)
        self.slot(5, 44)
        self.cpu.mem_write(0x204000 + 5 * 0x450 + 0xD6, b"\x02")
        kit = bytes(self.cpu.mem_read(0x204000, 16 * 0x450))
        self.assertEqual(self.call(w.ASSIGN, 300, 5, 0x204000), 0)
        self.assertEqual(bytes(self.cpu.mem_read(0x204000, 16 * 0x450)), kit)
        self.assertEqual(self.get(0x209000 + 300 * 16), 0x7FFD0001)
        self.assertEqual(self.get(w.STATE + 80), 1)

    def test_capture_cancel_and_normalization_wait(self):
        self.arm()
        self.edge()
        self.call(b.STEP)
        self.put(b.STATE + b.CANCEL, 1)
        self.call(b.STEP)
        self.assertEqual(self.get(0x2071A4), 0)
        self.assertEqual(self.get(b.STATE + b.USES), 0)
        self.arm()
        self.edge()
        self.call(b.STEP)
        self.edge()
        self.call(b.STEP)
        self.put(b.STATE + b.CANCEL, 1)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 5)
        self.put(0x2071A4, 4)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)

    def publishing(self):
        self.arm()
        self.edge()
        self.call(b.STEP)
        self.edge()
        self.call(b.STEP)
        self.put(0x2071A4, 4)
        self.call(b.STEP)

    def test_queue_worker_assignment_failure_preserves_completed_capture(self):
        self.put(0x207618, 0)
        self.publishing()
        self.assertEqual(self.get(b.STATE + b.RESULT), 0xFFFFFFFD)
        self.assertEqual(self.get(0x2071A4), 4)
        for worker, assignment in ((-1, 0), (0, -1)):
            self.setUp()
            self.publishing()
            self.put(0x20760C, worker & 0xFFFFFFFF)
            self.put(0x207610, assignment & 0xFFFFFFFF)
            status = self.call(b.WORKER)
            self.call(b.DONE, 0x207700, status)
            self.assertEqual(self.get(b.STATE + b.USES), 0)
            self.assertEqual(self.get(w.STATE + 12), 0)
            self.assertEqual(self.get(0x2071A4), 4)

    def test_publishing_cancellation_aborts_only_in_completion(self):
        self.publishing()
        self.put(b.STATE + b.CANCEL, 1)
        self.call(b.STEP)
        self.assertEqual(self.get(b.STATE + b.PHASE), 4)
        self.assertEqual(self.get(w.STATE + 12), 1)
        self.call(b.DONE, 0x207700, 0)
        self.assertEqual(self.get(0x207614), 1)
        self.assertEqual(self.get(b.STATE + b.USES), 0)

    def test_stale_project_never_discards_or_releases_another_job(self):
        self.arm()
        self.put(n.STATE, 2)
        self.put(0x2071A4, 2)
        self.call(b.CANCEL_FN)
        self.assertEqual(self.get(w.STATE + 12), 1)
        self.assertEqual(self.get(0x2071A4), 2)
        self.assertEqual(self.get(b.STATE + b.PHASE), 0)
        self.setUp()
        self.publishing()
        self.put(n.STATE, 2)
        self.put(w.STATE + 12, 3)
        self.call(b.DONE, 0x207700, 0)
        self.assertEqual(self.get(w.STATE + 12), 3)
        self.assertEqual(self.get(0x207614), 0)
        self.assertEqual(self.get(b.STATE + b.RESULT), 0xFFFFFFFB)

    def test_normal_and_other_arm_callers_execute_original_body(self):
        self.put(w.DEST, 0)
        self.arm()
        self.assertEqual(self.get(0x2071A4), 1)
        self.assertEqual(self.get(0x402A1490), 1)
        self.assertEqual(self.get(b.STATE + b.ARMS), 0)
        self.setUp()
        self.arm(caller=0x20FF00)
        self.assertEqual(self.get(0x2071A4), 1)

    def test_register_stack_and_deterministic_repeat(self):
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
            self.cpu.reg_write(reg, 0x200000 + 16 * i)
        expected = [self.cpu.reg_read(reg) for reg in regs]
        self.arm()
        self.call(b.STEP)
        self.assertEqual([self.cpu.reg_read(reg) for reg in regs], expected)
        state = bytes(self.cpu.mem_read(b.STATE, 256))
        self.setUp()
        self.arm()
        self.call(b.STEP)
        self.assertEqual(bytes(self.cpu.mem_read(b.STATE, 256)), state)
