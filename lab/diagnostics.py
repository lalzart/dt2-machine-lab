"""Resource snapshots from saved experiments; no guest execution or firmware edits."""

import argparse
import hashlib
import html
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from lab.metrics import distribution
from lab.project import ROOT, read_json, require, sha256, write_json

SCHEMA = "dt2-resource-snapshot-v1"
INPUT_LIMIT = 64 * 1024 * 1024
WORKLOAD_LABELS = {
    "idle": "Idle",
    "one-pad": "1 pad: ONESHOT",
    "two-pads": "2 pads: ONESHOT",
    "four-pads": "4 pads: STRETCH mix",
    "four-pads-oneshot": "4 pads: ONESHOT",
    "one-pad-grid": "1 pad: GRID",
    "sine-active": "SINE active",
    "plaits-fm-active": "Plaits FM active",
    "stretch-idle": "STRETCH idle",
    "stretch-preparation": "STRETCH preparation",
    "stretch-pending-trigger": "STRETCH unready trigger",
    "stretch-one-loop": "STRETCH 1 track",
    "stretch-one-fast": "STRETCH 1 track, fast",
    "stretch-four-loop": "STRETCH 4 tracks",
    "stretch-sixteen-loop": "STRETCH 16 tracks",
    "stretch-sixteen-mixed": "STRETCH 16 tracks, mixed",
}


class Inputs:
    """Freeze each imported JSON document and detect changes before exporting."""

    def __init__(self):
        self.hashes = {}

    def read(self, path):
        path = Path(path).resolve()
        require(
            path.stat().st_size <= INPUT_LIMIT, f"Diagnostic input too large: {path}"
        )
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(self.hashes.get(str(path), digest) == digest, f"Input changed: {path}")
        self.hashes[str(path)] = digest
        result = json.loads(raw)
        require(isinstance(result, dict), f"Expected a JSON object: {path}")
        return result

    def verify(self):
        for path, digest in self.hashes.items():
            require(sha256(path) == digest, f"Input changed while importing: {path}")


def integer(value, label):
    require(type(value) is int and value >= 0, f"Invalid nonnegative integer: {label}")
    return value


def series(values, label, *, integral=False):
    require(isinstance(values, list) and values, f"Missing series: {label}")
    for value in values:
        if type(value) is int:
            require(0 <= value <= 2**64 - 1, f"Sample exceeds counter range: {label}")
        require(
            type(value) in (int, float) and math.isfinite(value) and value >= 0,
            f"Invalid sample: {label}",
        )
        if integral:
            integer(value, label)
    result = distribution(values)
    require(math.isfinite(result["mean"]), f"Nonfinite aggregate: {label}")
    return result


def load_profile(path, inputs):
    path = Path(path).resolve()
    require(path.name.endswith("-profile.json"), "Expected a *-profile.json file")
    name = path.name.removesuffix("-profile.json")
    data = inputs.read(path)
    record = inputs.read(path.with_name(name + ".json"))
    manifest = inputs.read(path.parent / "manifest.json")
    firmware = inputs.read(ROOT / "profiles/dt2-1.16/profile.json")
    require(manifest.get("status") == "passed", "Profile run did not pass")
    fixture = manifest["fixture_files"]
    require(
        fixture["sections/section_3_MAIN_OS.bin"] == firmware["stock_main_sha256"]
        and fixture["sections/section_7_BLOB.bin"] == firmware["stock_blob_sha256"],
        "Profile firmware does not match the OS 1.16 adapter",
    )
    instructions = series(data["instructions"], "DSP instructions", integral=True)
    host = series(data["host_us"], "host microseconds")
    require(
        instructions["count"] == host["count"] == record["frames"],
        "Block count mismatch",
    )
    scope = data["scope"]
    require(scope == record["profile"], "Profile/result scope mismatch")
    require(
        scope["instructions_per_block"] == instructions
        and scope["host_us_per_block"] == host,
        "Recorded statistics disagree with raw samples",
    )
    # Timing from future hardware probes needs its own validated adapter.
    require(
        scope.get("target_cpu_load_percent") is None
        and scope.get("target_dsp_load_percent") is None,
        "Hardware percentages cannot be imported through the emulator adapter",
    )
    identity = {
        "stock_main_sha256": firmware["stock_main_sha256"],
        "stock_blob_sha256": firmware["stock_blob_sha256"],
        "initial_state_sha256": fixture["native/state.pack"],
        "native_library_sha256": record.get(
            "native_library_sha256", fixture["native/libsharc_native.dylib"]
        ),
        "dependencies": manifest["dependencies"],
        "capture_sha256": record["capture_sha256"],
        "frames": record["frames"],
        "preroll_trigger_frame": record["preroll_trigger_frame"],
        "sample_rates": record["sample_rates"],
        "boundary": scope["boundary"],
        "instruction_unit": scope["instruction_unit"],
        "replay_setup": record.get("replay_setup"),
    }
    return {
        "id": str(path),
        "label": f"{path.parent.name} / {name}",
        "firmware": firmware["firmware"],
        "recorded_utc": manifest.get("finished_utc"),
        "run_status": manifest["status"],
        "dsp_blob_sha256": record["dsp_blob_sha256"],
        "workload": identity,
        "platform": manifest["platform"],
        "instructions_per_block": instructions,
        "host_us_per_block": host,
        "instructions": data["instructions"],
        "capture_scope": {
            key: record.get(key)
            for key in (
                "cpu_stock",
                "workload",
                "installed_variant",
                "origin",
                "max_active_voice_lanes",
                "fext_fallbacks",
                "replay_blob_sha256",
                "output_scope",
                "ready_after_measured_block",
                "minimum_custom_backends",
                "maximum_custom_backends",
            )
        },
        "memory_bank": bank_accounting(record.get("memory_bank")),
    }


