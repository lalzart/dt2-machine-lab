"""Explicit opt-in native Sketch installation over the unchanged BUF adapter."""

import struct

from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import buf_performance as perf
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as worker
from lab import sketch as s
from lab.buf_next_bar_ui import NextBarUI
from lab.project import require


class SketchUI(NextBarUI):
    def __init__(
        self,
        *args,
        sketch_enabled=False,
        arm_enabled=False,
        freeze_enabled=False,
        **kwargs,
    ):
        require(not arm_enabled or sketch_enabled, "Sketch ARM needs Sketch enabled")
        require(
            not freeze_enabled or sketch_enabled, "Sketch FREEZE needs Sketch enabled"
        )
        self.sketch_enabled = sketch_enabled
        self.arm_enabled = arm_enabled
        self.freeze_enabled = freeze_enabled
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        if not self.sketch_enabled:
            return
        fw = self.fw
        parts = s.payload(
            main, arm_enabled=self.arm_enabled, freeze_enabled=self.freeze_enabled
        )
        sites = (
            (
                perf.KEY_SITE,
                bytes.fromhex("4ef9")
                + struct.pack(">I", perf.KEY)
                + bytes.fromhex("4e71"),
                s.KEY,
            ),
            (s.MAIN_SITE, s.MAIN_BYTES, s.MAIN_KEY),
            (s.ROUTE_SITE, bytes.fromhex("4fefffa048d77cfc"), s.ROUTE),
        )
        for at, expected, _ in sites:
            require(
                fw.read(at, len(expected)) == expected, f"Sketch patch drift {at:#x}"
            )
        if self.arm_enabled or self.freeze_enabled:
            expected = worker.entry()
            require(
                fw.read(worker.ENTRY, len(expected)) == expected,
                "Sketch USE gate drift",
            )
            fw.write(
                worker.ENTRY, bytes.fromhex("4ef9") + struct.pack(">I", nb.USE_GATE)
            )
            fw.uc.ctl_remove_cache(worker.ENTRY, worker.ENTRY + len(expected))
        if self.freeze_enabled:
            for at, expected in ((q.GATE, q.gate()), (q.DONE, q.done())):
                require(
                    fw.read(at, len(expected)) == expected,
                    f"Sketch FREEZE patch drift {at:#x}",
                )
            for at in range(bf.BASE, bf.END, 4096):
                fw.m.ensure(at)
                fw.write(at, bytes(4096))
            for at, raw in bf.payload().items():
                fw.write(at, raw)
            fw.uc.ctl_remove_cache(bf.BASE, bf.END)
            for at, target in ((q.GATE, bf.GATE), (q.DONE, bf.DONE)):
                fw.write(at, bytes.fromhex("4ef9") + struct.pack(">I", target))
                fw.uc.ctl_remove_cache(at, at + 6)
        for at in range(s.BASE, s.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        fw.write(s.STATE + s.BUF, struct.pack(">I", 1))
        for at, raw in parts.items():
            fw.write(at, raw)
        fw.uc.ctl_remove_cache(s.BASE, s.END)
        for at, expected, target in sites:
            fw.write(
                at,
                bytes.fromhex("4ef9")
                + struct.pack(">I", target)
                + bytes.fromhex("4e71") * ((len(expected) - 6) // 2),
            )
            fw.uc.ctl_remove_cache(at, at + len(expected))
