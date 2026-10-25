"""Adapter lifecycle decisions with the real four-mode ColdFire state core."""
import struct
import unittest
from types import SimpleNamespace

from unicorn import m68k_const as regs
from lab.arp_integration import (ArpIntegration, MENU_KEY, PROJECT_LOAD,
    PROJECT_LOAD_RETURN, PROJECT_CACHE, PROJECT_CACHE_RETURN)
from lab.arp_integration import MENU_LOAD, MENU_LOAD_RETURN, MENU_DECODE, PROJECT_READ, PROJECT_READ_RETURN
from lab.arp_modes_emulation import ModesCore


class ArpIntegrationLifecycleTests(unittest.TestCase):
    def adapter(self):
        core = ModesCore(enabled=2)
        adapter = object.__new__(ArpIntegration)
        adapter.machine = SimpleNamespace(uc=core.cpu)
        adapter.direct = False
        adapter.collecting = True
        adapter.playing = False
        adapter.pending_panic = False
        adapter.pending_mode = adapter.pending_view = None
        adapter.menu_events = []
        adapter.menu_releases = []
        adapter.key_owners = {}
        adapter.direct_keys = {}
        adapter.pattern_modes = [2] + [0] * 127
        adapter.pattern_id = adapter.selected_track = 0
        adapter.pending_storage = []
        adapter.pending_unknown_load = False
        adapter.cache_request = adapter.load_binding = adapter.loading = adapter.read_request = None
        adapter.pending_recall = []
        adapter.project_data = 0x41776C9C
        adapter.menu_loading = None
        adapter.storage_events = []
        adapter.card_firmware = None
        adapter.func_down = False
        adapter.destination = lambda: (0, 0)
        adapter.tick = lambda: core.field('tick')
        adapter.core_call = lambda name, *args: core.call(name, *args)[1]
        adapter.outputs = []
        adapter.stock_event = adapter.outputs.append
        return core, adapter

    def menu_key(self, adapter, code, flags):
        event, stack = 0x60005000, 0x6000F000
        adapter.uc.mem_write(event, bytes(12) + struct.pack('>II', code, flags))
        adapter.uc.mem_write(stack, struct.pack('>III', 0, 0, event))
        adapter.uc.reg_write(regs.UC_M68K_REG_A7, stack)
        adapter.menu(adapter.uc, MENU_KEY, 2, None)

    def test_menu_release_after_mode_change_consumes_original_owner(self):
        core, adapter = self.adapter()
        core.call('press', 60, 100)
        core.call('clock', 0, 1); core.call('clock', 7060, 1)
        adapter.key_owners[25] = 60
        self.assertEqual(core.call('mode', 3)[1], [('off', 60, 0)])
        self.menu_key(adapter, 25, 16)
        adapter.service()
        self.assertEqual(core.field('owned'), 0)
        self.assertEqual(adapter.key_owners, {})
        self.assertEqual(adapter.outputs, [])

    def test_track_change_closes_gate_and_later_menu_release_is_silent(self):
        core, adapter = self.adapter()
        core.call('press', 60, 100)
        core.call('clock', 0, 1); core.call('clock', 7060, 1)
        adapter.key_owners[25] = 60
        adapter.destination = lambda: (1, 0)
        adapter.service()
        self.assertEqual(adapter.outputs, [('off', 60, 0)])
        self.assertEqual(core.field('owned'), 1)
        self.assertEqual(core.field('enabled'), 0)
        self.menu_key(adapter, 25, 16)
        adapter.service()
        self.assertEqual(core.field('owned'), 0)
        self.assertEqual(adapter.outputs, [('off', 60, 0)])

    def test_func_release_in_menu_does_not_leave_a_sticky_modifier(self):
        _, adapter = self.adapter()
        self.menu_key(adapter, 17, 1)
        self.assertTrue(adapter.func_down)
        self.menu_key(adapter, 17, 0)
        self.assertFalse(adapter.func_down)

    def test_unbound_gui_load_defaults_off_and_retains_release_ownership(self):
        core, adapter = self.adapter()
        core.call('press', 60, 100)
        core.call('clock', 0, 1); core.call('clock', 7060, 1)
        adapter.key_owners[25] = 60
        adapter.storage_hook(adapter.uc, PROJECT_LOAD, 2, None)
        adapter.service()
        self.assertEqual(adapter.outputs, [('off', 60, 0)])
        self.assertEqual(adapter.pattern_modes, [0] * 128)
        self.assertEqual(core.field('enabled'), 0)
        self.assertEqual(core.field('owned'), 1)
        self.menu_key(adapter, 25, 16)
        adapter.service()
        self.assertEqual(core.field('owned'), 0)
        self.assertEqual(adapter.storage_events[-1]['status'], 'unbound-default-off')

    def bind(self, adapter, slot=7, node_slot=7):
        stack, node = 0x6000F000, 0x60005000
        adapter.uc.mem_write(stack, struct.pack('>III', 0, 0x1234, slot))
        adapter.uc.reg_write(regs.UC_M68K_REG_A7, stack)
        adapter.storage_hook(adapter.uc, PROJECT_CACHE, 2, None)
        adapter.uc.mem_write(node, struct.pack('>III', node_slot, 0, node_slot))
        adapter.uc.reg_write(regs.UC_M68K_REG_D0, node)
        adapter.storage_hook(adapter.uc, PROJECT_CACHE_RETURN, 2, None)
        return node + 12, stack

    def test_binding_is_consumed_and_only_successful_exact_buffer_recalls(self):
        _, adapter = self.adapter()
        buffer, stack = self.bind(adapter)
        blob = bytes.fromhex('beefbace00000005') + b'original project'
        adapter.load_blob = lambda at: blob
        adapter.uc.mem_write(stack + 8, struct.pack('>I', buffer))
        adapter.storage_hook(adapter.uc, PROJECT_LOAD, 2, None)
        self.assertIsNone(adapter.load_binding)
        self.assertEqual(adapter.loading, (7, blob))
        adapter.uc.reg_write(regs.UC_M68K_REG_D0, 0)
        adapter.storage_hook(adapter.uc, PROJECT_LOAD_RETURN, 2, None)
        self.assertEqual(adapter.pending_recall, [])
        # A fresh successful cache/load pair queues the immutable input bytes.
        buffer, stack = self.bind(adapter)
        adapter.uc.mem_write(stack + 8, struct.pack('>I', buffer))
        adapter.storage_hook(adapter.uc, PROJECT_LOAD, 2, None)
        adapter.uc.reg_write(regs.UC_M68K_REG_D0, 1)
        adapter.storage_hook(adapter.uc, PROJECT_LOAD_RETURN, 2, None)
        self.assertEqual(adapter.pending_recall, [(7, blob)])
        adapter.storage_hook(adapter.uc, PROJECT_LOAD_RETURN, 2, None)
        self.assertEqual(adapter.pending_recall, [(7, blob)])

    def test_wrong_node_slot_buffer_and_format_cannot_bind(self):
        _, adapter = self.adapter()
        self.bind(adapter, node_slot=8)
        self.assertIsNone(adapter.load_binding)
        buffer, stack = self.bind(adapter)
        adapter.uc.mem_write(stack + 8, struct.pack('>I', buffer + 4))
        adapter.load_blob = lambda at: self.fail('Wrong buffer must not be read')
        adapter.storage_hook(adapter.uc, PROJECT_LOAD, 2, None)
        self.assertIsNone(adapter.loading)

    def test_saved_cache_node_uses_authoritative_slot_not_stale_read_stamp(self):
        _,adapter=self.adapter()
        stack,node=0x6000F000,0x60005000
        adapter.uc.reg_write(regs.UC_M68K_REG_A7,stack)
        adapter.uc.mem_write(stack,struct.pack('>III',0,0x1234,7))
        adapter.storage_hook(adapter.uc,PROJECT_CACHE,2,None)
        adapter.uc.mem_write(node,struct.pack('>III',7,1,99))
        adapter.uc.reg_write(regs.UC_M68K_REG_D0,node)
        adapter.storage_hook(adapter.uc,PROJECT_CACHE_RETURN,2,None)
        self.assertEqual(adapter.load_binding,(7,node+12))

    def test_live_clone_is_not_a_saved_project_load(self):
        _,adapter=self.adapter();stack=0x6000F000
        adapter.uc.reg_write(regs.UC_M68K_REG_A7,stack)
        adapter.uc.mem_write(stack,struct.pack('>IIII',0,0x1234,0xFFFFFFFF,adapter.project_data))
        adapter.storage_hook(adapter.uc,MENU_LOAD,2,None)
        self.assertFalse(adapter.pending_unknown_load)
        self.assertIsNone(adapter.menu_loading)

        buffer, stack = self.bind(adapter)
        adapter.uc.mem_write(stack + 8, struct.pack('>I', buffer))
        adapter.load_blob = lambda at: b'unknown!'
        adapter.storage_hook(adapter.uc, PROJECT_LOAD, 2, None)
        self.assertIsNone(adapter.loading)

    def test_normal_menu_live_destination_binding_and_failed_return(self):
        for success in (0, 1):
            _, adapter = self.adapter()
            stack=0x6000F000
            adapter.uc.reg_write(regs.UC_M68K_REG_A7, stack)
            adapter.uc.mem_write(stack, struct.pack('>IIII', 0, 0x1234, 7, adapter.project_data))
            adapter.storage_hook(adapter.uc, MENU_LOAD, 2, None)
            self.assertTrue(adapter.pending_unknown_load)
            buffer, stack=self.bind(adapter)
            blob=bytes.fromhex('beefbace00000005')+b'exact input'
            adapter.load_blob=lambda at: blob
            adapter.uc.mem_write(stack,struct.pack('>IIII',0,adapter.project_data,buffer,0))
            adapter.storage_hook(adapter.uc,MENU_DECODE,2,None)
            adapter.uc.reg_write(regs.UC_M68K_REG_D0,success)
            adapter.storage_hook(adapter.uc,MENU_LOAD_RETURN,2,None)
            self.assertEqual(adapter.pending_recall,[(7,blob)] if success else [])
            self.assertIsNone(adapter.load_binding)

    def test_export_destination_does_not_panic_or_recall_and_failed_read_clears_binding(self):
        _, adapter=self.adapter();stack=0x6000F000
        adapter.uc.reg_write(regs.UC_M68K_REG_A7,stack)
        adapter.uc.mem_write(stack,struct.pack('>IIII',0,0x1234,7,0x60006000))
        adapter.storage_hook(adapter.uc,MENU_LOAD,2,None)
        self.assertFalse(adapter.pending_unknown_load)
        self.assertIsNone(adapter.menu_loading)
        self.bind(adapter)
        adapter.uc.mem_write(stack,struct.pack('>IIII',0,0x1234,0x60006000,7))
        adapter.storage_hook(adapter.uc,PROJECT_READ,2,None)
        adapter.uc.reg_write(regs.UC_M68K_REG_D0,1)  # Legacy/failed format.
        adapter.storage_hook(adapter.uc,PROJECT_READ_RETURN,2,None)
        self.assertIsNone(adapter.load_binding)