def bank_accounting(value):
    if value is None:
        return None
    result = {
        key: integer(value[key], key)
        for key in (
            "keys",
            "capacity",
            "frames",
            "allocated_array_bytes",
            "shared_readers_bytes",
            "total_reserved_bytes",
        )
    }
    require(
        2 <= result["keys"] <= result["capacity"] <= 576004
        and 141 <= result["frames"] <= 576000,
        "Invalid Capicola bank bounds",
    )
    require(
        result["allocated_array_bytes"] == result["capacity"] * 12
        and result["allocated_array_bytes"] + result["shared_readers_bytes"]
        <= result["total_reserved_bytes"],
        "Inconsistent Capicola bank accounting",
    )
    return result


def compare_profiles(candidate, baseline):
    """Compare equal replay workloads; different DSP images are intentional."""
    differences = [
        key
        for key, value in candidate["workload"].items()
        if baseline["workload"].get(key) != value
    ]
    if differences:
        return {
            "eligible": False,
            "reason": "Different workload: " + ", ".join(differences),
        }
    deltas = {}
    for key in ("mean", "p50", "p95", "p99", "max_observed"):
        before = baseline["instructions_per_block"][key]
        change = candidate["instructions_per_block"][key] - before
        deltas[key] = {
            "instructions": change,
            "percent": 100 * change / before if before else None,
        }
    return {
        "eligible": True,
        "instruction_deltas": deltas,
        "scope": "Change in emulated instruction cost for the same saved replay workload",
        "host_timing_comparison": "Descriptive only; host contention and profiling overhead are uncontrolled",
    }


