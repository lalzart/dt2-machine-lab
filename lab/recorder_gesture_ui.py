"""Opt-in emulator dry-run: host arbitration, stock single-tap replay, OLED overlay.

No calls to recorder commands or FREEZE. Native code is only a register/CCR
preserving bridge for an ordinary deferred navigation event. The feedback
compositor changes a copy of the latched host display, never guest pixels.
"""

import struct

from lab.emit import Code
from lab.project import require
from lab.recorder_gestures import Context, Gestures
from lab.recorder_normal import NormalBufferUI

# isort: off
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

DISPATCH = 0x40030BD0
ENCODER = 0x40030B64
MAIN_KEY = 0x4005DC58
RECORDER_KEY = 0x40022C6E
LOOP = 0x40033D00
PANEL_TICK = 0x47DDEC1C
BASE = 0x10500000  # Explicit emulator mapping; no target reservation.
EVENT = BASE + 0x400
REGISTERS = tuple(
    getattr(k, "UC_M68K_REG_" + n)
    for n in (
        "D0",
        "D1",
        "D2",
        "D3",
        "D4",
        "D5",
        "D6",
        "D7",
        "A0",
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
    )
)


def replay_bridge(dispatcher, resume, function=DISPATCH):
    c = Code()
    c.emit("4fefffc0 48d77fff 40c0 2f40003c")
    c.imm("4879", EVENT)
    c.imm("4879", dispatcher)
    c.imm("4eb9", function)
    c.emit("508f 202f003c 44c0 4cd77fff 4fef0040")
    c.imm("4ef9", resume)
    return c.finish(BASE)


# Original, deliberately small 5x7 bitmap font for the host-only feedback.
# Rows are five bits, top first. No firmware font assets are copied.
GLYPHS = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "W": (17, 17, 17, 21, 21, 21, 10),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (30, 1, 1, 14, 1, 1, 30),
    "4": (2, 6, 10, 18, 31, 2, 2),
}


def overlay(raw, effect):
    """Render two short lines over a copy of a 128x64 native page-order frame."""
    require(len(raw) == 1024, "Unexpected OLED extent")
    buf = bytearray(raw)

    def pixel(x, y, value):
        # emu.panel: byte=8*column+inverted page, low bit is the page's top.
        index, mask = x * 8 + 7 - y // 8, 1 << (y % 8)
        buf[index] = (buf[index] | mask) if value else (buf[index] & ~mask)

    for y in range(20, 45):
        for x in range(7, 121):
            pixel(x, y, int(y in (20, 44) or x in (7, 120)))
    lines = (
        {
            "would-arm": "WOULD ARM",
            "would-freeze": "WOULD FREEZE",
            "would-cancel": "ARM CANCELED",
            "would-record": "WOULD RECORD",
            "would-refuse": "ARM REFUSED",
        }[effect.kind],
        f"BUF {effect.destination} NEXT BAR"
        if effect.kind == "would-arm"
        else f"BUF {effect.destination}",
    )
    for y, line in zip((24, 35), lines, strict=True):
        x0 = (128 - (len(line) * 6 - 1)) // 2
        for n, ch in enumerate(line):
            for dy, row in enumerate(GLYPHS[ch]):
                for dx in range(5):
                    if row & (1 << (4 - dx)):
                        pixel(x0 + n * 6 + dx, y + dy, 1)
    return bytes(buf)


