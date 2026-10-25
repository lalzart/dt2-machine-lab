#!/usr/bin/env python3
"""Package the opt-in ARM diagnostic after matching upload/startup/UI checks.

Preserves the original experimental package and refuses changes outside the
admission diagnostics and their UI. Does not transfer firmware to hardware.
"""

# ruff: noqa: E402
import argparse
import json
import os
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
for name in ("build", "upload", "startup", "baseline_package", "output"):
    p.add_argument(name, type=Path)
p.add_argument(
    "--clock-proof",
    type=Path,
    help="matching bounded native clock/one-capture proof; required only for clock profile",
)
a = p.parse_args()
out = a.output.resolve()
require(
    out.is_relative_to(ROOT / "out/runs") and not out.exists(),
    "Use fresh ignored output",
)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
from lab import buf_next_bar as nb
from lab import recorder_freeze_worker_code as q
from lab import sketch as s
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build, relocate
from lab.sketch_device_validation import DeviceBuild
from lab.sketch_dsp_device import audit
from lab.upload import REFERENCE_REVISION, verify_candidate

device = DeviceBuild(a.build, STOCK_MAIN.read_bytes())
require(device.meta.get("arm_diagnostics") is True, "Diagnostic profile required")
clock_fix = device.meta.get("clock_fix", False)
require(
    bool(clock_fix) == bool(a.clock_proof),
    "Clock profile requires its separate native clock proof",
)
operations = device.meta.get("operation_diagnostics", False)
require(
    device.manifest["source_hashes"] == provenance["source_hashes"],
    "Build source drift",
)
proofs = {}
for label, folder, status in (
    ("upload", a.upload, "passed-stream-rules-and-native-cpu-upload"),
    ("startup", a.startup, "passed-native-candidate-application-startup"),
):
    path = folder.resolve() / "report.json"
    proof = json.loads(path.read_text())
    require(proof["status"] == status, label + " did not pass")
    require(
        proof["source_hashes"] == provenance["source_hashes"], label + " source drift"
    )
    require(proof["device"] == device.identity, label + " build identity differs")
    proofs[label] = proof
upload, startup = proofs["upload"], proofs["startup"]
clock = None
if clock_fix:
    require(not operations, "Clock and operation-trace profiles must remain separate")
    clock = json.loads((a.clock_proof.resolve() / "report.json").read_text())
    require(
        clock["status"] == "passed-native-clock-recording",
        "Native clock/capture proof missing",
    )
    require(
        clock["source_hashes"] == provenance["source_hashes"],
        "Clock proof source drift",
    )
    require(
        clock["firmware"]["main_sha256"] == device.meta["sha256"]
        and clock["firmware"]["blob_sha256"] == sha256(device.blob_path),
        "Clock proof firmware differs",
    )
    require(
        clock["container"] == upload["test_container"], "Clock proof container differs"
    )
    flow = clock["flow"]
    require(
        flow["status"] == "passed"
        and flow["two_real_bar_receipts"]
        and flow["host_positive_clock_writes"] is False
        and flow["cancelled_before_start"]
        and flow["recordings"] == 1
        and flow["starts"] == 1
        and flow["stops"] == 1
        and flow["publications"] == 1
        and flow["assignments_preserved"]
        and flow["CPU_canaries_and_code_intact"],
        "Incomplete clock/capture qualification",
    )
    require(
        startup.get("arm_diagnostics", {}).get("waiting_samples_UI", {}).get("status")
        == "passed",
        "Passive sample-wait UI proof missing",
    )
require(
    startup.get("arm_diagnostics", {}).get("status") == "passed",
    "Native diagnostic controls missing",
)
if operations:
    require(
        len(startup["arm_diagnostics"].get("operation_cases", [])) == 5,
        "Native sample-operation UI controls missing",
    )
    trace = startup.get("startup_operations", {})
    require(
        trace.get("final_count") == 0
        and trace.get("unmatched_events") == 0
        and trace.get("diagnostic_metadata", {}).get("matches_read_only_trace") is True,
        "Cold-start operation counter/metadata proof missing",
    )
