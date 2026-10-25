"""Native project-menu recall using a preserved private recording/card overlay."""
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
p.add_argument("capture", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--negatives", action="store_true")
p.add_argument("--mode", choices=("off","up","order","random"), default="up")
p.add_argument("--record",action="store_true")
p.add_argument("--record-only",action="store_true",help="Isolate recording/storage from menu lifecycle checks; no UI acceptance claim")
args = p.parse_args()
args.capture=args.capture.resolve()
meta=json.loads((args.capture / "arp.json").read_text())
require(meta["status"]=="passed" and meta.get("record_replay_passed"),"Need a passing recording capture")
args.mode=meta["condition"]
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
deadline = time.monotonic() + 900
fingerprint = source_hashes()
report = {"status": "running", "condition": args.mode,
          "inputs": inputs, "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
          "source_sha256": fingerprint, "gestures": [], "stages": [],
          "scope": "Actual panel/menu callbacks and native project load, with emulated eMMC transfers; no hardware, physical timing or DSP rendering claim"}


def advance(n=2_000_000):
    target = worker.stats["instrs"] + n + gui.BUDGET
    require(target <= 6_500_000_000, "Arp instruction bound exceeded")
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


def pattern_bytes():
    project=arp.call(0x401988A2,[])
    pattern=project+0x43D0+meta['saved_pattern']*0x954
    storage=arp.call(arp.u32(arp.u32(pattern)+0x28),[pattern])
    return bytes(arp.uc.mem_read(storage,0x1DB8C))


def menu_load(slot, expected_modes, name):
    # Clamp to the first real project; native indices are zero based.
    begin=len(arp.storage_events)
    for _ in range(3):tap('NO')
    tap('SETTINGS');advance(10_000_000);tap('YES');advance(10_000_000)
    project_menu_frame=bytes(worker._panel_latch)
    # The sidebar title can disappear after LOAD OK. The highlighted LOAD
    # PROJECT row stays stable and distinguishes the parent from the picker.
    project_title={p for p in panel.lit(project_menu_frame) if p[0]>=40 and p[1]<12}
    require(project_title,'Project menu row was not rendered')
    stage(name+'-project-menu')
    tap('YES');advance(10_000_000)
    for _ in range(3):tap('UP')
    for _ in range(slot):tap('DOWN')
    tap('YES')
    completed=False
    for _ in range(90):
        if any(e.get('boundary')=='native-project-menu' for e in arp.storage_events[begin:]):
            completed=True;break
        px=panel.lit(worker._panel_latch or bytes(1024))
        save_prompt=all(p in px for p in ((19,20),(109,20),(19,43),(109,43)))
        discard_prompt=all(p in px for p in ((7,20),(121,20),(7,43),(121,43)))
        if save_prompt or discard_prompt:break
        advance(10_000_000)
    else:raise RuntimeError('Native load confirmation/completion did not appear')
    if not completed:
        if save_prompt:
            stage(name+'-save-prompt');tap('NO');advance(20_000_000)
        stage(name+'-discard-confirm');tap('YES')
    for _ in range(100):
        events=[e for e in arp.storage_events[begin:] if e.get('boundary')=='native-project-menu']
        if events:break
        advance(10_000_000)
    else:raise RuntimeError('Native menu did not complete an authenticated load')
    event=events[-1]
    require(event['status']=='passed' and event['slot']==slot,'Wrong project binding or failed recall')
    require(event['modes']==expected_modes and arp.pattern_modes==expected_modes,'Menu recalled wrong modes')
    require(pattern_bytes()==expected_pattern,'Menu changed recorded pattern bytes')
    require(not arp.playing and arp.field('held')==0 and arp.field('active')==0xFFFFFFFF,
            'Recall restored live notes or transport')
    # Import return precedes the sample-loader completion callback. Wait for
    # the actual stock parent menu before sending another panel command.
    for _ in range(120):
        title={p for p in panel.lit(worker._panel_latch or bytes(1024)) if p[0]>=40 and p[1]<12}
        if title==project_title:break
        advance(10_000_000)
    else:raise RuntimeError('Native loading dialog did not return to the project menu')
    stage(name+'-loaded')
    require(pattern_bytes()==expected_pattern,'Completed load changed recorded pattern bytes')
    require(arp.pattern_modes==expected_modes,'Completed load changed recalled modes')
    report.setdefault('menu_loads',[]).append(event)
    return event


try:
    require(worker.ready.wait(60) and not worker.error,'CPU startup failed')
    raw=(args.capture / 'card-overlay.bin').read_bytes()
    require(raw[:4]==b'ASOV' and len(raw)>=8,'Invalid overlay')
    count=struct.unpack_from('>I',raw,4)[0]
    require(count<=100_000 and len(raw)==8+count*516,'Invalid overlay extent')
    from lab.arp_storage import AttachedCard
    from lab.arp_persistence import ModeJournal,NativeFiles
    arp.card_firmware=fw=AttachedCard(arp.machine,clock['events'],inputs['card'])
    with fw.transaction():
        for n in range(count):
            sector=struct.unpack_from('>I',raw,8+n*516)[0]
            require(sector<8_388_608,'Invalid overlay sector')
            fw.card.overlay[sector]=raw[12+n*516:524+n*516]
    with fw.transaction():
        require(fw.call(fw.check.MOUNT,[0],limit=200_000_000)==0,'Native mount failed')
    fw.gui_io=True
    while len(recorder.frames)<32:advance(10_000_000)
    arp.arm();recorder.recording=False
    expected_pattern=(args.capture / 'pattern-recorded.bin').read_bytes()
    arp.load_project(meta['saved_slot'])
    require(pattern_bytes()==expected_pattern,'Initial native reload changed notes')
    require(arp.pattern_modes==meta['pattern_modes'],'Initial mode recall failed')
    saved=arp.save_project(0)
    require(pattern_bytes()==expected_pattern,'Save changed live notes')
    report['saved_project']=saved
    arp.recall_modes([0]*128)
    menu_load(0,meta['pattern_modes'],'first')
    if args.negatives:
        # Save an ordinary second slot through the stock writer, without a
        # companion, to check slot isolation even when project bytes match.
        arp.collecting=False
        try:
            with fw.transaction():
                project=fw.call(0x401988A2,[]);progress=fw.alloc(bytes(32))
                require(fw.call(0x40043A30,[project,1,progress],limit=800_000_000)&255==1,'Missing-companion fixture save failed')
        finally:arp.collecting=True
        menu_load(1,[0]*128,'missing-companion')
        menu_load(0,meta['pattern_modes'],'return-to-saved')
        with fw.transaction():
            from lab.arp_storage import read_saved_project
            _,blob=read_saved_project(fw,0)
            files=NativeFiles(fw)
            paths,records,_=ModeJournal(files).inspect(0,blob)
            require(any(records),'No companion to corrupt')
            for path,record in zip(paths,records):
                if record:
                    damaged=bytearray(record);damaged[-1]^=1
                    files.write(path,damaged)
        menu_load(1,[0]*128,'switch-before-corrupt')
        # Force a nonzero current selection so OFF cannot pass by inertia.
        arp.recall_modes(meta['pattern_modes'])
        menu_load(0,[0]*128,'corrupt-companion')
    require(not worker.error and not worker._faulted_pages,'CPU fault during menu load')
    require(source_hashes()==fingerprint,'Source changed during project load tests')
    report.update(status='passed', exact_pattern_bytes=len(expected_pattern),
        pattern_sha256=sha256(args.capture / 'pattern-recorded.bin'),
        overlay_sha256=sha256(args.capture / 'card-overlay.bin'),
        capture_sha256=sha256(args.capture / 'arp.json'),
        storage_sync={'imported_sectors':fw.sync.imported,'published_sectors':fw.sync.published},
        protected_guest_stack_transactions=fw.stack_checks)
except BaseException as error:
    report.update(status='failed',error=str(error));raise
finally:
    worker.stop_flag.set();worker.pause.clear();worker.join(30)
    require(not worker.is_alive(),'Worker did not stop')
    if arp.card_firmware:arp.card_firmware.close()
    if worker._panel_latch:panel.write_png(worker._panel_latch,str(out/'last-frame.png'))
    report.update(storage_events=arp.storage_events, faulted_pages=sorted(worker._faulted_pages),worker_error=worker.error)
    write_json(out / 'project-load.json',report)
print('PASS native project menu:',args.mode,len(report['menu_loads']),'loads')
