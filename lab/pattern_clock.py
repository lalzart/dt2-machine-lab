"""Opt-in OS 1.16 GUI adapter: SSI cadence and guest-requested sequencer IRQs.

The pinned dependency is unchanged. This adapter delivers the requests that
the firmware writes to INTFRC; it never schedules notes or advances steps.
SSI's 96 kHz request rate is the existing emulator's explicit audio-clock
assumption, not a measurement of the physical board.
"""

from collections import Counter
from types import SimpleNamespace

from lab.project import require

MAX_FRAMES = 32768
SAMPLE_TICK = 0x40966500
# INTC0 high: sequencer deadline and its continuation. INTC2 low: scheduler.
SOFTWARE_SOURCES = ((0xFC048000, 44), (0xFC048000, 57), (0xFC050000, 13))


def pending_interrupts(read, ipl):
    """Read live force/priority registers; forced sources bypass INTC masks."""
    result = []
    for base, source in SOFTWARE_SOURCES:
        register = base + (0x10 if source >= 32 else 0x14)
        if int.from_bytes(read(register, 4), "big") & (1 << (source % 32)):
            level = read(base + 0x40 + source, 1)[0] & 7
            if level > ipl:
                first = 64 + ((base - 0xFC048000) // 0x4000) * 64
                result.append((level, first + source))
    return sorted(result, reverse=True)


class Recorder:
    period = 88000  # GUI status only; frames come from SSI, not FrameForcer.

    def __init__(self):
        self.frames = []
        self.ticks = []
        self.machine = None
        self.recording = True

    def open(self):
        return self

    def close(self):
        pass

    def device_name(self):
        return "buffered pattern capture (SSI clock)"

    def push_frame(self, frame):
        if not self.recording:
            return
        require(len(self.frames) < MAX_FRAMES, "Pattern capture bound exceeded")
        # DSPI exchange is padded to its 0xabc-byte receive extent; TX is 0x802.
        require(len(frame) == 0xABC, "Unexpected OS 1.16 control frame size")
        self.frames.append(bytes(frame))
        self.ticks.append(
            int.from_bytes(self.machine.uc.mem_read(SAMPLE_TICK, 4), "big")
        )

    def frame_stats(self):
        return SimpleNamespace(
            pushed=len(self.frames),
            trig_pushed=sum(
                bool(int.from_bytes(f[0x22:0x24], "big") & 1) for f in self.frames
            ),
            taken=0,
            repeats=0,
            max_depth=len(self.frames),
            merged=0,
        )

    def stats(self):
        return SimpleNamespace(underruns=0)

    def render_stats(self):
        return SimpleNamespace(
            frames=0, clean=0, stopped=0, nonzero_frames=0, median_us=0, p99_us=0
        )


def install(gui, recorder, *, sequencer_irqs=True):
    """Install for a single GUI worker in this process; return runtime state.

    Input is the existing legacy prepared checkpoint. The SSI topology upgrade
    is explicit. Checkpoint reload is deliberately outside this adapter.
    """
    from emu import livesharc
    from emu.ssi import AUDIO_SSI0_REQUEST_HZ, RxHandoverPeer
    from unicorn.m68k_const import UC_M68K_REG_SR

    require(
        not getattr(gui, "_lab_pattern_clock", False), "Pattern clock already installed"
    )
    gui._lab_pattern_clock = True
    original_build, original_spin = gui.build, gui.spin
    state = {"interrupts": Counter()}

    def build(*args, **kwargs):
        kwargs.update(ssi0_request_hz=AUDIO_SSI0_REQUEST_HZ, ssi0_legacy_upgrade=True)
        result = original_build(*args, **kwargs)
        machine, events = result[:2]
        recorder.machine = machine
        events["ssi0_dma"].peer = RxHandoverPeer(machine)
        state.update(machine=machine, events=events)
        return result

    class Clock:
        def __init__(self, machine, timers, period):
            self.pits = timers
            self.forced = self.deferred = 0
            state["timers"] = timers
            source = state["events"]["ssi0_dma"]
            source.ips = timers.sources[0].ips
            source.align(timers.now)

        def on_chunk(self, pc, done):
            if not sequencer_irqs:
                return
            machine = state["machine"]
            ipl = (machine.uc.reg_read(UC_M68K_REG_SR) >> 8) & 7
            pending = pending_interrupts(machine.uc.mem_read, ipl)
            if pending:
                level, vector = pending[0]
                if machine.raise_vector(vector, level=level):
                    state["interrupts"][vector] += 1
                    self.forced += 1

    def spin(*args, **kwargs):
        source = state["events"]["ssi0_dma"]
        ips = kwargs["pits"].sources[0].ips
        if source.ips != ips:
            source.rescale(ips)
        kwargs["async_events"] = (source,)
        result = original_spin(*args, **kwargs)
        worker, target = state.get("worker"), state.get("pause_after")
        if (
            worker is not None
            and target is not None
            and not worker.inbox
            and worker.stats["instrs"] + result[1] >= target
        ):
            # Pause in the worker at this boundary. A host polling loop can
            # otherwise overshoot by a whole chunk and change encoder results.
            state.pop("pause_after")
            worker.pause.set()
        return result

    gui.build, gui.spin, livesharc.FrameForcer = build, spin, Clock
    return state
