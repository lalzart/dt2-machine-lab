"""Native track isolation, stock compatibility and selected-track arp ownership."""

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

import test_arp_stopped as harness

from lab import arp_firmware as fw
from lab.cpu_extension import build_cpu
from lab.cpu_fixture import install
from lab.project import ROOT
from lab.track_scope import DESTINATION, SOURCE, TYPE_BASE

u, r = harness.u, harness.r


@unittest.skipIf(u is None, 'Configured native runtime required')
class AnyTrackCPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from lab import runtime  # noqa: F401

        cls.stock = (ROOT / '.local/fixture/sections/section_3_MAIN_OS.bin').read_bytes()
        with tempfile.TemporaryDirectory(dir=ROOT / 'out/runs') as d:
            cls.image, cls.meta = build_cpu(cls.stock, features='all', output=Path(d),
                                           arp_stopped=True, any_tracks=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'out/runs') as d:
            cls.old, cls.oldmeta = build_cpu(cls.stock, features='all', output=Path(d),
                                           arp_stopped=True)

    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, n in ((0x40000000, 0x400000), (0x47E8B000, 0x10000),
                      (0x60000000, 0x10000), (0x80000000, 0x10000)):
            self.cpu.mem_map(at, n)
        self.cpu.mem_write(0x40000400, self.stock)
        install(self.cpu.mem_write, self.image, self.meta)

    def call(self, pc, *args, stop=0x6000FFE0):
        sp = 0x6000F000
        self.cpu.mem_write(sp, struct.pack('>' + 'I' * (len(args) + 1), 0x6000FFE0, *args))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, sp)
        self.cpu.emu_start(pc, stop, count=100000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_actual_permissions_all_tracks_and_stock_types(self):
        for typ in range(9):
            for track in range(17):
                got = self.call(0x400DA3B0, typ, track)
                if typ == 7:
                    self.assertEqual(got, int(track < 16))
                else:
                    self.cpu.mem_write(0x40000400, self.old)
                    self.cpu.ctl_remove_cache(0x40000000, 0x40400000)
                    expected = self.call(0x400DA3B0, typ, track)
                    install(self.cpu.mem_write, self.image, self.meta)
                    self.cpu.ctl_remove_cache(0x40000000, 0x40400000)
                    self.assertEqual(got, expected)

    def test_native_raw_transport_only_touches_plaits_fields(self):
        self.cpu.mem_write(0x80003000, bytes([0xA5]) * 0x4000)
        original = bytes([0x5A]) * (16 * 142)
        start = 0x80005B50
        self.cpu.mem_write(start, original)
        expected = bytearray(original)
        for track in range(16):
            typ = 7 if track % 3 else 2
            self.cpu.mem_write(TYPE_BASE + track * 154, bytes([typ]))
            values = struct.pack('>7H', 32512-track, track*256, 5639+track,
                                 111, 222, 27143-track, 2304+track)
            self.cpu.mem_write(SOURCE + track * 142, values)
            if typ == 7:
                for off, size in ((0, 4), (4, 2), (10, 2), (12, 2)):
                    pos = DESTINATION - start + track * 142 + off
                    expected[pos:pos+size] = values[off:off+size]
        saved = [r.UC_M68K_REG_D1, r.UC_M68K_REG_D2, r.UC_M68K_REG_D3,
                 r.UC_M68K_REG_A0, r.UC_M68K_REG_A1, r.UC_M68K_REG_A2]
        for reg in saved:
            self.cpu.reg_write(reg, 0xBAD000 + reg)
        self.assertEqual(self.call(self.meta['track_locations']['transport'], stop=0x400D934C),
                         0x80005B50)
        self.assertEqual(bytes(self.cpu.mem_read(start, len(expected))), expected)
        for reg in saved:
            self.assertEqual(self.cpu.reg_read(reg), 0xBAD000 + reg)

    def test_repack_guard_preserves_all_plaits_tracks_and_stock_semantics(self):
        for track in range(16):
            for typ in range(8):
                for value in (0, 519, 1024, 5639, 32512):
                    buffer = 0x80005B50 + track * 142
                    before = bytes([0x5A]) * 0x5A + struct.pack('>HHH', value, 512, 768)
                    results = []
                    for old in (True, False):
                        if old:
                            self.cpu.mem_write(0x40000400, self.old)
                        else:
                            install(self.cpu.mem_write, self.image, self.meta)
                        self.cpu.ctl_remove_cache(0x40000000, 0x40400000)
                        for i in range(16):
                            self.cpu.mem_write(TYPE_BASE+i*154, bytes([typ]))
                        self.cpu.mem_write(buffer, before)
                        self.cpu.reg_write(r.UC_M68K_REG_D6, track)
                        self.cpu.reg_write(r.UC_M68K_REG_A4, buffer)
                        self.call(0x4002E978, stop=0x4002E994)
                        results.append(bytes(self.cpu.mem_read(buffer, len(before))))
                    self.assertEqual(results[1], before if typ == 7 else results[0])

    def test_flex_native_assignment_all_destinations_preserves_other_controls(self):
        self.cpu.mem_map(0x40500000, 0x100000)
        kit, slot, pool = 0x60008000, 37, 0x60003000
        self.cpu.mem_write(0x80004704, struct.pack('>I', kit))
        self.cpu.mem_write(0x405BA768+slot*4, struct.pack('>I', 0x1234))
        ref = bytes(range(16))
        self.cpu.mem_write(0x405B1368+slot*16, ref)
        self.cpu.mem_write(0x60002100, struct.pack('>I', 0x60002200))
        self.cpu.mem_write(0x60002228, struct.pack('>I', 0x60002500))
        refresh = []

        def peer(cpu, pc, size, unused):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            if pc == 0x4002D438:
                refresh.append(struct.unpack('>II', cpu.mem_read(sp+4, 8)))
            value = {0x401988A2: 0x60002000, 0x40041D18: 0x60002100,
                     0x60002500: pool, 0x4002D438: 0}[pc]
            cpu.reg_write(r.UC_M68K_REG_D0, value)
            cpu.reg_write(r.UC_M68K_REG_PC, int.from_bytes(cpu.mem_read(sp, 4), 'big'))
            cpu.reg_write(r.UC_M68K_REG_A7, sp+4)
        for pc in (0x401988A2, 0x40041D18, 0x60002500, 0x4002D438):
            self.cpu.hook_add(u.UC_HOOK_CODE, peer, begin=pc, end=pc)
        before = bytearray(b'Z'*(16*0x450))
        for track in range(16):
            before[track*0x450+0xD6] = 0
        self.cpu.mem_write(kit, bytes(before))
        for track in range(16):
            self.assertEqual(self.call(self.meta['flex']['locations']['assign'], slot, track, kit), 0)
            before[track*0x450+0x80:track*0x450+0x82] = struct.pack('>H', slot)
            self.assertEqual(bytes(self.cpu.mem_read(kit, len(before))), before)
            self.assertEqual(refresh[-1], (kit+track*0x450+0x34, track))
            self.assertEqual(bytes(self.cpu.mem_read(pool+slot*16+0x1D2, 16)), ref)
        self.assertEqual(self.call(self.meta['flex']['locations']['assign'], slot, 16, kit), 0xFFFFFFFF)
        self.assertEqual(len(refresh), 16)

    def test_existing_stopped_package_and_reservation_preserved(self):
        from lab.capicola_ui import apply_switch

        switched, _ = apply_switch(self.old, self.oldmeta)
        self.assertEqual(hashlib.sha256(switched).hexdigest(),
                         '87b014cda1672397c4e8f611cfb935dcddbf4b0b7d0c3ab19a7f1310ffbb93c4')
        self.assertEqual(self.meta['reservation'], self.oldmeta['reservation'])
        self.assertEqual(self.meta['arp']['state_bytes'], 8192)


@unittest.skipIf(u is None, 'Configured native runtime required')
class AnyTrackArp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '.local/fixture/sections/section_3_MAIN_OS.bin').read_bytes()

    def prepare(self):
        h = harness.StoppedArp()
        h.stock = self.stock
        h.prepare(any_track=True)
        return h

    def test_all_sixteen_destinations_with_stopped_playback_and_gate_release(self):
        for track in range(16):
            h = self.prepare()
            h.put(fw.TRACK, track)
            h.chord()
            h.tick(0)
            h.tick(6000)
            h.tick(9000)
            self.assertEqual(h.outputs, [(6000, 'on', 60), (9000, 'off', 60)])
            self.assertEqual([t for _, t, _ in h.destinations], [track, track])

    def test_native_sync_closes_old_track_before_moving_and_rejects_invalid_track(self):
        h = self.prepare()
        h.cpu.hook_del(h.endpoint_hooks[h.p['sync']])
        selected = [0]

        def stub(pc, value):
            def run(cpu, pc, size, extra):
                sp = cpu.reg_read(r.UC_M68K_REG_A7)
                cpu.reg_write(r.UC_M68K_REG_D0, value() if callable(value) else value)
                cpu.reg_write(r.UC_M68K_REG_PC, h.u32(sp))
                cpu.reg_write(r.UC_M68K_REG_A7, sp+4)
            h.cpu.hook_add(u.UC_HOOK_CODE, run, begin=pc, end=pc)

        for pc, value in [(0x401988A2, 0x60008400), (0x40041D18, 0x60008000),
                          (0x4004AF88, 1), (0x4004ABE8, lambda: selected[0]),
                          (0x40199680, 0x60008500), (0x400F541C, 0)]:
            stub(pc, value)
        h.put(fw.MODES, 9)
        h.call('sync')
        h.chord()
        h.tick(0)
        h.tick(6000)
        selected[0] = 15
        h.call('sync')
        self.assertEqual(h.destinations[-1], (fw.OFF, 0, 60))
        self.assertEqual(h.u32(h.state+fw.TRACK), 15)
        self.assertEqual(h.u32(h.state), 1)
        self.assertEqual(h.u32(h.state+36), 0)
        for note in (60, 64, 67):
            h.call('release', h.state, note)
        h.chord()
        h.tick(6000)
        h.tick(12000)
        self.assertEqual(h.destinations[-1], (fw.ON, 15, 60))
        selected[0] = 7
        h.call('sync')
        self.assertEqual(h.destinations[-1], (fw.OFF, 15, 60))
        self.assertEqual(h.u32(h.state+fw.TRACK), 7)
        for note in (60, 64, 67):
            h.call('release', h.state, note)
        h.chord()
        h.tick(12000)
        h.tick(18000)
        self.assertEqual(h.destinations[-1], (fw.ON, 7, 60))
        selected[0] = 16
        h.call('sync')
        self.assertEqual(h.destinations[-1], (fw.OFF, 7, 60))
        self.assertEqual(h.u32(h.state), 0)
        self.assertEqual(h.u32(h.state+fw.TRACK), 0xffffffff)