def load_flex(path, inputs):
    data = inputs.read(path)
    require(data.get("status") == "PASS", "Flex experiment did not pass")
    require("OS 1.16" in data.get("scope", ""), "Unknown Flex experiment version")
    stages = []

    def counters(label, values):
        require(
            isinstance(values, list) and len(values) == 4,
            "Invalid Flex accounting record",
        )
        takes, cached, pcm, requested = [integer(v, label) for v in values]
        require(
            cached <= takes <= 32 and pcm <= requested, "Inconsistent Flex counters"
        )
        stages.append(
            dict(
                stage=label,
                takes=takes,
                cached_save_refs=cached,
                pcm_bytes=pcm,
                requested_heap_bytes=requested,
            )
        )

    counters("After USE", data["accounting_after_accept"])
    if "accounting_after_clear_reload" in data:
        counters("After slot clear/reload", data["accounting_after_clear_reload"])
    handover = data.get("managed_handover", {})
    if "accounting_after_save" in handover:
        counters("After save handover", handover["accounting_after_save"])
    reuse = data.get("sequential_reuse")
    heap = None
    if "heap_trace" in data:
        trace = data["heap_trace"]
        require(trace["pending_calls"] == 0, "Incomplete allocator trace")
        arena = integer(trace["initial"]["arena_bytes"], "heap arena")
        require(
            arena > 0 and arena == trace["final"]["arena_bytes"], "Heap arena changed"
        )
        for stage in ("initial", "final"):
            free = integer(trace[stage]["free_bytes"], "free heap")
            largest = integer(trace[stage]["largest_block"], "largest free block")
            require(largest <= free <= arena, "Inconsistent heap snapshot")
        minimum = integer(trace["minimum_free"], "minimum free heap")
        free_samples = [trace[s]["free_bytes"] for s in ("initial", "final")]
        largest_samples = [trace[s]["largest_block"] for s in ("initial", "final")]
        for event in trace["events"]:
            for key in ("free_before", "free_after"):
                value = integer(event[key], key)
                require(value <= arena, "Heap sample exceeds arena")
                free_samples.append(value)
            largest = integer(event["largest_after"], "largest_after")
            require(largest <= event["free_after"], "Largest block exceeds free heap")
            largest_samples.append(largest)
        require(minimum == min(free_samples), "Heap minimum disagrees with trace")
        heap = {
            "arena_bytes": arena,
            "initial_free_bytes": trace["initial"]["free_bytes"],
            "final_free_bytes": trace["final"]["free_bytes"],
            "minimum_free_bytes": minimum,
            "peak_occupied_bytes": arena - minimum,
            "final_largest_free_block": trace["final"]["largest_block"],
            "minimum_observed_largest_free_block": min(largest_samples),
            "allocation_failures": sum(
                e.get("failed") is True for e in trace["events"]
            ),
            "scope": "Whole CPU heap observed at allocator calls in this emulator experiment; includes stock allocations",
        }
    if reuse:
        for key in ("cycles", "retained_source_bytes", "retained_descriptor_bytes"):
            integer(reuse[key], key)
        require(1 <= reuse["cycles"] <= 32, "Invalid reuse count")
        reuse = {
            k: reuse[k]
            for k in ("cycles", "retained_source_bytes", "retained_descriptor_bytes")
        }
    return {
        "source": str(Path(path).resolve()),
        "label": Path(path).parent.name,
        "firmware": "Digitakt II OS 1.16 (reported by source experiment)",
        "main_sha256": data.get("main_sha256"),
        "scope": data["scope"],
        "frames": data["frames"],
        "stereo": data["stereo"],
        "stages": stages,
        "heap": heap,
        "reuse": reuse,
        "accounting_scope": "Flex source PCM and requested source/descriptor allocations; excludes allocator rounding and stock playback copies",
    }


def load_layout(path, inputs):
    """Build placement is capacity information, never live consumption."""
    data = inputs.read(path)
    require(data["layout"] == "reserved-state", "Unsupported memory layout")
    base = integer(data["state_base"], "state base")
    size = integer(data["state_bytes"], "state span")
    end = integer(data["reservation_end"], "reservation end")
    require(base + size <= end, "Working state exceeds reservation")
    regions = []
    previous = base
    for region in data["regions"]:
        start = integer(region["start"], "region start")
        limit = integer(region["end"], "region end")
        require(
            previous <= start < limit <= base + size, "Overlapping/out-of-bounds region"
        )
        regions.append({"name": region["name"], "bytes": limit - start})
        previous = limit
    code = data["instruction_code"]
    code_bytes = integer(code["bytes"], "instruction bytes")
    return {
        "source": str(Path(path).resolve()),
        "label": Path(path).parent.parent.name,
        "scope": "Candidate build placement; occupied bytes and live sample-pool free space are unmeasured",
        "working_state_span_bytes": size,
        "instruction_code_bytes": code_bytes,
        "instruction_ownership_verified": code["runtime_ownership_verified"],
        "hardware_verified": data["hardware_verified"],
        "regions": regions,
    }


def load_reservation(path, inputs):
    data = inputs.read(path)
    if "overlay" in data:
        require(data.get("status") == "passed", "Reservation experiment did not pass")
        data = data["overlay"]
    reserved = integer(data["reserved_bytes"], "reserved bytes")
    sample = integer(data["sample_bytes"], "sample capacity")
    begin = integer(data["bank_base"], "bank base")
    end = integer(data["bank_end"], "bank end")
    require(0 < end - begin <= reserved, "Invalid reservation bounds")
    return {
        "source": str(Path(path).resolve()),
        "label": Path(path).parent.name,
        "sample_pool_reserved_bytes": reserved,
        "remaining_sample_pool_capacity_bytes": sample,
        "main_sha256": data["sha256"],
        "bank_base": begin,
        "bank_end": end,
        "hardware_verified": data["hardware_verified"],
        "scope": "Declared CPU candidate sample-pool capacity; live occupancy and free space are unmeasured",
    }


