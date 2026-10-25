#!/usr/bin/env python3
"""Connect the OS1.16 BUF recorder to opt-in native DigiKit 38dfbe4.

Build current firmware locally, copy/extend only the boot crate, run a bounded
two-take/FREEZE flow and exact saved-page audio repeats. No pins or upstream sources change.
"""

# ruff: noqa: E402
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import (
    doctor,
    git,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--native-upstream", type=Path, required=True)
p.add_argument("--prepare-only", action="store_true")
p.add_argument(
    "--clock-only",
    action="store_true",
    help="opt-in clock fix: one native capture, real bar-edge trace, refusal/cancellation controls; skip broad audio flow",
)
p.add_argument(
    "--performance-controls",
    action="store_true",
    help="BAR/NOW and page-exit slice; requires --clock-only",
)
p.add_argument(
    "--now-only",
    action="store_true",
    help="Target the NOW slice without repeating the BAR capture",
)
p.add_argument(
    "--targeted-replacement",
    action="store_true",
    help="One BAR then NOW replacement; reuse existing clock-negative coverage",
)
p.add_argument(
    "--replay", type=Path, help="Compare a completed native flow; zero new recordings"
)
p.add_argument(
    "--repeat-flow",
    action="store_true",
    help="Optional second capture workflow; saved audio already repeats by default",
)
p.add_argument(
    "--navigation-fixes",
    action="store_true",
    help="native bank and track-exit regression; requires performance controls",
)
p.add_argument(
    "--track-only",
    action="store_true",
    help="target the native controller gesture after unchanged-selector bank validation",
)
p.add_argument(
    "--fixed-buf-slots",
    action="store_true",
    help="validate the fixed H124-H127 profile",
)
a = p.parse_args()
require(
    not a.performance_controls or a.clock_only,
    "Performance slice requires --clock-only",
)
require(
    not a.now_only or a.performance_controls, "NOW-only requires performance controls"
)
require(
    not a.targeted_replacement or (a.performance_controls and not a.now_only),
    "Targeted replacement requires performance controls and a BAR take",
)
require(
    not a.clock_only or not (a.replay or a.repeat_flow),
    "Clock slice is separate from broad flow/replay",
)
require(
    not a.navigation_fixes or a.performance_controls,
    "Navigation fixes require performance controls",
)
require(
    not a.track_only or (a.navigation_fixes and a.now_only),
    "Track-only requires navigation fixes and NOW-only",
)
require(
    not a.fixed_buf_slots or a.navigation_fixes,
    "Fixed BUF slots require navigation fixes",
)
out, upstream = a.output.resolve(), a.native_upstream.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored output")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.native_migration import REVISION, prepare_recorder_boot
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build
from lab.sketch_device_validation import address as relocate
from lab.sketch_dsp_device import build as build_dsp

env = {
    k: v for k, v in os.environ.items() if not k.startswith(("SHARC_", "DSP_", "DIGI_"))
}
generation = upstream / "out/native/shared-core/gen"
env["SHARC_GEN_DIR"] = str(generation)
gen = {
    str(f.relative_to(generation)): sha256(f)
    for f in generation.iterdir()
    if f.is_file()
}
report = dict(
    status="running",
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    upstream=REVISION,
    generated_core=gen,
    hardware=False,
    pins_changed=False,
)


def run(label, cmd, *, cwd=ROOT, timeout=900):
    print(label, flush=True)
    with (out / f"{label}.log").open("w") as log:
        subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=timeout,
        )


def helper(name, *args):
    code = "import runpy,sys;sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')"
    return [
        sys.executable,
        "-B",
        "-c",
        code,
        str(ROOT / "lab/native" / name),
        *map(str, args),
    ]


def prepare_replay_template(blob):
    """Use the authenticated callback fixture, separately from live cold state."""
    template = ROOT / "out/runs/sketch-native-migration-20261023-07"
    expected = {
        "report.json": "6adb784e490a0e3270f596e553f4a18b04f68ca27e6f737c798cac87ab3f7ec0",
        "prepared.state": "546f91e97f8ac07b4230d99779c9a846f13bd1cac54956f141bf0bb8e403a52f",
        "prepared-options.json": "4d6bcad189b43136cc9838684548ab4d51b32cda596dd632a00dbdaa100a89d4",
    }
    for name, digest in expected.items():
        require(sha256(template / name) == digest, "Replay template drift: " + name)
    proof = json.loads((template / "report.json").read_text())
    require(proof["replay"]["legacy_voice_PCM_exact"], "Unqualified callback template")
    require(
        sha256(blob) == proof["input_hashes"]["blob"],
        "Replay DSP differs from template",
    )
    shutil.copyfile(template / "prepared.state", out / "replay.state")
    shutil.copyfile(template / "prepared-options.json", out / "replay-options.json")
    report["replay_template"] = dict(
        source=str(template),
        hashes=expected,
        scope="Authenticated callback/SEC fixture; live cold-state export remains separate",
    )