require(
    startup["boot"]["candidate_container_loaded"]
    and not startup["boot"]["host_MAIN_overlay"],
    "Full candidate startup missing",
)
require(
    startup["boot"]["CPU_canaries_and_code_intact"]
    and startup["boot"]["Sketch_rendered"],
    "Startup integrity failed",
)
candidate = a.upload.resolve() / "candidate-test-fixture.syx"
require(
    sha256(candidate) == upload["test_container"]["sha256"], "Candidate container drift"
)
require(
    sha256(candidate) == startup["input_hashes"]["candidate"],
    "Startup container differs",
)

baseline = a.baseline_package.resolve()
base = json.loads((baseline / "manifest.json").read_text())
require(base["status"] == "local-experimental-package-validated", "Unknown baseline")
require(
    sha256(baseline / base["package"]) == base["package_sha256"],
    "Original package changed",
)
ordinary_image, ordinary = build(STOCK_MAIN.read_bytes())
require(ordinary["sha256"] == base["device"]["main_sha256"], "Default firmware changed")
require(
    sha256(device.blob_path) == base["device"]["dsp_sha256"],
    "DSP differs from original package",
)
for field in ("hooks", "arenas", "reservation", "guards"):
    require(
        device.meta[field] == ordinary[field],
        "Device placement/hooks changed: " + field,
    )
before = {w["address"]: w for w in ordinary["writes"]}
after = {w["address"]: w for w in device.meta["writes"]}
require(set(before) <= set(after), "Missing baseline payload")
changed = {at for at, value in before.items() if value != after[at]}
allowed = {relocate(at) for at in (nb.ARM_ONLY, s.ARM_SUBMIT, s.DRAW, s.TEXTS)}
if clock_fix:
    allowed |= {relocate(nb.IRQ), relocate(nb.CHECK)}
if operations:
    allowed |= {relocate(q.ENTER), relocate(q.LEAVE)}
    label = next(
        at for at, write in after.items() if write["after"] == b"BUSY SAMPLE %u\0".hex()
    )
    # This string is added relative to the ordinary (non-diagnostic) baseline.
    if label in before:
        allowed.add(label)
require(changed == allowed, "Non-diagnostic payload changed")
require(
    {at for at in set(after) - set(before) if after[at]["kind"] != "data"}
    == ({relocate(nb.OP_SNAPSHOT), relocate(s.OP_DIAG)} if operations else set()),
    "Unexpected added executable payload",
)

ref = ROOT / "out/references/elekloader-upload-audit"
require(
    git(ref, "rev-parse", "HEAD") == REFERENCE_REVISION
    and not git(ref, "status", "--porcelain"),
    "Codec identity drift",
)
sys.path[:0] = [str(config["digikit"]), str(ref)]
from elekloader.syx import Syx

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(sha256(inputs["syx"]) == base["stock_sha256"], "Stock OS1.16 drift")
stock = Syx(Path(inputs["syx"]).read_bytes())
verify_candidate(
    (baseline / base["package"]).read_bytes(),
    stock,
    {3: ordinary_image, 7: device.blob},
)
container = verify_candidate(
    candidate.read_bytes(), stock, {3: device.image, 7: device.blob}
)
require(container == upload["test_container"], "Final container verification differs")
stream = audit(device.blob)
require(
    source_hashes() == provenance["source_hashes"], "Source changed during packaging"
)
out.mkdir(parents=True, exist_ok=False)
filename = (
    "EXPERIMENTAL_SKETCH_BUF_SAMPLE_DIAG_OS1.16.syx"
    if operations
    else "EXPERIMENTAL_SKETCH_BUF_ARM_DIAG_OS1.16.syx"
)
if clock_fix:
    filename = "EXPERIMENTAL_SKETCH_BUF_CLOCK_OS1.16.syx"
