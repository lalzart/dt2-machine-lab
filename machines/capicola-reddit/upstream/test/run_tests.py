"""The repository's tests. Exit status 0 only if every check passes.

    python3 test/run_tests.py [host|emu|all] [--update] [-j N] [-k NAME]

host  (anywhere: a C compiler and Python 3) gen_host, built from the sources with
      tools/build_gen.sh's flags, replays the voice records in test/golden/ and
      test/rec_st.txt; each output's sha256 must equal test/golden/host.json's.
      Catches any change to what dt2gen.c computes.
emu   (deps/ from ./build.sh --tests, or the workspace: DT2_WORKSPACE with the
      stock firmware, digikit and its runner; tools/build_gen.sh run first) for
      each OS whose Elektron file is here (1.16, 1.17),
      firmware/build_cap.py builds the release and diag images (its checks of every
      patch site must pass) and the release section 7 must be the same for both;
      then, in the DSP emulator on that section 7:
        ours   each case's output is the host replay's, bit for bit, and the
               golden output (so device == host == golden);
        stock  with CAPI off, each machine's output is stock firmware's, bit for bit.
all   host, then emu (with --update: emu first, it writes the records host replays).

--update  rewrite test/golden/ from this run (after a deliberate change to the sound
          or to the cases; review the diff). Without it test/golden/ is only read.

Golden files are our test inputs and output hashes; nothing in them comes from the
firmware image except the voice records the stock DSP code fills in for our test
signal. Everything this writes goes to build/test/ (never committed).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
TEST = REPO / "test"
GOLDEN = TEST / "golden"
BUILD = REPO / "build"
OUT = BUILD / "test"
sys.path.insert(0, str(REPO / "firmware"))
import fwver  # noqa: E402  (which Elektron OS files are here)
WORKSPACE = fwver.WORKSPACE
DIGIKIT = pathlib.Path(os.environ.get("DIGIKIT") or next(
    (p for p in (fwver.DEPS / "digikit", WORKSPACE / "work" / "digikit") if p.is_dir()), WORKSPACE / "work" / "digikit"))
ALL_FIRMWARES = ("1.16", "1.17")
FIRMWARES = tuple(v for v in ALL_FIRMWARES if fwver.stock_path(v))   # those whose Elektron OS file is here

# The emulator cases: test/dt2trace_gen.py's settings (MACHINE is the page's type:
# 2 STRETCH, 3 REPITCH, 4 GRID, 6 SLICE; CAPI is slot 2: on/off for STRETCH and
# REPITCH, 1 REP / 2 STR for GRID and SLICE; POKE 0xea is slot 6, BARS or GRID).
OURS = {
    "stretch_stereo": (30, "CAPI=1 MACHINE=2 PLAY=3 TUNE=4 BPM=100 STEREO=1 RETRIG=10,25"),
    "stretch_rev":    (30, "CAPI=1 MACHINE=2 PLAY=1 TUNE=-12"),
    "repitch_stereo": (30, "CAPI=1 MACHINE=3 PLAY=2 TUNE=7 STEREO=1"),
    "slice_str":      (30, "CAPI=2 MACHINE=6 TUNE=3 BPM=100 STEREO=1 POKE=0xea:0x500 FORCESE=6000,30000 RETRIG=1"),
    "slice_rep":      (30, "CAPI=1 MACHINE=6 TUNE=-2 BPM=120 STEREO=1 POKE=0xea:0x200 FORCESE=0,24000 RETRIG=1"),
    "grid_rep":       (30, "CAPI=1 MACHINE=4 BPM=90 STEREO=1 POKE=0xea:0x100 RETRIG=1"),
    "grid_str":       (30, "CAPI=2 MACHINE=4 TUNE=5 BPM=100 STEREO=1 POKE=0xea:0x200 RETRIG=1"),
}
STOCK = {   # CAPI off against the unpatched firmware
    "stock_stretch": (12, "MACHINE=2 TUNE=4 BPM=100"),
    "stock_repitch": (12, "MACHINE=3"),
    "stock_slice":   (12, "MACHINE=6"),
    "stock_grid":    (12, "MACHINE=4 RETRIG=1"),
}
# Host-only cases: test/rec_st.txt (a STRETCH pair) on test/tone.i16, 600 blocks,
# the play modes, tunings and stretches test/hostq.py's `same` covers.
TONE = {
    "tone_plain":   "",
    "tone_retrig":  "RETRIG=10,50,51,200",
    "tone_up7":     "HTUNE=7 RETRIG=30,90",
    "tone_rev":     "HTUNE=-5 HPLAY=1",
    "tone_revloop": "HTUNE=4 HPLAY=3 HEND=20000",
    "tone_up24":    "HTUNE=24 HSTRETCH=0.6",
    "tone_down7":   "HTUNE=-7 HSTRETCH=1.7 RETRIG=40,41,300",
}


def env_of(spec: str) -> dict:
    return dict(kv.split("=", 1) for kv in spec.split())


def tracer_vars() -> set:
    """every setting test/dt2trace_gen.py reads: cleared from the inherited environment"""
    src = (TEST / "dt2trace_gen.py").read_text()
    return set(re.findall(r'os\.environ(?:\.get\(|\[)"([A-Z0-9_]+)"', src))


HOST_VARS = ("STEREO", "CAPI", "HTUNE", "HEND", "HPLAY", "HSTRETCH", "RETRIG", "TAPEDUMP", "POS", "FASTSTAT")


def words_of(text: str) -> list:
    return [int(w, 16) for w in text.split()]


def digest(ws: list) -> str:
    return hashlib.sha256(struct.pack(f">{len(ws)}I", *ws)).hexdigest()


def rms(ws: list) -> float:
    f = struct.unpack(f"<{len(ws)}f", struct.pack(f"<{len(ws)}I", *ws))
    return (sum(v * v for v in f) / max(1, len(f))) ** 0.5


class Report:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, note=""):
        """ok: True pass, False fail, None skipped (said so, never counted as a pass)"""
        self.rows.append((name, ok, note))
        print(f"  {'skip' if ok is None else 'pass' if ok else 'FAIL'}  {name:<28} {note}", flush=True)

    @property
    def failed(self):
        return [r for r in self.rows if r[1] is False]

    @property
    def skipped(self):
        return [r for r in self.rows if r[1] is None]


# ---- host ------------------------------------------------------------------------

def test_signal() -> tuple:
    """build/sig.f32 (tools/mksig.py) as the runner turns it into int16: (mono, stereo) files"""
    subprocess.run([sys.executable, str(REPO / "tools" / "mksig.py")], check=True)
    sig = struct.unpack("<48000f", (BUILD / "sig.f32").read_bytes())
    i16 = [max(-32768, min(32767, round(v * 32767))) for v in sig]
    mono = struct.pack(f"<{len(i16)}h", *i16)
    i16_r = i16[1000:] + i16[:1000]
    stereo = mono + bytes(0x20000 - 2 * len(i16)) + struct.pack(f"<{len(i16_r)}h", *i16_r)
    (OUT / "sig_mono.i16").write_bytes(mono)
    (OUT / "sig_stereo.i16").write_bytes(stereo)
    return OUT / "sig_mono.i16", OUT / "sig_stereo.i16"


def run_host(gen_host, blocks, rec, sample, spec) -> list:
    env = {k: v for k, v in os.environ.items() if k not in HOST_VARS}
    env.update(env_of(spec))
    out = subprocess.run([str(gen_host), str(blocks), str(rec), str(sample)], env=env,
                         capture_output=True, text=True, check=True).stdout
    return words_of(out)


def host_tier(rep: Report, update: bool, only):
    print("host: gen_host from the sources", flush=True)
    hdir = OUT / "host"
    hdir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["sh", str(REPO / "tools" / "build_gen.sh")], env=dict(os.environ, HOST_ONLY="1", GEN_BUILD="0", GEN_OUT_DIR=str(hdir)),
                       capture_output=True, text=True)
    if r.returncode:
        rep.add("build gen_host", False, (r.stdout + r.stderr).strip()[-400:])
        return
    gen_host = hdir / "gen_host"
    mono, stereo = test_signal()
    gpath = GOLDEN / "host.json"
    golden = json.loads(gpath.read_text()) if gpath.exists() else {}
    new = {}
    sig_hash = hashlib.sha256(stereo.read_bytes()).hexdigest()
    new["_signal"] = sig_hash
    if not update and golden.get("_signal") != sig_hash:
        rep.add("test signal", False, "tools/mksig.py's signal changed (or this platform's math library rounds differently): every case below will differ")
    cases = [(n, frames, GOLDEN / f"{n}.rec", stereo if "STEREO=1" in spec else mono, spec) for n, (frames, spec) in OURS.items()]
    cases += [(n, 600, TEST / "rec_st.txt", TEST / "tone.i16", "STEREO=1 " + spec) for n, spec in TONE.items()]
    for name, blocks, rec, sample, spec in cases:
        if only and not re.search(only, name):
            continue
        if not rec.exists():
            rep.add(f"host {name}", False, f"no {rec.relative_to(REPO)}: run `emu --update` in the workspace first")
            continue
        try:
            ws = run_host(gen_host, blocks, rec, sample, spec)
        except subprocess.CalledProcessError as e:
            rep.add(f"host {name}", False, f"gen_host failed ({e.returncode})")
            continue
        new[name] = {"sha256": digest(ws), "words": len(ws), "rms": round(rms(ws), 6)}
        if update:
            rep.add(f"host {name}", True, f"recorded, rms {new[name]['rms']}")
            continue
        g = golden.get(name)
        if g is None:
            rep.add(f"host {name}", False, "not in test/golden/host.json (--update to add it)")
        elif g["sha256"] == new[name]["sha256"]:
            rep.add(f"host {name}", True, f"{len(ws)} words identical")
        else:
            rep.add(f"host {name}", False, f"output changed: rms {g['rms']} -> {new[name]['rms']}, {g['words']} -> {len(ws)} words")
    if update:
        merged = {**golden, **new} if only else new
        gpath.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n")
        print(f"  wrote {gpath.relative_to(REPO)}")


# ---- emu -------------------------------------------------------------------------

def build_images(rep: Report) -> pathlib.Path | None:
    """release and diag images for each OS: the patch-site checks run; the sections 7 agree"""
    for fw in ALL_FIRMWARES:
        if fw not in FIRMWARES:
            rep.add(f"images {fw}", None, f"no Elektron OS {fw} file (./build.sh --stock, or DT2_STOCK_SYX)")
    if not FIRMWARES:
        rep.add("build images", False, "no Elektron OS file at all")
        return None
    for need in ("dt2gen_l1.dxe", "dt2gen_l1_diag.dxe", "gen_host"):
        if not (BUILD / need).exists():
            rep.add("build images", False, f"no build/{need}: run tools/build_gen.sh first")
            return None
    jobs = []
    for fw in FIRMWARES:
        tag = fw.replace(".", "")
        jobs.append((f"release image {fw}", fw, ["--release", "--slice-ui", "-o", str(OUT / f"release_{tag}.syx"),
                                                 "--section7-out", str(OUT / f"sec7_release_{tag}.bin")]))
        jobs.append((f"diag image {fw}", fw, ["--diag", "--slice-ui", "-o", str(OUT / f"diag_{tag}.syx")]))

    def one(job):
        name, fw, args = job
        r = subprocess.run(["uv", "run", "--quiet", "--python", "3.12", "--no-project", "python", str(REPO / "firmware" / "build_cap.py"), *args],
                           cwd=REPO, env=dict(os.environ, DT2_FW=fw), capture_output=True, text=True)
        return name, r

    ok = True
    with cf.ThreadPoolExecutor(len(jobs)) as ex:
        for name, r in ex.map(one, jobs):
            good = r.returncode == 0 and "all checks pass" in r.stdout
            ok &= good
            rep.add(name, good, "built, all checks pass" if good else (r.stdout + r.stderr).strip()[-400:])
    if not ok:
        return None
    s7 = [(OUT / f"sec7_release_{fw.replace('.', '')}.bin").read_bytes() for fw in FIRMWARES]
    same = all(s == s7[0] for s in s7)
    rep.add("section 7 same on every OS", same, "" if same else "the DSP side differs between OS builds")
    return OUT / f"sec7_release_{FIRMWARES[0].replace('.', '')}.bin" if same else None


def run_tracer(name, frames, spec, sec7, clear):
    out = OUT / "emu" / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in clear}
    env.update(env_of(spec), GEN_OUT=str(out), BUILT=str(sec7), DXE=str(BUILD / "dt2gen_l1.dxe"), DT2_FW=FIRMWARES[0])
    t0 = time.time()
    r = subprocess.run(["uv", "run", "--quiet", "python", str(TEST / "dt2trace_gen.py"), str(frames)],
                       cwd=DIGIKIT, env=env, capture_output=True, text=True)
    (out / "log.txt").write_text(r.stdout + r.stderr)
    return name, r, out, time.time() - t0


def out_words(out: pathlib.Path, machine: str, stereo: bool, stock=False) -> list:
    """the runner's outputs in gen_host's order: per block L, then R if stereo"""
    left = (out / f"gen_out_m{machine}{'_stock' if stock else ''}.txt").read_text().splitlines()
    right = (out / f"gen_out_m{machine}_r.txt").read_text().splitlines()
    ws = []
    for b, line in enumerate(left):
        ws += words_of(line)
        if stereo:
            ws += words_of(right[b])
    return ws


def emu_tier(rep: Report, update: bool, only, jobs: int):
    print(f"emu: firmware images for OS {', '.join(FIRMWARES) or '(none found)'}", flush=True)
    if not DIGIKIT.exists():
        rep.add("emu", False, f"no digikit at {DIGIKIT} (DT2_WORKSPACE or DIGIKIT)")
        return
    sec7 = build_images(rep)
    if sec7 is None:
        return
    clear = tracer_vars() | {"GEN_OUT"}
    runs = [(n, f, s, "ours") for n, (f, s) in OURS.items()]
    runs += [(n, f, s, "wrap") for n, (f, s) in STOCK.items()]
    runs += [(n + ":stock", f, s + " NOPATCH=1", "stock") for n, (f, s) in STOCK.items()]
    runs = [r for r in runs if not only or re.search(only, r[0].split(":")[0])]
    print(f"emu: {len(runs)} emulator runs, {jobs} at a time (about 100 s and up to 3 GB each; -j to change)", flush=True)
    golden = json.loads((GOLDEN / "host.json").read_text()) if (GOLDEN / "host.json").exists() else {}
    done = {}
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = [ex.submit(run_tracer, n.replace(":", "_"), f, s + (" STOCKWRAP=1" if kind == "wrap" else ""), sec7, clear)
                for n, f, s, kind in runs]
        for fut in cf.as_completed(futs):
            name, r, out, dt = fut.result()
            done[name] = (r, out)
            print(f"    ran {name} ({dt:.0f} s, exit {r.returncode})", flush=True)
    for name, (frames, spec) in OURS.items():
        if name not in done:
            continue
        r, out = done[name]
        e = env_of(spec)
        if r.returncode:
            tail = [l for l in (r.stdout + r.stderr).splitlines() if "differ" in l or "rror" in l or "max |diff|" in l]
            rep.add(f"emu {name}", False, "; ".join(tail[-3:]) or f"exit {r.returncode}, see {out / 'log.txt'}")
            continue
        ws = out_words(out, e["MACHINE"], "STEREO" in e)
        rec = (out / "gen_rec.txt").read_text()
        gold_rec = GOLDEN / f"{name}.rec"
        if update:
            gold_rec.write_text(rec)
            rep.add(f"emu {name}", True, f"runner == host; record written to {gold_rec.relative_to(REPO)}")
            continue
        if not gold_rec.exists() or gold_rec.read_text() != rec:
            rep.add(f"emu {name}", False, f"runner == host, but the voice record differs from {gold_rec.relative_to(REPO)} (the runner or the case changed?)")
        elif golden.get(name, {}).get("sha256") != digest(ws):
            rep.add(f"emu {name}", False, "runner == host, but not the golden output (run the host tier)")
        else:
            rep.add(f"emu {name}", True, f"runner == host == golden, {len(ws)} words")
    for name, (frames, spec) in STOCK.items():
        if name not in done or f"{name}_stock" not in done:
            continue
        (r1, o1), (r2, o2) = done[name], done[f"{name}_stock"]
        if r1.returncode or r2.returncode:
            rep.add(f"emu {name}", False, f"exit {r1.returncode}/{r2.returncode}, see {o1 / 'log.txt'}, {o2 / 'log.txt'}")
            continue
        m = env_of(spec)["MACHINE"]
        a, b = out_words(o1, m, False), out_words(o2, m, False, stock=True)
        loud = sum(1 for w in b if w & 0x7FFFFFFF)
        if a != b:
            rep.add(f"emu {name}", False, "CAPI off differs from the stock firmware")
        elif loud == 0:
            rep.add(f"emu {name}", False, "both silent: the case tests nothing")
        else:
            rep.add(f"emu {name}", True, f"CAPI off == stock, {len(a)} words ({loud} non-zero)")


JOB_BYTES = 3 << 30   # one emulator run peaks at about 2.2 GB


def free_memory() -> int | None:
    """bytes the emulator runs may use: Linux's MemAvailable (and a container's
    cgroup limit, if lower); on macOS, which pages out freely, the total less 6 GB"""
    try:
        if sys.platform.startswith("linux"):
            avail = next(int(l.split()[1]) * 1024 for l in open("/proc/meminfo") if l.startswith("MemAvailable:"))
            try:
                lim = open("/sys/fs/cgroup/memory.max").read().strip()
                if lim != "max":
                    avail = min(avail, int(lim))
            except OSError:
                pass
            return avail
        if sys.platform == "darwin":
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
            return max(0, total - (6 << 30))
    except (OSError, ValueError, StopIteration):
        pass
    return None


def default_jobs() -> int:
    """parallel emulator runs: half the cores, at most 8, and no more than memory allows"""
    jobs = max(1, min(8, (os.cpu_count() or 2) // 2))
    mem = free_memory()
    if mem is not None:
        jobs = max(1, min(jobs, mem // JOB_BYTES))
    return jobs


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("tier", nargs="?", default="host", choices=("host", "emu", "all"))
    p.add_argument("--update", action="store_true", help="rewrite test/golden/ from this run")
    p.add_argument("-j", "--jobs", type=int, default=None, help="parallel emulator runs (default: by cores and free memory, about 3 GB each)")
    p.add_argument("-k", dest="only", help="only the cases whose name matches this regex")
    a = p.parse_args()
    a.jobs = a.jobs or default_jobs()
    OUT.mkdir(parents=True, exist_ok=True)
    GOLDEN.mkdir(exist_ok=True)
    rep = Report()
    order = {"host": ("host",), "emu": ("emu",), "all": ("emu", "host") if a.update else ("host", "emu")}[a.tier]
    for t in order:
        host_tier(rep, a.update, a.only) if t == "host" else emu_tier(rep, a.update, a.only, a.jobs)
    bad, skip = rep.failed, rep.skipped
    n = len(rep.rows) - len(skip)
    print(f"\n{n - len(bad)} of {n} passed" + ("" if not bad else ": failed " + ", ".join(r[0] for r in bad))
          + (f"; skipped {', '.join(r[0] for r in skip)}" if skip else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