if a.replay:
    # A corrected comparator must not require repeating native recordings.
    try:
        source = a.replay.resolve()
        original = json.loads((source / "report.json").read_text())
        flow = json.loads((source / "flow.json").read_text())
        require(
            flow == original["flow"] and flow["status"] == "passed",
            "Incomplete native source flow",
        )
        current_sources = source_hashes()
        changed = [
            k
            for k, v in original["source_hashes"].items()
            if current_sources.get(k) != v
        ]
        require(
            set(changed)
            <= {
                "lab/native/buf_recording_probe.rs",
                "scripts/check-native-buf-recording.py",
            },
            "Native flow source drift: " + str(changed),
        )
        old_prefix = (source / "src/main.rs").read_text().split("fn replay(")[0]
        new_prefix = (
            (ROOT / "lab/native/buf_recording_probe.rs")
            .read_text()
            .split("fn replay(")[0]
        )
        require(old_prefix == new_prefix, "Recording/observer implementation changed")
        require(
            sha256(source / "runner") == original["runner_sha256"],
            "Source native runner drift",
        )
        require(original["generated_core"] == gen, "Native source core differs")
        spec = json.loads((source / "spec.json").read_text())
        require(
            sha256(spec["main"]) == original["firmware"]["main_sha256"],
            "Source MAIN drift",
        )
        require(
            sha256(spec["blob"]) == original["firmware"]["blob_sha256"],
            "Source DSP drift",
        )
        spec["output"] = str(out)
        write_json(out / "spec.json", spec)
        for name in (
            "reset-inputs/image.bin",
            "stock-dsp.image",
            "flow/wire.bin",
            "stock-oracle/A.lp0",
            "stock-oracle/B.lp0",
            "stock-oracle/reference-1.lp0",
            "stock-oracle/reference-2.lp0",
            "stock-oracle/report.json",
        ):
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, dest)
        report["source_flow"] = dict(
            folder=str(source),
            report_sha256=sha256(source / "report.json"),
            flow_sha256=sha256(source / "flow.json"),
            flow=flow,
            recording_and_observer_source_exact=True,
            comparator_source_changes=changed,
            new_recordings=0,
        )
        report["input_hashes"] = {
            str(f.relative_to(out)): sha256(f) for f in out.rglob("*") if f.is_file()
        }
        prepare_replay_template(Path(spec["blob"]))
        report["adapter"] = prepare_recorder_boot(upstream, out / "native-boot")
        (out / "src").mkdir()
        shutil.copyfile(ROOT / "lab/native/buf_recording_probe.rs", out / "src/main.rs")
        shutil.copyfile(ROOT / "lab/native/buf_adapter.rs", out / "src/buf_adapter.rs")
        manifest = (
            (source / "Cargo.toml")
            .read_text()
            .replace(str(source / "native-boot"), str(out / "native-boot"))
        )
        (out / "Cargo.toml").write_text(manifest)
        run(
            "build",
            [
                "rustup",
                "run",
                "1.98.1",
                "cargo",
                "build",
                "--offline",
                "--release",
                "--manifest-path",
                str(out / "Cargo.toml"),
                "--target-dir",
                str(upstream / "out/native/target/generic"),
            ],
            cwd=upstream,
        )
        shutil.copy2(
            upstream / "out/native/target/generic/release/dt2-native-buf-recording",
            out / "runner",
        )
        report["runner_sha256"] = sha256(out / "runner")
        run(
            "replay",
            [str(out / "runner"), str(out / "spec.json"), "replay"],
            cwd=upstream,
        )
        report["replay"] = json.loads((out / "replay.json").read_text())
        require(report["replay"]["recordings"] == 0, "Replay submitted recordings")
        require(source_hashes() == provenance["source_hashes"], "Replay source drift")
        require(not git(upstream, "status", "--porcelain"), "Upstream source changed")
        require(
            gen
            == {
                str(f.relative_to(generation)): sha256(f)
                for f in generation.iterdir()
                if f.is_file()
            },
            "Core drift",
        )
        report.update(
            status="passed-native-recorder-saved-replay",
            recordings=0,
            default_migration_ready=False,
        )
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(out / "report.json", report)
    print(report["status"], flush=True)
    sys.exit(0)


