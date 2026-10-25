"""Targeted SONG LED substitution/stock fallback and R7 opt-out checks."""

import os
import unittest

from selector_core_support import r
import test_sketch_controls as controls
from lab import buf_next_bar as nb
from lab import sketch_led as led
from lab.emit import Code
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build


@unittest.skipUnless(os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire required")
class RecordingLedTests(unittest.TestCase):
    def test_only_SONG_during_owned_native_capture_substitutes_without_state_or_argument_writes(self):
        f = controls.PerformanceControls().view()
        for at, raw in led.payload().items():
            f.cpu.mem_write(at, raw)
        # Displaced stock LINK/MOVE execute. Observe its two arguments at the
        # tail boundary, then return normally; UART/queue work is tested natively.
        c = Code()
        c.emit("202e0008")
        c.imm("23c0", 0x200A80)
        c.emit("202e000c")
        c.imm("23c0", 0x200A84)
        c.emit("4fee0000 2c5f 4e75")  # Restore native LINK frame, then RTS.
        f.cpu.mem_write(led.SITE + len(led.PREFIX), c.finish(led.SITE + len(led.PREFIX)))
        preserved = [getattr(r, f"UC_M68K_REG_D{i}") for i in range(2, 8)]
        preserved += [getattr(r, f"UC_M68K_REG_A{i}") for i in range(2, 7)]
        for reg in preserved:
            f.cpu.reg_write(reg, 0xA1B20000 + reg)
        for phase in (0, 1, 2, 3, 4, 5, 6):
            for recorder_state in (0, 1, 2, 3, 4):
                for key in (0, 1, 4, led.SONG, 6, 10, 26, 49, 50):
                    for ctrl in (0, 0x205000) if key == led.SONG else (0x205000,):
                        with self.subTest(phase=phase, recorder=recorder_state, key=key, ctrl=ctrl):
                            f.put(nb.STATE + nb.PHASE, phase)
                            f.put(nb.STATE + nb.CTRL, ctrl)
                            f.native_value(nb.auto.RECORDER_STATE, recorder_state)
                            before = bytes(f.cpu.mem_read(nb.STATE, 0x200))
                            f.call(led.ENTRY, key, 0x71)
                            actual = int.from_bytes(f.cpu.mem_read(0x200A84, 4), "big")
                            expected = led.RED if key == led.SONG and phase == 2 and ctrl and recorder_state == 2 else 0x71
                            self.assertEqual(actual, expected)
                            self.assertEqual(bytes(f.cpu.mem_read(0x200A80, 4)), key.to_bytes(4, "big"))
                            self.assertEqual(bytes(f.cpu.mem_read(0x20F004, 8)), key.to_bytes(4, "big") + bytes.fromhex("00000071"))
                            self.assertEqual(bytes(f.cpu.mem_read(nb.STATE, 0x200)), before)
                            for reg in preserved:
                                self.assertEqual(f.cpu.reg_read(reg), 0xA1B20000 + reg)

    def test_opt_out_is_exact_R7_and_opt_in_adds_only_LED_hook_and_code(self):
        flags = dict(arm_diagnostics=True, clock_fix=True, buf_selector=True,
                     performance_controls=True, navigation_fixes=True,
                     fixed_buf_slots=True, startup_capture=True,
                     copy_shortcuts=True, stopped_recording=True)
        stock = STOCK_MAIN.read_bytes()
        _old_image, old = build(stock, **flags)
        self.assertEqual(old["sha256"], "b5f167e5bbfb9ac35f1de9db7e507e3775663c8702450e270945e4040277f7af")
        _image, new = build(stock, recording_led=True, **flags)
        self.assertEqual(new["reservation"], old["reservation"])
        self.assertEqual(new["guards"], old["guards"])
        self.assertEqual([h for h in new["hooks"] if h["address"] != led.SITE], old["hooks"])
        additions = [w for w in new["writes"] if w not in old["writes"]]
        self.assertEqual({w["source_address"] for w in additions}, {led.ENTRY, led.TRAMP})
        self.assertTrue(all(w in new["writes"] for w in old["writes"]))
        self.assertEqual(new["payload_bytes"] - old["payload_bytes"], sum(len(bytes.fromhex(w["after"])) for w in additions))