def load_stock(path, inputs):
    data = inputs.read(path)
    manifest = inputs.read(Path(path).parent / "manifest.json")
    firmware = inputs.read(ROOT / "profiles/dt2-1.16/profile.json")
    require(
        data.get("status") == manifest.get("status") == "passed",
        "Stock capture did not pass",
    )
    require(
        data.get("main_sha256") == firmware["stock_main_sha256"]
        and data.get("stock_blob_sha256") == firmware["stock_blob_sha256"],
        "Unsupported stock capture firmware",
    )
    require(
        data.get("faulted_pages") == []
        and data.get("worker_error") is None
        and data.get("worker_stopped") is True,
        "Stock capture worker was not healthy",
    )
    stages = []
    for row in data["cpu_stages"]:
        heap = row["heap"]
        arena = integer(heap["arena_bytes"], "arena")
        free = integer(heap["free_bytes"], "free")
        largest = integer(heap["largest_block"], "largest block")
        require(arena > 0 and largest <= free <= arena, "Inconsistent stock heap")
        types = row["machine_types"]
        require(
            isinstance(types, list) and len(types) == 16,
            "Missing stock machine settings",
        )
        for value in types:
            integer(value, "machine type")
        stages.append(
            {
                "stage": row["name"],
                "machine_types": types,
                "arena_bytes": arena,
                "free_bytes": free,
                "occupied_bytes": arena - free,
                "largest_block": largest,
            }
        )
    require(
        stages and len({s["arena_bytes"] for s in stages}) == 1,
        "Missing or inconsistent stock heap stages",
    )
    return {
        "source": str(Path(path).resolve()),
        "label": Path(path).parent.name,
        "scope": data["scope"],
        "cpu_snapshot_sha256": data["cpu_snapshot_sha256"],
        "main_sha256": data["main_sha256"],
        "stages": stages,
        "measurement": "Paused stock CPU buddy-heap snapshots; excludes sample pool and other memory arenas",
    }


def make_snapshot(
    runs,
    flex_reports=(),
    layouts=(),
    baseline=None,
    reservations=(),
    stock_reports=(),
    paired_stock=False,
    integration_reports=(),
):
    inputs = Inputs()
    profiles = []
    for run in runs:
        paths = sorted(Path(run).glob("*-profile.json"))
        require(paths, f"No DSP profiles in {run}")
        profiles.extend(load_profile(path, inputs) for path in paths)
    order = {name: i for i, name in enumerate(WORKLOAD_LABELS)}
    variants = {"stock": 0, "sine-installed": 1, "plaits-installed": 2}
    profiles.sort(
        key=lambda p: (
            order.get(p["capture_scope"].get("workload"), 99),
            p["capture_scope"].get("workload") or p["label"],
            variants.get(p["capture_scope"].get("installed_variant"), 99),
            p["label"],
        )
    )
    require(
        not (baseline and paired_stock),
        "Choose a single baseline or paired stock baselines",
    )
    if baseline:
        reference = load_profile(baseline, inputs)
        for profile in profiles:
            profile["comparison"] = compare_profiles(profile, reference)
            profile["baseline"] = reference["label"]
    else:
        reference = None
        if paired_stock:
            references = [
                p
                for p in profiles
                if p["dsp_blob_sha256"] == p["workload"]["stock_blob_sha256"]
            ]
            for profile in profiles:
                matches = [
                    p for p in references if compare_profiles(profile, p)["eligible"]
                ]
                if len(matches) == 1:
                    profile["comparison"] = compare_profiles(profile, matches[0])
                    profile["baseline"] = matches[0]["label"]
                else:
                    profile["comparison"] = {
                        "eligible": False,
                        "reason": "No identical stock replay"
                        if not matches
                        else "Multiple identical stock replays; select a baseline explicitly",
                    }
                    profile["baseline"] = "Unpaired"
    result = {
        "schema": SCHEMA,
        "created_utc": datetime.now(UTC).isoformat(),
        "mode": "saved-experiments",
        "profiles": profiles,
        "baseline": reference,
        "flex": [load_flex(path, inputs) for path in flex_reports],
        "layouts": [load_layout(path, inputs) for path in layouts],
        "reservations": [load_reservation(path, inputs) for path in reservations],
        "stock": [load_stock(path, inputs) for path in stock_reports],
        "integration": [load_integration(path, inputs) for path in integration_reports],
        "hardware": {
            "cpu_load_percent": None,
            "dsp_load_percent": None,
            "missed_audio_deadlines": None,
            "live_memory_free_bytes": None,
        },
        "scope": "Independent saved experiments, each with its own workload; values are not a combined live device reading",
        "inputs": inputs.hashes,
    }
    inputs.verify()
    return result