try:
    report["adapter"] = prepare_recorder_boot(upstream, out / "native-boot")
    flags = dict(arm_diagnostics=True, clock_fix=True) if a.clock_only else {}
    if a.performance_controls:
        flags.update(
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=a.navigation_fixes,
            fixed_buf_slots=a.fixed_buf_slots,
        )
    main, meta = build(STOCK_MAIN.read_bytes(), **flags)
    require(
        build(STOCK_MAIN.read_bytes(), **flags) == (main, meta),
        "Current MAIN build is not exact-repeat",
    )
    (out / "SKETCH_MAIN.bin").write_bytes(main)
    write_json(out / "native-patches.json", meta)
    blob, dsp = build_dsp(out / "dsp")
    report["firmware"] = dict(main_sha256=sha256(out / "SKETCH_MAIN.bin"), **dsp)
    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    require(
        sha256(inputs["syx"])
        == "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec",
        "Stock OS1.16 drift",
    )
    require(
        sha256(inputs["card"])
        == "f0a30d418c256ad2d8a87c395a36ffbce2fb8ad0119d755927b442f77df28cea",
        "Card drift",
    )
    from lab.upload import REFERENCE_REVISION, assemble_container, verify_candidate

    ref = ROOT / "out/references/elekloader-upload-audit"
    require(
        git(ref, "rev-parse", "HEAD") == REFERENCE_REVISION
        and not git(ref, "status", "--porcelain"),
        "Container codec drift",
    )
    sys.path[:0] = [str(config["digikit"]), str(ref)]
    from elekloader.codec.aplib import pack_section
    from elekloader.syx import Syx

    stock = Syx(Path(inputs["syx"]).read_bytes())
    raw = assemble_container(stock, {3: pack_section(main), 7: pack_section(blob)})
    report["container"] = verify_candidate(raw, stock, {3: main, 7: blob})
    (out / "candidate-test-fixture.syx").write_bytes(raw)
    reset = ROOT / "out/runs/sketch-dsp-startup-20261023-01/report.json"
    require(
        sha256(reset)
        == "86c599454f5d3dfbecf4e7ee5cd9da7f6b2b2da165caa79d480228738dc3c8e1",
        "Reset model drift",
    )
    write_json(out / "reset-values.json", json.loads(reset.read_text())["reset_values"])
    run(
        "pack-reset",
        helper(
            "sketch_cold_inputs.py",
            out / "dsp/RETIRE_BLOB.bin",
            out / "reset-values.json",
            out / "reset-inputs",
        ),
        cwd=upstream,
    )
    # The same relocations used to build firmware resolve observation symbols.
    symbols = {}
    for label, module in (
        ("nb", nb),
        ("w", w),
        ("n", n),
        ("q", q),
        ("s", s),
        ("bf", bf),
    ):
        symbols[label] = {
            key: (relocate(value) if 0x10000000 <= value < 0x11300000 else value)
            for key, value in vars(module).items()
            if type(value) is int
        }
    write_json(out / "symbols.json", symbols)
    spec = dict(
        clock_only=a.clock_only,
        performance_controls=a.performance_controls,
        now_only=a.now_only,
        targeted_replacement=a.targeted_replacement,
        navigation_fixes=a.navigation_fixes,
        track_only=a.track_only,
        fixed_buf_slots=a.fixed_buf_slots,
        output=str(out),
        stock_syx=inputs["syx"],
        card=inputs["card"],
        candidate=str(out / "candidate-test-fixture.syx"),
        lab=str(ROOT),
        main=str(out / "SKETCH_MAIN.bin"),
        blob=str(out / "dsp/RETIRE_BLOB.bin"),
    )
    write_json(out / "spec.json", spec)
    if not a.clock_only or a.fixed_buf_slots:
        prepare_replay_template(Path(spec["blob"]))
    # A small independent Python-model oracle checks Rust wrap/count/readback.
    import struct

    from lab.flex_recorder import RecorderInput, Take

    source = b"".join(
        struct.pack(">hh", i * 7 - 7000, 5000 - i * 3) for i in range(2048)
    )
    model = RecorderInput(Take(source, True), ticks_per_frame=1)
    model.begin(0xFFFFFFF0)
    counts = [model.count(t) for t in (0xFFFFFFF0, 0xFFFFFFF1, 0x10, 0x4000)]
    model.finish(0x4000)
    write_json(
        out / "model-oracle.json",
        dict(
            source=source.hex(),
            counts=counts,
            chunk=model.chunk(3, 512, 0).hex(),
            extrema=model.extrema(3, 99).hex(),
        ),
    )
    (out / "src").mkdir()
    for name in ("buf_recording_probe.rs", "buf_adapter.rs"):
        shutil.copyfile(
            ROOT / "lab/native" / name,
            out / "src" / ("main.rs" if name.startswith("buf_recording") else name),
        )
    (out / "Cargo.toml").write_text(
        '[package]\nname="dt2-native-buf-recording"\nversion="0.1.0"\nedition="2024"\n'
        '[dependencies]\nserde_json="1"\nsha2="0.10"\n'
        "elektron-native-boot={path="
        + json.dumps(str(out / "native-boot"))
        + ',features=["sharc"]}\n'
        "sharc-native={path="
        + json.dumps(str(upstream / "packages/emulator/sharc"))
        + "}\n"
    )
    run(
        "build",
        [
            "rustup",
            "run",
            "1.98.1",
            "cargo",
            "build",
            "--offline",
            "--release",
            "--manifest-path",
            str(out / "Cargo.toml"),
            "--target-dir",
            str(upstream / "out/native/target/generic"),
        ],
        cwd=upstream,
    )
    shutil.copy2(
        upstream / "out/native/target/generic/release/dt2-native-buf-recording",
        out / "runner",
    )
    report["runner_sha256"] = sha256(out / "runner")
    report["cargo_lock_sha256"] = sha256(out / "Cargo.lock")
    run("model", [str(out / "runner"), str(out / "spec.json"), "model"], cwd=upstream)
    if not a.prepare_only:
        for mode in (
            ("flow", "fixed-replay")
            if a.fixed_buf_slots
            else ("flow",)
            if a.clock_only
            else ("flow", *(("repeat",) if a.repeat_flow else ()), "replay")
        ):
            if mode == "fixed-replay":
                from lab.flex_lite import publication_bytes
                from lab.sketch_validation import pages

                # Native dump_pages is a variable-length recorder trace, not
                # the replay adapter's fixed-width LP0 packet stream.
                (out / "flow/fixed-pages.lp0").write_bytes(
                    b"".join(publication_bytes(pages(out / "flow/pages-A-frozen.bin")))
                )
                run(
                    "stock-replay-inputs",
                    helper("recorder_replay_inputs.py", out / "spec.json"),
                    cwd=upstream,
                )
            if mode == "replay":
                run("stock-oracle", helper("recorder_oracle.py", out / "spec.json"))
                run(
                    "stock-replay-inputs",
                    helper("recorder_replay_inputs.py", out / "spec.json"),
                    cwd=upstream,
                )
            run(
                mode,
                [str(out / "runner"), str(out / "spec.json"), mode],
                cwd=upstream,
                timeout=1800,
            )
            report[mode] = json.loads((out / f"{mode}.json").read_text())
            write_json(out / "report.json", report)
    require(source_hashes() == provenance["source_hashes"], "Lab source drift")
    require(not git(upstream, "status", "--porcelain"), "Native upstream changed")
    require(
        gen
        == {
            str(f.relative_to(generation)): sha256(f)
            for f in generation.iterdir()
            if f.is_file()
        },
        "Generated core drift",
    )
    report["status"] = (
        "prepared-native-recorder-adapter"
        if a.prepare_only
        else "passed-native-performance-controls"
        if a.performance_controls
        else "passed-native-clock-recording"
        if a.clock_only
        else "passed-native-recorder-flow"
    )
    report["default_migration_ready"] = False
    report["scope"] = (
        "Modeled external recorder service; native CPU/DSP jobs. No physical input or hardware claim."
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
print(report["status"], flush=True)
