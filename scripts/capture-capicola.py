# ruff: noqa: E402
"""Exercise Capicola selection and encoder controls in a prepared OS1.16 CPU."""

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--prepared",
    type=Path,
    help="Reuse a checkpoint beside its exact CAPICOLA_MAIN_OS.bin",
)
p.add_argument(
    "--feedback-replies",
    type=Path,
    help="Replay native reply snapshots for SRC caption checks",
)
p.add_argument(
    "--live-feedback",
    action="store_true",
    help="Refresh SRC automatically with slot-correlated replies",
)
args = p.parse_args()
if args.live_feedback:
    require(args.feedback_replies, "Live feedback requires native v2 reply snapshots")
if args.feedback_replies:
    require(args.prepared, "Feedback UI requires the exact prepared baseline")
    args.feedback_replies = args.feedback_replies.resolve()
if args.prepared:
    args.prepared = args.prepared.resolve()
args.machine = "capicola"
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.pattern_clock import Recorder, install

# isort: off
from lab.runtime import REPO
from emu import gui, panel
# isort: on

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(
    sha256(inputs["main"])
    == "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830",
    "Unexpected inherited CPU image",
)
old = Path(inputs["main"]).read_bytes()
if args.machine == "capicola":
    from lab.capicola_controls import patch_cpu as controls
    from lab.capicola_memory import SAMPLE_BYTES
    from lab.capicola_memory import patch_cpu as reserve
    from lab.flex_native_build import patch_cpu as flex
    from lab.plaits import build_cpu
    from lab.plaits_menu import patch_cpu as menu

    build_cpu(family="integration")
    new, candidate = controls(
        reserve(menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0])[0]
    )
    (out / "CAPICOLA_MAIN_OS.bin").write_bytes(new)

else:
    # Keep the checkpoint's CPU integration; select the untouched stock sampler.
    # Reverting the image under live objects is not a stock cold-boot comparison.
    new = old
    candidate = {
        "sha256": sha256(inputs["main"]),
        "stock_machine_in_prepared_cpu": True,
    }
require(len(old) == len(new), "Image extent changed")
os.chdir(REPO)
os.environ.update(
    DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"], DT2_MAIN_IMG=inputs["main"]
)
# Resume before the stock machine-list widgets are constructed. A ready
# checkpoint already owns copied eight-entry widgets and cannot validate a
# newly extended selector. Use the normal intro/timer path before SSI capture.
import contextlib
import signal

import guirun

if args.prepared:
    inputs["snapshot"] = str(args.prepared.resolve())
    require(
        (args.prepared.resolve().parent / "CAPICOLA_MAIN_OS.bin").read_bytes() == new,
        "Prepared Capicola image mismatch",
    )
else:
    boot_input = str(Path(inputs["snapshot"]).with_name("boot400M.snap"))
    boot_output = out / "capicola-ready.snap"
    original_boot_build = guirun.build

    def boot_build(*a, **kw):
        result = original_boot_build(*a, **kw)
        machine = result[0]
        i = 0
        while i < len(old):
            if old[i] == new[i]:
                i += 1
                continue
            first = i
            while i < len(old) and old[i] != new[i]:
                i += 1
            address = 0x40000400 + first
            require(
                bytes(machine.uc.mem_read(address, i - first)) == old[first:i],
                "Early checkpoint image drift",
            )
            machine.uc.mem_write(address, new[first:i])
        machine.uc.ctl_remove_cache(0x40000400, 0x40000400 + len(new))
        return result

    guirun.build = boot_build
    saved_argv = sys.argv
    sys.argv = [
        "guirun",
        boot_input,
        "--syx",
        inputs["syx"],
        "--card-image",
        inputs["card"],
        "--exact",
        "--intro-timers",
        "pit3",
        "--limit",
        "400000000",
        "--save-at",
        f"400M:{boot_output}",
        "--flexbus-log",
        str(out / "flexbus.raw"),
    ]
    print("Preparing native CPU initialization and sample-load checkpoint", flush=True)
    signal.alarm(600)
    try:
        with (
            (out / "boot.log").open("w") as boot_log,
            contextlib.redirect_stdout(boot_log),
        ):
            guirun.main()
    finally:
        signal.alarm(0)
        sys.argv = saved_argv
        guirun.build = original_boot_build
    require(boot_output.is_file(), "Native initialization checkpoint not produced")
    inputs["snapshot"] = str(boot_output)
    print(
        "CPU initialization checkpoint saved; exercising selector and encoders",
        flush=True,
    )


