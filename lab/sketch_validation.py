"""Validation-only runtime selection and stock-file voice PCM comparisons.

No firmware edits, host recorder commits, live-state clones or retirement grants.
The private instruction adapters already exist; fingerprint them before reuse.
"""

import array
import hashlib
import json
import math
import os
import struct
import wave
from collections import Counter
from types import MethodType

from lab.project import ROOT, require, sha256, write_json


def runtime(output):
    from lab.type7a_runtime import activate

    build = ROOT / "out/runs/sharc-type7a-build-20261022-02"
    meta = activate(build)
    from lab import runtime as rt
    from lab.pattern_native import RESUME

    private = ROOT / "out/runs/buf-alignment-fext-runtime-20261022-01"
    manifest = json.loads((private / "build.json").read_text())
    library = private / "target/release/libsharc_native.dylib"
    require(manifest["base"] == meta["library_sha256"], "Runtime base drift")
    require(manifest["core"] == meta["core_sha256"], "Runtime core drift")
    require(
        manifest["resume_sha256"] == hashlib.sha256(RESUME.encode()).hexdigest(),
        "Resume adapter drift",
    )
    require(sha256(library) == manifest["sha256"], "Private library drift")
    rt.LIB = library
    os.environ["SHARC_NATIVE_LIB"] = str(library)
    from lab import pattern_dsp as fext
    from lab import recorder_ack_loop as loop

    fext.library = lambda: library
    cases = fext.check_fext()
    metadata = dict(
        library=str(library),
        sha256=sha256(library),
        type7a_core=meta["core_sha256"],
        fext_cases=cases,
        scope="Existing conditional MODIFY, exact-site register FEXT and resume ABI; prepared SEC reset model",
    )
    write_json(output / "runtime.json", metadata)
    Base = loop.engine_class()

    class Engine(Base):
        def __init__(self, *args, **kwargs):
            self.fext_count = 0
            super().__init__(*args, **kwargs)

        def run_segment(self, start, stop):
            core, native = self.core, self.native
            core.set_option(native.OPT_STOP_PC, stop)
            core.fresh_call(start)
            before = core.stats()["instructions"]
            bound = 4_000_000
            while bound > 0:
                bound -= core.run(bound)
                if core.pc() == stop:
                    break
                why = core.halt_reason or ""
                require(
                    core.pc() == fext.FEXT_PC
                    and why.startswith(
                        "native-trap: sharc_core.compute._compute:339: raise ValueError"
                    ),
                    f"Unexpected native trap {core.pc():#x}: {why}",
                )
                fext.execute_fext(core, native)
                self.fext_count += 1
                bound -= 1
            require(core.pc() == stop, "Native segment exceeded bound")
            core.set_option(native.OPT_STOP_PC, -1)
            return core.stats()["instructions"] - before

    return Engine, metadata


def pages(path):
    raw = path.read_bytes()
    require(len(raw) % 4104 == 0, "Incomplete native page capture")
    return [
        (
            struct.unpack_from(">I", raw, i)[0],
            raw[i + 8 : i + 4104],
            struct.unpack_from(">I", raw, i + 4)[0],
        )
        for i in range(0, len(raw), 4104)
    ]


