"""Bounded four-mode menu, recording and native project-save experiment."""
import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--mode", choices=("off","up","order","random"), default="up")
p.add_argument("--record",action="store_true")
p.add_argument("--record-only",action="store_true",help="Isolate recording/storage from menu lifecycle checks; no UI acceptance claim")
args = p.parse_args()
require(not args.record or args.mode!="off","Recording runner requires UP, ORDER or RANDOM")
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.runtime import REPO
from lab.pattern_clock import Recorder, install
from lab.arp_integration import ArpIntegration
from emu import gui, panel

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
require(sha256(inputs["main"]) == "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830",
        "Unexpected prepared CPU fixture")
main = Path(inputs["main"]).read_bytes()
os.chdir(REPO)
os.environ.update(DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"],
                  DT2_MAIN_IMG=inputs["main"])
gui.BUDGET = 50_000
recorder = Recorder()
clock = install(gui, recorder)
arp = ArpIntegration(gui, clock, main, card_path=inputs["card"])
worker = gui.Emulator(inputs["snapshot"], syx=inputs["syx"], card_image=inputs["card"],
                      live=recorder, fast=False, realtime=False, panel_dwell=4)
clock["worker"] = worker
worker.pause.set(); worker.start()
deadline = time.monotonic() + 600
fingerprint = source_hashes()
report = {"status": "running", "condition": args.mode,
          "inputs": inputs, "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
          "source_sha256": fingerprint, "gestures": [], "stages": [],
          "scope": "Native four-mode core and G draw/edit hooks; diagnostic clock and prepared sampler; no permanent firmware, hardware or DAC claim"}


def advance(n=2_000_000):
    target = worker.stats["instrs"] + n + gui.BUDGET
    require(target <= 950_000_000, "Arp instruction bound exceeded")
    clock["pause_after"] = target; worker.pause.clear()
    while worker.stats["status"] != "paused" or worker.stats["instrs"] < target:
        require(not worker.error and worker.is_alive(), f"CPU stopped: {worker.error}")
        require(time.monotonic() < deadline, "Arp wall-time bound exceeded")
        time.sleep(0.005)


def button(name, kind):
    matches = [k for k, v in worker.button_names.items() if v == name]
    require(len(matches) == 1, f"Unknown panel control {name}")
    report["gestures"].append([worker.stats["instrs"], kind, name])
    worker.inbox.append((kind, matches[0], None)); advance()


def tap(name):
    button(name, "press"); button(name, "release")


def chord(mod, name):
    button(mod, "press"); tap(name); button(mod, "release")


def encoder(name,delta):
    matches=[k for k,v in worker.encoder_names.items() if v=="ENCODER "+name]
    require(len(matches)==1,f"Unknown encoder {name}: {worker.encoder_names}")
    worker.inbox.append(("encoder",matches[0],delta));advance(4_000_000)


def stage(name):
    report["stages"].append({"name": name, "frame": len(recorder.frames),
                             "tick": arp.tick(), "instructions": worker.stats["instrs"]})
    if worker._panel_latch:
        panel.write_png(worker._panel_latch, str(out / (name + ".png")))
    print(name, worker.stats["instrs"], "frames", len(recorder.frames),
          "arp notes", len([e for e in arp.outputs if e["kind"] == "on"]), flush=True)


