"""Exact OS1.16 native instructions, checked against rational timing and codecs."""
import hashlib,struct,unittest
from pathlib import Path
import test_arp_firmware as legacy
u,r=legacy.u,legacy.r
from lab import arp_firmware as fw,arp_firmware_storage as st,arp_tempo as t
from lab.arp_persistence import encode as old_encode
from lab.arp_tempo_persistence import encode,decode,RateJournal

@unittest.skipIf(u is None,'Configured Unicorn required')
class NativeTempo(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.stock=(Path(__file__).resolve().parents[1]/'.local/fixture/sections/section_3_MAIN_OS.bin').read_bytes()
  cls.image,cls.meta=fw.patch_cpu(cls.stock,tempo_ui=True)
 setUp=legacy.NativeJournal.setUp
 u32=legacy.NativeJournal.u32
 put=legacy.NativeJournal.put
 call=legacy.NativeJournal.call
 read=legacy.NativeJournal.read
 write=legacy.NativeJournal.write
 modes=legacy.NativeJournal.modes
 def start(self,bpm=12240,rate=2,mode=1,tick=0):
  self.call('init',self.state,tick,mode);self.put(t.RATE,-1);self.call('rate',self.state,rate);self.put(t.TEMPO,bpm)
  for note in (67,64,60):self.call('press',self.state,note,100)
  self.call('clock',self.state,tick,1)
 def test_rational_tempo_rate_and_mode_grid(self):
  vectors={1:[60,64,67,60,64,67,60,64],2:[67,64,60,67,64,60,67,64],3:[64,64,60,60,60,64,67,60]}
  for bpm in (3600,7200,10800,12240,14400,15300,21600,28800,36000):
   for rate,step in enumerate(t.STEPS):
    for mode,expected in vectors.items():
     with self.subTest(tempo120=bpm,rate=rate,mode=mode):
      self.start(bpm,rate,mode);events={};ons=[];offs=[];last=0
      for n in range(1,9):
       onset=(n*step+bpm-1)//bpm;gate=onset+(step//2+bpm-1)//bpm
       for x in (onset-1,onset,gate-1,gate):events[x]=None
      for tick in sorted(events):
       while tick-last>24000:
        last+=24000;self.assertEqual(self.call('clock',self.state,last,1),0)
       flags=self.call('clock',self.state,tick,1);last=tick
       if flags&2:ons.append((tick,self.u32(self.state+44)))
       if flags&1:offs.append((tick,self.u32(self.state+40)))
      self.assertEqual([n for _,n in ons],expected)
      self.assertEqual([x for x,_ in ons],[(n*step+bpm-1)//bpm for n in range(1,9)])
      self.assertEqual([x for x,_ in offs],[x+(step//2+bpm-1)//bpm for x,_ in ons])
      self.assertEqual([n for _,n in offs],expected)
 def test_live_tempo_fractional_gate_rate_edit_and_invalid_clock(self):
  self.start(14400);self.call('clock',self.state,3000,1);self.put(t.TEMPO,7200)
  self.assertEqual(self.call('clock',self.state,8999,1),0)
  self.assertEqual(self.call('clock',self.state,9000,1),2)
  self.put(t.TEMPO,15300)
  self.assertEqual(self.call('clock',self.state,11823,1),0)
  self.assertEqual(self.call('clock',self.state,11824,1),1)
  self.call('clock',self.state,14648,1)
  before=bytes(self.cpu.mem_read(self.state+64,2048));self.assertEqual(self.call('rate',self.state,3),1)
  self.assertEqual(bytes(self.cpu.mem_read(self.state+64,2048)),before);self.assertEqual(self.u32(self.state+36),3);self.assertEqual(self.u32(self.state+12),0)
  self.assertEqual(self.call('rate',self.state,4),0xffffffff)
  self.put(t.TEMPO,0);self.call('clock',self.state,15000,1);self.assertEqual(self.u32(self.state+36),0)
  self.start();self.call('clock',self.state,48001,1);self.assertEqual(self.u32(self.state+36),0)
  self.start(tick=0xfffff000);self.assertEqual(self.call('clock',self.state,(0xfffff000+7059)&0xffffffff,1),2)
  self.start(mode=0);self.assertEqual(self.call('clock',self.state,20000,1),0)
 def test_long_fractional_phase_and_bounded_late_service(self):
  self.start(15300,3)
  for n in range(1,4097):
   tick=(n*t.STEPS[3]+15299)//15300
   self.assertTrue(self.call('clock',self.state,tick,1)&2)
   self.assertEqual(self.u32(self.state+12),tick*15300-n*t.STEPS[3])
  # Many missed steps produce only one output, with modulo phase retained.
  flags=self.call('clock',self.state,tick+48000,1);self.assertEqual(flags,3)
  self.assertLess(self.u32(self.state+12),t.STEPS[3])
 def stub(self,pc,value=0):
  def run(cpu,pc,size,data):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);cpu.reg_write(r.UC_M68K_REG_D0,value);cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  return self.cpu.hook_add(u.UC_HOOK_CODE,run,begin=pc,end=pc)
 def test_allocation_defaults_and_pattern_rate_recall(self):
  self.cpu.mem_map(0x40966000,4096);self.cpu.mem_write(self.p['pointer'],bytes(4));self.stub(0x4011E674,self.state)
  self.cpu.mem_write(self.state+fw.SIZE,b'BOUNDARY');self.call('ensure')
  self.assertEqual(self.u32(self.p['pointer']),self.state);self.assertEqual(self.modes(),[8]*128)
  self.assertEqual(self.u32(self.state+t.RATE),2);self.assertEqual(self.u32(self.state+t.FOCUS),0)
  self.assertEqual(bytes(self.cpu.mem_read(self.state+fw.SIZE,8)),b'BOUNDARY')
  for pc,value in ((0x401988A2,0x60008400),(0x40041D18,0x60008000),(0x4004AF88,1),(0x40199680,0x60008500)):
   self.stub(pc,value)
  track=self.stub(0x4004ABE8,0);pattern=self.stub(0x400F541C,0)
  self.put(fw.MODES,14);self.call('sync');self.assertEqual(self.u32(self.state),2);self.assertEqual(self.u32(self.state+t.RATE),3)
  self.cpu.hook_del(track);track=self.stub(0x4004ABE8,1);self.call('sync');self.assertEqual(self.u32(self.state),0)
  self.cpu.hook_del(track);self.stub(0x4004ABE8,0);self.cpu.hook_del(pattern);self.stub(0x400F541C,1)
  self.put(fw.MODES+4,1);self.call('sync');self.assertEqual(self.u32(self.state),1);self.assertEqual(self.u32(self.state+t.RATE),0)
 def test_original_getter_and_g_focus_guards(self):
  for tempo in (3600,12240,15300,36000):
   self.cpu.mem_write(0x402b62bc,struct.pack('>I',tempo));self.p['stock_tempo']=t.TEMPO_GET
   self.assertEqual(self.call('stock_tempo'),tempo)
  func_hook=self.stub(0x4011DE70);self.stub(0x4011AE46);event=0x60009000;view=0x60008000
  self.cpu.mem_write(view+t.G_MOTION,struct.pack('>5I',1,2,3,4,5))
  def focus(flags=1,main=0,key=47):
   self.cpu.mem_write(event,struct.pack('>5I',0,0,0,key,flags));return self.call('rate_focus',view,event,main)
  self.assertEqual(focus(),0);self.assertEqual(self.u32(self.state+t.FOCUS),1)
  self.assertEqual(bytes(self.cpu.mem_read(view+t.G_MOTION,20)),struct.pack('>5I',1,2,0,0,5))
  for flags in (16,9,0):self.assertEqual(focus(flags),0);self.assertEqual(self.u32(self.state+t.FOCUS),1)
  self.assertEqual(focus(main=1),0);self.assertEqual(focus(key=46),0)
  self.put(fw.TRACK,1);self.assertEqual(focus(),0);self.put(fw.TRACK,0)
  self.assertEqual(focus(),0);self.assertEqual(self.u32(self.state+t.FOCUS),0)
  self.put(fw.BUSY,1);self.assertEqual(focus(),0);self.assertEqual(self.u32(self.state+t.FOCUS),0)
  self.put(fw.BUSY,0);self.cpu.hook_del(func_hook);self.stub(0x4011DE70,1);self.assertEqual(focus(),0)
 def knob(self):
  self.start();self.stub(self.p['sync']);self.stub(0x4011DE70);self.stub(0x4005AA8E,300)
  # Actual ready-state stock enum resource, normal /6 and pushed /6 *4.
  self.cpu.mem_write(t.ENUM_CONFIG,struct.pack('>7I',0,0,6,1,0,6,4))
  self.p.update(stock_scale=t.ENCODER_SCALE,stock_decay=0x40111940)
  self.put(fw.PATTERN,0);self.put(fw.MODES,9);view=0x60008000;event=0x60009000
  def turn(delta):
   self.cpu.mem_write(event,struct.pack('>6I',0,0,0,7,delta&0xffffffff,0));return self.call('encoder',view,event)
  return view,event,turn
 def test_encoder_small_motion_is_filtered_without_redraw_or_note_change(self):
  view,event,turn=self.knob();refresh=[]
  def redraw(cpu,pc,size,data):
   refresh.append(pc);sp=cpu.reg_read(r.UC_M68K_REG_A7);cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  self.cpu.hook_add(u.UC_HOOK_CODE,redraw,begin=0x4011AE46,end=0x4011AE46)
  self.put(t.FOCUS,1);self.put(fw.MODES,9);before=bytes(self.cpu.mem_read(self.state,2120))
  for _ in range(5):self.assertEqual(turn(1),1)
  self.assertEqual(self.u32(self.state+t.RATE),2);self.assertEqual(self.u32(self.state+fw.MODES),9)
  self.assertEqual(bytes(self.cpu.mem_read(self.state,2120)),before);self.assertEqual(refresh,[])
  turn(1);self.assertEqual(self.u32(self.state+t.RATE),3);self.assertEqual(self.u32(self.state+fw.MODES),13)
  self.assertEqual(self.u32(self.state+36),3);self.assertEqual(len(refresh),1)
  self.cpu.mem_write(view+t.G_MOTION,bytes(20));turn(96)
  self.assertEqual(len(refresh),1);self.assertEqual(self.u32(self.state+36),3)
  for offset in (fw.BUSY,fw.DIRECT):
   self.put(offset,1);lane=bytes(self.cpu.mem_read(view+t.G_MOTION,20));turn(-96)
   self.assertEqual(bytes(self.cpu.mem_read(view+t.G_MOTION,20)),lane);self.assertEqual(self.u32(self.state+t.RATE),3);self.put(offset,0)
  self.assertEqual(len(refresh),1)
 def test_encoder_matches_original_stock_scaler_for_modes_rates_and_reversals(self):
  view,event,turn=self.knob();self.stub(0x4011AE46);oracle=0x60008400
  for focus in (0,1):
   self.put(t.FOCUS,focus);off=t.RATE if focus else 0;expected=self.u32(self.state+off)
   self.cpu.mem_write(view+t.ENCODER_STATE,bytes(0x100));self.cpu.mem_write(oracle,bytes(0x100))
   for delta in [1]*7+[-1]*7+[12,0,96,96,-96,-96]+[1,-1]*8+[6]*8:
    self.cpu.mem_write(event,struct.pack('>6I',0,0,0,7,delta&0xffffffff,0))
    scaled=self.call('stock_scale',oracle,event,t.ENUM_CONFIG)
    if scaled>=0x80000000:scaled-=2**32
    expected=max(0,min(3,expected+scaled));self.assertEqual(turn(delta),1)
    self.assertEqual(self.u32(self.state+off),expected)
    self.assertEqual(self.u32(self.state+fw.MODES),self.u32(self.state)|(self.u32(self.state+t.RATE)<<2))
    self.assertEqual(bytes(self.cpu.mem_read(view+t.ENCODER_STATE,0x100)),bytes(self.cpu.mem_read(oracle,0x100)))
    for acc in (view+t.ENCODER_STATE,oracle):self.call('stock_decay',acc,0)
 def test_native_v2_journal_legacy_import_migration_and_failures(self):
  legacy=[i%4 for i in range(128)];self.files[65]=old_encode(7,9,self.project,legacy)
  self.assertEqual(self.call('journal',0),1);self.assertEqual(self.modes(),[m|8 for m in legacy])
  packed=[i%16 for i in range(128)];self.cpu.mem_write(self.state+fw.SAVE_MODES,struct.pack('>128I',*packed))
  self.assertEqual(self.call('journal',1),1);self.assertEqual(self.files[66],encode(7,10,self.project,packed))
  self.assertEqual(self.call('journal',0),1);self.assertEqual(self.modes(),packed)
  self.fault=True;self.assertEqual(self.call('journal',1),0);self.assertEqual(self.call('journal',0),1);self.assertEqual(self.modes(),packed)
  self.files={65:b'unknown',66:b'unknown'};self.assertEqual(self.call('journal',1),0)
  self.assertEqual(self.files,{65:b'unknown',66:b'unknown'})
  for blob in (encode(7,1,b'wrong',packed),encode(7,1,self.project,packed)[:-1]+b'X'):
   self.files={65:blob};self.assertEqual(self.call('journal',0),0);self.assertIsNone(decode(blob,7,self.project))
  self.files={65:encode(7,1,self.project,packed),66:encode(7,1,self.project,[8]*128)};self.assertEqual(self.call('journal',0),0)
  self.files={65:old_encode(7,8,self.project,[1]*128),66:encode(7,8,self.project,[1]*128)};self.assertEqual(self.call('journal',0),0)
  self.files={65:encode(7,(1<<32)-1,self.project,packed)};self.fault=False;self.assertEqual(self.call('journal',1),1)
  self.assertEqual(decode(self.files[66],7,self.project)['sequence'],1<<32)
 def test_selector_draw_values_and_legacy_binary_preserved(self):
  with self.assertRaises(ValueError):fw.patch_cpu(self.stock,tempo_ui=True,diagnostics=True)
  self.assertEqual(bytes(self.cpu.mem_read(self.p['g_blank'],20)),struct.pack('>5I',0x4021CB40,17,17,1,self.p['g_pixels']))
  self.assertEqual(bytes(self.cpu.mem_read(self.p['g_pixels'],68)),bytes(68))
  self.assertEqual(hashlib.sha256(fw.patch_cpu(self.stock)[0]).hexdigest(),'5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310')
  seen=[]
  def render(cpu,pc,size,data):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);text=self.u32(sp+24);seen.append(bytes(cpu.mem_read(text,16)).split(b'\0')[0].decode())
   cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  self.cpu.hook_add(u.UC_HOOK_CODE,render,begin=0x40113AE8,end=0x40113AE8)
  self.cpu.reg_write(r.UC_M68K_REG_A2,self.state);self.put(0,1);self.put(t.RATE,3)
  self.call('rate_draw',0x12345678);self.assertEqual(seen,['ARP','UP','1/32'])
  seen.clear();self.put(t.FOCUS,1);self.call('rate_draw',0x12345678);self.assertEqual(seen,['RATE','1/32','UP'])
  seen.clear();self.put(fw.STATUS,-1);self.call('rate_draw',0x12345678);self.assertEqual(seen[0],'ARP!')

class HostRateJournal(unittest.TestCase):
 def test_defaults_v1_import_and_v2_bank_save(self):
  class Files:
   def __init__(self):self.data={}
   def read(self,p):return self.data.get(p)
   def write(self,p,b):self.data[p]=b
  files=Files();j=RateJournal(files);project=b'project'
  self.assertEqual(j.load(0,project),[8]*128)
  files.write(j.paths(0,project)[0],old_encode(0,1,project,[1]*128));self.assertEqual(j.load(0,project),[9]*128)
  j.save(0,project,[15]*128);self.assertEqual(j.load(0,project),[15]*128)
  paths=j.paths(0,project);files.write(paths[0],old_encode(0,8,project,[1]*128));files.write(paths[1],encode(0,8,project,[1]*128))
  self.assertEqual(j.load(0,project),[8]*128)
