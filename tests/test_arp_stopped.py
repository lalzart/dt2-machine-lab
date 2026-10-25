"""Native heartbeat clock selection, real tempo getter and note endpoints."""

import hashlib
import struct
import unittest

import test_arp_firmware as legacy

from lab import arp_firmware as fw
from lab import arp_tempo as tempo
from lab.project import ROOT

u, r = legacy.u, legacy.r


@unittest.skipIf(u is None, 'Configured Unicorn required')
class StoppedArp(unittest.TestCase):
    u32 = legacy.NativeJournal.u32
    put = legacy.NativeJournal.put
    call = legacy.NativeJournal.call

    @classmethod
    def setUpClass(cls):
        cls.stock = (ROOT / '.local/fixture/sections/section_3_MAIN_OS.bin').read_bytes()

    def prepare(self, stopped=True, bpm=14400, rate=2, mode=1, tick=0, any_track=False):
        self.image, self.meta = fw.patch_cpu(
            self.stock, tempo_ui=True, stopped_playback=stopped, any_track=any_track)
        self.p = self.meta['locations']
        self.state = 0x60002000
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, size in ((0x40000000, 0x400000), (0x40966000, 4096),
                              (0x60000000, 0x10000)):
            self.cpu.mem_map(address, size)
        self.cpu.mem_write(0x40000400, self.image)
        self.cpu.mem_write(self.p['pointer'], struct.pack('>I', self.state))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2700)
        self.outputs = []
        self.destinations = []
        self.endpoint_hooks = {}

        def endpoint(cpu, pc, size, data):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            if pc in (fw.ON, fw.OFF):
                self.destinations.append((pc, self.u32(sp + 4), self.u32(sp + 8)))
                self.outputs.append((self.u32(fw.TICK),
                                     'on' if pc == fw.ON else 'off', self.u32(sp + 8)))
            # At continuation, the original displaced instruction pushed an arg.
            if pc == fw.MAINLOOP + 6:
                sp += 4
            cpu.reg_write(r.UC_M68K_REG_PC, self.u32(sp))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (self.p['ensure'], self.p['sync'], fw.ON, fw.OFF, fw.MAINLOOP + 6):
            self.endpoint_hooks[pc] = self.cpu.hook_add(u.UC_HOOK_CODE, endpoint, begin=pc, end=pc)
        self.call('init', self.state, tick, mode)
        self.put(tempo.RATE, -1)
        self.call('rate', self.state, rate)
        self.put(fw.KEYBOARD, 1)
        self.put(fw.TRACK, 0)
        self.set_tempo(bpm)
        self.tick(tick)

    def set_tempo(self, value):
        self.cpu.mem_write(0x402B62BC, struct.pack('>I', value))

    def tick(self, tick):
        self.cpu.mem_write(fw.TICK, struct.pack('>I', tick & 0xffffffff))
        registers = [getattr(r, 'UC_M68K_REG_' + name)
                     for name in ('D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7',
                                  'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6')]
        for index, reg in enumerate(registers):
            self.cpu.reg_write(reg, 0xBAD000 + index)
        sr = self.cpu.reg_read(r.UC_M68K_REG_SR)
        self.call('heartbeat')
        self.assertEqual([self.cpu.reg_read(reg) for reg in registers],
                         [0xBAD000 + i for i in range(len(registers))])
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR), sr)

    def chord(self):
        for note in (67, 64, 60):
            self.call('press', self.state, note, 100)

    def test_stopped_rational_grid_all_modes_rates_and_tempos(self):
        vectors = {1: [60, 64, 67, 60], 2: [67, 64, 60, 67], 3: [64, 64, 60, 60]}
        for bpm in (3600, 12240, 14400, 15300, 36000):
            for rate, step in enumerate(tempo.STEPS):
                for mode, expected in vectors.items():
                    with self.subTest(bpm=bpm, rate=rate, mode=mode):
                        self.prepare(bpm=bpm, rate=rate, mode=mode)
                        self.chord()
                        self.tick(0)
                        last = 0
                        times = sorted({x for n in range(1, 5)
                                        for x in ((n * step + bpm - 1) // bpm - 1,
                                                  (n * step + bpm - 1) // bpm,
                                                  (n * step + bpm - 1) // bpm
                                                  + (step // 2 + bpm - 1) // bpm)})
                        for tick in times:
                            while tick - last > 24000:
                                last += 24000
                                self.tick(last)
                            self.tick(tick)
                            last = tick
                        self.assertEqual([(t, n) for t, k, n in self.outputs if k == 'on'],
                                         [((i * step + bpm - 1) // bpm, n)
                                          for i, n in enumerate(expected, 1)])
                        self.assertEqual([n for _, k, n in self.outputs if k == 'off'], expected)
                        self.assertEqual(self.u32(self.state + fw.PLAY), 0)

    def test_play_handoff_matches_continuously_playing_reference(self):
        states = []
        for stopped, handoff in ((False, False), (True, False), (True, True)):
            self.prepare(stopped=stopped)
            self.put(fw.PLAY, 0 if handoff else 1)
            self.chord()
            self.tick(0)
            for tick in (3000, 6000, 7500, 9000, 12000, 15000, 18000):
                if tick == 7500:
                    self.put(fw.PLAY, 1)
                self.tick(tick)
            states.append((self.outputs[:], bytes(self.cpu.mem_read(self.state, 2120))))
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[0], states[2])

    def test_release_stop_rearm_keyboard_exit_and_tempo_change(self):
        self.prepare()
        self.chord()
        self.tick(0)
        self.tick(3000)
        self.set_tempo(7200)
        self.tick(8999)
        self.assertEqual(self.outputs, [])
        self.tick(9000)
        self.assertEqual(self.outputs[-1], (9000, 'on', 60))
        for note in (60, 64, 67):
            self.call('release', self.state, note)
            self.call('events')
        self.assertEqual(self.outputs[-1][1:], ('off', 60))
        self.tick(12000)
        self.assertEqual(self.u32(self.state + 4), 0)
        self.chord()
        self.tick(12000)
        self.tick(24000)
        self.assertEqual(self.outputs[-1], (24000, 'on', 60))
        # The actual unchanged STOP input path must close and clear the chord.
        event = 0x60009000
        self.cpu.mem_write(event, struct.pack('>5I', 0, 0, 0, 21, 1))
        self.call('input', 0, event, 0)
        self.assertEqual(self.outputs[-1][1:], ('off', 60))
        self.assertEqual(self.u32(self.state + 36), 0)
        count = len(self.outputs)
        self.tick(36000)
        self.assertEqual(len(self.outputs), count)
        for note in (60, 64, 67):
            self.call('release', self.state, note)
        self.chord()
        self.tick(36000)
        self.tick(48000)
        self.assertEqual(self.outputs[-1], (48000, 'on', 60))
        self.put(fw.KEYBOARD, 0)
        self.tick(48001)
        self.assertEqual(self.outputs[-1][1:], ('off', 60))
        self.assertEqual(self.u32(self.state + 36), 0)

    def test_off_busy_wrap_late_service_and_original_stopped_negative(self):
        self.prepare(stopped=False)
        self.chord()
        for tick in (0, 6000, 12000, 18000):
            self.tick(tick)
        self.assertEqual(self.outputs, [])
        self.prepare(mode=0)
        self.chord()
        self.tick(6000)
        self.assertEqual(self.outputs, [])
        self.prepare(tick=0xfffff000)
        self.chord()
        self.tick(0xfffff000)
        self.put(fw.BUSY, 1)
        self.tick(0xfffff100)
        self.assertEqual(self.outputs, [])
        self.put(fw.BUSY, 0)
        self.tick((0xfffff000 + 6000) & 0xffffffff)
        self.assertEqual(self.outputs[-1][1:], ('on', 60))
        before = len(self.outputs)
        self.tick((0xfffff000 + 6000 + 48000) & 0xffffffff)
        self.assertEqual(len(self.outputs) - before, 2)
        self.tick((0xfffff000 + 6000 + 48000 + 48001) & 0xffffffff)
        self.assertEqual(self.u32(self.state + 36), 0)

    def test_default_bytes_state_extent_and_invalid_options(self):
        image, metadata = fw.patch_cpu(self.stock, tempo_ui=True)
        self.assertEqual(hashlib.sha256(image).hexdigest(),
                         'eec11e5201fa39b42d9b4919c05ff83b7f3973425783712a2d2a092b40121f44')
        self.assertEqual(hashlib.sha256(fw.patch_cpu(self.stock)[0]).hexdigest(),
                         '5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310')
        self.prepare()
        self.assertEqual(self.meta['state_bytes'], metadata['state_bytes'])
        self.assertEqual(len(image), len(self.image))
        with self.assertRaises(ValueError):
            fw.patch_cpu(self.stock, stopped_playback=True)