(out / filename).write_bytes(candidate.read_bytes())
require(sha256(out / filename) == container["sha256"], "Delivered package copy differs")
report = dict(
    status="local-sample-operation-diagnostic-package-validated"
    if operations
    else "local-arm-diagnostic-package-validated",
    firmware="Digitakt II OS1.16",
    package=filename,
    package_sha256=container["sha256"],
    container=container,
    stream=stream,
    device=device.identity,
    source_hashes=provenance["source_hashes"],
    dependencies=provenance["dependencies"],
    baseline_package=str(baseline / base["package"]),
    baseline_sha256=base["package_sha256"],
    default_MAIN_byte_exact=True,
    DSP_byte_exact=True,
    changed_payloads=[after[at]["label"] for at in sorted(changed)],
    diagnosis="First failed predicate and observed value; existing return ABI and guards retained",
    diagnostic_labels=[
        dict(id=i, name=name, result=result)
        for i, (name, result) in enumerate(nb.ARM_DIAGNOSTICS, 1)
    ],
    operation_diagnostics=operations,
    clock_changes_included=bool(clock_fix),
    proofs={
        label: dict(
            path=str(folder.resolve() / "report.json"),
            sha256=sha256(folder / "report.json"),
        )
        for label, folder in (("upload", a.upload), ("startup", a.startup))
    },
    user_report="Original experimental firmware reaches device UI; ARM refused/busy with REC READY and BUF IDLE. Root cause not yet identified.",
    new_recordings=0,
    recorder_workflow_revalidated=False,
    hardware_transferred=False,
    hardware_validated=False,
    limitations=base["limitations"],
)
write_json(out / "manifest.json", report)
if clock_fix:
    report.update(
        status="local-clock-fix-package-validated",
        new_recordings=1,
        diagnosis="Normal16/mode0/scale2 semantic clock qualification and stock transport predicate; specific clock refusals and passive WAIT SAMPLES",
        clock_proof=dict(
            path=str(a.clock_proof.resolve() / "report.json"),
            sha256=sha256(a.clock_proof / "report.json"),
        ),
        user_report="User reports advancing BUSY LOAD slots clear after waiting; running transport then reaches REF CLOCK 0. Physical clock cause remains unconfirmed.",
        recorder_workflow_revalidated="Focused one-capture slice; broader unchanged DSP/FREEZE/voice evidence remains separate",
    )
    write_json(out / "manifest.json", report)
(out / "SHA256SUMS").write_text(f"{container['sha256']}  {filename}\n")
(out / "README.md").write_text(
    "# Sketch ARM diagnostic — OS 1.16\n\n"
    "Experimental diagnostic package. The assistant has not transferred this build to hardware.\n\n"
    f"Package: `{filename}`\n\nSHA-256: `{container['sha256']}`\n\n"
    "Uses the same SONG / FUNC+SONG / held-SONG controls. A failed ARM now displays the first "
    "blocking check and its observed unsigned value, for example `BUSY WORKER 1` or `REF CLOCK 0`. "
    "These are examples, not a diagnosed device cause. Read the whole message after one ARM "
    "attempt; repeated attempts can replace it. No busy flag is cleared or guard bypassed.\n\n"
    "BUSY labels: REQUEST (existing BUF transaction), WORKER (shared lease), FREEZE (operation "
    "count), LOCK (generation mutation), LOADER (stock sample-loader busy), RECORDER (stock recorder state).\n\n"
    "REF labels: BUF (selection), PLAY (transport), CTRL (controller), LENGTH (native recorder length), "
    "CLOCK (no admitted bar clock), MODE (unqualified selector value), SETUP, POOL or KIT (initialization/context). "
    "The clock selector is a configuration guard; MODE does not by itself identify an external clock source.\n\n"
    "Ordinary-profile MAIN and DSP remain byte-exact to the original experimental package. This profile "
    "changes only the ARM diagnostic path, its latched UI feedback and text table/strings. The existing "
    "recording, publication, cancellation, FREEZE and memory policy remain. Package integrity, native "
    "upload, application startup and two injected UI refusals pass. No new recordings are used.\n\n"
    "The original package is preserved. Physical boot/memory/recorder/timing limits remain experimental; "
    "this build diagnoses the refusal and does not claim to fix its cause. See manifest.json for hashes and evidence.\n"
)
if operations:
    (out / "README.md").write_text(
        "# Sketch startup sample diagnostic - OS 1.16\n\n"
        f"Firmware: `{filename}`\n\nSHA-256: `{container['sha256']}`\n\n"
        "This diagnoses the first post-boot BUSY refusal. The pending clock correction is excluded. "
        "No automatic guard clearing, ARM retry, recorder/FREEZE jobs, capture/publication change, "
        "DSP change or memory-policy change is introduced. The assistant has not transferred it to hardware.\n\n"
        "Use the existing SONG and FUNC+SONG controls. On a sample-operation refusal, "
        "`BUSY LOAD n`, `BUSY UNLOAD n` or `BUSY CLEAR n` identifies a still-active outer stock "
        "sample operation. Here n is the sample-pool slot, not BUF 1-4 or a count. "
        "`BUSY SAMPLE n` reports the operation count when the outer context is unknown or has "
        "already returned while another operation remains. This avoids claiming an old context is active. "
        "All messages latch the failed ARM snapshot. Later completion does not update the old refusal.\n\n"
        "An opt-in trace records the outer wrapper/caller, arguments, task, raw tick, stack frame, "
        "return state and entry/exit totals. ARM reads that context and the unchanged operation count "
        "together under an interrupt mask. Unknown context keeps the generic busy label. "
        "Diagnostic instructions briefly extend the masked counter update; hardware timing is unqualified.\n\n"
        "Native cold startup validates matching entry/exit totals and zero remaining count. "
        "Five injected UI controls validate the three operation labels plus returned/unknown fallbacks; "
        "they do not reproduce or diagnose the hardware failure. Upload/backpressure, full-container "
        "application startup and package integrity pass. No new recordings are used.\n\n"
        "The original experimental and first diagnostic packages are preserved. The ordinary MAIN "
        "and DSP remain byte-exact. Physical startup, recorder, cache/DMA, timing and DSP ROM/SPI "
        "limitations remain. See manifest.json and the repository diagnostic notes for evidence.\n"
    )
