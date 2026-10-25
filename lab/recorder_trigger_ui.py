"""Opt-in trigger comparison using stock ARM detection and one dry request sink."""

from dataclasses import asdict
from queue import Empty, SimpleQueue

from lab.project import require
from lab.recorder_gesture_ui import LOOP, DryRunUI
from lab.recorder_gestures import Effect, Gestures
from lab.recorder_trigger_model import ArmRequests

# isort: off
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on

ARM = 0x40015F9C
GLOBAL_ARM_RETURN = 0x40016BAE
SETTINGS_VALUE = 0x4004CCC6  # CHAN is reached even when MON is unavailable.


class TriggerComparisonUI(DryRunUI):
    def __init__(self, *args, trigger_method="both", buf_arm="next-bar", **kwargs):
        require(trigger_method in ("double", "chord", "both"), "Unknown trigger trial")
        require(buf_arm in ("stock", "next-bar"), "Unknown BUF arm option")
        self.trigger_method, self.buf_arm = trigger_method, buf_arm
        self.arm_requests = ArmRequests()
        self.request_log = []
        self.arm_entry_log = []
        self._settings_data = None
        self._settings_owner = None
        self._bar_steps = SimpleQueue()
        self._model_bar_index = 10
        super().__init__(*args, **kwargs)
        self.gestures = Gestures(double_enabled=trigger_method != "chord")

    def install(self, main):
        super().install(main)
        for pc in (ARM, SETTINGS_VALUE):
            require(
                self.fw.read(pc, 8) == main[pc - 0x40000400 : pc - 0x40000400 + 8],
                f"Trigger comparison site drift {pc:#x}",
            )
            self.hooks.append(
                self.fw.uc.hook_add(UC_HOOK_CODE, self.compare_hook, begin=pc, end=pc)
            )

    def settings_snapshot(self):
        owner = (self.epoch, self.fw.u32(0x80004704))
        require(
            self._settings_data and self._settings_owner == owner,
            "Recorder settings have not been observed for this project",
        )
        return self.fw.read(self._settings_data + 0x1AE, 36)

    def request_arm(self, trigger):
        context = self.context()
        try:
            settings = self.settings_snapshot()
        except ValueError:
            result = "refused"
        else:
            result = self.arm_requests.request(
                epoch=self.epoch,
                kit=context.kit,
                destination=context.destination,
                settings=settings,
            )
        plan = asdict(self.arm_requests.plan) if self.arm_requests.plan else None
        if plan:
            plan["settings"] = plan["settings"].hex()
        self.request_log.append(
            dict(trigger=trigger, result=result, plan=plan, tick=self.now())
        )
        kind = (
            "would-arm"
            if result in ("armed", "unclocked")
            else "would-cancel"
            if result == "canceled"
            else "would-refuse"
        )
        effect = Effect(kind, context.destination, self.now())
        super().effects((effect,), LOOP)

    def effects(self, effects, resume):
        for effect in effects:
            if effect.kind == "would-arm":
                self.request_arm("double")
            else:
                super().effects((effect,), resume)

    def test_bar(self, index, *, epoch=None, clock=1):
        """Only an explicitly injected model event; never called by a timer."""
        plan = self.arm_requests.boundary(
            index, epoch=self.epoch if epoch is None else epoch, clock=clock
        )
        self.request_log.append(
            dict(
                trigger="test-bar",
                index=index,
                clock=clock,
                would_start=plan is not None,
                tick=self.now(),
            )
        )
        if plan:
            super().effects(
                (Effect("would-record", plan.destination, self.now()),), LOOP
            )
        return plan

    def queue_test_bar(self):
        """GUI thread posts only a token; guest access stays on its worker."""
        self._bar_steps.put(True)

    def invalidate_gesture(self, reason, *, project=False):
        super().invalidate_gesture(reason, project=project)
        if project:
            self._settings_data = self._settings_owner = None
            self.arm_requests.project(self.epoch)
        elif reason in ("key-21", "key-12", "save", "modal"):
            if self.arm_requests.plan:
                self.request_log.append(
                    dict(trigger="cancel", reason=reason, tick=self.now())
                )
            self.arm_requests.cancel()

    def gesture_hook(self, uc, pc, *args):
        super().gesture_hook(uc, pc, *args)
        if pc == LOOP and self.gestures_enabled and not self.fw.direct:
            ctx = self.context()
            if not self.arm_requests.validate(
                epoch=self.epoch,
                kit=ctx.kit,
                destination=ctx.destination,
                busy=ctx.busy or ctx.recorder_state != 0,
            ):
                self.request_log.append(
                    dict(trigger="cancel", reason="context", tick=self.now())
                )
                self.feedback = None
            try:
                self._bar_steps.get_nowait()
            except Empty:
                pass
            else:
                self._model_bar_index += 1
                self.test_bar(self._model_bar_index)

    def compare_hook(self, uc, pc, *_):
        fw = self.fw
        if fw.direct:
            return
        if pc == SETTINGS_VALUE:
            self._settings_data = uc.reg_read(k.UC_M68K_REG_A0)
            self._settings_owner = (self.epoch, fw.u32(0x80004704))
            return
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        entry = dict(
            tick=self.now(),
            caller=hex(fw.u32(sp)),
            destination=self.destination,
            suppressed=False,
        )
        self.arm_entry_log.append(entry)
        if (
            not self.gestures_enabled
            or not self.destination
            or self.buf_arm == "stock"
            or self.trigger_method == "double"
            or fw.u32(sp) != GLOBAL_ARM_RETURN
        ):
            return
        ctx = self.context()
        if (
            self._performance
            and ctx.recorder_state == 0
            and not ctx.busy
            and not (self._held_keys - {50, 10})
            and self._awaiting_recorder is None
        ):
            self.request_arm("chord")
            entry["suppressed"] = True
            self.returned(0)  # Native caller retains its own key-consumption path.
