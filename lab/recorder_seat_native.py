"""Opt-in seat overlay; capture and transport remain explicit models."""

from lab import recorder_dsp_reuse as r
from lab import recorder_seat_reuse as seats
from lab.recorder_freeze_worker_native import QueuedFreezeUI


class SeatReuseUI(QueuedFreezeUI):
    def install(self, main):
        super().install(main)
        fw = self.fw
        for at in range(seats.BASE, seats.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        r.install(fw)
        for at, block in seats.payload().items():
            fw.write(at, block)
            fw.uc.ctl_remove_cache(at, at + len(block))
