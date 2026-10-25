"""Execute native journal instructions against the independent Python codec."""
import hashlib,struct,unittest
from pathlib import Path
try:
 import unicorn as u
 from unicorn import m68k_const as r
except ImportError:u=None
from lab import arp_firmware as fw
from lab import arp_firmware_storage as st
from lab.arp_persistence import encode,decode,ModeJournal

@unittest.skipIf(u is None,'Configured Unicorn runtime required')
class NativeJournal(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  path=Path(__file__).resolve().parents[1]/'.local/fixture/sections/section_3_MAIN_OS.bin'
  if not path.is_file():raise unittest.SkipTest('Private stock image required')
  cls.image,cls.meta=fw.patch_cpu(path.read_bytes())
 def setUp(self):
  self.cpu=u.Uc(u.UC_ARCH_M68K,u.UC_MODE_BIG_ENDIAN);self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
  self.cpu.mem_map(0x40000000,0x400000);self.cpu.mem_write(0x40000400,self.image);self.cpu.mem_map(0x44d2e000,0x2000);self.cpu.mem_map(0x60000000,0x10000);self.p=self.meta['locations'];self.state=0x60002000;self.files={};self.fault=False
  self.cpu.mem_write(self.p['pointer'],struct.pack('>I',self.state));self.cpu.reg_write(r.UC_M68K_REG_SR,0x2700)
  self.project=b'authenticated serialized project oracle';self.hash=hashlib.sha256(self.project).digest();self.cpu.mem_write(self.state+st.HASH,self.hash);self.put(st.SLOT,7)
  # Native file wrapper endpoints only. The journal and actual OS SHA execute.
  for name,fn in (('file_read',self.read),('file_write',self.write)):
   def hook(cpu,pc,size,data,fn=fn):
    sp=cpu.reg_read(r.UC_M68K_REG_A7);args=[self.u32(sp+i) for i in (4,8)];val=fn(*args);ret=self.u32(sp);cpu.reg_write(r.UC_M68K_REG_D0,val&0xffffffff);cpu.reg_write(r.UC_M68K_REG_A7,sp+4);cpu.reg_write(r.UC_M68K_REG_PC,ret)
   handle=self.cpu.hook_add(u.UC_HOOK_CODE,hook,begin=self.p[name],end=self.p[name])
   if name=='file_read':self.read_hook=handle
 def u32(self,a):return int.from_bytes(self.cpu.mem_read(a,4),'big')
 def put(self,off,v):self.cpu.mem_write(self.state+off,struct.pack('>I',v&0xffffffff))
 def call(self,name,*args):
  sp=0x6000f000;stop=0x6000ffe0;self.cpu.mem_write(sp,struct.pack('>'+('I'*(len(args)+1)),stop,*args));self.cpu.reg_write(r.UC_M68K_REG_A7,sp)
  self.cpu.emu_start(self.p[name],stop,count=1_000_000);self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC),stop);self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7),sp+4);return self.cpu.reg_read(r.UC_M68K_REG_D0)
 def read(self,record,bank):
  b=self.files.get(bank)
  if b is None:return 0
  if len(b)!=210:return -1
  self.cpu.mem_write(record,b);return 1
 def write(self,*_):
  if self.fault:return 0
  bank=65+self.u32(self.state+st.TARGET);self.files[bank]=bytes(self.cpu.mem_read(self.state+st.RECORD,210));return 1
 def modes(self):return [self.u32(self.state+fw.MODES+4*i) for i in range(128)]
 def test_native_journal_codec_and_inactive_bank_failure(self):
  modes=[i%4 for i in range(128)]
  self.cpu.mem_write(self.state+fw.SAVE_MODES,struct.pack('>128I',*modes));self.assertEqual(self.call('journal',1),1)
  self.assertEqual(self.files[65],encode(7,1,self.project,modes));self.assertEqual(self.call('journal',0),1);self.assertEqual(self.modes(),modes)
  changed=[3]*128;self.cpu.mem_write(self.state+fw.SAVE_MODES,struct.pack('>128I',*changed));self.assertEqual(self.call('journal',1),1);self.assertEqual(self.files[66],encode(7,2,self.project,changed))
  self.fault=True;self.assertEqual(self.call('journal',1),0);self.assertEqual(self.files[66],encode(7,2,self.project,changed));self.assertEqual(self.call('journal',0),1);self.assertEqual(self.modes(),changed)
 def test_missing_corrupt_wrong_project_conflict_and_64bit_sequence(self):
  modes=[1]*128
  self.assertEqual(self.call('journal',0),0)
  self.files[65]=encode(7,1,self.project,modes)[:-1]+b'X';self.assertEqual(self.call('journal',0),0)
  self.files[65]=encode(7,1,b'wrong project',modes);self.assertEqual(self.call('journal',0),0)
  self.files[65]=encode(7,(1<<32)-1,self.project,modes);self.assertEqual(self.call('journal',1),1);self.assertEqual(decode(self.files[66],7,self.project)['sequence'],1<<32)
  self.files={65:encode(7,8,self.project,modes),66:encode(7,8,self.project,[2]*128)};self.assertEqual(self.call('journal',0),0)
  self.files={65:b'unknown',66:b'unknown'};self.assertEqual(self.call('journal',1),0);self.assertEqual(self.files,{65:b'unknown',66:b'unknown'})
 def test_native_path_matches_existing_companions(self):
  result=self.call('path',65);raw=bytes(self.cpu.mem_read(result,40)).split(b'\0')[0].decode()
  self.assertEqual(raw,ModeJournal(None).paths(7,self.project)[0])
 def test_relocated_mode_vectors_and_allocation_failure(self):
  expected={1:[60,64,67,60,64,67,60,64],2:[67,64,60,67,64,60,67,64],3:[64,64,60,60,60,64,67,60]}
  for mode,notes in expected.items():
   self.call('init',self.state,0,mode)
   for pitch in (67,64,60):self.call('press',self.state,pitch,100)
   self.call('clock',self.state,0,1);actual=[]
   for step in range(1,9):
    flags=self.call('clock',self.state,step*7059,1);self.assertTrue(flags&2);actual.append(self.u32(self.state+44))
   self.assertEqual(actual,notes)
  self.cpu.mem_write(self.p['pointer'],bytes(4))
  def fail(cpu,pc,size,data):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);ret=self.u32(sp);cpu.reg_write(r.UC_M68K_REG_D0,0);cpu.reg_write(r.UC_M68K_REG_A7,sp+4);cpu.reg_write(r.UC_M68K_REG_PC,ret)
  self.cpu.hook_add(u.UC_HOOK_CODE,fail,begin=0x4011E674,end=0x4011E674)
  self.call('ensure');self.assertEqual(self.u32(self.p['pointer']),0)
 def test_native_file_lookup_passes_complete_root_name(self):
  # Execute the actual read wrapper up to the stock lookup API. This catches
  # pointer arithmetic that endpoint-only journal mocks cannot exercise.
  self.cpu.hook_del(self.read_hook)
  seen=[]
  def lookup(cpu,pc,size,data):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);name=self.u32(sp+8);text=bytes(cpu.mem_read(name,40)).split(b'\0')[0].decode();seen.append((self.u32(sp+4),text,self.u32(sp+12)))
   cpu.reg_write(r.UC_M68K_REG_D0,0);cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  self.cpu.hook_add(u.UC_HOOK_CODE,lookup,begin=0x401572E0,end=0x401572E0)
  self.assertEqual(self.call('file_read',self.state+st.B0,65),0)
  self.assertEqual(seen,[(2,ModeJournal(None).paths(7,self.project)[0][1:],self.state+st.FOUND)])
 def test_owned_release_is_consumed_while_storage_is_busy(self):
  self.call('init',self.state,0,1);self.call('press',self.state,60,100);self.put(fw.KEYS,61);self.put(fw.BUSY,1)
  self.call('panic',self.state)
  event=0x60009000;self.cpu.mem_write(event,struct.pack('>5I',0,0,0,25,0x10))
  self.assertEqual(self.call('input',0,event,0),1);self.assertEqual(self.u32(self.state+32),0);self.assertEqual(self.u32(self.state+fw.KEYS),0)
 def test_function_play_does_not_start_arp_but_record_play_does(self):
  self.call('init',self.state,0,1);event=0x60009000;self.cpu.mem_write(event,struct.pack('>5I',0,0,0,20,3));held=[1]
  def key_down(cpu,pc,size,data):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);self.assertEqual(self.u32(sp+4),17);cpu.reg_write(r.UC_M68K_REG_D0,held[0]);cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  self.cpu.hook_add(u.UC_HOOK_CODE,key_down,begin=0x4011DE70,end=0x4011DE70)
  self.call('input',0,event,0);self.assertEqual(self.u32(self.state+fw.PLAY),0)
  held[0]=0;self.call('input',0,event,0);self.assertEqual(self.u32(self.state+fw.PLAY),1)
 def test_sync_uses_restored_stock_keyboard_setting_and_closes_on_exit(self):
  # The real stock getter reads offset 0x38 through the settings vtable.
  # Mock only object selection; execute that original getter and native sync.
  obj=0x60008000;vtable=0x60008100;data=0x60008200;getter=0x60008300
  self.cpu.mem_write(obj,struct.pack('>I',vtable));self.cpu.mem_write(vtable+0x28,struct.pack('>I',getter))
  self.cpu.mem_write(getter,bytes.fromhex('203c')+struct.pack('>I',data)+bytes.fromhex('4e75'))
  def stub(value):
   def run(cpu,pc,size,extra):
    sp=cpu.reg_read(r.UC_M68K_REG_A7);cpu.reg_write(r.UC_M68K_REG_D0,value);cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
   return run
  for pc,value in ((0x401988A2,0x60008400),(0x40041D18,obj),(0x4004ABE8,0),(0x40199680,0x60008500),(0x400F541C,0)):
   self.cpu.hook_add(u.UC_HOOK_CODE,stub(value),begin=pc,end=pc)
  self.call('init',self.state,0,1);self.put(fw.TRACK,0);self.put(fw.PATTERN,0)
  self.cpu.mem_write(data+0x38,struct.pack('>I',1));self.put(fw.KEYBOARD,0)
  self.call('sync');self.assertEqual(self.u32(self.state+fw.KEYBOARD),1)
  self.call('press',self.state,60,100)
  self.cpu.mem_write(data+0x38,bytes(4));self.call('sync')
  self.assertEqual(self.u32(self.state+fw.KEYBOARD),0);self.assertEqual(self.u32(self.state+36),0)
  self.assertEqual(self.u32(self.state+32),1) # Consumed release still owned.
  self.assertEqual(self.u32(self.state+20),0xffffffff)
 def test_decoder_binds_slot_zero_and_rejects_unarmed_or_wrong_destination(self):
  node=0x4317B694;self.cpu.mem_map(0x4317b000,4096);self.cpu.mem_write(node,struct.pack('>III',0,0x01000000,99))
  dest=0x60008000;self.put(st.SLOT,0);self.put(st.DEST,dest)
  def run(loading,target,d3):
   self.put(st.LOADING,loading);self.put(st.BUFFER,0);sp=0x6000f000;self.cpu.mem_write(sp,struct.pack('>4I',0x6000ffe0,target,node+12,0));self.cpu.reg_write(r.UC_M68K_REG_A7,sp);self.cpu.reg_write(r.UC_M68K_REG_D3,d3)
   self.cpu.emu_start(self.p['decoder'],0x400DF7F6+8,count=2000);self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC),0x400DF7F6+8);return self.u32(self.state+st.BUFFER)
  self.assertEqual(run(1,dest,0),node+12)
  self.assertEqual(run(0,dest,1),0)
  self.assertEqual(run(1,dest+4,1),0)
 def test_optional_d1_readouts_are_native_and_do_not_service_the_arp(self):
  stock=(Path(__file__).resolve().parents[1]/'.local/fixture/sections/section_3_MAIN_OS.bin').read_bytes()
  default,_=fw.patch_cpu(stock)
  self.assertEqual(hashlib.sha256(default).hexdigest(),'5219513604b63106275f7796cb7e798a1b458693f1e9491bfaea6ea4c1f4f310')
  image,meta=fw.patch_cpu(stock,diagnostics=True);self.p=meta['locations']
  self.cpu=u.Uc(u.UC_ARCH_M68K,u.UC_MODE_BIG_ENDIAN);self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
  self.cpu.mem_map(0x40000000,0x400000);self.cpu.mem_write(0x40000400,image)
  self.cpu.mem_map(0x44d2e000,0x2000);self.cpu.mem_map(0x60000000,0x10000)
  self.cpu.mem_write(self.p['pointer'],struct.pack('>I',self.state));self.cpu.reg_write(r.UC_M68K_REG_SR,0x2700)
  for off,value in ((0,1),(36,3),(fw.PLAY,1),(fw.KEYBOARD,1),(fw.DIAG_CLOCK,1),(fw.DIAG_NOTES,8),(fw.DIAG_API,3),(fw.DIAG_CALLER,0x4005C666)):self.put(off,value)
  self.cpu.reg_write(r.UC_M68K_REG_A2,self.state);self.cpu.reg_write(r.UC_M68K_REG_A3,0x12345678)
  before=bytes(self.cpu.mem_read(self.state,fw.DIAG_TOP));seen=[]
  def render(cpu,pc,size,extra):
   sp=cpu.reg_read(r.UC_M68K_REG_A7);text=self.u32(sp+24)
   seen.append((bytes(cpu.mem_read(text,16)).split(b'\0')[0].decode(),self.u32(sp+12),self.u32(sp+16),self.u32(sp+4)))
   cpu.reg_write(r.UC_M68K_REG_PC,self.u32(sp));cpu.reg_write(r.UC_M68K_REG_A7,sp+4)
  self.cpu.hook_add(u.UC_HOOK_CODE,render,begin=0x40113AE8,end=0x40113AE8)
  def forbidden(*_):self.fail('Drawing diagnostics must not clock or emit notes')
  for pc in (fw.ON,fw.OFF,self.p['clock'],self.p['press']):self.cpu.hook_add(u.UC_HOOK_CODE,forbidden,begin=pc,end=pc)
  self.call('diag_draw')
  self.assertEqual(seen,[('H3P1',80,27,0x12345678),('UPN08',80,12,0x12345678),('K1C1',80,2,0x12345678),('D1A03',112,54,0x12345678),('R4005',112,44,0x12345678),('C666',112,35,0x12345678)])
  self.assertEqual(bytes(self.cpu.mem_read(self.state,fw.DIAG_TOP)),before)
