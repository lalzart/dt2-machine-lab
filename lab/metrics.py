"""Signal and descriptive work metrics; no emulator imports."""

import math

from lab.project import require


def distribution(values):
    ordered = sorted(values)
    require(bool(ordered), "Empty profiling series")
    return {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "p50": ordered[math.ceil(len(ordered) * 0.50) - 1],
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "p99": ordered[math.ceil(len(ordered) * 0.99) - 1],
        "max_observed": ordered[-1],
    }


def analyze_sine(source):
    begin = 151 * 64
    require(len(source) == 96000, "Wrong source length")
    require(all(map(math.isfinite, source)), "Non-finite source sample")
    require(not any(source[:begin]), "Source starts before latched trigger")
    require(not any(source[begin + 24000 :]), "Source continues after envelope")
    error = max(
        abs(
            source[begin + i]
            - 0.125
            * max(0, min(1, i / 480, (24000 - i) / 480))
            * math.sin(2 * math.pi * i * 440 / 96000)
        )
        for i in range(24000)
    )
    crossings = []
    for i in range(begin + 1000, begin + 22000):
        if source[i] <= 0 < source[i + 1]:
            crossings.append(i - source[i] / (source[i + 1] - source[i]))
    require(len(crossings) >= 2, "Not enough sine crossings")
    hz = 96000 * (len(crossings) - 1) / (crossings[-1] - crossings[0])
    peak = max(map(abs, source))
    require(error <= 1e-4, f"Analytic sine/envelope error: {error}")
    require(abs(hz - 440) <= 1, f"Wrong frequency: {hz}")
    require(peak <= 0.126, f"Excess source peak: {peak}")
    return {
        "ok": True,
        "hz": hz,
        "source_peak": peak,
        "max_analytic_error": error,
        "silence_before_and_after": True,
    }