def playback(output, inputs, wire, stable, frozen, history_a, history_b):
    """Fresh stock DSPs; exact A/retained-A/B/frozen-A plus an incorrect-source control."""
    # Runtime paths must be selected before these imports.
    import plusdrive_check as check
    import tools.plusdrive as pd
    from live_gui_check import write_wav

    from lab.flex_audio import baseline_pages
    from lab.flex_freeze_probe import payload, retarget
    from lab.flex_lite import FlexDsp
    from lab.pattern_dsp import PatternDsp
    from lab.runtime import STOCK_MAIN

    output.mkdir(exist_ok=False)
    require(
        history_b[: len(history_a)] == history_a, "Publication history prefix changed"
    )
    pcm_a, pcm_b = (payload(h, stable) for h in (history_a, history_b))
    require(pcm_a != pcm_b, "A/B fixtures must differ")
    source = output / "stock-file-references"
    source.mkdir()
    for label, pcm in (("A", pcm_a), ("B", pcm_b)):
        with wave.open(str(source / f"{label}.wav"), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(
                b"".join(pcm[j : j + 2][::-1] for j in range(0, len(pcm), 2))
            )
    card = output / "stock-file-references.img"
    entries = pd.build(str(source), str(card), main_os=STOCK_MAIN.read_bytes())
    snapshot = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Stock CPU oracle fixture drift",
    )
    cpu = check.Firmware(card, snapshot, STOCK_MAIN)
    references = []
    try:
        cpu.call(0x40154358, [])
        check.check_mount(cpu, entries[0]["ref"])
        for index, pcm in enumerate((pcm_a, pcm_b)):
            loaded = check.check_load(cpu, entries[index]["ref"], stable + index)
            require(
                loaded["load_d0"] == 0
                and all(
                    check.sent_pcm_matches(loaded, pd.build_native_sample(pcm, True))
                ),
                "Stock file oracle failed",
            )
            references.append(retarget(list(cpu.pages), stable))
    finally:
        cpu.close()

    baseline = baseline_pages(inputs["lp0"])
    voices = (0, 1, 8, 9, 10, 11)
    all_runs = []
    results = {}
    for repeat in range(2):
        engines = [FlexDsp(), FlexDsp(), FlexDsp()]
        for dsp in engines:
            dsp.fallbacks = Counter()
            dsp.call = MethodType(PatternDsp.call, dsp)
            dsp.publish(baseline)
        actual, oracle, wrong = engines
        actual.publish(history_a)
        oracle.publish(references[0])
        oracle.publish(retarget(references[0], frozen))
        wrong.publish(references[0])
        wrong.publish(retarget(references[0], frozen))
        require(
            actual.slot_record(stable) == actual.slot_record(frozen),
            "Frozen descriptor differs from A",
        )

        def block(dsp, trigger):
            packet = bytearray(wire)
            for off in (0x22, 0x24, 0x26, 0x28, 0x2A):
                struct.pack_into(
                    ">H", packet, off, trigger if off in (0x22, 0x26) else 0
                )
            for track, slot in ((0, stable), (4, stable), (5, frozen)):
                struct.pack_into(">H", packet, 0xE0 + track * 0x60, slot)
            active = [
                bool(dsp.core.peek(0x2412CC + v * 0x1D8 + 0x1B8, 1)) for v in voices
            ]
            dsp.frame(bytes(packet))
            lanes = []
            for v, was_active in zip(voices, active, strict=True):
                base = 0x2412CC + v * 0x1D8
                if was_active or dsp.core.peek(base + 0x1B8, 1):
                    words = [
                        dsp.core.peek(base + dsp.h.FIELD_WORK_BUFFER + i * 4)
                        for i in range(64)
                    ]
                    samples = struct.unpack("<64f", struct.pack("<64I", *words))
                    lanes.append(
                        [0.5 * (samples[i] + samples[i + 1]) for i in range(0, 64, 2)]
                    )
                else:
                    lanes.append([0.0] * 32)
            values = [v for sample in zip(*lanes, strict=True) for v in sample]
            require(all(map(math.isfinite, values)), "Nonfinite voice PCM")
            return array.array("f", values).tobytes()

        run = []
        for name, count, mask in (
            ("A-and-frozen-A", 12, 49),
            ("retained-A-during-B-publication", 12, 0),
            ("current-B-and-frozen-A", 48, 49),
            ("late-frozen-A", 24, 32),
        ):
            if name == "retained-A-during-B-publication":
                pointers = [actual.core.peek(0x2412CC + v * 0x1D8) for v in voices]
                require(all(pointers), "No active old readers")
                actual.publish(history_b[len(history_a) :])
                require(
                    pointers
                    == [actual.core.peek(0x2412CC + v * 0x1D8) for v in voices],
                    "Publication retargeted an active reader",
                )
            if name == "current-B-and-frozen-A":
                oracle.publish(references[1])
                wrong.publish(references[1])
                wrong.publish(retarget(references[1], frozen))
            chunks, incorrect = [], []
            for index in range(count):
                x, y, z = (block(dsp, mask if index == 0 else 0) for dsp in engines)
                require(x == y, f"Stock-file PCM differs: {name}, block {index}")
                chunks.append(x)
                incorrect.append(z)
            data = b"".join(chunks)
            values = struct.unpack(f"<{len(data) // 4}f", data)
            stereo = [
                [
                    v
                    for i in range(0, len(values), 6)
                    for v in values[i + lane : i + lane + 2]
                ]
                for lane in (0, 2, 4)
            ]
            peaks = [max(map(abs, s)) for s in stereo]
            require(
                peaks[2] > 0 and (mask == 32 or all(peaks)), "Silent playback oracle"
            )
            if name == "current-B-and-frozen-A":
                require(
                    data != b"".join(incorrect),
                    "Incorrect-source control cannot distinguish frozen A from B",
                )
            if repeat == 0:
                (output / f"{name}.f32").write_bytes(data)
                for track, samples in zip((1, 5, 6), stereo, strict=True):
                    write_wav(str(output / f"{name}-T{track}.wav"), samples, 48000)
                results[name] = dict(
                    exact=True,
                    blocks=count,
                    peaks=peaks,
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            run.append(data)
        all_runs.append(b"".join(run))
    require(all_runs[0] == all_runs[1], "Fresh-state exact repeat differs")
    result = dict(
        status="pass",
        phases=results,
        exact_repeat=True,
        different_source_control=True,
        recordings_performed=0,
        layer="Fresh stock-file CPU loads and stock SHARC voice buffers; modeled LP0/control schedule, no live SEC clone, final mix, real time or hardware claim",
    )
    write_json(output / "report.json", result)
    return result