class DryRunUI(NormalBufferUI):
    def __init__(
        self, *args, gestures_enabled=False, model_armed_status=False, **kwargs
    ):
        self.gestures_enabled = gestures_enabled
        self.model_armed_status = model_armed_status
        self.gestures = Gestures()
        self.gesture_log = []
        self.navigation = []
        self.feedback = None
        self.feedback_until = 0
        self.epoch = 1
        self._tick_raw = None
        self._tick_total = 0
        self._main_owner = 0
        self._performance = False
        self._recorder_event = False
        self._held_keys = set()
        self._controller = None
        self._dispatcher = None
        self._replaying = None
        self._raw_panel = None
        self._rendered_panel = None
        self._resume_hooks = {DISPATCH, ENCODER, MAIN_KEY, RECORDER_KEY, LOOP}
        self.bridge_log = []
        self._encoder_queue = []
        self.encoder_log = []
        self._awaiting_recorder = None
        self._recorder_drawn = False
        self.status_model_reads = 0
        super().__init__(*args, **kwargs)
        original_spin = args[0].spin

        def spin(*a, **kw):
            result = original_spin(*a, **kw)
            worker = self.clock_state.get("worker")
            if worker is not None and worker._panel_latch is not None:
                if worker._panel_latch is not self._rendered_panel:
                    self._raw_panel = worker._panel_latch
                if self._raw_panel is not None:
                    active = self.feedback and self.now() < self.feedback_until
                    self._rendered_panel = (
                        overlay(self._raw_panel, self.feedback)
                        if active
                        else self._raw_panel
                    )
                    worker._panel_latch = self._rendered_panel
                self.window_status = dict(
                    destination=self.destination,
                    mode=self.gestures.mode,
                    pending=self.gestures.pending is not None,
                    tick=self.now(),
                    feedback=self.feedback.kind if self.feedback else None,
                )
            return result

        args[0].spin = spin

    def install(self, main):
        super().install(main)
        fw = self.fw
        fw.m.ensure(BASE)
        for pc in (
            DISPATCH,
            ENCODER,
            MAIN_KEY,
            RECORDER_KEY,
            LOOP,
            0x40015F6C,
            0x400CD702,
            0x400F5050,
            0x40043A30,
            0x40031122,
        ):
            require(
                fw.read(pc, 8) == main[pc - 0x40000400 : pc - 0x40000400 + 8],
                f"Gesture site drift {pc:#x}",
            )
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.gesture_hook, begin=pc, end=pc)
            )

    def now(self):
        raw = self.fw.u32(PANEL_TICK) & 0xFFF
        if self._tick_raw is not None:
            self._tick_total += (raw - self._tick_raw) & 0xFFF
        self._tick_raw = raw
        return self._tick_total

    def context(self, *, performance=None, owner=None):
        state = (
            self.fw.u32(self.fw.u32(self._controller + 16) + 0xA4)
            if self._controller
            else 0
        )
        return Context(
            destination=self.destination,
            epoch=self.epoch,
            kit=self.fw.u32(0x80004704),
            owner=self._main_owner if owner is None else owner,
            performance=(self._performance if performance is None else performance)
            and not (self._held_keys - {50}),
            recorder_state=state,
            busy=self.pending is not None,
        )

    def invalidate_gesture(self, reason, *, project=False):
        if project:
            self.epoch += 1
        self.gestures.cancel(self.now())
        self.feedback = None
        self._encoder_queue.clear()
        self._awaiting_recorder = None
        self._recorder_drawn = False
        self.gesture_log.append(
            dict(kind="cancel", reason=reason, tick=self.now(), epoch=self.epoch)
        )

    def effects(self, effects, resume):
        for effect in effects:
            self.gesture_log.append(
                dict(kind=effect.kind, tick=effect.tick, destination=effect.destination)
            )
            if effect.kind == "single":
                self.inject_single(effect, resume)
            else:
                self.feedback, self.feedback_until = effect, self.now() + 120

    def inject_single(self, effect, resume):
        fw = self.fw
        require(len(effect.payload) == 24, "Invalid deferred key event")
        require(
            struct.unpack_from(">II", effect.payload, 12) == (50, 16),
            "Only ordinary unmodified SAMPLING release may be replayed",
        )
        self._awaiting_recorder = (
            self.now(),
            self.epoch,
            fw.u32(0x80004704),
            effect.destination,
        )
        self._recorder_drawn = False
        self.navigation.append(
            dict(
                released_at=effect.released_at,
                replay_at=self.now(),
                drawn_at=None,
                resume=hex(resume),
            )
        )
        self.inject_call(DISPATCH, self._dispatcher, effect.payload, resume)

    def inject_call(self, function, dispatcher, payload, resume):
        fw = self.fw
        require(
            self._replaying is None and dispatcher is not None,
            "Nested/missing UI replay context",
        )
        require(len(payload) == 24, "UI event extent drift")
        saved = tuple(fw.uc.reg_read(r) for r in REGISTERS)
        ccr = fw.uc.reg_read(k.UC_M68K_REG_SR) & 31
        self._replaying = dict(
            resume=resume, registers=saved, ccr=ccr, function=function
        )
        fw.write(EVENT, payload)
        code = replay_bridge(dispatcher, resume, function)
        fw.write(BASE, code)
        fw.uc.ctl_remove_cache(BASE, BASE + len(code))
        if resume not in self._resume_hooks:
            self.hooks.append(
                fw.uc.hook_add(
                    UC_HOOK_CODE, self.gesture_hook, begin=resume, end=resume
                )
            )
            self._resume_hooks.add(resume)
        fw.uc.reg_write(k.UC_M68K_REG_PC, BASE)

    def defer_input(self, function, sp):
        fw = self.fw
        dispatcher, event = fw.u32(sp + 4), fw.u32(sp + 8)
        require(len(self._encoder_queue) < 16, "Dry-run input queue exhausted")
        payload = fw.read(event, 24)
        self._encoder_queue.append((function, dispatcher, payload))
        self.encoder_log.append(
            dict(
                kind="defer",
                function=hex(function),
                tick=self.now(),
                payload=payload.hex(),
            )
        )
        self.returned(1)

    def extra_hook(self, uc, pc, *args):
        if pc == 0x40021DE0:
            self._performance = False
            if self._awaiting_recorder:
                self._recorder_drawn = True
            if self.navigation and self.navigation[-1]["drawn_at"] is None:
                self.navigation[-1]["drawn_at"] = self.now()
                self.navigation[-1]["drawn_pit_time"] = self.clock_state["timers"].now
        super().extra_hook(uc, pc, *args)

    def gesture_hook(self, uc, pc, *_):
        fw = self.fw
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if self._replaying:
            if pc == self._replaying["resume"]:
                require(
                    tuple(uc.reg_read(r) for r in REGISTERS)
                    == self._replaying["registers"],
                    "UI replay clobbered registers/stack",
                )
                require(
                    uc.reg_read(k.UC_M68K_REG_SR) & 31 == self._replaying["ccr"],
                    "UI replay clobbered CCR",
                )
                self.bridge_log.append(
                    dict(
                        function=hex(self._replaying["function"]),
                        resume=hex(pc),
                        tick=self.now(),
                        registers_preserved=True,
                        ccr_preserved=True,
                    )
                )
                self._replaying = None
            else:
                return
        if fw.direct:
            return
        if pc == 0x40015F6C:
            self._controller = fw.u32(sp + 4)
            return
        if pc == 0x400CD702:
            if self.model_armed_status and self.context().recorder_state == 1:
                self.status_model_reads += 1
                self.returned(1)
            return
        if not self.gestures_enabled:
            return
        if pc == 0x400F5050:
            self.invalidate_gesture("project-load", project=True)
        elif pc == 0x40043A30:
            self.invalidate_gesture("save")
        elif pc == 0x40031122 and self._awaiting_recorder is None:
            self.invalidate_gesture("modal")
        elif pc == RECORDER_KEY:
            self._recorder_event = True
        elif pc == LOOP:
            if self._awaiting_recorder:
                started, epoch, kit, dest = self._awaiting_recorder
                if (
                    (epoch, kit) != (self.epoch, fw.u32(0x80004704))
                    or (not self._recorder_drawn and dest != self.destination)
                    or self.now() - started > 64
                ):
                    self.invalidate_gesture("encoder-navigation-stale-or-timeout")
                elif self._recorder_drawn:
                    if self._encoder_queue:
                        function, dispatcher, payload = self._encoder_queue.pop(0)
                        self.encoder_log.append(
                            dict(
                                kind="apply",
                                function=hex(function),
                                tick=self.now(),
                                payload=payload.hex(),
                            )
                        )
                        self.inject_call(function, dispatcher, payload, pc)
                        return
                    self._awaiting_recorder = None
            self.effects(self.gestures.poll(self.now(), self.context()), pc)
        elif pc == ENCODER:
            effects = self.gestures.encoder(self.now(), self.context())
            if effects or self._awaiting_recorder:
                # The original call must not route this turn to the old page.
                # Clone the bounded value-only event; the original is destroyed
                # normally by its caller. Deliver it after the recorder draws.
                self.defer_input(ENCODER, sp)
                self.effects(effects, uc.reg_read(k.UC_M68K_REG_PC))
        elif pc == DISPATCH:
            self._dispatcher = fw.u32(sp + 4)
            self._recorder_event = False
            event = fw.u32(sp + 8)
            key, flags = fw.u32(event + 12), fw.u32(event + 16)
            # A released SAMPLING tap followed by YES means ordinary recorder
            # navigation, unlike YES while SAMPLING is physically held (ARM).
            flush_yes = key == 10 and (self.gestures.pending or self._awaiting_recorder)
            effects = (
                self.gestures.encoder(self.now(), self.context()) if flush_yes else ()
            )
            if not flags & 8:
                if flags & 1:
                    self._held_keys.add(key)
                else:
                    self._held_keys.discard(key)
            if flush_yes:
                self.defer_input(DISPATCH, sp)
                self.effects(effects, uc.reg_read(k.UC_M68K_REG_PC))
                return
            if key == 50 and self._awaiting_recorder:
                # A too-late second tap belongs to the recorder being opened,
                # even if the view's asynchronous activation is still queued.
                self.defer_input(DISPATCH, sp)
                return
            if key != 50:
                if flags & 1 and not flags & 8:
                    self.invalidate_gesture(f"key-{key}")
                return
            if (
                self.gestures.mode != "idle"
                or self.gestures.pending
                or self.now() < self.gestures.quiet_until
            ):
                decision = self.gestures.sampling(
                    self.now(), flags, self.context(), fw.read(event, 24)
                )
                if decision.effects and decision.effects[0].kind == "single":
                    self.defer_input(DISPATCH, sp)
                    self.effects(decision.effects, uc.reg_read(k.UC_M68K_REG_PC))
                    return
                self.effects(decision.effects, pc)
                if decision.consume:
                    self.returned(1)
        elif pc == MAIN_KEY:
            event = fw.u32(sp + 8)
            if fw.u32(event + 12) != 50:
                return
            self._main_owner = fw.u32(sp + 4)
            self._performance = not self._recorder_event
            decision = self.gestures.sampling(
                self.now(), fw.u32(event + 16), self.context(), fw.read(event, 24)
            )
            self.effects(decision.effects, pc)
            if decision.consume:
                self.returned(1)
