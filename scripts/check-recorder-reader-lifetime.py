#!/usr/bin/env python3
# ruff: noqa: E402
"""Stock CPU unload/allocation versus an active stock SHARC ONESHOT reader.

Deliberately unsafe isolated negative control, never a retirement policy.
CPU and DSP run separately; transport, card and call entry are modeled.
"""

import argparse
import array
import hashlib
import os
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored out/runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.runtime import STOCK_MAIN
from lab.flex_lite import FlexDsp, RamFirmware
from lab.flex_dsp_probe import control
import plusdrive_check as check
import tools.plusdrive as pd
# isort: on

sources = source_hashes()
write_json(out / "sources.json", sources)
source_path = Path(__file__)
(out / "executed-probe.py").write_bytes(source_path.read_bytes())
report = dict(
    status="running",
    provenance=provenance,
    native_retirement=False,
    scope=__doc__,
    host_reader_authorization=False,
)
fw = None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audio(dsp, wire, blocks, trigger=False):
    pcm = array.array("f")
    for i in range(blocks):
        pcm.extend(dsp.frame(control(wire, 300, trigger=trigger and i == 0)))
    return pcm.tobytes()


try:
    samples = out / "samples"
    samples.mkdir()
    for take in (1, 2):
        with wave.open(str(samples / f"{take}.wav"), "wb") as f:
            f.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            f.writeframes(
                b"".join(
                    struct.pack(
                        "<hh",
                        (i * (37 + take * 11)) % 20001 - 10000,
                        (i * (61 + take * 17)) % 16001 - 8000,
                    )
                    for i in range(96000)
                )
            )
    card = out / "card.img"
    entries = pd.build(str(samples), str(card), main_os=STOCK_MAIN.read_bytes())
    snapshot = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "CPU snapshot drift",
    )
    fw = RamFirmware(card, snapshot)
    fw.call(0x40154358, [])
    check.check_mount(fw, entries[0]["ref"])
    loaded = check.check_load(fw, entries[0]["ref"], 300)
    require(loaded["load_d0"] == 0, "A failed")
    pages_a = list(fw.pages)
    wire = fw.capture_assignment(300)
    oracle, actual = FlexDsp(), FlexDsp()
    for dsp in (oracle, actual):
        dsp.publish(pages_a)
    first = audio(actual, wire, 8, True)
    require(
        first == audio(oracle, wire, 8, True) and any(first), "Initial oracle differs"
    )
    pointer = actual.voice()["pointer"]
    descriptor_a = actual.slot_record(300)
    require(actual.reading(300), "Old reader not active")
    repeat = FlexDsp(actual.state_bytes())
    fw.pages.clear()
    fw.call(0x401540C6, [300])
    clear_pages = list(fw.pages)
    actual.publish(clear_pages)
    repeat.publish(clear_pages)
    require(actual.slot_record(300)[2] == 0, "Unload did not clear DSP slot")
    require(
        actual.voice()["pointer"] == pointer and actual.voice()["active"],
        "Unload unexpectedly detached old voice",
    )
    tail = audio(actual, wire, 8)
    require(tail == audio(repeat, wire, 8), "Unload repeat differs")
    require(tail == audio(oracle, wire, 8), "Clearing header changed retained reader")
    loaded = check.check_load(fw, entries[1]["ref"], 300)
    require(loaded["load_d0"] == 0, "B failed")
    native_b = pd.build_native_sample(
        b"".join(
            struct.pack(">hh", (i * 59) % 20001 - 10000, (i * 95) % 16001 - 8000)
            for i in range(96000)
        ),
        True,
    )
    require(all(check.sent_pcm_matches(loaded, native_b)), "B publication PCM differs")
    pages_b = list(fw.pages)
    actual.publish(pages_b)
    repeat.publish(pages_b)
    descriptor_b = actual.slot_record(300)
    require(descriptor_a[:3] == descriptor_b[:3], "Allocator did not reuse backing")
    require(
        actual.voice()["pointer"] == pointer and actual.voice()["active"],
        "Old voice lost before reuse control",
    )
    poisoned, expected = audio(actual, wire, 16), audio(oracle, wire, 16)
    require(poisoned != expected, "Premature-reuse control failed to corrupt audio")
    require(poisoned == audio(repeat, wire, 16), "Unsafe reuse is not repeatable")
    # Retrigger comparison requires the same voice/envelope history. A fresh
    # engine is an invalid oracle when the old active voice can crossfade.
    b = audio(actual, wire, 16, True)
    require(b == audio(repeat, wire, 16, True), "New B retrigger repeat differs")
    report.update(
        checks=dict(
            slot_clear_preserves_active_reader=True,
            allocator_reuses_address_without_reader_ack=True,
            premature_reuse_changes_old_voice=True,
            b_publication_pcm_exact=True,
            subsequent_b_trigger_repeat_exact=True,
        ),
        descriptor_a=descriptor_a,
        descriptor_b=descriptor_b,
        active_pointer=pointer,
        unload_packets=len(clear_pages),
        modeled_loader_events=fw.events,
        pcm=dict(
            initial=digest(first),
            after_unload=digest(tail),
            premature_reuse=digest(poisoned),
            retained_a=digest(expected),
            new_b=digest(b),
        ),
    )
    for name, data in (
        ("old-a-expected", expected),
        ("old-a-after-unsafe-reuse", poisoned),
    ):
        (out / f"{name}.f32").write_bytes(data)
    require(source_hashes() == sources, "Source changed during run")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if fw:
        fw.close()
    write_json(out / "report.json", report)
