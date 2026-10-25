"""Dry-action SAMPLING arbitration; no firmware, audio or clock imports.

Time is a monotonically unwrapped native panel tick, not a musical clock.
Only an ordinary deferred single tap is replayable. Intent effects have no
connection to recording, sample resources, FREEZE, assignments or persistence.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    destination: int = 0
    epoch: int = 1
    kit: int = 0
    owner: int = 0
    performance: bool = False
    recorder_state: int = 0
    busy: bool = False

    @property
    def eligible(self):
        return (
            1 <= self.destination <= 4
            and self.performance
            and self.owner != 0
            and self.recorder_state == 0
            and not self.busy
        )


@dataclass(frozen=True)
class Effect:
    kind: str
    destination: int
    tick: int
    payload: bytes = b""
    released_at: int | None = None


@dataclass(frozen=True)
class Decision:
    consume: bool = False
    effects: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class Tap:
    context: Context
    pressed_at: int
    released_at: int
    payload: bytes


class Gestures:
    def __init__(self, *, double_ticks=32, hold_ticks=64, double_enabled=True):
        if not 0 < double_ticks < hold_ticks:
            raise ValueError("Need a positive double window shorter than the hold")
        self.double_ticks, self.hold_ticks = double_ticks, hold_ticks
        self.double_enabled = double_enabled
        self.mode = "idle"
        self.context = None
        self.pressed_at = None
        self.pending = None
        self.quiet_until = 0
        self.last_tick = -1

    def _time(self, tick):
        if tick < self.last_tick:
            raise ValueError("Unwrap panel ticks before recognition")
        self.last_tick = tick

    def cancel(self, tick):
        self._time(tick)
        self.pending = None
        self.quiet_until = 0
        # An owned physical cycle must never leak a navigation release.
        if self.mode != "idle":
            self.mode = "spent"

    def poll(self, tick, context):
        self._time(tick)
        if tick < self.quiet_until and self.context != context:
            self.cancel(tick)
        if self.pending and self.pending.context != context:
            self.cancel(tick)
        if self.mode == "first" and self.context != context:
            self.cancel(tick)
        if self.pending and tick >= self.pending.pressed_at + self.double_ticks:
            tap, self.pending = self.pending, None
            return (
                Effect(
                    "single",
                    tap.context.destination,
                    tick,
                    tap.payload,
                    tap.released_at,
                ),
            )
        if self.mode == "first" and tick >= self.pressed_at + self.hold_ticks:
            self.mode = "spent"
            return (Effect("would-freeze", self.context.destination, tick),)
        return ()

    def encoder(self, tick, context):
        """Navigation after a released tap precedes this encoder's dispatch."""
        effects = self.poll(tick, context)
        if effects or not self.pending:
            return effects
        tap, self.pending = self.pending, None
        return (
            Effect(
                "single", tap.context.destination, tick, tap.payload, tap.released_at
            ),
        )

    def sampling(self, tick, flags, context, payload=b""):
        effects = self.poll(tick, context)
        if effects and effects[0].kind == "single":
            # The caller must deliver navigation before routing this new input.
            return Decision(effects=effects)
        if flags & 8:  # Native repeat/milestone is not another physical press.
            return Decision(self.mode != "idle", effects)
        if flags & 1:
            if self.mode != "idle":
                return Decision(True, effects)  # Duplicate/bounced down edge.
            if not context.eligible or flags & 2:
                self.cancel(tick)
                return Decision(effects=effects)
            self.context, self.pressed_at = context, tick
            self.mode = "first"
            if tick < self.quiet_until:
                self.mode = "spent"
                self.quiet_until = tick + self.double_ticks
                return Decision(True, effects)
            if self.pending:
                self.pending = None
                self.mode = "spent"
                self.quiet_until = tick + self.double_ticks
                return Decision(
                    True, (*effects, Effect("would-arm", context.destination, tick))
                )
            return Decision(effects=effects)  # First down edge is stock-safe.

        if self.mode == "idle":
            return Decision(effects=effects)
        mode, self.mode = self.mode, "idle"
        if mode == "spent":
            # Preserve a native modified/consumed chord release. Only the
            # ordinary unmodified navigation release belongs to our cycle.
            return Decision(flags == 16, effects)
        if flags & 16 and context == self.context and context.eligible:
            if not self.double_enabled or tick >= self.pressed_at + self.double_ticks:
                return Decision(effects=effects)  # Longer short tap: no added delay.
            self.pending = Tap(context, self.pressed_at, tick, bytes(payload))
            return Decision(True, effects)
        return Decision(True, effects)