try:
    require(worker.ready.wait(60) and not worker.error, f"CPU startup failed: {worker.error}")
    while len(recorder.frames) < 32 and worker.stats["instrs"] < 220_000_000:
        advance(10_000_000)
    require(len(recorder.frames) >= 32, "Audio-link warmup did not complete")
    tap("STOP"); tap("STOP")
    chord("FUNC", "SRC")
    for _ in range(8): tap("UP")
    tap("YES"); tap("YES"); tap("TRIG 1")
    tap("RECORD"); chord("FUNC", "PLAY"); tap("RECORD")
    tap("KEYBOARD")
    arp.arm(); stage("armed")
    chord("FUNC","KEYBOARD")
    advance(10_000_000);stage("menu-off")
    encoder("G",20);require(arp.field("enabled")==3,"G did not clamp to RANDOM")
    stage("menu-random")
    encoder("G",-20);require(arp.field("enabled")==0,"G did not clamp to OFF")
    mode=("off","up","order","random").index(args.mode)
    if mode:encoder("G",mode)
    require(arp.field("enabled")==mode,"G selected wrong mode")
    stage("menu-"+args.mode)
    if not args.record_only:
        current=arp.field("enabled")
        # The native jump/renderer must preserve every pixel outside G.
        from lab.arp_modes import FIELDS
        arp.uc.mem_write(0x60002000+FIELDS["ui_active"],bytes(4))
        delta=1 if mode<3 else -1
        encoder("G",delta)
        advance(20_000_000)
        base=bytes(worker._panel_latch);stage("menu-stock-neighbors")
        arp.uc.mem_write(0x60002000+FIELDS["ui_active"],(1).to_bytes(4,"big"))
        encoder("G",-delta)
        advance(20_000_000)
        shown=bytes(worker._panel_latch)
        changed=panel.lit(base)^panel.lit(shown)
        (out/"menu-stock.bin").write_bytes(base);(out/"menu-shown.bin").write_bytes(shown)
        print("G pixel diff",len(changed),sorted(changed)[:20],flush=True)
        require(changed and all(64<=x<96 and 32<=y<64 for x,y in changed),"G redraw changed neighboring pixels")
        report["g_pixel_changes"]=len(changed)
        (out/"menu-stock.bin").write_bytes(base);(out/"menu-shown.bin").write_bytes(shown)
        stage("menu-final")
        report['neighbor_controls'] = []
        for name,x,amount in (("E",0,30),("F",32,12),("H",96,30)):
            project=arp.call(0x401988A2,[]);pattern=arp.call(0x400428EA,[project])
            scale=arp.call(0x4003F3AE,[pattern])
            note_cfg=arp.call(0x4003F6FC,[pattern])
            getter,context={"E":(0x4003EE8E,scale),"F":(0x4003F6FC,pattern),"H":(0x4003EF22,scale)}[name]
            def value():
                v=arp.call(getter,[context])
                if name=="F":
                    keyboard=arp.call(0x4004294E,[project])
                    octave=arp.call(0x4005565A,[keyboard])&255
                    if octave&128:octave-=256
                    v+=12*octave
                if name=="H":v &=255
                return v
            native_before=value()
            before_pixels=panel.lit(bytes(worker._panel_latch))
            # Stock controls accumulate fractional movement and may drop the
            # first event. Require a real native value change, within 8 packets.
            for movement in range(8):
                encoder(name,amount)
                native_after=value()
                if native_after!=native_before:break
            advance(10_000_000)
            print("neighbor",name,native_before,native_after,flush=True)
            require(native_before!=native_after,f"Neighbor {name} native value did not change")
            turned_pixels=panel.lit(bytes(worker._panel_latch))
            cell=lambda pixels:{(a,b) for a,b in pixels if x<=a<x+32 and 32<=b<64}
            require(cell(before_pixels)!=cell(turned_pixels),f"Neighbor {name} did not change")
            require(arp.field("enabled")==current,f"Neighbor {name} changed arp mode")
            if name=="F":
                # Stock Root turns accelerate and include the octave. Restore
                # the full MIDI root through the same native setter as F.
                require(0<=native_before<=127,"Unknown stock root")
                arp.call(0x4003FBCC,[pattern,native_before])
            else:
                for movement in range(8):
                    encoder(name,-amount)
                    if value()==native_before:break
            advance(10_000_000)
            panel.write_png(worker._panel_latch,str(out/("neighbor-"+name+"-returned.png")))
            require(value()==native_before,f"Neighbor {name} native value did not return")
            report['neighbor_controls'].append({"encoder":name,"before":native_before,"turned":native_after})
        tap("ENCODER G");require(arp.field("enabled")==current,"G push changed the mode")
        # Stock push/view behavior is retained. Reenter settings for a valid
        # display comparison; a transient page after push is not the menu.
        chord("FUNC","KEYBOARD");advance(5_000_000)
        stage("menu-after-push")
    tap("NO");advance(5_000_000)
    input_start,stock_start=len(arp.inputs),len(arp.stock_calls)
    report.update(input_start=input_start,stock_start=stock_start)
    first_frame=len(recorder.frames)
    project=arp.call(0x401988A2,[])
    pattern=arp.call(0x400428EA,[project])
    storage=arp.call(arp.u32(arp.u32(pattern)+0x28),[pattern])
    before=bytes(arp.uc.mem_read(storage,0x1DB8C))
    for name in ("TRIG 13","TRIG 11","TRIG 9"):button(name,"press")
    if args.record:chord("RECORD","PLAY")
    else:tap("PLAY")
    expected={"up":[60,64,67,60,64,67,60,64],
              "order":[67,64,60,67,64,60,67,64],
              "random":[64,64,60,60,60,64,67,60]}
    if mode:
        while len([e for e in arp.outputs if e["kind"]=="on"])<8:advance(3_000_000)
        require([e["note"] for e in arp.outputs if e["kind"]=="on"]==expected[args.mode],"Mode sequence differs")
    else:advance(100_000_000)
    stage("phrase-"+args.mode)
    for name in ("TRIG 11","TRIG 9","TRIG 13"):button(name,"release")
    tap("STOP");advance(8_000_000)
    require(arp.field("held")==arp.field("owned")==0,"Input ownership remained")
    physical=[e for e in arp.inputs[input_start:] if e["kind"]=="on"]
    require([e["note"] for e in physical]==[67,64,60],"Unexpected mapped inputs")
    if not mode:
        require(not arp.outputs,"OFF generated output")
        require([e["note"] for e in arp.stock_calls[stock_start:] if e["kind"]=="on" and e["track"]==0]==[67,64,60],"OFF stock path differs")
    after=bytes(arp.uc.mem_read(storage,0x1DB8C))
    (out/"pattern-before.bin").write_bytes(before);(out/"pattern-recorded.bin").write_bytes(after)
    report["pattern_storage"]={"address":hex(storage),"changed_bytes":sum(a!=b for a,b in zip(before,after)),"record":args.record}
    if args.record:
        require(before!=after,"Generated notes did not record")
        report["record_outputs"]=list(arp.outputs)
        record_end=len(recorder.frames)
        from emu import snapshot
        snapshot.save(arp.machine,str(out/"recorded.snap"),components=clock["events"]["checkpoint_components"])
        saved=arp.save_project()
        report["saved_modes"]=saved
        report["saved_slot"]=128;report["saved_pattern"]=arp.pattern_id
        overlay=arp.card_firmware.card.overlay
        (out/"card-overlay.bin").write_bytes(b"ASOV"+struct.pack(">I",len(overlay))+b"".join(struct.pack(">I",k)+v for k,v in sorted(overlay.items())))
        arp.load_project()
        require(bytes(arp.uc.mem_read(storage,0x1DB8C))==after,"Diagnostic project recall changed the pattern")
        require(arp.pattern_modes[arp.pattern_id]==mode,"Diagnostic project recall changed arp mode")
        old_inputs=len(arp.inputs);old_outputs=len(arp.outputs)
        tap("PLAY")
        def replay_trigs():
            return [int.from_bytes(f[2:4],"big")//256 for f in recorder.frames[record_end:]
                    if int.from_bytes(f[0x22:0x24],"big")&1]
        while len(replay_trigs())<8:advance(3_000_000)
        report["replay_notes"]=replay_trigs()[:8]
        require(report["replay_notes"]==expected[args.mode],"Recorded phrase replay differs")
        require(not arp.outputs[old_outputs:] and not arp.inputs[old_inputs:],"Sequencer notes were re-collected")
        tap("STOP");advance(8_000_000)
        report["record_replay_passed"]=True
        report["record_end"]=record_end
    unsupported_start = len(arp.stock_calls)
    chord("TRK", "TRIG 2")
    tap("TRIG 9")
    unsupported = arp.stock_calls[unsupported_start:]
    require(any(e["kind"] == "on" and e["track"] == 1 and e["note"] == 60
                and not e["generated"] for e in unsupported), "Other track was intercepted")
    require(any(e["kind"] == "off" and e["track"] == 1 and e["note"] == 60
                and not e["generated"] for e in unsupported), "Other track release was intercepted")
    stage("unsupported-track-stock")
    report["unsupported_calls"] = unsupported
    trigs = [{"frame": i, "tick": recorder.ticks[i],
              "note_word": int.from_bytes(f[2:4], "big")}
             for i, f in enumerate(recorder.frames) if i >= first_frame
             and int.from_bytes(f[0x22:0x24], "big") & 1]
    if mode and not args.record:
        ons = [e for e in arp.outputs if e["kind"] == "on"]
        require([e["note_word"] for e in trigs] == [e["note"] * 256 for e in ons],
                "Native arp pitches did not reach the actual DSP control frames")
        lag = [t["tick"] - e["tick"] for t, e in zip(trigs, ons, strict=True)]
        require(all(0 <= n <= 64 for n in lag), "Control delivery exceeded two modeled blocks")
        report["control_delivery_samples"] = lag
        report["native_on_intervals_samples"] = [b["tick"] - a["tick"]
                                                   for a, b in zip(ons, ons[1:])]
    require(all((b-a) & 0xFFFFFFFF == 32 for a, b in zip(recorder.ticks, recorder.ticks[1:])),
            "Capture clock has missing or duplicate blocks")
    require(not worker.error and not worker._faulted_pages, "CPU error or fault pages")
    require(source_hashes() == fingerprint, "Source changed during capture")
    report.update(status="passed", render_start=first_frame, render_end=len(recorder.frames), menu_events=arp.menu_events, pattern_modes=arp.pattern_modes, storage_events=arp.storage_events)
