"""Isolated OS1.16 Sketch/BUF placement; existing emulator emitters stay intact.

Keep arena-relative offsets so local branches and structure arithmetic retain
their meaning. Relocate only audited long instruction operands and explicitly
classified pointer tables, never a byte-pattern replacement over an image.
This experimental reservation has CPU-emulator evidence, not physical ownership.
"""

import hashlib
import struct
from dataclasses import dataclass

from lab.coldfire import audit_code
from lab.cpu_extension import (
    CAVE,
    GUARD,
    LIMIT,
    MAIN_LIMIT,
    RESET,
    RESET_BYTES,
    Segment,
    loader,
    segment_chain,
)
from lab.dt2_116 import BASE as MAIN_BASE
from lab.dt2_116 import STOCK_SHA
from lab.project import require


@dataclass(frozen=True)
class Arena:
    name: str
    source: int
    size: int
    destination: int


# Separate from the existing 64 KiB Arp/Flex reservation. One guarded interval
# per inherited arena preserves state ABI and avoids a new compacting linker.
START = LIMIT
_SPECS = (
    ("destination", 0x10300000, 0x1000),
    ("generations", 0x10400000, 0x8000),
    ("worker", 0x10600000, 0xB000),
    ("freeze_queue", 0x10700000, 0x4000),
    ("sender", 0x10800000, 0x2000),
    ("receipt", 0x10900000, 0x4000),
    ("receive_loop", 0x10A00000, 0x4000),
    ("disabled_diagnostic", 0x10B00000, 0x4000),
    ("generation_seats", 0x10C00000, 0x4000),
    ("retirement", 0x10D00000, 0x10000),
    ("cleanup", 0x10E00000, 0x4000),
    ("performance", 0x10F00000, 0x4000),
    ("next_bar", 0x11000000, 0x8000),
    ("sketch", 0x11100000, 0x8000),
    ("freeze_source", 0x11200000, 0x4000),
)
_cursor = START
_arenas = []
for _name, _source, _size in _SPECS:
    _arenas.append(Arena(_name, _source, _size, _cursor + 0x100))
    _cursor += _size + 0x200
ARENAS = tuple(_arenas)
END = (_cursor + 4095) & ~4095
# Append only in the managed profile; inherited reservations and offsets stay exact.
MANAGED_ARENA = Arena("managed", 0x11300000, 0x4000, END + 0x100)
MANAGED_END = (MANAGED_ARENA.destination + MANAGED_ARENA.size + 0x100 + 4095) & ~4095
ASSIGN_ARENA = Arena("assign_popup", 0x11400000, 0x4000, MANAGED_END + 0x100)
ASSIGN_END = (ASSIGN_ARENA.destination + ASSIGN_ARENA.size + 0x100 + 4095) & ~4095


def relocate(value):
    for arena in (*ARENAS, MANAGED_ARENA, ASSIGN_ARENA):
        if arena.source <= value < arena.source + arena.size:
            return arena.destination + value - arena.source
    # All known synthetic CPU addresses must have an explicit arena owner.
    require(
        not 0x10000000 <= value < 0x11500000, f"Unowned synthetic address {value:#x}"
    )
    return value


def relocate_code(raw, address):
    """The audited subset has at most one long extension per instruction.

    A six-byte instruction contains its long operand at +2. Other forms cannot
    hide a relocatable long: check and reject such an emitter change. Local
    relative branches are preserved by whole-arena placement.
    """
    data, relocations = bytearray(raw), []
    for instruction in audit_code(raw, address):
        off = instruction["address"] - address
        size = len(bytes.fromhex(instruction["bytes"]))
        if size == 6 and instruction["kind"] != "BRANCH":
            value = int.from_bytes(raw[off + 2 : off + 6], "big")
            target = relocate(value)
            if target != value:
                struct.pack_into(">I", data, off + 2, target)
                relocations.append(dict(offset=off + 2, source=value, target=target))
        else:
            for at in range(off + 2, off + size - 3, 2):
                value = int.from_bytes(raw[at : at + 4], "big")
                require(relocate(value) == value, "Unreviewed long operand placement")
    audit_code(data, relocate(address))
    return bytes(data), relocations


