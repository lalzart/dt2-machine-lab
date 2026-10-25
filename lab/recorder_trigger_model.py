"""Shared dry request boundary. No audio, firmware or time-based scheduling.

A test clock must be primed before arming. A panel tick, elapsed wall time,
or a first late clock observation can never start a request.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArmPlan:
    ticket: int
    epoch: int
    kit: int
    destination: int
    settings: bytes
    clock: int | None
    after_bar: int | None


class ArmRequests:
    """One bounded pending request, identical for both input methods."""

    def __init__(self):
        self.epoch = 1
        self.serial = 0
        self.clock = self.last_bar = None
        self.plan = None
        self.state = "idle"

    def cancel(self):
        self.plan = None
        self.state = "idle"

    def project(self, epoch):
        self.cancel()
        self.epoch = epoch
        self.clock = self.last_bar = None

    def request(self, *, epoch, kit, destination, settings):
        if destination == 0:
            return "stock"
        if epoch != self.epoch or not kit or not 1 <= destination <= 4:
            return "refused"
        if len(settings) != 36:
            raise ValueError("Expected the complete 36-byte recorder settings region")
        if self.state == "pending":
            self.cancel()
            return "canceled"
        if self.state != "idle":
            return "busy"
        self.serial += 1
        self.plan = ArmPlan(
            self.serial,
            epoch,
            kit,
            destination,
            bytes(settings),
            self.clock,
            self.last_bar,
        )
        self.state = "pending"
        return "armed" if self.clock is not None else "unclocked"

    def boundary(self, index, *, epoch, clock):
        """Explicit test-supplied bar; return only a dry would-start receipt."""
        if epoch != self.epoch or index < 0 or clock < 1:
            return None
        if self.clock is not None and clock != self.clock:
            self.cancel()
            self.last_bar = None
        if self.last_bar is not None and index <= self.last_bar:
            return None
        self.clock, self.last_bar = clock, index
        if self.state != "pending":
            return None
        plan = self.plan
        if plan.clock is None or plan.clock != clock or plan.after_bar + 1 != index:
            self.cancel()  # Never guess a missed or unprimed boundary.
            return None
        self.state = "would-record"
        return plan

    def validate(self, *, epoch, kit, destination, busy=False):
        if self.plan and (
            (epoch, kit, destination)
            != (self.plan.epoch, self.plan.kit, self.plan.destination)
            or busy
        ):
            self.cancel()
            return False
        return True
