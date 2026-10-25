"""Isolated quick-record contract; no firmware key, clock or capture hook.

The caller supplies authoritative bar/record-completion events. Host wall time
and modeled instruction clocks deliberately cannot start or commit a take.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    ticket: int
    epoch: int
    destination: int
    source: int
    channel: int
    bars: int


class QuickRecord:
    def __init__(self):
        self.epoch = 1
        self.serial = 0
        self.state = "idle"
        self.plan = None
        self.started_bar = None

    def gesture(self, *, destination, playing, source=0, channel=0, bars=1):
        if destination == 0:
            return "stock"
        if self.state == "armed":
            self.cancel()
            return "canceled"
        if self.state != "idle" or not playing:
            return "busy" if self.state != "idle" else "stopped"
        if not 1 <= destination <= 4 or bars < 1:
            raise ValueError("Invalid quick-record destination or length")
        self.serial += 1
        self.plan = Plan(self.serial, self.epoch, destination, source, channel, bars)
        self.state = "armed"
        return "armed"

    def bar(self, index, *, epoch):
        if epoch != self.epoch:
            return None
        if self.state == "armed":
            self.started_bar, self.state = index, "recording"
            return "start", self.plan
        if self.state == "recording" and index >= self.started_bar + self.plan.bars:
            self.state = "stopping"
            return "stop", self.plan
        return None

    def captured(self, ticket):
        if self.state != "stopping" or self.plan != ticket:
            raise ValueError("Stale or incomplete quick-record capture")
        self.state = "publishing"

    def published(self, ticket, *, complete):
        if self.state != "publishing" or ticket != self.plan or not complete:
            raise ValueError("Stale or incomplete quick-record publication")
        self.cancel()
        return ticket

    def cancel(self):
        self.state, self.plan, self.started_bar = "idle", None, None

    def project_change(self):
        self.cancel()
        self.epoch += 1