feedback = None
if args.feedback_replies:
    from emu import livesharc
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_D0

    from lab.capicola_feedback import TEXT
    from lab.capicola_feedback import patch_cpu as feedback_cpu

    if args.live_feedback:
        from lab.capicola_live_feedback import TITLES
        from lab.capicola_live_feedback import patch_cpu as feedback_cpu
    origin = args.feedback_replies.resolve()
    origin_report = json.loads((origin / "report.json").read_text())
    require(
        origin_report["status"] == "passed" and origin_report["native_reply_snapshots"],
        "Unverified native replies",
    )
    payload = (origin / "native-preparation-replies.bin").read_bytes()
    statuses = json.loads((origin / "native-reply-statuses.json").read_text())
    require(len(payload) == len(statuses) * 0xABC, "Reply count mismatch")
    native_replies = [
        payload[i * 0xABC : (i + 1) * 0xABC] for i in range(len(statuses))
    ]
    feedback = dict(
        response=native_replies[0],
        observed=[],
        cases=[],
        source_sha256=sha256(origin / "native-preparation-replies.bin"),
    )
    feedback_image, feedback_meta = feedback_cpu(new)
    (out / "FEEDBACK_MAIN_OS.bin").write_bytes(feedback_image)
    write_json(out / "feedback-cpu-patches.json", feedback_meta)

    class ReplyPeer(livesharc.LiveFramePeer):
        def exchange(self, tx):
            super().exchange(tx)
            if int.from_bytes(tx[0x94:0x96], "big") == 8 and (
                args.live_feedback or int.from_bytes(tx[0xE0:0xE2], "big") == 7
            ):
                return feedback["response"]
            return bytes(len(tx))

    livesharc.LiveFramePeer = ReplyPeer
recorder = Recorder()
runtime = install(gui, recorder, sequencer_irqs=True)
emu = gui.Emulator(
    inputs["snapshot"],
    syx=inputs["syx"],
    card_image=inputs["card"],
    live=recorder,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
runtime["worker"] = emu
emu.pause.set()
emu.start()
deadline = time.monotonic() + 1200
fingerprint = source_hashes()
report = {
    "inputs": inputs,
    "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
    "source_sha256": fingerprint,
    "cpu_candidate": candidate,
    "machine": args.machine,
    "sequencer_irqs": True,
    "gestures": [],
    "stages": [],
    "passes": [],
    "scope": "Prepared OS 1.16; real panel editing and PLAY; SSI clock assumption 96000 Hz; zero DSP replies; initialization resumed from the early checkpoint, not reset; no project reload, final mixer or hardware claim.",
}


def advance(n=2_000_000):
    # Retain one chunk of panel dwell, but make its end independent of host
    # scheduling. The adapter pauses the worker before another chunk begins.
    target = emu.stats["instrs"] + n + gui.BUDGET
    runtime["pause_after"] = target
    emu.pause.clear()
    while emu.stats["status"] != "paused" or emu.stats["instrs"] < target:
        require(not emu.error and emu.is_alive(), f"CPU stopped: {emu.error}")
        require(time.monotonic() < deadline, "1200-second CPU bound exceeded")
        time.sleep(0.005)


def code(name, encoder=False):
    names = emu.encoder_names if encoder else emu.button_names
    hits = [k for k, v in names.items() if v.upper() == name]
    require(len(hits) == 1, f"Unknown control {name}")
    return hits[0]


def button(name, kind):
    report["gestures"].append([emu.stats["instrs"], kind, name])
    emu.inbox.append((kind, code(name), None))
    advance()


def tap(name):
    button(name, "press")
    button(name, "release")


def chord(modifier, name):
    button(modifier, "press")
    tap(name)
    button(modifier, "release")


def turn(encoder, delta, count):
    report["gestures"].append([emu.stats["instrs"], "turn", encoder, delta, count])
    emu._dwell_chunks = 0
    for _ in range(count):
        emu.inbox.append(("encoder", code("ENCODER " + encoder, True), delta))
        advance(200_000)
    emu._dwell_chunks = 4
    advance(4_000_000)


def values(f):
    return {
        k: int.from_bytes(f[o : o + 2], "big")
        for k, o in {
            "trig": 0x22,
            "type": 0x94,
            "note": 2,
            "tune": 0xDA,
            "harmonics": 0xDC,
            "rate": 0xDE,
            "sample": 0xE0,
            "morph": 0xE6,
            "length": 0xE8,
            "level": 0xEC,
        }.items()
    }


def triggers(start):
    return [
        {"frame": i, "tick": recorder.ticks[i], "values": values(recorder.frames[i])}
        for i in range(start, len(recorder.frames))
        if int.from_bytes(recorder.frames[i][0x22:0x24], "big") & 1
    ]


def stage(name):
    row = {
        "name": name,
        "frame": len(recorder.frames),
        "instructions": emu.stats["instrs"],
        "wire": values(recorder.frames[-1]),
    }
    report["stages"].append(row)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(out / (name + ".png")))
    print(json.dumps(row), flush=True)


