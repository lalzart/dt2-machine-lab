"""Bounded SINE replay checks; expected results are never rewritten."""

import array
import math

from lab import cpu, dsp
from lab.formats import read_frames
from lab.metrics import analyze_sine
from lab.project import ROOT, read_json, require, sha256, write_json
from lab.runtime import FIXTURE, OUT


def source(name):
    result = array.array("f")
    result.frombytes((OUT / f"{name}-source.f32").read_bytes())
    return result


def render(
    name,
    *,
    machine=7,
    frames=450,
    sine=False,
    route=False,
    as_stock=False,
    capture=None,
    preroll=0,
):
    dsp.render(
        machine,
        route,
        frames,
        as_stock=as_stock,
        sine=sine,
        preroll=preroll,
        capture=FIXTURE / "captures" / (capture or f"type-{machine}.dtfr"),
        label=name,
    )
    return read_json(OUT / f"{name}.json")


def lifecycle():
    frames = read_frames(FIXTURE / "captures/sine-type-7.dtfr")
    trig = next(i for i, f in enumerate(frames) if f[0x22:0x24] != b"\0\0")
    require(trig <= 150, "Trigger outside pre-roll budget")
    frames = [frames[0]] * (150 - trig) + frames
    steady, trigger = frames[-1], frames[150]
    stock = read_frames(FIXTURE / "captures/type-6.dtfr")[-1]
    engine = dsp.Dsp((OUT / "SINE_BLOB.bin").read_bytes())
    samples = array.array("f")
    states = {}
    for i in range(650):
        wire = frames[i] if i < len(frames) else steady
        if i in (220, 500):
            wire = trigger
        elif 300 <= i < 400:
            wire = stock
        engine.frame(wire)
        samples.extend(engine.source)
        if i == 302:
            states[i] = [engine.core.peek(0x200F0100 + 4 * j) for j in range(8)]
    require(all(map(math.isfinite, samples)), "Non-finite lifecycle output")
    reference = samples[151 * 64 : 171 * 64]
    require(
        samples[221 * 64 : 241 * 64] == reference, "Retrigger changed phase/envelope"
    )
    require(states[302] == [0] * 8, "Switch-away did not clear state")
    require(not any(samples[401 * 64 : 500 * 64]), "Tone resumed without trigger")
    require(samples[501 * 64 : 521 * 64] == reference, "Trigger after switch differs")
    return {"ok": True, "retrigger": True, "switch_clear": True, "silent_return": True}


def build():
    cpu_report = cpu.build()
    dsp.build_route_blob(sine=True)
    return {
        "cpu": cpu_report["patched_sha256"],
        "dsp": sha256(OUT / "SINE_BLOB.bin"),
        "code_bytes": (OUT / "sine-code.bin").stat().st_size,
        "scope": "Built CPU/DSP image overrides; no CPU boot in this command",
    }


def run(mode):
    built = build()
    result = {
        "ok": True,
        "build": built,
        "checks": {},
        "limits": [
            "Prepared stock-initialized DSP state",
            "Voice-buffer PCM, not final mix",
            "No CPU recapture, physical timing or hardware test",
        ],
    }
    write_json(OUT / "build.json", built)
    if mode == "build":
        return result
    rendered = render(
        "sine-440", frames=1500, sine=True, preroll=150, capture="sine-type-7.dtfr"
    )
    result["checks"]["signal"] = analyze_sine(source("sine-440"))
    result["render"] = rendered
    if mode in ("render", "profile"):
        return result
    expected = read_json(ROOT / "tests/fixtures/sine-1.16.json")["expected"]
    require(
        built["cpu"] == expected["sine_main_sha256"],
        "SINE CPU build differs from baseline",
    )
    require(
        built["dsp"] == expected["sine_blob_sha256"],
        "SINE DSP build differs from baseline",
    )
    require(
        sha256(OUT / "sine-440.f32") == expected["sine_pcm_sha256"],
        "SINE PCM differs from baseline",
    )
    render("repeat", frames=1500, sine=True, preroll=150, capture="sine-type-7.dtfr")
    require(
        (OUT / "repeat.f32").read_bytes() == (OUT / "sine-440.f32").read_bytes(),
        "Repeat PCM mismatch",
    )
    result["checks"]["exact_repeat_and_baseline"] = True
    render("stock", machine=6)
    render("stock-with-sine", machine=6, sine=True)
    require(
        (OUT / "stock.f32").read_bytes() == (OUT / "stock-with-sine.f32").read_bytes(),
        "Stock PCM changed",
    )
    result["checks"]["stock_isolation"] = True
    render("route", route=True)
    render("comparator", as_stock=True)
    require(
        (OUT / "route.f32").read_bytes() == (OUT / "comparator.f32").read_bytes(),
        "Clone PCM differs with identical controls",
    )
    result["checks"]["clone_parity"] = True
    render("negative", frames=1500, route=True, preroll=150, capture="sine-type-7.dtfr")
    window = source("negative")[14400:24000]
    mean = sum(window) / len(window)
    projections = [
        sum(
            (v - mean) * wave(2 * math.pi * 440 * i / 96000)
            for i, v in enumerate(window)
        )
        * 2
        / len(window)
        for wave in (math.sin, math.cos)
    ]
    amplitude = math.hypot(*projections)
    require(amplitude < 0.00125, "440 Hz survives with new DSP hook disabled")
    result["checks"]["negative_440hz_amplitude"] = amplitude
    result["checks"]["lifecycle"] = lifecycle()
    return result
