"""Stock-file/SHARC oracles for the isolated FREEZE experiment.

Generated disk images are reference fixtures, never buffer persistence.
"""

import array
import hashlib
import math
import struct
import wave

from lab.project import ROOT, require, sha256


def payload(pages, slot):
    memory, descriptor = {}, None
    for tag, block, _ in pages:
        if tag == 0xFFFFFFFF:
            fields = struct.unpack_from(">5I", block)
            if fields[0] == slot and fields[4]:
                descriptor = fields
        else:
            memory[tag] = block
    require(descriptor is not None, "No complete slot header")
    _, left, right, rate, length = descriptor
    require(rate == 48000, "Unexpected sample rate")

    def byte(offset):
        return memory[offset // 4096][offset % 4096]

    return bytes(
        value
        for frame in range(length // 2)
        for offset in (left + frame * 2, right + frame * 2)
        for value in (byte(offset), byte(offset + 1))
    )


def retarget(pages, slot):
    return [
        (
            tag,
            struct.pack(">I", slot) + block[4:] if tag == 0xFFFFFFFF else block,
            header,
        )
        for tag, block, header in pages
    ]


def dump_pages(path, pages):
    path.write_bytes(
        b"".join(struct.pack(">II", tag, header) + data for tag, data, header in pages)
    )


def audio_oracle(out, session_inputs, wire, stable, frozen, histories):
    """Compare A, overlapping B publication, B/A triggers, and late snapshots."""
    # Runtime must install the pinned tools path before these imports.
    # isort: off
    from lab.runtime import STOCK_MAIN

    import plusdrive_check as check
    import tools.plusdrive as pd
    from live_gui_check import write_wav

    from lab.flex_audio import baseline_pages
    from lab.flex_lite import FlexDsp
    # isort: on

    waves = out / "ordinary-reference-only"
    waves.mkdir()
    natives = []
    for index, pages in enumerate((histories["a"], histories["b"], histories["all"])):
        pcm = payload(pages, stable)
        natives.append(pd.build_native_sample(pcm, True))
        with wave.open(str(waves / f"{index}.wav"), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(
                b"".join(pcm[j : j + 2][::-1] for j in range(0, len(pcm), 2))
            )
    card = out / "ordinary-reference-only.img"
    entries = pd.build(str(waves), str(card), main_os=STOCK_MAIN.read_bytes())
    snapshot = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Oracle CPU fixture drift",
    )
    fw = check.Firmware(card, snapshot, STOCK_MAIN)
    try:
        fw.call(0x40154358, [])
        check.check_mount(fw, entries[0]["ref"])
        references = []
        for index in range(3):
            loaded = check.check_load(fw, entries[index]["ref"], stable + index)
            require(
                loaded["load_d0"] == 0
                and all(check.sent_pcm_matches(loaded, natives[index])),
                "Ordinary-file publication differs",
            )
            references.append(retarget(list(fw.pages), stable))
    finally:
        fw.close()
    actual, oracle = FlexDsp(), FlexDsp()
    for engine in (actual, oracle):
        engine.publish(baseline_pages(session_inputs["lp0"]))
    actual.publish(histories["af"])
    oracle.publish(references[0])
    oracle.publish(retarget(references[0], frozen))
    require(
        actual.slot_record(stable) == actual.slot_record(frozen),
        "Frozen DSP descriptor differs",
    )

    voices = (0, 1, 8, 9, 10, 11)

    def block(engine, mask):
        packet = bytearray(wire)
        for offset in (0x22, 0x24, 0x26, 0x28, 0x2A):
            struct.pack_into(
                ">H", packet, offset, mask if offset in (0x22, 0x26) else 0
            )
        for track in (0, 4):
            struct.pack_into(">H", packet, 0xE0 + track * 0x60, stable)
        struct.pack_into(">H", packet, 0xE0 + 5 * 0x60, frozen)
        before = [
            bool(engine.core.peek(0x2412CC + v * 0x1D8 + 0x1B8, 1)) for v in voices
        ]
        engine.frame(bytes(packet))
        lanes = []
        for v, active in zip(voices, before, strict=True):
            base = 0x2412CC + v * 0x1D8
            if active or engine.core.peek(base + 0x1B8, 1):
                words = [
                    engine.core.peek(base + engine.h.FIELD_WORK_BUFFER + i * 4)
                    for i in range(64)
                ]
                floats = struct.unpack("<64f", struct.pack("<64I", *words))
                lanes.append(
                    [0.5 * (floats[i] + floats[i + 1]) for i in range(0, 64, 2)]
                )
            else:
                lanes.append([0.0] * 32)
        result = [v for sample in zip(*lanes, strict=True) for v in sample]
        require(all(map(math.isfinite, result)), "Nonfinite voice PCM")
        return array.array("f", result).tobytes()

    phases = {}
    old_pointers = None
    for name, blocks, trigger in (
        ("a-buffer-and-snapshot", 12, 49),
        ("active-a-during-b-publication", 12, 0),
        ("new-b-and-immutable-a", 40, 49),
        ("late-snapshot-after-eight-generations", 24, 32),
    ):
        if name == "active-a-during-b-publication":
            old_pointers = [actual.core.peek(0x2412CC + v * 0x1D8) for v in voices]
            require(all(old_pointers), "Missing active A voice pointers")
            actual.publish(histories["b"][len(histories["af"]) :])
            require(
                old_pointers
                == [actual.core.peek(0x2412CC + v * 0x1D8) for v in voices],
                "Publication retargeted an active voice",
            )
        if name == "new-b-and-immutable-a":
            oracle.publish(references[1])
        if name == "late-snapshot-after-eight-generations":
            actual.publish(histories["all"][len(histories["b"]) :])
            oracle.publish(references[2])
        a, b = [], []
        for i in range(blocks):
            a.append(block(actual, trigger if i == 0 else 0))
            b.append(block(oracle, trigger if i == 0 else 0))
        require(a == b, "Stock-file voice PCM differs: " + name)
        raw = b"".join(a)
        values = struct.unpack(f"<{len(raw) // 4}f", raw)
        peaks = []
        for lane, track in ((0, 1), (2, 5), (4, 6)):
            stereo = [
                v
                for i in range(0, len(values), 6)
                for v in values[i + lane : i + lane + 2]
            ]
            peaks.append(max(map(abs, stereo)))
            write_wav(str(out / f"{name}-t{track}.wav"), stereo, 48000)
        require(
            peaks[2] > 0 and (trigger == 32 or all(peaks)), "Silent comparison oracle"
        )
        (out / f"{name}.f32").write_bytes(raw)
        phases[name] = dict(
            exact=True,
            blocks=blocks,
            peaks=peaks,
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    return dict(
        phases=phases,
        old_voice_pointers=old_pointers,
        layer="Original stock CPU file loader and SHARC callbacks/renderers; host page delivery, voice buffers, no final-mix or real-time claim",
    )