if clock_fix:
    (out / "README.md").write_text(
        "# Sketch clock correction candidate - OS 1.16\n\n"
        f"Firmware: `{filename}`\n\nSHA-256: `{container['sha256']}`\n\n"
        "Uses SONG to open Sketch and FUNC+SONG to ARM. During stock sample loading, "
        "an idle Sketch screen shows WAIT SAMPLES; requests remain guarded and may show BUSY SAMPLE n. "
        "No deferred ARM or automatic retry is added. The loader must finish before recording.\n\n"
        "The clock uses the stock playing predicate consistently and checks the actual master length "
        "16, normal mode 0 and qualified scale 2 instead of twelve fixture-specific bytes. "
        "Only a real 15 -> 0 -> 1 sequence supplies a new bar receipt. Other lengths/scales/modes, "
        "stopped or missing clocks, late/missed boundaries and context changes remain guarded. "
        "Use a normal sixteen-step pattern at the qualified 1x scale and recorder LEN 16/32/64.\n\n"
        "Remaining clock refusals identify a prerequisite: CLK NOIRQ, STOP, PATTERN, LEN, PATMODE, "
        "SCALE, STEP or SERIAL plus the observed value. NOIRQ means no enabled clock callback has "
        "qualified a failure yet. Existing REF MODE is a separate selector guard. Read the first "
        "complete message; a latched refusal does not update when its cause clears.\n\n"
        "The exact container passes native CPU upload/backpressure, complete-container application "
        "startup and a focused native one-capture flow: two real bar receipts without host clock writes, "
        "an injected unsupported-scale refusal, cancellation before recording, one next-bar start/stop "
        "and automatic publication with assignments preserved. Recorder input/normalization are modeled; "
        "DSP ROM/SPI, physical timing and hardware recording remain unqualified. This is a candidate "
        "for the reported device refusal; its exact physical cause is not confirmed.\n\n"
        "DSP, shared sample-operation guards, publication/FREEZE/cancellation code and memory policy "
        "remain unchanged. The original, ARM diagnostic and sample diagnostic packages are preserved. "
        "The assistant has not transferred this package to hardware. See manifest.json for exact proofs.\n"
    )
print(
    json.dumps(
        dict(
            status=report["status"],
            package=str(out / filename),
            sha256=container["sha256"],
        )
    )
)