except BaseException as exc:
    report.update(status="failed", error=str(exc)); raise
finally:
    worker.stop_flag.set(); worker.pause.clear(); worker.join(timeout=30)
    require(not worker.is_alive(), "CPU worker did not stop")
    if arp.card_firmware is not None:
        overlay=arp.card_firmware.card.overlay
        (out/"card-overlay.bin").write_bytes(b"ASOV"+struct.pack(">I",len(overlay))+b"".join(struct.pack(">I",k)+v for k,v in sorted(overlay.items())))
        arp.card_firmware.close()
    (out / "control.dtfr").write_bytes(b"DTFR" + struct.pack("<II", 1, len(recorder.frames)) +
        b"".join(struct.pack("<I", len(f)) + f for f in recorder.frames))
    (out / "state.bin").write_bytes(arp.raw() if arp.machine else b"")
    report.update(menu_events=arp.menu_events, storage_events=arp.storage_events, native_inputs=arp.inputs, native_outputs=arp.outputs, stock_calls=arp.stock_calls,
                  ticks=recorder.ticks, interrupts=dict(clock["interrupts"]),
                  faulted_pages=sorted(worker._faulted_pages), worker_error=worker.error,
                  capture_sha256=sha256(out / "control.dtfr"), transactions=arp.calls,
                  trigger_frames=[{"frame": i, "tick": recorder.ticks[i],
                                   "note_word": int.from_bytes(f[2:4], "big")}
                                  for i, f in enumerate(recorder.frames)
                                  if i >= report.get("render_start", 0) and int.from_bytes(f[0x22:0x24], "big") & 1])
    write_json(out / "arp.json", report)
print("PASS", report["condition"], len(arp.outputs), "native arp output edges")