def load_integration(path, inputs):
    data = inputs.read(path)
    require(data.get("schema") == "dt2-integration-resources-v1", "Unknown integration resource schema")
    require(data.get("firmware") == "Digitakt II OS1.16", "Unknown integration firmware")
    require(data.get("hardware_utilization") is None, "Declared resources cannot claim hardware utilization")
    records = data.get("records")
    require(isinstance(records, list) and records, "Missing per-owner resources")
    for record in records:
        require(all(isinstance(record.get(k), str) and record[k] for k in ("owner", "space", "measure")), "Unnamed integration resource")
        integer(record.get("bytes"), "resource bytes")
    return data


def number(value):
    return f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"


def memory(value):
    return f"{value / (1024 * 1024):,.3f} MiB ({value:,} B)"


def table(headers, rows):
    return (
        "<div class='scroll'><table><thead><tr>"
        + "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def details(value):
    return (
        "<details><summary>Source and measurement scope</summary><pre>"
        + html.escape(json.dumps(value, indent=2, allow_nan=False))
        + "</pre></details>"
    )


def render_html(snapshot):
    integration = "".join(
        "<h3>Declared integration bounds</h3><p>Nested capacities are separate; these rows are not additive or live device usage.</p>"
        + table(["Owner", "Address space", "Measurement", "Bytes"],
                [[r["owner"], r["space"], r["measure"], number(r["bytes"])] for r in record["records"]])
        for record in snapshot.get("integration", [])
    )
    matched_stretch = []
    for profile in snapshot["profiles"]:
        comparison = profile.get("comparison", {})
        if profile["capture_scope"].get(
            "installed_variant"
        ) == "capicola-stretch-r1" and comparison.get("eligible"):
            mean = profile["instructions_per_block"]["mean"]
            stock = mean - comparison["instruction_deltas"]["mean"]["instructions"]
            workload = profile["capture_scope"]["workload"]
            matched_stretch.append(
                [
                    WORKLOAD_LABELS.get(workload, workload),
                    number(stock),
                    number(mean),
                    number(profile["instructions_per_block"]["max_observed"]),
                    f"{mean / stock:.2f}×" if stock else "Undefined",
                ]
            )
    comparison_summary = (
        (
            "<h2 id='comparison'>Capicola versus stock</h2><p class='muted'>Whole DSP block instructions for identical adapted inputs. Capicola R1 includes the existing Plaits hook, maintenance and diagnostic copy. Ratios describe emulator work, not hardware utilization.</p>"
            + table(
                [
                    "Workload",
                    "Stock mean",
                    "Capicola mean",
                    "Capicola peak",
                    "Cost ratio",
                ],
                matched_stretch,
            )
        )
        if matched_stretch
        else ""
    )
    sections = []
    for profile in snapshot["profiles"]:
        stats = []
        for title, key in (
            ("DSP instructions/block", "instructions_per_block"),
            ("Host µs/block", "host_us_per_block"),
        ):
            stats.append(
                [title]
                + [
                    number(profile[key][k])
                    for k in ("mean", "p50", "p95", "p99", "max_observed")
                ]
            )
        values = profile["instructions"]
        # Envelope binning keeps one-block spikes visible in long captures.
        width = min(240, len(values))
        peaks = [
            max(values[i * len(values) // width : (i + 1) * len(values) // width])
            for i in range(width)
        ]
        scale = max(peaks) or 1
        points = " ".join(
            f"{i * 720 / max(1, width - 1):.2f},{100 - value * 90 / scale:.2f}"
            for i, value in enumerate(peaks)
        )
        graph = f"<svg viewBox='0 0 720 110' role='img' aria-label='DSP instruction peaks across the replay'><polyline points='{points}' fill='none' stroke='#79d6bc' stroke-width='2'/></svg>"
        comparison = profile.get("comparison")
        delta = ""
        if comparison:
            if comparison["eligible"]:
                mean = comparison["instruction_deltas"]["mean"]
                percent = (
                    f" ({mean['percent']:+.2f}%)" if mean["percent"] is not None else ""
                )
                delta = f"<p>Mean instruction change: {mean['instructions']:+,.2f}{percent}. Same saved replay workload.</p>"
            else:
                delta = (
                    "<p>Comparison unavailable: "
                    + html.escape(comparison["reason"])
                    + "</p>"
                )
            delta += (
                "<p class='muted'>Baseline: "
                + html.escape(profile["baseline"])
                + "</p>"
            )
        sections.append(
            "<article><h3>"
            + html.escape(profile["label"])
            + "</h3><p class='muted'>"
            + html.escape(profile["firmware"])
            + f" · {len(values):,} measured blocks · {html.escape(str(profile['recorded_utc']))}</p>"
            + table(
                ["Measurement", "Mean", "p50", "p95", "p99", "Observed peak"], stats
            )
            + graph
            + "<p class='muted'>Instruction peak per plot bin · replay start → end · vertical scale 0–"
            + number(scale)
            + " instructions/block</p>"
            + delta
            + details({k: v for k, v in profile.items() if k != "instructions"})
            + "</article>"
        )
    dsp = "".join(sections) or "<p>No DSP measurements imported.</p>"
    overview = []
    for profile in snapshot["profiles"]:
        comparison = profile.get("comparison", {})
        change = "Unpaired"
        if comparison.get("eligible"):
            value = comparison["instruction_deltas"]["mean"]["percent"]
            change = (
                f"{value:+.2f}%" if value is not None else "Undefined (zero baseline)"
            )
        scope = profile["capture_scope"]
        overview.append(
            [
                WORKLOAD_LABELS.get(
                    scope.get("workload"), scope.get("workload") or profile["label"]
                ),
                {
                    "stock": "Stock",
                    "sine-installed": "SINE hook",
                    "plaits-installed": "Plaits hook",
                    "capicola-stretch-r1": "Capicola R1",
                }.get(
                    scope.get("installed_variant"),
                    scope.get("installed_variant") or "See source",
                ),
                number(profile["instructions_per_block"]["mean"]),
                number(profile["instructions_per_block"]["max_observed"]),
                change,
                scope.get("max_active_voice_lanes")
                if scope.get("max_active_voice_lanes") is not None
                else "Unmeasured",
            ]
        )
    dsp = (
        table(
            [
                "Workload",
                "DSP image",
                "Mean instr.",
                "Peak instr.",
                "Vs stock",
                "Lanes*",
            ],
            overview,
        )
        + "<p class='muted'>Mean and peak: emulated instructions per DSP block. Vs stock: mean instruction change for an identical replay. *Peak active lane flags are emulator state observations. Pad events arrive serially; these captures do not establish sustained simultaneous polyphony. Active custom cases use separate captures.</p>"
        + dsp
    )
    if any(
        p["capture_scope"].get("installed_variant") == "capicola-stretch-r1"
        for p in snapshot["profiles"]
    ):
        dsp = (
            "<p class='muted'>Capicola R1 is the complete prototype DSP image: existing Plaits R3 hook, sample-preparation maintenance and renderer diagnostic copy included. Stock is original DSP code with replay sample backing. Matched replay initialization is required; these adapted STRETCH fixtures are separate from pad captures.</p>"
            + dsp
        )
    sections = []
    banks = {}
    for profile in snapshot["profiles"]:
        if profile["memory_bank"]:
            banks.setdefault(
                json.dumps(profile["memory_bank"], sort_keys=True), []
            ).append(profile)
    for bank_profiles in banks.values():
        bank = bank_profiles[0]["memory_bank"]
        sections.append(
            "<article><h3>Capicola shared bank observed in replay</h3>"
            + table(
                ["Measurement", "Value"],
                [
                    ["Source frames", bank["frames"]],
                    [
                        "Sparse keys / allocated capacity",
                        f"{bank['keys']} / {bank['capacity']}",
                    ],
                    ["Allocated bank arrays", memory(bank["allocated_array_bytes"])],
                    ["32 reader records", memory(bank["shared_readers_bytes"])],
                    ["Total reservation", memory(bank["total_reserved_bytes"])],
                ],
            )
            + "<p class='muted'>Bank arrays and reader records occupy parts of the total reservation; do not add them on top of it. Source PCM, constants, stacks and code have separate ownership. This is a prepared DSP replay observation, not a CPU heap measurement.</p>"
            + details({"bank": bank, "profiles": [p["id"] for p in bank_profiles]})
            + "</article>"
        )
    for stock in snapshot.get("stock", []):
        rows = [
            [
                WORKLOAD_LABELS.get(s["stage"], s["stage"]),
                ", ".join(str(v) for v in s["machine_types"][:4]),
                f"{s['occupied_bytes'] / 1024**2:.3f} MiB",
                f"{s['free_bytes'] / 1024**2:.3f} MiB",
                f"{s['largest_block'] / 1024**2:.3f} MiB",
            ]
            for s in stock["stages"]
        ]
        sections.append(
            "<article><h3>Stock OS 1.16 CPU heap</h3><p class='muted'>"
            + html.escape(stock["measurement"])
            + "</p>"
            + table(
                [
                    "Stage",
                    "Track 1–4 wire types",
                    "Occupied",
                    "Free",
                    "Largest free block",
                ],
                rows,
            )
            + "<p class='muted'>Wire types: 0 ONESHOT, 2 STRETCH, 4 GRID. Sequential stages share the same prepared project; snapshots are taken after each audition.</p>"
            + details(stock)
            + "</article>"
        )
    for flex in snapshot["flex"]:
        rows = [
            [
                s["stage"],
                s["takes"],
                s["cached_save_refs"],
                memory(s["pcm_bytes"]),
                memory(s["requested_heap_bytes"]),
            ]
            for s in flex["stages"]
        ]
        body = table(
            [
                "Stage",
                "Takes",
                "Cached save refs",
                "Source PCM",
                "Requested source heap",
            ],
            rows,
        )
        if flex["reuse"]:
            reuse = flex["reuse"]
            body += f"<p>After {reuse['cycles']} USE/save cycles: {memory(reuse['retained_source_bytes'])} retained source; {memory(reuse['retained_descriptor_bytes'])} retained descriptors.</p>"
        if flex["heap"]:
            heap = flex["heap"]
            body += (
                "<h4>CPU heap in this experiment</h4>"
                + table(
                    ["Measurement", "Value"],
                    [
                        [
                            key.replace("_", " ").capitalize(),
                            number(value)
                            if key == "allocation_failures"
                            else memory(value),
                        ]
                        for key, value in heap.items()
                        if key != "scope"
                    ],
                )
                + "<p class='muted'>"
                + html.escape(heap["scope"])
                + "</p>"
            )
        sections.append(
            "<article><h3>"
            + html.escape(flex["label"])
            + "</h3><p class='muted'>"
            + html.escape(flex["scope"])
            + "</p>"
            + body
            + details(flex)
            + "</article>"
        )
    for layout in snapshot["layouts"]:
        rows = [
            [key.replace("_", " ").capitalize(), memory(layout[key])]
            for key in ("working_state_span_bytes", "instruction_code_bytes")
        ]
        sections.append(
            "<article><h3>"
            + html.escape(layout["label"])
            + " — Capicola placement</h3><p class='muted'>"
            + html.escape(layout["scope"])
            + "</p>"
            + table(["Measurement", "Capacity / placement"], rows)
            + "<p>Working-state span and instruction code describe separate placements. Instruction-code ownership remains unverified.</p>"
            + details(layout)
            + "</article>"
        )
    for reservation in snapshot["reservations"]:
        sections.append(
            "<article><h3>"
            + html.escape(reservation["label"])
            + " — sample-pool reservation</h3><p class='muted'>"
            + html.escape(reservation["scope"])
            + "</p>"
            + table(
                ["Measurement", "Declared capacity"],
                [
                    ["Reserved", memory(reservation["sample_pool_reserved_bytes"])],
                    [
                        "Remaining pool capacity",
                        memory(reservation["remaining_sample_pool_capacity_bytes"]),
                    ],
                ],
            )
            + details(reservation)
            + "</article>"
        )
    mem = (
        "".join(sections)
        or "<p>No memory records imported. Use --flex-report or --layout.</p>"
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'">
<title>Digitakt II resource monitor</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101716;color:#e5eeea;font:15px/1.5 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px 24px}h1{font-size:30px;margin:0}h2{margin-top:32px}h3{overflow-wrap:anywhere;font-size:17px}h4{margin-bottom:8px}.muted{color:#a7bcb4;font-size:13px}.badge{color:#79d6bc;text-transform:uppercase;letter-spacing:.12em;font-size:12px}.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}.status div,article{background:#192321;border:1px solid #31433d;border-radius:10px;padding:18px;margin:14px 0}.status strong{display:block;font-size:21px;margin-top:8px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #31433d;white-space:nowrap}th{color:#a7bcb4}svg{width:100%;height:130px;margin-top:20px}details{margin-top:16px}summary{cursor:pointer;color:#79d6bc}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}nav a{color:#79d6bc;margin-right:20px}a:focus,summary:focus{outline:2px solid #79d6bc}
</style><main><p class="badge">Saved experiment measurements</p><h1>Digitakt II resource monitor</h1><p>Typical and peak consumption across recorded workloads.</p><p class="muted">"""
        + html.escape(snapshot["scope"])
        + "</p><nav><a href='#dsp'>DSP work</a><a href='#memory'>Memory</a><a href='#sources'>Sources</a></nav>"
        + """
<div class="status"><div>Hardware CPU load<strong>Unmeasured</strong></div><div>Hardware DSP load<strong>Unmeasured</strong></div><div>Audio deadline misses<strong>Unmeasured</strong></div></div>
<p class="muted">DSP instructions describe emulator work. Host microseconds describe emulator speed. Physical load needs validated device timing.</p>
"""
        + comparison_summary
        + "<h2 id='dsp'>DSP work</h2>"
        + dsp
        + "<h2 id='memory'>Memory</h2>"
        + mem
        + integration
        + "<h2 id='sources'>Snapshot provenance</h2>"
        + details({k: snapshot[k] for k in ("schema", "created_utc", "inputs")})
        + "</main></html>"
    )


def add_arguments(parser):
    parser.add_argument("--integration-report", type=Path, action="append", default=[],
                        help="per-owner integration-resources.json from labctl resources/build (repeatable)")
    parser.add_argument(
        "--run",
        type=Path,
        action="append",
        help="saved lab run (repeatable); defaults to out/latest.json",
    )
    parser.add_argument(
        "--flex-report",
        type=Path,
        action="append",
        default=[],
        help="Flex lifetime report (repeatable)",
    )
    parser.add_argument(
        "--layout",
        type=Path,
        action="append",
        default=[],
        help="Capicola candidate memory-layout.json (repeatable)",
    )
    parser.add_argument(
        "--reservation",
        type=Path,
        action="append",
        default=[],
        help="sample-pool reservation.json or owned-CPU report (repeatable)",
    )
    parser.add_argument(
        "--baseline", type=Path, help="*-profile.json for matched-workload comparisons"
    )
    parser.add_argument(
        "--paired-stock",
        action="store_true",
        help="pair each profile with an identical stock-DSP replay in the imported runs",
    )
    parser.add_argument(
        "--stock-report",
        type=Path,
        action="append",
        default=[],
        help="verified stock-capture.json with paused CPU heap snapshots (repeatable)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="new output directory; existing directories are refused",
    )


def main(args=None):
    if args is None:
        parser = argparse.ArgumentParser(description=__doc__)
        add_arguments(parser)
        args = parser.parse_args()
    try:
        runs = args.run or ([] if getattr(args, "integration_report", []) else [
            ROOT / "out/runs" / read_json(ROOT / "out/latest.json")["run"]
        ])
        snapshot = make_snapshot(
            runs,
            args.flex_report,
            args.layout,
            args.baseline,
            args.reservation,
            getattr(args, "stock_report", []),
            getattr(args, "paired_stock", False),
            getattr(args, "integration_report", []),
        )
        output = args.output or ROOT / "out/diagnostics" / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        )
        # Generate everything before creating the destination; never overwrite a baseline.
        page = render_html(snapshot)
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / "snapshot.json", snapshot)
        (output / "index.html").write_text(page)
        print(
            f"PASS: {len(snapshot['profiles'])} DSP profiles, {len(snapshot['flex'])} Flex experiments, {len(snapshot['layouts'])} memory layouts"
        )
        print(f"Screen: {(output / 'index.html').resolve()}")
        print(f"Snapshot: {(output / 'snapshot.json').resolve()}")
        print("Hardware CPU/DSP load and deadline misses remain unmeasured.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