try:
    require(emu.ready.wait(60) and not emu.error, f"CPU startup failed: {emu.error}")
    # This prepared fixture may already contain small samples. Reject any
    # allocation extending into the newly reserved range before patching.
    begin, end = (
        int.from_bytes(emu._uc.mem_read(a, 4), "big") for a in (0x405A0F64, 0x405A0F68)
    )
    require(
        begin <= end and (end - begin) % 52 == 0 and end - begin <= 52 * 1024,
        "Allocator fixture shape",
    )
    for record in range(begin, end, 52):
        start, size = struct.unpack(">II", emu._uc.mem_read(record + 16, 8))
        require(start + size <= SAMPLE_BYTES + 0x400, "Fixture overlaps reserved bank")
    report["checked_existing_allocations"] = (end - begin) // 52
    # Firmware patches were installed before native widget construction.
    if feedback:
        for w in feedback_meta["writes"]:
            before = bytes.fromhex(w["before"])
            require(
                bytes(emu._uc.mem_read(w["address"], len(before))) == before,
                "Feedback live image drift",
            )
            emu._uc.mem_write(w["address"], bytes.fromhex(w["after"]))
        emu._uc.ctl_remove_cache(0x40000400, 0x40000400 + len(new))

        def observe_hint(uc, *a):
            pointer = uc.reg_read(UC_M68K_REG_D0)
            if pointer in feedback_meta["pointers"]:
                feedback["observed"].append(
                    TEXT[feedback_meta["pointers"].index(pointer)]
                )

        emu._uc.hook_add(UC_HOOK_CODE, observe_hint, begin=0x40016E38, end=0x40016E38)
        if args.live_feedback:
            from unicorn.m68k_const import UC_M68K_REG_A2

            feedback["titles"] = []
            feedback["title_updates"] = 0

            def observe_title(uc, *unused):
                view = uc.reg_read(UC_M68K_REG_A2)
                if int.from_bytes(uc.mem_read(view, 4), "big") != 0x401ED888:
                    return
                widget = int.from_bytes(uc.mem_read(view + 0x6C, 4), "big")
                ptr = int.from_bytes(uc.mem_read(widget + 0x48, 4), "big")
                length = int.from_bytes(uc.mem_read(ptr - 12, 4), "big")
                require(length <= 32, "Native title bound")
                text = bytes(uc.mem_read(ptr, length)).decode("ascii")
                if not text.startswith("CAPICOLA"):
                    return
                if not feedback["titles"] or feedback["titles"][-1] != text:
                    feedback["titles"].append(text)

            def observe_update(uc, *unused):
                view = uc.reg_read(UC_M68K_REG_A2)
                if int.from_bytes(uc.mem_read(view, 4), "big") == 0x401ED888:
                    feedback["title_updates"] += 1

            emu._uc.hook_add(
                UC_HOOK_CODE, observe_title, begin=0x40016ECE, end=0x40016ECE
            )
            emu._uc.hook_add(
                UC_HOOK_CODE, observe_update, begin=0x4005B1E0, end=0x4005B1E0
            )
        report["scope"] = (
            "Prepared OS1.16 CPU receives buffered native SHARC reply snapshots through existing DSPI2/eDMA and native driver copy, then renders SRC captions. Snapshots held for display checks; no coupled DSP timing, final output or hardware proof."
        )
        report["feedback_cpu"] = feedback_meta
        report["native_reply_source_sha256"] = feedback["source_sha256"]

    while len(recorder.frames) < 32 and emu.stats["instrs"] < 220_000_000:
        advance(10_000_000)
    require(len(recorder.frames) >= 32, "Audio-link warmup failed")
    # Dismiss the normal post-initialization file-system notification.
    tap("YES")
    tap("YES")
    tap("STOP")
    tap("STOP")
    chord("FUNC", "SRC")
    for _ in range(10):
        tap("UP")
    for _ in range(7):
        tap("DOWN")
    lo, hi, cap = struct.unpack(">III", emu._uc.mem_read(0x4099CCD4, 12))
    require(
        hi - lo == 36 and cap - lo == 36,
        "Native list allocation/capacity is not nine entries",
    )
    report["native_list_allocation_bytes"] = cap - lo
    stage("menu-capicola")
    tap("YES")
    tap("YES")
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    selected = emu._uc.mem_read(ptr + 0xD6, 1)[0]
    require(selected == 8, f"Capicola selection failed: {selected}")
    tap("TRIG 1")
    advance(8_000_000)
    tap("SRC")
    if args.live_feedback:
        # Reconstruct the native parameter widgets after leaving the selector.
        # Subsequent reply cases deliberately keep SRC open without gestures.
        tap("AMP")
        tap("SRC")
        advance(20_000_000)
    stage("capicola-controls")
    if feedback:
        cases = []
        for low, high, text in [
            (0, 24, "P<25%"),
            (25, 49, "P<50%"),
            (50, 74, "P<75%"),
            (75, 100, "P<100%"),
        ]:
            index = next(
                i
                for i, v in enumerate(statuses)
                if v["state"] == 3
                and low
                <= (
                    100 * v["done"] // v["total"]
                    if args.live_feedback
                    else v["reply_word"] & 127
                )
                <= high
            )
            cases.append(
                (text, native_replies[index], text, "native prepared progress")
            )
        for state, text in [(5, "READY"), (4, "WAIT"), (1, "EMPTY"), (2, "FORMAT")]:
            index = next(
                i
                for i, v in enumerate(statuses)
                if v["state"] == state and (not args.live_feedback or v["slot"] == 7)
            )
            cases.append(
                (
                    text,
                    native_replies[index],
                    text,
                    "native status; invalid metadata cases are negatives",
                )
            )
        for word, label in (
            [
                (0, "missing"),
                (0xFFFF, "unknown"),
                (0x807A, "invalid-index"),
                (0x8085, "wrong-slot-ready"),
                (0xD6E4, "old-protocol"),
            ]
            if args.live_feedback
            else [
                (0, "missing"),
                (0xFFFF, "unknown"),
                (0xD680, "ready-without-100"),
                (0xD5FF, "progress-over-100"),
            ]
        ):
            reply = bytearray(native_replies[-1])
            reply[0x1A:0x1C] = struct.pack(">H", word)
            cases.append(
                (label, bytes(reply), "", "synthetic malformed reply negative")
            )
        for label, response, text, scope in cases:
            feedback["response"] = response
            if not args.live_feedback:
                tap("AMP")
                advance(10_000_000)
            first = len(feedback["observed"])
            if not args.live_feedback:
                tap("SRC")
            advance(20_000_000)
            require(
                bytes(emu._uc.mem_read(0x8000488C, 0xABC)) == response,
                "Native CPU receive-copy mismatch",
            )
            seen = feedback["observed"][first:]
            if args.live_feedback:
                expected_title = TITLES[TEXT.index(text)]
                require(
                    feedback["titles"] and feedback["titles"][-1] == expected_title,
                    f"Wrong automatic caption {label}: {feedback['titles']}",
                )
                seen = [feedback["titles"][-1]]
                updates = feedback["title_updates"]
                advance(10_000_000)
                require(
                    feedback["title_updates"] == updates,
                    "Stable status repeatedly rewrites title",
                )
            else:
                require(
                    seen and seen[-1] == text, f"Wrong native caption {label}: {seen}"
                )
            stage("feedback-" + label.replace("%", "percent").replace("<", "under"))
            feedback["cases"].append(
                dict(
                    label=label,
                    expected=text,
                    observed=seen,
                    scope=scope,
                    reply_word=int.from_bytes(response[0x1A:0x1C], "big"),
                )
            )
        report["feedback_cases"] = feedback["cases"]
        report["refresh"] = "SRC page open; continuous refresh remains deferred"
        if args.live_feedback:
            ready_index = next(
                i for i, v in enumerate(statuses) if v["state"] == 5 and v["slot"] == 7
            )
            feedback["response"] = native_replies[ready_index]
            advance(20_000_000)
            require(feedback["titles"][-1] == TITLES[5], "READY did not recover")
            turn("D", 1, 1)
            require(
                values(recorder.frames[-1])["sample"] != 7,
                "SAMP editing did not change slot",
            )
            advance(20_000_000)
            require(
                feedback["titles"][-1] == TITLES[0], "Old slot READY survived selection"
            )
            stage("feedback-selection-cleared")
            turn("D", -1, 1)
            require(values(recorder.frames[-1])["sample"] == 7, "SAMP did not restore")
            advance(20_000_000)
            require(
                feedback["titles"][-1] == TITLES[5], "Matching READY did not restore"
            )
            tap("AMP")
            updates = feedback["title_updates"]
            feedback["response"] = native_replies[0]
            advance(20_000_000)
            require(
                feedback["title_updates"] == updates, "Capicola refreshed another page"
            )
            report["refresh"] = "Native SRC draw path, no gestures between reply cases"
            report["title_updates"] = feedback["title_updates"]
            report["title_transitions"] = feedback["titles"]
            report["selection_invalidation"] = True
            report["other_page_unchanged"] = True
    else:
        for label, delta, expected in [("rate-min", -8, 0), ("rate-max", 8, 32512)]:
            turn("C", delta, 40)
            stage(label)
            base = int.from_bytes(emu._uc.mem_read(ptr + 0x48 + 27 * 2, 2), "big")
            require(base == expected, f"Rate endpoint did not reach base: {base}")
            # Preserve the stock continuous-control smoothing; wait for its
            # endpoint rather than substituting a raw mirror or bypassing it.
            for _ in range(12):
                advance(10_000_000)
                if abs(values(recorder.frames[-1])["rate"] - expected) <= 1:
                    break
            actual = values(recorder.frames[-1])["rate"]
            require(
                abs(actual - expected) <= 1,
                f"Rate did not reach wire: {actual} vs {expected}",
            )
        # A subsequent trigger must carry the selected type and edited controls.
        first = len(recorder.frames)
        tap("TRIG 1")
        advance(8_000_000)
        events = triggers(first)
        require(events, "No Capicola trigger")
        require(
            all(
                x["values"]["type"] == 8 and abs(x["values"]["rate"] - 32512) <= 1
                for x in events
            ),
            "Trigger control mismatch",
        )
        report["trigger_events"] = events
    require(not emu._faulted_pages, "CPU faulted pages")
    require(source_hashes() == fingerprint, "Source changed during capture")
    report["status"] = "passed"
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    frames = recorder.frames
    (out / "capicola.dtfr").write_bytes(
        b"DTFR"
        + struct.pack("<II", 1, len(frames))
        + b"".join(struct.pack("<I", len(f)) + f for f in frames)
    )
    report["worker_error"] = emu.error
    report["faulted_pages"] = sorted(emu._faulted_pages)
    write_json(out / "capture.json", report)
