"""Execute real Arp snapshot/journal callbacks through the shared save entry."""

import struct
import unittest

import test_arp_firmware as journal_fixture

from lab import arp_firmware as fw
from lab import arp_firmware_storage as storage
from lab.arp_persistence import encode
from lab.project_save import SavePhases, arp_callbacks, dispatcher

u, r = journal_fixture.u, journal_fixture.r


@unittest.skipIf(u is None, "Configured Unicorn required")
class IntegratedSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        journal_fixture.NativeJournal.setUpClass()

    def execute(self, flex_result=0, stock_result=1, journal_failure=False):
        fixture = journal_fixture.NativeJournal()
        fixture.setUp()
        fixture.call("init", fixture.state, 0, 1)
        cpu = fixture.cpu
        cpu.mem_map(0x61000000, 0x10000)
        locations = dict(
            arp_prepare=0x61001000, arp_commit=0x61002000, arp_cleanup=0x61003000
        )
        for name, code in arp_callbacks(locations, fixture.p).items():
            cpu.mem_write(locations[name], code)
        flex, stock, lookup = 0x61004000, 0x61005000, 0x400F4A74
        phases = SavePhases(
            stock,
            (locations["arp_prepare"], flex),
            (locations["arp_commit"],),
            (locations["arp_cleanup"],),
        )
        cpu.mem_write(0x61000000, dispatcher(0x61000000, phases))
        modes = [i % 4 for i in range(128)]
        cpu.mem_write(fixture.state + fw.MODES, struct.pack(">128I", *modes))
        node = 0x61008000
        cpu.mem_write(node, struct.pack(">I", 7))
        events = []

        def endpoint(machine, pc, _size, _data):
            sp = machine.reg_read(r.UC_M68K_REG_A7)
            if pc == flex:
                self.assertEqual(fixture.u32(fixture.state + fw.BUSY), 1)
                saved = struct.unpack(
                    ">128I", machine.mem_read(fixture.state + fw.SAVE_MODES, 512)
                )
                self.assertEqual(list(saved), modes)
                events.append("flex")
                value = flex_result
            elif pc == stock:
                events.append("stock")
                # User-visible current state may change; journal must use snapshot.
                machine.mem_write(fixture.state + fw.MODES, bytes(512))
                value = stock_result
            elif pc == lookup:
                events.append("serialized-project")
                value = node
            else:
                self.assertEqual(pc, fixture.p["project_hash"])
                events.append("project-hash")
                machine.mem_write(fixture.state + storage.HASH, fixture.hash)
                value = 1
            machine.reg_write(r.UC_M68K_REG_D0, value & 0xFFFFFFFF)
            machine.reg_write(r.UC_M68K_REG_PC, fixture.u32(sp))
            machine.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for target in (flex, stock, lookup, fixture.p["project_hash"]):
            cpu.hook_add(u.UC_HOOK_CODE, endpoint, begin=target, end=target)
        fixture.fault = journal_failure
        sp, stop = 0x6000F000, 0x6000FFE0
        cpu.mem_write(sp, struct.pack(">4I", stop, 123, 7, 0))
        cpu.reg_write(r.UC_M68K_REG_A7, sp)
        cpu.emu_start(0x61000000, stop, count=1_000_000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), sp + 4)
        self.assertEqual(fixture.u32(fixture.state + fw.BUSY), 0)
        return fixture, events, cpu.reg_read(r.UC_M68K_REG_D0), modes

    def test_real_snapshot_and_native_journal_use_final_serialized_identity(self):
        fixture, events, result, modes = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(
            events, ["flex", "stock", "serialized-project", "project-hash"]
        )
        self.assertEqual(fixture.files[65], encode(7, 1, fixture.project, modes))
        self.assertEqual(fixture.u32(fixture.state + fw.STATUS), 1)

    def test_real_cleanup_after_flex_or_stock_failure(self):
        for flex, stock, expected_events in (
            (-1, 1, ["flex"]),
            (0, 0, ["flex", "stock"]),
        ):
            fixture, events, result, _ = self.execute(flex, stock)
            self.assertEqual(events, expected_events)
            self.assertEqual(result, 0)
            self.assertFalse(fixture.files)

    def test_companion_failure_reports_separately_and_preserves_stock_success(self):
        fixture, _, result, _ = self.execute(journal_failure=True)
        self.assertEqual(result, 1)
        self.assertEqual(fixture.u32(fixture.state + fw.STATUS), 0xFFFFFFFF)
