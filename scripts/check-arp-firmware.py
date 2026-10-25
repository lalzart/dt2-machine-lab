#!/usr/bin/env python3
"""Stock-only native arp panel test; observers never implement arp behavior."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.project import doctor,settings,require,write_json,source_hashes
config=settings()
if Path(sys.executable).resolve()!=config['python'].resolve():os.execv(str(config['python']),[str(config['python']),__file__,*sys.argv[1:]])
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--mode',choices=('off','up','order','random'),default='up');p.add_argument('--record',action='store_true');p.add_argument('--storage',action='store_true');p.add_argument('--stale-keyboard',action='store_true',help='Inject a stale arp keyboard flag while the stock keyboard is active');p.add_argument('--keep-settings-open',action='store_true');p.add_argument('--diagnostics',action='store_true');p.add_argument('--tempo-ui',action='store_true');p.add_argument('--rate',choices=('1/4','1/8','1/16','1/32'),default='1/16');p.add_argument('--tempo',type=float,default=127.5);p.add_argument('--shared-save',action='store_true');p.add_argument('--instruction-limit',type=int,default=8_500_000_000,help='Bounded whole-scenario budget, including stock filesystem autosaves');p.add_argument('--cpu-extension',action='store_true',help='Prepared-fixture component test of the combined DDR image; cold reset is checked separately');p.add_argument('--package',type=Path,help='Check the exact CPU image from a local extension package');p.add_argument('--flex-take',action='store_true',help='Publish and assign a native Flex take before shared project save, then verify reload');p.add_argument('--stopped-playback',action='store_true',help='Enable native stopped arp variant');p.add_argument('--stopped',action='store_true',help='Audition with PLAY off');p.add_argument('--track',type=int,choices=range(1,17),default=1);args=p.parse_args();require(not args.stopped or (args.stopped_playback and args.tempo_ui and not args.record and not args.storage),'Stopped scenario needs tempo variant and no recording/storage');args.cpu_extension=bool(args.cpu_extension or args.package);require(not args.flex_take or (args.package and args.storage),'Flex take requires a package and storage scenario');require(0<args.instruction_limit<=16_000_000_000,'Instruction limit must be in 1..16000000000');doctor()
out=args.output.resolve();require(out.is_relative_to(ROOT/'out/runs'),'Fresh ignored output required');out.mkdir(exist_ok=False);os.environ['DT2_LAB_RUN_DIR']=str(out.relative_to(ROOT/'out/runs'))
from lab.runtime import REPO,STOCK_MAIN
from lab.flex_session import stock_inputs
from lab.arp_firmware import patch_cpu,ON,OFF,PLAY,KEYBOARD,MODES,TRACK,PATTERN
from lab.pattern_clock import Recorder,install
from unicorn import UC_HOOK_CODE,m68k_const as r
from emu import gui,panel
inputs=stock_inputs()
if args.cpu_extension:
 from lab.cpu_extension import build_cpu
 def patch_cpu(stock,**options):
  require(options['tempo_ui'] and not options['diagnostics'],'Extension uses normal tempo UI')
  if args.package:
   from lab.cpu_fixture import load_package
   image,combined,_manifest=load_package(args.package)
  else:
   options=dict(arp_stopped=args.stopped_playback)
   if args.track!=1:options.update(any_tracks=True,features='all',output=out/'base')
   image,combined=build_cpu(stock,**options)
  require(args.track==1 or combined['arp'].get('any_track'),'Non-T1 requires any-track package')
  return image,dict(combined,locations=combined['arp']['locations'])
image,meta=patch_cpu(STOCK_MAIN.read_bytes(),diagnostics=args.diagnostics,tempo_ui=args.tempo_ui,shared_save=args.shared_save,stopped_playback=args.stopped_playback);require(patch_cpu(STOCK_MAIN.read_bytes(),diagnostics=args.diagnostics,tempo_ui=args.tempo_ui,shared_save=args.shared_save,stopped_playback=args.stopped_playback)[0]==image,'Build repeat');(out/'ARP_MAIN_OS.bin').write_bytes(image);write_json(out/'native-patches.json',meta)
os.environ.update(DT2_DEVICES=str(REPO/'devices'),DT2_SYX=inputs['syx'],DT2_SECTIONS=inputs['sections'],DT2_MAIN_IMG=str(STOCK_MAIN));os.chdir(REPO)
gui.BUDGET=50_000;recorder=Recorder();runtime=install(gui,recorder);orig=gui.build;outputs=[];allnotes=[];native_ensure=[];clock_calls=[];native_saves=[];native_loads=[];phase_trace=[]
def build(*a,**kw):
 result=orig(*a,**kw);m=result[0]
 if args.cpu_extension:
  from lab.cpu_fixture import install as install_cpu
  install_cpu(m.uc.mem_write,image,meta)
 else:
  for w in meta['writes']:m.uc.mem_write(w['address'],bytes.fromhex(w['after']))
 def watch(uc,pc,size,data):
  sp=uc.reg_read(r.UC_M68K_REG_A7);u=lambda x:int.from_bytes(uc.mem_read(x,4),'big');ret=u(sp)
  e=dict(kind='on' if pc==ON else 'off',track=u(sp+4),note=u(sp+8),velocity=u(sp+12) if pc==ON else 0,tick=u(0x40966500),return_pc=ret)
  allnotes.append(e)
  if meta['locations']['events']<=ret<meta['locations']['events']+240:outputs.append(e)
 def storage_watch(uc,pc,size,data):
  sp=uc.reg_read(r.UC_M68K_REG_A7);uu=lambda x:int.from_bytes(uc.mem_read(x,4),'big');print('storage-enter',hex(pc),'args',[hex(uu(sp+i)) for i in (4,8,12)],flush=True)
  if pc==0x40043A30:native_saves.append([uu(sp+i) for i in (4,8,12)])
  if pc in (0x400F5050,0x40043F74):native_loads.append([uu(sp+i) for i in (4,8,12)])
 for pc in (0x40043A30,0x400F5050,0x40043F74,0x4011CD30):m.uc.hook_add(UC_HOOK_CODE,storage_watch,begin=pc,end=pc)
 if args.cpu_extension:
  phases=meta['save_phases']
  for label,pc in [('arp_prepare',phases['prepare'][0]),('flex_prepare',phases['prepare'][1]),('stock',phases['stock']),('arp_commit',phases['commit'][0]),('arp_cleanup',phases['cleanup'][0])]:
   m.uc.hook_add(UC_HOOK_CODE,lambda uc,pc,size,data,label=label:phase_trace.append(label),begin=pc,end=pc)
 if args.tempo_ui:
  def clock_watch(uc,pc,size,data):
   sp=uc.reg_read(r.UC_M68K_REG_A7);q=lambda x:int.from_bytes(uc.mem_read(x,4),'big')
   if q(sp+12):clock_calls.append(q(sp+8))
  m.uc.hook_add(UC_HOOK_CODE,clock_watch,begin=meta['locations']['clock'],end=meta['locations']['clock'])
 m.uc.hook_add(UC_HOOK_CODE,watch,begin=ON,end=ON);m.uc.hook_add(UC_HOOK_CODE,watch,begin=OFF,end=OFF)
 return result
gui.build=build
worker=gui.Emulator(inputs['snapshot'],syx=inputs['syx'],card_image=inputs['card'],live=recorder,fast=False,realtime=False,panel_dwell=4);runtime['worker']=worker;worker.pause.set();worker.start();deadline=time.monotonic()+2400;report=dict(status='running',sources=source_hashes(),mode=args.mode,gestures=[],native=True,python_arp_services=False,hardware=False,instruction_limit=args.instruction_limit,cpu_extension=args.cpu_extension,package=str(args.package) if args.package else None)
def u(x):return int.from_bytes(worker._uc.mem_read(x,4),'big')
def state():return u(meta['locations']['pointer'])
def advance(n=2_000_000):
 target=worker.stats['instrs']+n+gui.BUDGET;require(target<args.instruction_limit,'Instruction bound');runtime['pause_after']=target;worker.pause.clear()
 while worker.stats['status']!='paused' or worker.stats['instrs']<target:
  require(not worker.error and worker.is_alive(),f'CPU stopped {worker.error}');require(time.monotonic()<deadline,'Wall-time bound');time.sleep(.005)
 require(not worker._faulted_pages,'CPU fault pages')
 if args.storage and target//250_000_000 != (target-n)//250_000_000 and state():
  print('progress',target,'mode',u(state()),'busy',u(state()+2720),'slot',u(state()+3244),'loading',u(state()+3256),flush=True)
  if worker._panel_latch:panel.write_png(worker._panel_latch,str(out/'progress.png'))
def button(name,kind):
 code=next(k for k,v in worker.button_names.items() if v.upper()==name.upper());worker.inbox.append((kind,code,None));report['gestures'].append([kind,name]);advance()
def tap(n):button(n,'press');button(n,'release')
def chord(m,n):button(m,'press');tap(n);button(m,'release')
def enc(n,d):
 code=next(k for k,v in worker.encoder_names.items() if v=='ENCODER '+n);worker.inbox.append(('encoder',code,d));report['gestures'].append(['encoder',n,d]);advance(12_000_000)
def g_select(offset,target):
 # Original stock enum filtering consumes several pulses before a choice.
 for _ in range(48):
  current=u(state()+offset)
  if current==target:return
  enc('G',(6 if target>current else -6) if args.tempo_ui else target-current)
 require(u(state()+offset)==target,'G selection did not converge')
def g_boundary(offset,target):
 for _ in range(4):
  enc('G',96 if target else -96)
  if u(state()+offset)==target:return
 require(u(state()+offset)==target,'G boundary did not converge')
def shot(n):
 if args.diagnostics and state():
  print('D1',n,{str(x):u(state()+x) for x in (4344,4348,4352,4356)},flush=True)
 if worker._panel_latch:panel.write_png(worker._panel_latch,str(out/(n+'.png')))
 print(n,worker.stats['instrs'],'state',hex(state()),'mode',u(state()) if state() else None,'keyboard',u(state()+KEYBOARD) if state() else None,'track',u(state()+TRACK) if state() else None,'pattern',u(state()+PATTERN) if state() else None,'direct',u(state()+2716) if state() else None,'notes',len(outputs),'held',u(state()+36) if state() else None,'PLAY',u(state()+PLAY) if state() else None,flush=True)
try:
 require(worker.ready.wait(60) and not worker.error,'Startup failed')
 while len(recorder.frames)<32 and worker.stats['instrs']<220_000_000:advance(10_000_000)
 require(state(),'Native allocator/init not reached')
 tap('STOP');tap('STOP')
 if args.track!=1:chord('TRK',f'TRIG {args.track}');advance(12_000_000)
 require(u(state()+TRACK)==args.track-1,'Selected native track mismatch');report['track']=args.track
 # Prepare an empty stock pattern and the keyboard with original panel input.
 tap('RECORD');chord('FUNC','PLAY');tap('RECORD');advance(20_000_000);tap('KEYBOARD');advance(12_000_000);shot('keyboard')
 chord('FUNC','KEYBOARD');advance(10_000_000);shot('menu-off');g_boundary(0,3);shot('after-g');require(u(state())==3,'Native G upper clamp');shot('menu-random');g_boundary(0,0);require(u(state())==0,'Native G lower clamp')
 if args.tempo_ui:
  enc('G',1);require(u(state())==0,'One raw G pulse changed mode')
 mode=('off','up','order','random').index(args.mode)
 if mode:g_select(0,mode)
 require(u(state())==mode,'Mode selection');shot('menu-'+args.mode)
 if args.tempo_ui:
  from lab.arp_tempo import RATE,FOCUS,TEMPO,STEPS
  # Exercise physical encoder push 47. Names are read from stock resources.
  print('push-name',worker.button_names[47],flush=True);g_name=worker.button_names[47];tap(g_name);advance(40_000_000);require(u(state()+FOCUS)==1,'G push rate focus')
  g_boundary(RATE,0)
  require(u(state()+RATE)==0,'Rate lower clamp')
  g_boundary(RATE,3)
  require(u(state()+RATE)==3,'Rate upper clamp')
  rate=('1/4','1/8','1/16','1/32').index(args.rate)
  g_select(RATE,rate)
  require(u(state()+RATE)==rate,'Rate selection');shot('menu-rate')
  tap(g_name);advance(40_000_000);require(u(state()+FOCUS)==0,'G push mode focus');shot('menu-mode-rate')
  tap('NO');tap('TEMPO');shot('tempo-before')
  target=round(args.tempo*120);require(3600<=target<=36000 and target%12==0,'Tempo UI tenth-BPM bound')
  for _ in range(128):
   current=u(0x402a148c)
   if current==target:break
   difference=target-current;whole=int(difference/120)
   coarse=abs(difference)>1200
   units=max(-96,min(96,whole*32)) if coarse else (1 if difference>0 else -1)*32
   enc('A' if coarse else 'B',units);print('tempo-now',u(0x402a148c),u(0x402b62bc),flush=True)
  require(u(0x402a148c)==target,f'Stock desired tempo UI {u(0x402a148c)} != {target}');shot('tempo-selected');tap('NO')
  chord('FUNC','KEYBOARD');advance(10_000_000);shot('tempo-rate-menu')
  report['tempo_ui']={'tempo120':target,'bpm':target/120,'rate':args.rate,'g_push_name':g_name}

 if not args.keep_settings_open:tap('NO')
 advance(5_000_000)
 if args.stale_keyboard:
  worker._uc.mem_write(state()+KEYBOARD,bytes(4));report['fault_injection']='Arp keyboard flag reset while stock keyboard remains active'
 if args.record:
  # Enter ordinary live recording before playing a fresh keyboard chord.
  chord('RECORD','PLAY');advance(8_000_000);shot('live-record-start')
  if not u(state()+KEYBOARD):tap('KEYBOARD');advance(12_000_000)
  require(u(state()+KEYBOARD)==1 and u(state()+PLAY)==1,'Live recording keyboard/transport context')
 clock_begin=len(clock_calls);begin=len(outputs);notes_begin=len(allnotes)
 for name in ('TRIG 13','TRIG 11','TRIG 9'):button(name,'press')
 shot('held');require(not mode or u(state()+36)==3,'Native collector did not capture chord')
 if not args.record and not args.stopped:tap('PLAY')
 if args.tempo_ui:
  advance(8_000_000);require(u(0x402b62bc)==target,'Native active tempo did not follow selected tempo')
 expected={'up':[60,64,67,60,64,67,60,64],'order':[67,64,60,67,64,60,67,64],'random':[64,64,60,60,60,64,67,60]}
 if mode:
  wait_start=worker.stats['instrs'];wait_bound=3_000_000_000 if not args.tempo_ui else int((8*STEPS[rate]/target/48000+2)*132_000_000)
  while len([e for e in outputs[begin:] if e['kind']=='on'])<8:
   require(worker.stats['instrs']-wait_start<wait_bound,'Arp output deadline; inspect held/PLAY/keyboard state');advance(3_000_000)
  if args.diagnostics:
   require(u(state()+4344)==1,'D1 failed to observe native clock progress');require(u(state()+4348)==8,'D1 generated-note count');require(u(state()+4352)==3,'D1 physical API count excludes generated output');require(u(state()+4356)==0x4005C666,'D1 original physical caller');shot('playing-diagnostics')
  require(all(e['track']==args.track-1 for e in outputs[begin:]),'Arp output reached another track')
  actual=[e['note'] for e in outputs[begin:] if e['kind']=='on'];expected_notes=expected[args.mode];require(actual==expected[args.mode],f'Native vector {actual}')
  if args.tempo_ui and not args.record:
   onsets=[e['tick'] for e in outputs[begin:] if e['kind']=='on'];active_calls=clock_calls[clock_begin:];gaps=[b-a for a,b in zip(active_calls,active_calls[1:])];service=max(gaps)
   step=STEPS[rate];deadlines=[active_calls[0]+(n*step+target-1)//target for n in range(1,9)]
   lateness=[actual-deadline for actual,deadline in zip(onsets,deadlines)]
   require(all(0<=x<=service for x in lateness),f'Native cadence {lateness}, service {service}')
   offs=[e['tick'] for e in outputs[begin:] if e['kind']=='off']
   nominal_ends=[a+(step//2+target-1)//target for a in onsets]
   # Monophonic output must close an active gate when the next note arrives,
   # even if a late preceding onset leaves less than its nominal half gate.
   ends=[min(nominal,onsets[i+1]) if i+1<len(onsets) else nominal for i,nominal in enumerate(nominal_ends)]
   gate_lateness=[b-a for a,b in zip(ends,offs)]
   preempted=[i for i,b in enumerate(offs) if b<nominal_ends[i]]
   require(all(i+1<len(onsets) and offs[i]==onsets[i+1] for i in preempted),'Gate shortened without the next note')
   require(all(0<=x<=service for x in gate_lateness),f'Native gate cadence {gate_lateness}')
   report['timing']={'onset_ticks':onsets,'onset_lateness_samples':lateness,'gate_lateness_samples':gate_lateness,'gates_preempted_by_next_note':preempted,'max_service_gap_samples':service,'exact_interval_samples':step/target,'hardware_timing':False}

 else:advance(100_000_000);require(len(outputs)==begin,'OFF generated events')
 if args.stopped:
  require(u(state()+PLAY)==0,'Stopped audition unexpectedly started transport')
  report['stopped_playback']={'play':0,'sample_counter_advances':len(set(recorder.ticks))>1,'native_generated_ons':len([e for e in outputs[begin:] if e['kind']=='on'])}
 for name in ('TRIG 11','TRIG 9','TRIG 13'):button(name,'release')
 tap('STOP');advance(8_000_000);shot('stopped');require(u(state()+32)==u(state()+36)==0,'Held owners remain');require(u(state()+20)==0xffffffff,'Gate active after stop')
 if args.storage:
  recorder.recording=False
  from emu import snapshot
  snapshot.save(runtime['machine'],str(out/'recorded.snap'),components=runtime['events']['checkpoint_components'])
  from lab.arp_storage import AttachedCard,serialized_project
  from lab.arp_persistence import NativeFiles,ModeJournal
  if args.tempo_ui:
   from lab.arp_tempo_persistence import RateJournal as ModeJournal
  from lab.arp_firmware import STATUS,BUSY
  card=AttachedCard(runtime['machine'],runtime['events'],inputs['card'])
  flex_take=None
  if args.flex_take:
   from lab.combined_session import FlexTake
   flex_take=FlexTake(card,meta)
  with card.transaction():
   require(card.call(card.check.MOUNT,[0],limit=200_000_000)==0,'Mount')
   if flex_take:report['flex_take']={'published':flex_take.seed()}
   project=card.call(0x401988A2,[]);pat=card.call(0x400428EA,[project]);storage=card.call(card.u32(card.u32(pat)+0x28),[pat]);recorded=card.read(storage,0x1DB8C)
  expected=[u(state()+MODES+4*i) for i in range(128)];card.gui_io=True
  for _ in range(3):tap('NO')
  tap('SETTINGS');advance(10_000_000);tap('YES');advance(10_000_000)
  tap('DOWN');shot('save-menu');tap('YES');advance(12_000_000);shot('save-open')
  for attempt in range(3):
   if any(row[1]==0 for row in native_saves):break
   tap('YES');advance(12_000_000);shot('save-confirm-'+str(attempt))
  require(any(row[1]==0 for row in native_saves),'Native slot-zero Save Project did not start')
  runtime['timers'].rescale(1_056_000_000)
  for _ in range(700):
   if u(state()+BUSY)==0 and u(state()+STATUS)!=0:break
   advance(10_000_000)
  else:raise RuntimeError('Native GUI save did not complete')
  runtime['timers'].rescale(132_000_000);advance(10_000_000)
  require(u(state()+STATUS)==1,'Native GUI companion save failed')
  with card.transaction():
   blob=serialized_project(card,0);require(ModeJournal(NativeFiles(card)).load(0,blob)==expected,'Independent companion decoding')
  if flex_take:report['flex_take']['saved']=flex_take.saved()
  (out/'pattern-recorded.bin').write_bytes(recorded);shot('saved')
  snapshot.save(runtime['machine'],str(out/'saved.snap'),components=runtime['events']['checkpoint_components'])
  (out/'saved-overlay.bin').write_bytes(b'ASOV'+__import__('struct').pack('>I',len(card.card.overlay))+b''.join(__import__('struct').pack('>I',k)+v for k,v in sorted(card.card.overlay.items())))
  # Negative inertia fixture: clear RAM configuration before native recall.
  worker._uc.mem_write(state()+MODES,bytes(512))
  if args.tempo_ui:
   # Explicit negative fixture; no host callback implements arp behavior.
   import struct
   wrong=(rate+1)%4
   for offset,value in ((0,0),(RATE,wrong),(4484,STEPS[wrong]),(4488,STEPS[wrong]//2)):
    worker._uc.mem_write(state()+offset,struct.pack('>I',value))
  card.gui_io=True
  # Normal stock project menu and job scheduling; only eMMC sectors are modeled.
  load_begin=len(native_loads);direct_loading=False
  for _ in range(3):tap('NO')
  tap('SETTINGS');advance(10_000_000);tap('YES');advance(10_000_000)
  for _ in range(3):tap('UP')
  advance(5_000_000)
  title={q for q in panel.lit(worker._panel_latch) if q[0]>=40 and q[1]<12}
  tap('YES');advance(10_000_000)
  for _ in range(3):tap('UP')
  tap('YES')
  for _ in range(90):
   actual=[u(state()+MODES+4*i) for i in range(128)]
   if actual==expected and u(state()+2720)==0:break
   if len(native_loads)>load_begin:direct_loading=True;break
   px=panel.lit(worker._panel_latch or bytes(1024))
   save_prompt=all(q in px for q in ((19,20),(109,20),(19,43),(109,43)))
   discard_prompt=all(q in px for q in ((7,20),(121,20),(7,43),(121,43)))
   if save_prompt or discard_prompt:break
   advance(10_000_000)
  else:raise RuntimeError('Native load dialog missing')
  if actual!=expected and not direct_loading:
   if save_prompt:
    shot('save-prompt');tap('NO')
    runtime['timers'].rescale(1_056_000_000)
    for _ in range(350):
     px=panel.lit(worker._panel_latch or bytes(1024))
     if all(q in px for q in ((7,20),(121,20),(7,43),(121,43))):break
     advance(10_000_000)
    else:raise RuntimeError('Discard confirmation did not follow working-project autosave')
    runtime['timers'].rescale(132_000_000);advance(10_000_000)
   shot('discard-prompt');tap('YES');runtime['timers'].rescale(1_056_000_000)
  runtime['timers'].rescale(1_056_000_000)
  for _ in range(700):
   actual=[u(state()+MODES+4*i) for i in range(128)]
   current={q for q in panel.lit(worker._panel_latch or bytes(1024)) if q[0]>=40 and q[1]<12}
   if actual==expected and u(state()+2720)==0 and current==title:break
   advance(10_000_000)
  else:raise RuntimeError('Native GUI mode recall did not complete')
  runtime['timers'].rescale(132_000_000);advance(10_000_000)
  report['storage_clock_model']={'instructions_per_emulated_second':1_056_000_000,'reason':'Reduce modeled interrupt overhead during native filesystem/crypto work; normal 132M restored for panel gestures and notes','physical_timing_claim':False}
  require(bytes(worker._uc.mem_read(storage,0x1DB8C))==recorded,'Menu load changed exact pattern bytes');require(u(state())==mode,'Recalled mode not applied by native task')
  if args.tempo_ui:
   require(u(state()+RATE)==rate and u(state()+4484)==STEPS[rate],'Recalled rate not applied by native task')
  shot('recalled')
  if args.record:
   for _ in range(3):tap('NO')
   # Finish stock follow-up autosaves before starting recorded playback.
   quiet=0
   for _ in range(700):
    busy=u(state()+BUSY)
    desired=1_056_000_000 if busy else 132_000_000
    if runtime['timers'].sources[0].ips!=desired:runtime['timers'].rescale(desired)
    quiet=0 if busy else quiet+10_000_000
    if quiet>=264_000_000:break
    advance(10_000_000)
   else:raise RuntimeError('Stock load/autosave did not settle')
   for _ in range(3):tap('NO')
   recorder.recording=True
   first=len(recorder.frames);generated=len(outputs);tap('PLAY')
   def trigs():return [int.from_bytes(f[2+2*(args.track-1):4+2*(args.track-1)],'big')//256 for f in recorder.frames[first:] if int.from_bytes(f[0x22:0x24],'big')&(1<<(args.track-1))]
   while len(trigs())<8:advance(3_000_000)
   require(trigs()[:8]==expected_notes,f'Recorded replay pitches {trigs()[:8]}');require(len(outputs)==generated,'Playback recollected notes');tap('STOP');shot('recorded-replay')
   report['recorded_replay_pitches']=trigs()[:8]
  if args.cpu_extension:
   sequence=['arp_prepare','flex_prepare','stock','arp_commit','arp_cleanup']
   require(any(phase_trace[i:i+5]==sequence for i in range(len(phase_trace)-4)),'Shared save phase sequence not observed')
   report['native_save_phases']=phase_trace
  report['storage']={'saved_mode_vector':expected,'exact_pattern_bytes':len(recorded),'native_status':u(state()+STATUS),'native_callbacks':True,'host_arp_callbacks':False,'saved_rate':args.rate if args.tempo_ui else '1/16'}
  if flex_take:report['flex_take']['reloaded']=flex_take.reloaded()
  raw=b'ASOV'+__import__('struct').pack('>I',len(card.card.overlay))+b''.join(__import__('struct').pack('>I',k)+v for k,v in sorted(card.card.overlay.items()));(out/'card-overlay.bin').write_bytes(raw);card.close()
 if args.record and not args.storage:
  first=len(recorder.frames);generated=len(outputs);tap('PLAY')
  def trigs():return [int.from_bytes(f[2+2*(args.track-1):4+2*(args.track-1)],'big')//256 for f in recorder.frames[first:] if int.from_bytes(f[0x22:0x24],'big')&(1<<(args.track-1))]
  while len(trigs())<8:advance(3_000_000)
  require(trigs()[:8]==expected_notes,f'Recorded replay pitches {trigs()[:8]}');require(len(outputs)==generated,'Playback recollected notes');tap('STOP');shot('recorded-replay');report['recorded_replay_pitches']=trigs()[:8]
 report.update(status='passed',outputs=outputs,stock_notes=allnotes[notes_begin:],state_address=state(),instructions=worker.stats['instrs'],frames=len(recorder.frames),fault_pages=list(worker._faulted_pages),runtime_state=bytes(worker._uc.mem_read(state(),8192)).hex())
except BaseException as e:report.update(status='failed',error=f'{type(e).__name__}: {e}');raise
finally:
 if worker.ready.is_set():
  shot('last');report.update(ticks=recorder.ticks,outputs=outputs,stock_notes=allnotes,runtime_state=bytes(worker._uc.mem_read(state(),8192)).hex() if state() else '')
 from emu import snapshot
 from emu.checkpoint import save_longrun
 save_longrun(runtime['machine'],runtime['events'],runtime['timers'],str(out/'last.snap'))
 worker.stop_flag.set();worker.pause.clear();worker.join(30);write_json(out/'native.json',report)
 (out/'control.dtfr').write_bytes(b'DTFR'+__import__('struct').pack('<II',1,len(recorder.frames))+b''.join(__import__('struct').pack('<I',len(f))+f for f in recorder.frames))