class Overlay:
    def __init__(self, stock):
        require(
            hashlib.sha256(stock).hexdigest() == STOCK_SHA,
            "Sketch needs exact OS1.16 MAIN",
        )
        self.stock, self.parts, self.hooks = stock, {}, {}
        self.pointer_hooks = {}

    def put(self, at, raw, label, kind="code"):
        require(
            raw and kind in ("code", "stock-trampoline", "data", "pointers"),
            "Invalid payload",
        )
        # An overlay may replace an entry, never silently overlap its neighbor.
        for other, (data, _, _) in self.parts.items():
            require(
                other == at or at + len(raw) <= other or at >= other + len(data),
                f"Payload overlap {label}",
            )
        self.parts[at] = (raw, label, kind)

    def group(self, parts, owner):
        for at, raw in parts.items():
            self.put(at, raw, f"{owner}/{at:#x}")

    def jump(self, at, expected, target, label):
        require(len(expected) >= 6 and len(expected) % 2 == 0, "Hook extent")
        require(
            self.stock[at - MAIN_BASE : at - MAIN_BASE + len(expected)] == expected,
            f"Sketch stock hook drift: {label}",
        )
        require(at not in self.hooks, f"Duplicate hook {label}")
        raw = (
            b"\x4e\xf9"
            + struct.pack(">I", target)
            + b"\x4e\x71" * ((len(expected) - 6) // 2)
        )
        self.hooks[at] = (expected, raw, label)

    def pointer(self, at, expected, target, label):
        require(
            at not in self.pointer_hooks and at not in self.hooks,
            "Duplicate hook " + label,
        )
        require(
            self.stock[at - MAIN_BASE : at - MAIN_BASE + 4]
            == struct.pack(">I", expected),
            "Sketch stock pointer drift: " + label,
        )
        self.pointer_hooks[at] = (expected, target, label)


def compose(
    stock,
    *,
    arm_diagnostics=False,
    clock_fix=False,
    operation_diagnostics=False,
    buf_selector=False,
    performance_controls=False,
    navigation_fixes=False,
    fixed_buf_slots=False,
    startup_capture=False,
    copy_shortcuts=False,
    stopped_recording=False,
    recording_led=False,
    monitor_labels=False,
    freeze_h_slots=False,
    sketchbook_save=False,
    managed_buffers=False,
    assign_popup=False,
    buf_loading=False,
    early_buf_setup=False,
):
    """Final native install graph of SketchUI; no Machine or host job execution."""
    from lab import buf_auto_retirement as auto
    from lab import buf_freeze as bf
    from lab import buf_next_bar as nb
    from lab import buf_performance as perf
    from lab import recorder_ack_loop as loop
    from lab import recorder_destination as dest
    from lab import recorder_dsp_reuse as paused
    from lab import recorder_freeze_code as n
    from lab import recorder_freeze_worker_code as q
    from lab import recorder_native_retirement as t
    from lab import recorder_retirement as obs
    from lab import recorder_seat_reuse as seats
    from lab import recorder_worker_code as w
    from lab import sketch as s

    normal = dest
    require(
        not buf_loading or managed_buffers, "BUF loading UI requires managed buffers"
    )
    require(not early_buf_setup or buf_loading, "Early BUF setup requires loading UI")
    require(
        not freeze_h_slots or (fixed_buf_slots and copy_shortcuts and clock_fix),
        "FREEZE H slots require fixed BUF slots, COPY and the clock profile",
    )
    if freeze_h_slots:
        from lab import buf_freeze_slots as frozen_slots
    require(
        not performance_controls or clock_fix,
        "Performance controls require the working clock profile",
    )

    require(
        not navigation_fixes or (buf_selector and performance_controls),
        "Navigation fixes require BUF selector and performance controls",
    )
    require(
        not fixed_buf_slots or navigation_fixes,
        "Fixed BUF slots require navigation fixes",
    )
    require(
        not startup_capture or fixed_buf_slots, "Startup capture requires fixed H slots"
    )
    require(
        not stopped_recording or (startup_capture and performance_controls),
        "Stopped recording requires the startup and performance profiles",
    )
    o = Overlay(stock)
    o.put(dest.LABEL, b"DEST\0", "destination/label", "data")
    o.put(
        dest.TABLE,
        struct.pack(">5I", *(dest.ARENA + 0x110 + i * 8 for i in range(5))),
        "destination/table",
        "pointers",
    )
    for i, name in enumerate(("NORMAL", "BUF 1", "BUF 2", "BUF 3", "BUF 4")):
        o.put(
            dest.ARENA + 0x110 + i * 8,
            name.encode() + b"\0",
            f"destination/name{i}",
            "data",
        )
    o.group(
        {
            dest.DRAW: dest.cell(),
            dest.SET: dest.setter(),
            dest.ROTATE: dest.rotation(),
            normal.FILTER: normal.allocation_filter(),
        },
        "destination",
    )
    o.put(normal.RESERVED, b"\xff" * 52, "destination/reservations", "data")
    o.jump(0x400209AE, bytes.fromhex("487800052f02"), dest.ROTATE, "destination/rotate")
    o.jump(0x400221A0, bytes.fromhex("487800014878002f"), dest.DRAW, "destination/draw")
    o.jump(
        normal.SEARCH_SITE,
        normal.SEARCH_BYTES,
        normal.FILTER,
        "destination/reserved-search",
    )

    parts, originals = n.payload()
    for i, (op, (pc, _)) in enumerate(n.RESOURCE_SITES.items()):
        o.jump(pc, originals[pc], w.DISPATCH + i * 256, "resource/" + op)
    for i, pc in enumerate((n.SAVE, n.LOAD_PROJECT)):
        before = stock[pc - MAIN_BASE : pc - MAIN_BASE + 8]
        tramp, guard = n.TRAMPOLINES + 0x700 + i * 32, n.GUARDS + i * 256
        parts[tramp] = before + b"\x4e\xf9" + struct.pack(">I", pc + 8)
        parts[guard] = n.project_guard(guard, tramp)
        o.jump(pc, before, guard, "volatile-project-guard/" + str(i))
    for i, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
        before = stock[pc - MAIN_BASE : pc - MAIN_BASE + 8]
        tramp = n.TRAMPOLINES + 0x800 + i * 32
        parts[tramp] = before + b"\x4e\xf9" + struct.pack(">I", pc + 8)
        o.jump(pc, before, t.GUARDS + i * 256, "slot-guard/" + str(i))
    o.group(parts, "generations")
    o.put(n.STATE, struct.pack(">I", 1), "generations/epoch", "data")
    o.put(n.GEN_NAME, b"/TEMP/BUF-GEN\0".ljust(32, b"\0"), "generations/name", "data")
    for buf in range(4):
        for serial in range(8):
            o.put(
                n.NAMES + (buf * 8 + serial) * 32,
                f"/TEMP/B{buf + 1}-{serial + 1:03d}".encode().ljust(32, b"\0"),
                f"generations/frozen-name-{buf}-{serial}",
                "data",
            )
    o.group(w.payload(), "worker")
    if fixed_buf_slots:
        from lab import buf_fixed_slots

        o.put(
            w.SETUP,
            buf_fixed_slots.setup(freeze_h_slots=freeze_h_slots),
            "fixed-buf-slots/setup",
        )
    finish_raw, _, _ = o.parts.pop(w.FINISH)
    require(finish_raw[24:32] == bytes(8), "Worker FINISH padding drift")
    o.put(w.FINISH, finish_raw[:24], "worker/finish-dispatch")
    o.put(w.FINISH + 32, finish_raw[32:], "worker/finish-body")
    for i, (name, text) in enumerate(w.f.USE_ERRORS.items()):
        text = (
            "BUF: SESSION LIMIT" if name == "limit" else text.replace("FLEX:", "BUF:")
        )
        o.put(
            w.ERROR_NAMES + i * 64,
            text.encode().ljust(64, b"\0"),
            "worker/error/" + name,
            "data",
        )
    o.put(
        w.ERROR_TABLE,
        struct.pack(
            ">" + "I" * len(w.ERRORS),
            *(w.ERROR_NAMES + i * 64 for i in range(len(w.ERRORS))),
        ),
        "worker/errors",
        "pointers",
    )
    o.jump(0x40021986, bytes.fromhex("487940229675"), w.ERROR_ENTRY, "worker/error")
    o.jump(0x400CD638, bytes.fromhex("4feffff448d70c04"), w.PAGE_FILTER, "worker/page")
    for pc, (before, target) in w.HOOKS.items():
        o.jump(pc, bytes.fromhex(before), target, "worker/entry/" + hex(pc))
    require(
        not operation_diagnostics or (arm_diagnostics and not clock_fix),
        "Operation diagnostics require ARM diagnostics and a separate clock profile",
    )
    o.group(q.payload(operation_diagnostics=operation_diagnostics), "freeze-queue")
    if freeze_h_slots:
        o.put(
            q.BODY,
            n.freeze(address=q.BODY, worker_gate=q.GATE, slot_picker=frozen_slots.PICK),
            "freeze-h-slots/body",
        )
        o.put(frozen_slots.PICK, frozen_slots.picker(), "freeze-h-slots/picker")
    o.put(q.LABEL, b"FREEZE\0", "freeze-queue/label", "data")
    o.group(loop.cpu(), "receive-loop")
    o.group(seats.payload(), "generation-seats")
    o.group(t.payload() | t.receipt_cpu(), "retirement")
    sender = obs.sender()
    for old, new in ((n.FIRST_ID, seats.FIRST_ID), (n.FIRST_ID + 7, seats.LAST_ID)):
        require(sender.count(struct.pack(">I", old)) == 1, "Sender bounds drift")
        sender = sender.replace(struct.pack(">I", old), struct.pack(">I", new))
    o.put(obs.CF_ENTRY, sender, "retirement/sender")
    o.put(paused.ENTRY, bytes.fromhex("70ff4e75"), "retirement/disabled-paused-command")
    o.put(t.LABEL, b"RETIRE\0", "retirement/label", "data")
    o.put(
        n.LOOKUP,
        b"\x4e\xf9" + struct.pack(">I", t.LOOKUP_GUARD),
        "retirement/lookup-gate",
    )
    o.jump(loop.RECEIVE_SITE, loop.RECEIVE_BYTES, loop.RECEIVE, "retirement/receive")
    o.jump(t.DRIVER_SITE, t.DRIVER_BYTES, t.DRIVER, "retirement/driver")
    o.group(auto.payload(), "cleanup")
    o.group(perf.payload(), "performance")
    o.put(q.SUBMIT, b"\x4e\xf9" + struct.pack(">I", perf.SUBMIT), "performance/submit")
    require(not clock_fix or arm_diagnostics, "Clock fix requires diagnostics")
    o.group(
        nb.payload(
            arm_diagnostics=arm_diagnostics,
            clock_fix=clock_fix,
            operation_diagnostics=operation_diagnostics,
            performance_controls=performance_controls,
        ),
        "next-bar",
    )
    o.put(nb.STATE + nb.ENABLED, struct.pack(">I", 1), "next-bar/enabled", "data")
    o.put(nb.LABEL, b"BUF AUTO USE\0", "next-bar/label", "data")
    o.put(perf.KEY, nb.key_bridge(), "next-bar/key")
    o.put(w.WORKER, seats.worker(require_track=False), "next-bar/worker")
    o.put(w.ASSIGN, w.assign(assign_track=False), "next-bar/publication")
    o.put(perf.ELIGIBLE, perf.eligible(all_oneshot=False), "next-bar/eligibility")
    o.jump(nb.ARM_SITE, nb.ARM_BYTES, nb.ARM, "next-bar/arm")
    o.jump(nb.CLOCK_SITE, nb.CLOCK_BYTES, nb.IRQ, "next-bar/clock")
    o.jump(q.GUI, q.GUI_BYTES, nb.POLL, "next-bar/poll")
    o.put(w.ENTRY, b"\x4e\xf9" + struct.pack(">I", nb.USE_GATE), "sketch/use-gate")
    o.group(
        bf.payload(slot_picker=frozen_slots.PICK if freeze_h_slots else None),
        "freeze-source",
    )
    o.put(q.GATE, b"\x4e\xf9" + struct.pack(">I", bf.GATE), "freeze-source/gate")
    o.put(q.DONE, b"\x4e\xf9" + struct.pack(">I", bf.DONE), "freeze-source/done")
    o.put(s.STATE + s.BUF, struct.pack(">I", 1), "sketch/selection", "data")
    pointer_tables = {s.TEXTS, s.VTABLE - 8, s.SHARED, s.SHARED + 0x50}
    panel_code = set()
    if sketchbook_save:
        from lab import sketch_panel

        panel_code = {sketch_panel.DRAW}
    for at, raw in s.payload(
        stock,
        arm_enabled=True,
        freeze_enabled=True,
        arm_diagnostics=arm_diagnostics,
        clock_fix=clock_fix,
        operation_diagnostics=operation_diagnostics,
        performance_controls=performance_controls,
        navigation_fixes=navigation_fixes,
        fixed_buf_slots=fixed_buf_slots,
        startup_capture=startup_capture,
        copy_shortcuts=copy_shortcuts,
        stopped_recording=stopped_recording,
        monitor_labels=monitor_labels,
        freeze_h_slots=freeze_h_slots,
        sketchbook_save=sketchbook_save,
        managed_buffers=managed_buffers,
    ).items():
        kind = (
            "pointers"
            if at in pointer_tables
            else "data"
            if s.STRINGS <= at < s.LINE and at not in panel_code
            else "code"
        )
        o.put(at, raw, "sketch/" + hex(at), kind)
    o.jump(perf.KEY_SITE, perf.KEY_BYTES, s.KEY, "sketch/key")
    o.jump(s.MAIN_SITE, s.MAIN_BYTES, s.MAIN_KEY, "sketch/main-key")
    o.jump(s.ROUTE_SITE, bytes.fromhex("4fefffa048d77cfc"), s.ROUTE, "sketch/route")
    o.put(
        n.FREEZE,
        b"\x4e\xf9" + struct.pack(">I", w.FREEZE_GUARD) + b"\x4e\x71",
        "worker/freeze-guard",
    )
    if buf_selector:
        from lab import buf_selector as selector

        for at, raw in selector.payload(
            stock, navigation_fixes=navigation_fixes, buf_loading=buf_loading
        ).items():
            kind = "data" if selector.NAMES <= at < selector.NAMES + 128 else "code"
            o.put(at, raw, f"buf-selector/{at:#x}", kind)
        for at, (before, target) in selector.HOOKS.items():
            o.jump(at, bytes.fromhex(before), target, "buf-selector/" + hex(at))
        for at, (before, target) in selector.POINTERS.items():
            o.pointer(at, before, target, "buf-selector/" + hex(at))
    if startup_capture:
        from lab import buf_startup as pending

        o.group(pending.payload(), "startup-capture")
        o.put(
            nb.ARM_ONLY,
            b"\x4e\xf9" + struct.pack(">I", pending.ARM_BODY),
            "startup/arm",
        )
        o.put(
            nb.INIT_BODY,
            b"\x4e\xf9" + struct.pack(">I", pending.INIT_GATE),
            "startup/setup-gate",
        )
        for at, raw in {
            nb.CHECK: nb.check(clock_fix=True, startup_capture=True),
            nb.STEP: nb.step(performance_controls=True, startup_capture=True),
            nb.CANCEL_FN: nb.cancel(startup_capture=True),
            nb.POLL: nb.poll(startup_capture=True),
            nb.WORKER: nb.worker(startup_capture=True),
            nb.USE_GATE: nb.use_gate(startup_capture=True),
        }.items():
            o.put(at, raw, "startup/" + hex(at))
        o.put(pending.FREEZE_STOCK, o.parts[perf.ELIGIBLE][0], "startup/freeze-stock")
        o.put(
            perf.ELIGIBLE,
            b"\x4e\xf9" + struct.pack(">I", pending.FREEZE_GATE),
            "startup/freeze-gate",
        )
        o.put(
            auto.STEP,
            b"\x4e\xf9" + struct.pack(">I", pending.AUTO_GATE),
            "startup/cleanup-gate",
        )
        guard = n.GUARDS + 0x100
        o.put(pending.PROJECT_STOCK, o.parts[guard][0], "startup/project-stock")
        o.put(
            guard,
            b"\x4e\xf9" + struct.pack(">I", pending.PROJECT_GATE),
            "startup/project-gate",
        )
        before, _raw, label = o.hooks[nb.ARM_SITE]
        o.hooks[nb.ARM_SITE] = (
            before,
            b"\x4e\xf9" + struct.pack(">I", pending.ARM_GATE) + b"\x4e\x71",
            label,
        )
        o.jump(
            pending.BATCH_SITE,
            pending.BATCH_BYTES,
            pending.BATCH_ENTER,
            "startup/batch-enter",
        )
        o.jump(
            pending.BATCH_RETURN,
            pending.RETURN_BYTES,
            pending.BATCH_LEAVE,
            "startup/batch-return",
        )
        o.jump(
            nb.START, pending.START_BYTES, pending.START_GATE, "startup/recorder-start"
        )
    for at, (raw, label, _kind) in list(o.parts.items()):
        if (
            n.TRAMPOLINES <= at < n.GUARDS
            or w.TRAMP <= at < w.TRAMP + 0x100
            or at in (q.TRAMP, t.RAW_DRIVER, s.MAIN_KEY + 0x80)
        ):
            # Prefix bytes came from authenticated stock; only the appended
            # JMP belongs to this emitter's independently audited ISA subset.
            require(raw[-6:-4] == b"\x4e\xf9", "Stock trampoline tail")
            require(
                not any(
                    0x10000000 <= int.from_bytes(raw[i : i + 4], "big") < 0x11300000
                    for i in range(0, len(raw) - 9, 2)
                ),
                "Synthetic stock prefix",
            )
            o.put(at, raw, label, "stock-trampoline")
    if stopped_recording:
        from lab import buf_stopped as free

        o.group(free.payload(), "stopped-recording")
        o.put(
            nb.CHECK,
            nb.check(clock_fix=True, startup_capture=True, stopped_recording=True),
            "stopped/check",
        )
        o.put(
            nb.STEP,
            nb.step(
                performance_controls=True, startup_capture=True, stopped_recording=True
            ),
            "stopped/step",
        )
    if recording_led:
        from lab import sketch_led

        require(
            stopped_recording, "Recording LED requires the performance recorder profile"
        )
        o.group(sketch_led.payload(), "sketch-recording-led")
        o.jump(
            sketch_led.SITE,
            sketch_led.PREFIX,
            sketch_led.ENTRY,
            "sketch-recording-led/output",
        )
    if sketchbook_save:
        from lab import sketchbook_preview as preview
        from lab import sketchbook_save as book
        from lab import sketchbook_ui as book_ui
        from lab.dt2_116 import verify_navigation_names

        require(freeze_h_slots, "Sketchbook save requires the R10 fixed freeze profile")
        verify_navigation_names(stock)
        o.group(book.payload(), "sketchbook-save")
        o.group(preview.payload(), "sketchbook-preview")
        require(
            preview.OLD_ROUTE + len(o.parts[s.ROUTE][0]) <= book.RX,
            "Preview route reaches receive data",
        )
        o.put(preview.OLD_ROUTE, o.parts[s.ROUTE][0], "sketchbook-preview/stock-route")
        o.put(
            s.ROUTE,
            b"\x4e\xf9" + struct.pack(">I", preview.CANCEL_KEY),
            "sketchbook-preview/cancel-key",
        )
        ui_parts, ui_data = book_ui.payload()
        o.group(ui_parts, "sketchbook-ui")
        for at, raw in ui_data.items():
            o.put(at, raw, "sketchbook-ui/text", "data")
        o.put(preview.NAME, b"PREVIEW\0", "sketchbook-preview/name", "data")
        for at, target in ((book.WORKER, preview.DISPATCH), (book.DONE, preview.DONE)):
            o.put(at, b"\x4e\xf9" + struct.pack(">I", target), "sketchbook-preview/job")
        for op, at in (
            ("open", preview.OPEN),
            ("read", preview.READ),
            ("size", preview.SIZE),
            ("close", preview.CLOSE),
        ):
            pc = book.n.RESOURCE_SITES[op][0]
            before, _raw, label = o.hooks[pc]
            o.hooks[pc] = (
                before,
                b"\x4e\xf9"
                + struct.pack(">I", at)
                + b"\x4e\x71" * ((len(before) - 6) // 2),
                label,
            )
        before, _raw, label = o.hooks[q.GUI]
        o.hooks[q.GUI] = (before, b"\x4e\xf9" + struct.pack(">I", book_ui.POLL), label)
        for at, target in ((w.RETIRE, book.CAPTURE), (t.DRIVER, book.DRIVER)):
            o.put(
                at, b"\x4e\xf9" + struct.pack(">I", target), "sketchbook-save/wrapper"
            )
        for i, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
            before, _raw, label = o.hooks[pc]
            o.hooks[pc] = (
                before,
                b"\x4e\xf9" + struct.pack(">I", book.GUARDS + i * 128) + b"\x4e\x71",
                label,
            )
        o.jump(
            0x401586B8,
            bytes.fromhex("66544a826724"),
            book.EXCLUSIVE,
            "sketchbook-save/exclusive-open",
        )
        o.put(book.LABEL, b"SKETCHBOOK SAVE\0", "sketchbook-save/label", "data")
        o.put(book.DIRECTORY, b"/Sketchbook\0", "sketchbook-save/directory", "data")
    if managed_buffers:
        from lab import sketch_managed as managed

        require(
            sketchbook_save and stopped_recording,
            "Managed buffers require the full Sketchbook profile",
        )
        o.group(managed.payload(), "managed")
        o.put(
            managed.TEXTS,
            b"".join(x.encode().ljust(16, b"\0") for x in (*managed.LABELS, "BUFFER")),
            "managed/status-text",
            "data",
        )
        o.put(managed.OLD_ARM, o.parts[s.ARM_SUBMIT][0], "managed/original-arm")
        o.put(s.ARM_SUBMIT, b"\x4e\xf9" + struct.pack(">I", managed.ARM), "managed/arm")
        before, _, label = o.hooks[q.GUI]
        o.hooks[q.GUI] = (before, b"\x4e\xf9" + struct.pack(">I", managed.POLL), label)
    if buf_loading:
        from lab import buf_loading as loading

        code, data = loading.payload(early_setup=early_buf_setup)
        o.group(code, "buf-loading")
        for at, raw in data.items():
            o.put(at, raw, "buf-loading/labels", "data")
        o.put(
            managed.STATUS_TEXT,
            managed.status_text(buf_loading=True),
            "buf-loading/status",
        )
        o.put(managed.POLL, managed.poll(buf_loading=True), "buf-loading/retry")
        if early_buf_setup:
            o.put(
                pending.BATCH_ENTER,
                pending.batch_enter(early_setup=loading.EARLY),
                "buf-loading/early-setup",
            )
    if assign_popup:
        from lab import sketch_assign as prompt

        require(managed_buffers, "Assignment popup requires managed buffers")
        code, pointers, data = prompt.payload(stock)
        o.group(code, "assign-popup")
        for parts, kind in ((pointers, "pointers"), (data, "data")):
            for at, raw in parts.items():
                o.put(at, raw, f"assign-popup/{at:#x}", kind)
        o.put(
            nb.DONE,
            nb.done(release_recorder=True, publication_notify=prompt.QUEUE),
            "assign-popup/publication-notify",
        )
        o.put(
            s.ROUTE, b"\x4e\xf9" + struct.pack(">I", prompt.ROUTE), "assign-popup/route"
        )
        before, _, label = o.hooks[q.GUI]
        o.hooks[q.GUI] = (before, b"\x4e\xf9" + struct.pack(">I", prompt.POLL), label)
    return o


def build(
    stock,
    *,
    arm_diagnostics=False,
    clock_fix=False,
    operation_diagnostics=False,
    buf_selector=False,
    performance_controls=False,
    navigation_fixes=False,
    fixed_buf_slots=False,
    startup_capture=False,
    copy_shortcuts=False,
    stopped_recording=False,
    recording_led=False,
    monitor_labels=False,
    freeze_h_slots=False,
    sketchbook_save=False,
    managed_buffers=False,
    assign_popup=False,
    buf_loading=False,
    early_buf_setup=False,
):
    overlay = compose(
        stock,
        arm_diagnostics=arm_diagnostics,
        clock_fix=clock_fix,
        operation_diagnostics=operation_diagnostics,
        buf_selector=buf_selector,
        performance_controls=performance_controls,
        navigation_fixes=navigation_fixes,
        fixed_buf_slots=fixed_buf_slots,
        startup_capture=startup_capture,
        copy_shortcuts=copy_shortcuts,
        stopped_recording=stopped_recording,
        recording_led=recording_led,
        monitor_labels=monitor_labels,
        freeze_h_slots=freeze_h_slots,
        sketchbook_save=sketchbook_save,
        managed_buffers=managed_buffers,
        assign_popup=assign_popup,
        buf_loading=buf_loading,
        early_buf_setup=early_buf_setup,
    )
    arenas = (*ARENAS, MANAGED_ARENA) if managed_buffers else ARENAS
    reservation_end = MANAGED_END if managed_buffers else END
    if assign_popup:
        arenas = (*arenas, ASSIGN_ARENA)
        reservation_end = ASSIGN_END
    images = {a.name: bytearray(a.size) for a in arenas}
    writes, fixes = [], []
    for at, (raw, label, kind) in sorted(overlay.parts.items()):
        arena = next((a for a in arenas if a.source <= at < a.source + a.size), None)
        require(
            arena is not None and at + len(raw) <= arena.source + arena.size,
            "Arena overflow " + label,
        )
        if kind == "stock-trampoline":
            tail, relocations = relocate_code(raw[-6:], at + len(raw) - 6)
            data = raw[:-6] + tail
            relocations = [
                dict(r, offset=r["offset"] + len(raw) - 6) for r in relocations
            ]
        elif kind == "code":
            data, relocations = relocate_code(raw, at)
        elif kind == "pointers":
            require(len(raw) % 4 == 0, "Pointer table alignment")
            data, relocations = bytearray(raw), []
            for off in range(0, len(raw), 4):
                value = int.from_bytes(raw[off : off + 4], "big")
                target = relocate(value)
                if target != value:
                    struct.pack_into(">I", data, off, target)
                    relocations.append(dict(offset=off, source=value, target=target))
            data = bytes(data)
        else:
            data, relocations = raw, []
        images[arena.name][at - arena.source : at - arena.source + len(data)] = data
        writes.append(
            dict(
                address=relocate(at),
                source_address=at,
                after=data.hex(),
                label=label,
                kind=kind,
            )
        )
        fixes.extend(
            dict(label=label, address=relocate(at) + r["offset"], **r)
            for r in relocations
        )
    segments, guards = [], []
    for arena in arenas:
        data = bytes(images[arena.name])
        used = (len(data.rstrip(b"\0")) + 3) & ~3
        segments.extend(
            (
                Segment(arena.destination - 0x100, GUARD),
                Segment(arena.destination, data[:used], arena.size - used),
                Segment(arena.destination + arena.size, GUARD),
            )
        )
        guards.extend(
            (
                [arena.destination - 0x100, len(GUARD)],
                [arena.destination + arena.size, len(GUARD)],
            )
        )
    chain = segment_chain(segments, reservation=(START, reservation_end))
    image = bytearray(stock)
    hooks = []
    for at, (expected, raw, label) in sorted(overlay.hooks.items()):
        data, relocations = relocate_code(raw, at)
        image[at - MAIN_BASE : at - MAIN_BASE + len(data)] = data
        hooks.append(
            dict(
                address=at,
                before=expected.hex(),
                after=data.hex(),
                label=label,
                kind="code",
            )
        )
        fixes.extend(
            dict(label=label, address=at + r["offset"], **r) for r in relocations
        )
    for at, (expected, source, label) in sorted(overlay.pointer_hooks.items()):
        target = relocate(source)
        data = struct.pack(">I", target)
        image[at - MAIN_BASE : at - MAIN_BASE + 4] = data
        hooks.append(
            dict(
                address=at,
                before=struct.pack(">I", expected).hex(),
                after=data.hex(),
                label=label,
                kind="pointers",
            )
        )
        fixes.append(
            dict(label=label, address=at, offset=0, source=source, target=target)
        )
    reset_loader = loader(MAIN_BASE + len(stock))
    for at, expected, data, label in (
        (CAVE, bytes(len(reset_loader)), reset_loader, "reset/loader"),
        (
            RESET,
            RESET_BYTES,
            b"\x4e\xb9" + struct.pack(">I", CAVE) + b"\x4e\x71",
            "reset/hook",
        ),
    ):
        require(
            image[at - MAIN_BASE : at - MAIN_BASE + len(expected)] == expected,
            "Reset guard " + label,
        )
        image[at - MAIN_BASE : at - MAIN_BASE + len(data)] = data
        hooks.append(
            dict(
                address=at,
                before=expected.hex(),
                after=data.hex(),
                label=label,
                kind="code",
            )
        )
    image.extend(chain)
    require(len(image) <= MAIN_LIMIT, "Sketch MAIN staging ceiling")
    require(
        image[0x40312000 - MAIN_BASE : len(stock)] == stock[0x40312000 - MAIN_BASE :],
        "SRAM reset source changed",
    )
    metadata = dict(
        firmware="Digitakt II OS1.16",
        profile="isolated-sketch-buf",
        hardware_ready=False,
        stock_sha256=STOCK_SHA,
        sha256=hashlib.sha256(image).hexdigest(),
        reservation=[START, reservation_end],
        reservation_bytes=reservation_end - START,
        arenas=[vars(a) for a in arenas],
        guards=guards,
        relocations=fixes,
        payload_bytes=sum(len(bytes.fromhex(w["after"])) for w in writes),
        initialized_bytes=sum(len(s.data) for s in segments),
        bss_bytes=sum(s.bss for s in segments),
        appended_bytes=len(chain),
        chain_address=MAIN_BASE + len(stock),
        main_bytes=len(image),
        segments=[
            dict(
                destination=s.destination,
                data_bytes=len(s.data),
                bss=s.bss,
                sha256=hashlib.sha256(s.data).hexdigest(),
            )
            for s in segments
        ],
        hooks=hooks,
        writes=writes,
        limits=[
            "Experimental DDR ownership; physical cache/DMA/stack behavior unverified",
            "Isolated profile; cannot compose with existing Flex/Arp/Plaits patch hooks",
            "Prepared recorder input and DSP transport differ from physical startup",
            "NORMAL ready label retains stock SAVE; BUF ready label is not dynamically changed",
        ],
    )
    if managed_buffers:
        metadata["managed_buffers"] = True
    if assign_popup:
        metadata["assign_popup"] = True
    if buf_loading:
        metadata["buf_loading"] = True
    if early_buf_setup:
        metadata["early_buf_setup"] = True
    if recording_led:
        metadata["recording_led"] = True
    if sketchbook_save:
        metadata["sketchbook_save"] = True
    if monitor_labels:
        metadata["monitor_labels"] = True
    if freeze_h_slots:
        from lab import buf_freeze_slots as frozen_slots

        metadata["freeze_h_slots"] = True
        metadata["freeze_public_slots"] = list(frozen_slots.SLOTS)
    if arm_diagnostics:
        metadata["arm_diagnostics"] = True
    if clock_fix:
        metadata["clock_fix"] = True
    if operation_diagnostics:
        metadata["operation_diagnostics"] = True
    if buf_selector:
        metadata["buf_selector"] = True
    if performance_controls:
        metadata["performance_controls"] = True
    if navigation_fixes:
        metadata["navigation_fixes"] = True
    if fixed_buf_slots:
        from lab.buf_fixed_slots import PUBLIC

        metadata["fixed_buf_slots"] = True
        metadata["buf_public_slots"] = list(PUBLIC)
    if startup_capture:
        metadata["startup_capture"] = True
    if copy_shortcuts:
        metadata["copy_shortcuts"] = True
    if stopped_recording:
        metadata["stopped_recording"] = True
    return bytes(image), metadata
