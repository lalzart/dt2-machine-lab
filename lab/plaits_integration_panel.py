"""Panel-level R3 acceptance: ranges, LFO routing and unsupported-track rejection."""

from lab.project import require


def check(emu, recorder, tap, chord, turn, advance, stage, values, report):
    turn("C", 8, 20)
    stage("model-granular")
    require(values(recorder.frames[-1])["model"] == 1280, "MODEL maximum")
    turn("C", -8, 20)
    stage("model-virtual-analog")
    require(values(recorder.frames[-1])["model"] == 0, "MODEL minimum")
    turn("F", 8, 80)
    stage("duration-12800ms")
    require(
        values(recorder.frames[-1])["length"] == 32512, "Duration maximum transport"
    )
    turn("F", -8, 80)
    stage("duration-100ms")
    require(values(recorder.frames[-1])["length"] == 0, "Duration minimum transport")
    turn("F", 8, 12)
    tap("MOD")
    targets = ("harmonics", "timbre", "morph")
    report["lfo"] = []
    for index, target in enumerate(targets):
        turn("D", 1, 1)
        stage("lfo-menu-" + target)
        tap("DOWN")  # None -> HARM -> TIMB -> MORP
        tap("YES")
        if index == 0:
            turn("H", 8, 12)  # positive depth from stock zero-depth centre
            turn("A", 8, 8)
        stage("lfo-selected-" + target)
        first = len(recorder.frames)
        advance(80_000_000)
        last = len(recorder.frames)
        distinct = {
            name: sorted({values(f)[name] for f in recorder.frames[first:last]})
            for name in targets
        }
        require(len(distinct[target]) > 16, f"LFO did not modulate {target}")
        require(
            all(len(distinct[name]) == 1 for name in targets if name != target),
            f"LFO leaked from {target} into another macro",
        )
        require(all(0 <= v <= 32512 for v in distinct[target]), "LFO range")
        report["lfo"].append(
            dict(
                target=target,
                first_frame=first,
                last_frame=last,
                distinct={k: len(v) for k, v in distinct.items()},
                minimum=min(distinct[target]),
                maximum=max(distinct[target]),
            )
        )
        print("PASS actual LFO-to-wire", report["lfo"][-1], flush=True)
    turn("D", 1, 1)
    for _ in range(3):
        tap("UP")
    tap("YES")
    first = len(recorder.frames)
    advance(60_000_000)
    require(
        all(
            len({values(f)[name] for f in recorder.frames[first:]}) == 1
            for name in targets
        ),
        "None destination did not stop macro modulation",
    )
    report["lfo_none_negative"] = True
    chord("TRK", "TRIG 16")
    chord("FUNC", "SRC")
    for _ in range(8):
        tap("UP")
    for _ in range(7):
        tap("DOWN")
    tap("YES")
    tap("YES")
    stage("unsupported-track-16")
    frame = recorder.frames[-1]
    require(
        int.from_bytes(frame[0x94 + 30 : 0x96 + 30], "big") != 7,
        "Unsupported track selected Plaits",
    )
    require(int.from_bytes(frame[0x94:0x96], "big") == 7, "Track 1 was changed")
    report["track16_rejection"] = True
    tap("NO")
    chord("TRK", "TRIG 1")
    tap("SRC")
