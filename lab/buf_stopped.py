"""Opt-in stopped capture through the stock recorder and existing BUF publisher.

FUNC+SONG finishes only this mode's active capture; NO/STOP still cancel.
No track assignment, recorder-setting mutation, or additional PCM storage.
"""

from lab import buf_next_bar as b
from lab import buf_performance as perf
from lab import buf_startup as pending
from lab import recorder_freeze_code as n
from lab.emit import Code

MODE, FINISH = 2, 0x170  # Spare next-bar state, before startup state at +0x180.
# Vacant tail of the existing startup/disabled-diagnostic reservation.
ARM, DISPATCH, CAPTURE, IS_STOPPED = [
    pending.CODE + x for x in (0x3700, 0x3C00, 0x3D00, 0x3F00)
]


def dispatch():
    """GUI ABI (controller*, selected BUF, BAR/NOW); latch mode at admission."""
    c = Code()
    c.emit("4feffff0 48d7001c 242f0014 262f0018 282f001c")
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "new_request")
    b.load(c, b.START_MODE)
    c.imm("0c80", MODE)
    c.branch(6, "timed_request")
    b.load(c, b.PHASE)
    c.imm("0c80", 2)
    c.branch(6, "busy")
    # Finish remains latched to the original destination/context. The GUI poll
    # owns STOP, normalization, validation, and asynchronous publication.
    b.setv(c, FINISH, 1)
    c.emit("7000")
    c.branch(0, "return")
    c.label("new_request")
    n.call(c, perf.PLAY_GET)
    c.emit("4a80")
    c.branch(6, "timed_request")
    c.emit("2f03 2f02")
    n.call(c, ARM, 8)
    c.branch(0, "return")
    c.label("timed_request")
    c.emit("2f03 2f02")
    c.imm("0c84", 1)
    c.branch(6, "bar")
    n.call(c, b.ARM_NOW, 8)
    c.branch(0, "return")
    c.label("bar")
    n.call(c, b.ARM_ONLY, 8)
    c.branch(0, "return")
    c.label("busy")
    c.imm("203c", b.ARM_BUSY)
    c.label("return")
    c.emit("4cd7001c 4fef0010 4e75")
    return c.finish(DISPATCH)


def capture():
    """Called only by the guarded GUI STEP in stopped phase 1/2."""
    c = Code()
    b.controller(c, b.auto.RECORDER_STATE)
    b.load(c, b.PHASE, 1)
    c.imm("0c81", 1)
    c.branch(6, "recording")
    c.emit("4a80")
    c.branch(6, "cancel")
    c.imm("2039", b.TICK)
    b.store(c, b.START_TICK)
    b.store(c, b.LAST_TICK)
    b.setv(c, pending.START_ALLOW, 1)
    b.controller(c, b.START)
    b.setv(c, pending.START_ALLOW, 0)
    b.inc(c, b.STARTS)
    b.setv(c, b.PHASE, 2)
    c.branch(0, "return")
    c.label("recording")
    c.imm("0c80", 2)
    c.branch(7, "recording_clock")
    c.imm("0c80", 3)
    c.branch(7, "native_completed")
    c.imm("0c80", 4)
    c.branch(6, "cancel")
    c.label("native_completed")
    n.call(c, b.NOW_COMPLETED)
    c.emit("4a80")
    c.branch(6, "cancel")
    c.imm("2039", b.TICK)
    b.store(c, b.STOP_TICK)
    b.inc(c, b.STOPS)
    b.setv(c, b.PHASE, 3)
    c.branch(0, "return")
    c.label("recording_clock")
    c.imm("2039", b.TICK)
    b.load(c, b.START_TICK, 1)
    c.emit("9081")
    c.imm("0c80", b.MAX_CAPTURE_FRAMES)
    c.branch(2, "capacity")
    b.load(c, FINISH)
    c.emit("4a80")
    c.branch(6, "stop")
    n.call(c, b.NOW_TIME)
    c.emit("4a80")
    c.branch(7, "return")
    c.branch(11, "cancel")
    c.label("stop")
    c.imm("2039", b.TICK)
    b.store(c, b.STOP_TICK)
    b.controller(c, b.STOP)
    b.inc(c, b.STOPS)
    b.setv(c, b.PHASE, 3)
    c.branch(0, "return")
    c.label("capacity")
    n.call(c, b.CANCEL_FN)
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(6, "return")
    b.setv(c, b.RESULT, b.CAPACITY_RESULT)
    c.branch(0, "return")
    c.label("cancel")
    n.call(c, b.CANCEL_FN)
    c.label("return")
    c.emit("4e75")
    return c.finish(CAPTURE)


def is_stopped():
    """Read-only UI query: latched transaction mode, or stopped when idle."""
    c = Code()
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "idle")
    b.load(c, b.START_MODE)
    c.imm("0c80", MODE)
    c.branch(7, "yes")
    c.emit("7000 4e75")
    c.label("idle")
    n.call(c, perf.PLAY_GET)
    c.emit("4a80")
    c.branch(7, "yes")
    c.emit("7000 4e75")
    c.label("yes")
    c.emit("7001 4e75")
    return c.finish(IS_STOPPED)


def payload():
    return {
        # Opt in with the stopped-recording profile; older experiment payloads
        # remain byte-identical. This covers BAR/NOW auto completion too.
        b.DONE: b.done(release_recorder=True),
        ARM: b.arm_only(
            diagnostics=True,
            performance_controls=True,
            startup_capture=True,
            stopped=True,
        ),
        DISPATCH: dispatch(),
        CAPTURE: capture(),
        IS_STOPPED: is_stopped(),
    }
