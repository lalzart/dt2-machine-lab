//! Native CPU/DSP BUF workflow; external recorder model only, no host jobs.
mod buf_adapter;
use buf_adapter::NativeBuf;
use elektron_native_boot::{Emulator, RecorderPeer, sharc_peer::{DspEngine, SharedDsp, SharcPeer, Shared, DT2_IDLE}};
use sharc_native::Engine;
use sha2::{Digest,Sha256};
use std::{cell::RefCell, rc::Rc, fs, env, path::{Path,PathBuf}, time::Instant};
use serde_json::{Value,json};
fn read(p:impl AsRef<Path>)->Vec<u8>{fs::read(p).unwrap()}
fn save(p:impl AsRef<Path>,v:&Value){fs::write(p,serde_json::to_vec_pretty(v).unwrap()).unwrap()}
fn hash(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn unhex(s:&str)->Vec<u8>{(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect()}
fn source(n:i32)->Vec<u8>{(0..240_000).flat_map(|i|{let l=((i*(37+n*16))%20001-10000) as i16;let r=((i*(67+n*22))%16001-8000) as i16;[l.to_be_bytes(),r.to_be_bytes()].concat()}).collect()}
fn nonzero(pcm:&[u8])->bool{pcm.chunks_exact(2).any(|w|w!=[0,0])}
fn model(out:&Path){
 let o:Value=serde_json::from_slice(&read(out.join("model-oracle.json"))).unwrap();
 let mut p=RecorderPeer::new(unhex(o["source"].as_str().unwrap())).unwrap();p.begin(0xfffffff0).unwrap();
 let c:Vec<_>=[0xfffffff0,0xfffffff1,0x10,0x4000].into_iter().map(|t|p.count(t)).collect();assert_eq!(json!(c),o["counts"]);
 p.finish(0x4000);p.lock_depth=2;
 let d=[4u16.to_be_bytes().as_slice(),0u16.to_be_bytes().as_slice(),3u32.to_be_bytes().as_slice(),512u32.to_be_bytes().as_slice()].concat();
 assert_eq!(&p.response(&d,2048,0).unwrap(),&unhex(o["chunk"].as_str().unwrap()));
 let d=[3u16.to_be_bytes().as_slice(),0u16.to_be_bytes().as_slice(),3u32.to_be_bytes().as_slice(),99u32.to_be_bytes().as_slice()].concat();
 assert_eq!(&p.response(&d,16,0).unwrap(),&unhex(o["extrema"].as_str().unwrap()));
 assert!(p.response(&[0,99],0,0).is_err());assert!(p.response(&[0,4],2048,0).is_err());
 p.discard(0);assert!(!p.active&&p.completed.is_none()&&p.captured==0);
 assert!(p.response(&[0,4,0,0,0,0,0,0,0,0,0,1],2048,0).is_err());
 assert!(!nonzero(&vec![0;4096]),"zero-input qualification control");
 save(out.join("model.json"),&json!({"status":"passed","python_model_exact":true,"wrap_count_extrema_PCM":true,"zero_input_refused":true,"invalid_and_disconnected_readback_refused":true}));
}
fn descriptor(d:&SharedDsp,slot:u32)->Vec<u32>{(0..5).map(|i|{let e=d.0.borrow();e.peek((0x257810+slot*20+i*4) as u64,if i==4{1}else{4}).unwrap().unwrap()}).collect()}
fn readers(d:&SharedDsp)->Vec<(u32,u32)>{(0..32).map(|v|{let e=d.0.borrow();(e.peek((0x2412cc+v*0x1d8) as u64,4).unwrap().unwrap(),e.peek((0x2412cc+v*0x1d8+0x1b8) as u64,1).unwrap().unwrap())}).collect()}
#[derive(Default)]
struct Observed {publications:Vec<Value>,frames:usize,voice:Sha256,mix:Sha256,wire:Vec<u8>,last_slots:Vec<u16>, sounding:[u64;3],last_descriptor:Vec<u32>, tx:Vec<u8>, rx:Vec<u8>}
struct Observer {dsp:SharedDsp,ob:Rc<RefCell<Observed>>,clock_only:bool}
impl DspEngine for Observer {
 fn spi2_exchange(&mut self,b:&[u8])->Result<Vec<u8>,String>{
  let mut o=self.ob.borrow_mut();o.wire=b.to_vec();o.last_slots=[0,4,5].iter().map(|t|u16::from_be_bytes(b[0xe0+t*0x60..0xe2+t*0x60].try_into().unwrap())).collect();drop(o);let r=self.dsp.spi2_exchange(b)?;let mut o=self.ob.borrow_mut();o.tx.extend(b);o.rx.extend(&r);Ok(r)
 }
 fn lp0_ready(&self)->bool{self.dsp.lp0_ready()}
 fn lp0_transfer(&mut self,b:&[u8])->Result<(),String>{
  if self.clock_only {return self.dsp.lp0_transfer(b);}
  let before=descriptor(&self.dsp,300);let old=readers(&self.dsp);self.dsp.lp0_transfer(b)?;
  let after=descriptor(&self.dsp,300);assert_eq!(old,readers(&self.dsp),"LP0 changed active reader pointers");
  if before!=after && after[2]!=0 {
   let addresses=[0x8422b9c8u32.wrapping_add(before[0]),0x8422b9c8u32.wrapping_add(before[1])];
   let kept:Vec<_>=old.iter().enumerate().filter(|(_,p)|p.1!=0&&addresses.contains(&p.0)).map(|(i,_)|i).collect();
   let mut o=self.ob.borrow_mut();let frame=o.frames;o.publications.push(json!({"frame":frame,"descriptor":after,"retained":kept}));
  }Ok(())
 }
 fn step(&mut self,n:u32)->u32{self.dsp.step(n)}
 fn step_until_in(&mut self,n:u32,r:(u32,u32))->Option<u32>{self.dsp.step_until_in(n,r)}
 fn step_until_in_aligned(&mut self,n:u32,r:(u32,u32),c:u32,b:u64)->Option<u32>{self.dsp.step_until_in_aligned(n,r,c,b)}
 fn sport_block(&mut self)->Result<Option<Vec<u8>>,String>{
  if self.clock_only {self.ob.borrow_mut().frames+=1;return self.dsp.sport_block();}
  let desc=descriptor(&self.dsp,300);let rs=readers(&self.dsp);
  let mut o=self.ob.borrow_mut();
  if desc!=o.last_descriptor && desc[2]>0 {
   let kept:Vec<_>=rs.iter().enumerate().filter(|(_,r)|r.1!=0 && o.last_descriptor.len()==5 && [0x8422b9c8u32.wrapping_add(o.last_descriptor[0]),0x8422b9c8u32.wrapping_add(o.last_descriptor[1])].contains(&r.0)).map(|(i,_)|i).collect();
   let frame=o.frames;o.publications.push(json!({"frame":frame,"descriptor":desc,"retained":kept}));o.sounding=[0;3];
  }
  o.last_descriptor=desc;let e=self.dsp.0.borrow();
  for lane in 0..32 {for i in 0..64 {let w=e.peek((0x2412cc+lane*0x1d8+4+i*4) as u64,4).unwrap().unwrap();assert!(f32::from_bits(w).is_finite());o.voice.update(w.to_le_bytes());}}
  for i in 0..64 {let w=e.peek((0x25f180+i*4) as u64,4).unwrap().unwrap();assert!(f32::from_bits(w).is_finite());o.mix.update(w.to_le_bytes());}
  for (i,t) in [0,4,5].into_iter().enumerate(){
   let target=[300,300,312][i];
   let left=e.peek((0x257810+target*20) as u64,4).unwrap().unwrap();let right=e.peek((0x257814+target*20) as u64,4).unwrap().unwrap();
   let mut sounding=false;for l in [t*2,t*2+1]{
    let pointer=e.peek((0x2412cc+l*0x1d8) as u64,4).unwrap().unwrap();
    if o.last_slots[i]==target as u16 && [0x8422b9c8u32.wrapping_add(left),0x8422b9c8u32.wrapping_add(right)].contains(&pointer) && e.peek((0x2412cc+l*0x1d8+0x1b8) as u64,1).unwrap().unwrap()!=0 {
     sounding|=(0..64).any(|j|e.peek((0x2412cc+l*0x1d8+4+j*4) as u64,4).unwrap().unwrap()&0x7fffffff!=0);
    }
   }if sounding{o.sounding[i]+=1;}
  }
  o.frames+=1;drop(e);drop(o);self.dsp.sport_block()
 }
 fn pc(&self)->u32{self.dsp.pc()}
 fn halt_reason(&self)->Option<String>{self.dsp.halt_reason()}
 fn peek_word(&self,a:u32)->Option<u32>{self.dsp.peek_word(a)}
}
struct Flow {e:Emulator,dsp:SharedDsp,shared:Rc<RefCell<Shared>>,ob:Rc<RefCell<Observed>>,symbols:Value,out:PathBuf,start:Instant,heartbeat:Instant,checks:Vec<String>,cycles:Vec<Value>}
impl Flow {
 fn symbol(&self,m:&str,k:&str)->u32{self.symbols[m][k].as_u64().unwrap() as u32}
 fn val(&mut self,m:&str,k:&str)->u32{let base=self.symbol(m,"STATE");let off=self.symbol(m,k);self.e.peek32(base+off).unwrap()}
 fn absolute(&mut self,a:u32)->u32{self.e.peek32(a).unwrap()}
 fn step(&mut self,n:u64){let end=self.e.icount()+n;while self.e.icount()<end{
  let st=self.e.step_chunk((end-self.e.icount()).min(250_000) as u32).status;
  assert!(st.error.is_none(),"CPU error {:?}",st);assert!(self.shared.borrow().halted.is_none(),"DSP halt {:?}",self.shared.borrow().halted);
  assert!(self.start.elapsed().as_secs()<1500,"bounded native flow timeout");
  if self.heartbeat.elapsed().as_secs()>=30 {
   let step=self.absolute(0x43164f98)>>16;let phase=self.val("nb","PHASE");let starts=self.val("nb","STARTS");let uses=self.val("nb","USES");
   eprintln!("progress: CPU={} step={} phase={} starts={} uses={} frames={}",self.e.icount(),step,phase,starts,uses,self.ob.borrow().frames);self.heartbeat=Instant::now();
  }
 }}
 fn wait(&mut self,ms:u64){self.step(132_000*ms)}
 fn edge(&mut self,k:u8,on:bool,ms:u64){self.e.button(k,on).unwrap();self.wait(ms);}
 fn tap(&mut self,k:u8){self.edge(k,true,40);self.edge(k,false,40);}
 fn chord(&mut self,m:u8,k:u8){self.edge(m,true,90);self.tap(k);self.edge(m,false,90);}
 fn until(&mut self,label:&str,mut pred:impl FnMut(&mut Self)->bool,max_ms:u64){
  for _ in 0..max_ms.div_ceil(50){if pred(self){eprintln!("{label}: phase={} starts={} uses={} frames={}",self.val("nb","PHASE"),self.val("nb","STARTS"),self.val("nb","USES"),self.ob.borrow().frames);return;}self.wait(50);}
  self.screen("failure");panic!("{label}: timeout phase={} result={:#x} recorder events={:?}",self.val("nb","PHASE"),self.val("nb","RESULT"),self.e.recorder_peer().unwrap().events);
 }
 fn check(&mut self,label:&str,v:bool){assert!(v,"{label}");self.checks.push(label.into());}
 fn slots(&mut self)->Vec<u16>{let kit=self.absolute(0x80004704);(0..16).map(|t|u16::from_be_bytes(self.e.peek(kit+t*0x450+0x80,2).unwrap().try_into().unwrap())).collect()}
 fn screen(&mut self,n:&str){if let Some((_,f))=self.e.current_frame(){fs::write(self.out.join(format!("{n}.frame")),f).unwrap();}}
 fn sketch(&mut self,open:bool){
  let at=self.symbol("s","STATE")+self.symbol("s","VIEW");
  if (self.absolute(at)!=0)!=open {
   self.tap(24);
   self.wait(40);
  }
  if (self.absolute(at)!=0)!=open {
   self.screen("view-state-failure");
   panic!("Sketch view ownership did not reach {open}");
  }
 }
 fn choose_len(&mut self,v:u32){self.sketch(true);for _ in 0..20{
  let view=self.absolute(self.symbol("s","STATE")+self.symbol("s","VIEW"));let wrap=self.absolute(view+self.symbol("s","SETTINGS"));let inner=self.absolute(wrap+16);let cur=self.absolute(inner+0x1ba);
  if cur==v{return;}self.e.turn(4,if cur<v{10}else{-10}).unwrap();self.wait(90);
 }self.screen("length-failure");let view=self.absolute(self.symbol("s","STATE")+self.symbol("s","VIEW"));panic!("LEN selection failed with Sketch view {view:#x}");}
 fn choose_slot(&mut self,track:u32,target:u16){
  self.sketch(false);self.chord(16,25+track as u8);self.tap(2);self.tap(44);
  let cur=self.slots()[track as usize];for _ in 0..((target/128+8-cur/128)%8){self.tap(15);}
  for _ in 0..(target%128).abs_diff(cur%128) {let key=if target%128>cur%128{14}else{11};self.edge(key,true,20);self.edge(key,false,20);}
  self.tap(10);let v=self.slots()[track as usize]==target;self.check(&format!("native sample selector T{}",track+1),v);
 }
 fn dump_pages(&self,n:&str){let mut b=vec![];for(tag,data,head)in &self.e.recorder_peer().unwrap().pages{b.extend(tag.to_be_bytes());b.extend(head.to_be_bytes());b.extend(data);}fs::write(self.out.join(n),b).unwrap();}
 fn capture(&mut self,number:i32){
  self.capture_before(number,5);
 }
 fn capture_before(&mut self,number:i32,last_arm_step:u32){
  self.e.recorder_peer_mut().unwrap().source=source(number);self.choose_len(4);
  self.until("arm away from bar",|f|(3..=last_arm_step).contains(&(f.absolute(0x43164f98)>>16)),8000);
  let assigned=self.slots();let uses=self.val("nb","USES");self.chord(17,24);
  let admitted=self.val("nb","PHASE")==1&&self.val("nb","DEST")==1;self.check("Sketch ARM admitted",admitted);
  self.until("capture starts",|f|f.val("nb","PHASE")==2,8000);
  self.until("capture publishes",|f|f.val("nb","USES")==uses+1&&f.val("nb","PHASE")==0,10000);
  let same=self.slots()==assigned;self.check("capture preserves shared assignments",same);
  let state=self.symbol("w","STATE");let len=self.absolute(state+28);let data=self.e.recorder_peer().unwrap().completed.as_ref().unwrap().clone();
  assert!(nonzero(&data));assert_eq!(data.len(),len as usize*4);
  fs::write(self.out.join(format!("take-{number}.pcm")),&data).unwrap();
  let serial=self.val("nb","LAST_BAR")-self.val("nb","START_BAR");assert_eq!(serial,1);
  let pcm_hash=hash(&data);let tick=self.val("nb","PUBLISH_TICK");
  self.cycles.push(json!({"take":number,"frames":len,"pcm_sha256":pcm_hash,"native_bars":serial,"published_tick":tick}));
  self.screen(&format!("take-{number}-ready"));
 }
}
fn clock_slice(f:&mut Flow,out:&Path){
 let initial=f.slots();let ptr=f.absolute(0x4316501c);let header=f.e.peek(ptr+0x1db74,12).unwrap();
 assert_eq!(u16::from_be_bytes(header[..2].try_into().unwrap()),16);assert_eq!(header[5],0);assert_eq!(header[6],2);
 assert_eq!(f.val("nb","STARTS"),0);assert_eq!(f.val("nb","ARMS"),0);
 let mut steps=Vec::new();let mut previous=f.absolute(0x43164f98)>>16;let serial=f.val("nb","SERIAL");let mut last_serial=serial;
 for _ in 0..2000 {
  f.wait(5);let step=f.absolute(0x43164f98)>>16;let now=f.val("nb","SERIAL");
  assert_eq!(f.val("nb","VALID"),1);
  if step!=previous {
   assert_eq!(step,(previous+1)&15,"native clock skipped a step");
   assert_eq!(now,last_serial+u32::from(previous==0&&step==1),"bar receipt must occur at 0 -> 1");
   steps.push(json!({"previous":previous,"step":step,"serial":now,"icount":f.e.icount()}));previous=step;last_serial=now;
  }
  if now>=serial+2 {break;}
 }
 assert_eq!(last_serial,serial+2,"two real bar receipts required");
 // Negative control only: change one pattern scale byte. No host writes supply
 // transport, steps, VALID, receipts, timestamps or an admitted request.
 f.e.poke(ptr+0x1db7a,&[1]).unwrap();
 f.until("unsupported scale refused by IRQ",|f|f.val("nb","VALID")==0&&f.val("nb","CLOCK_DIAG")==5,2000);
 f.chord(17,24);assert_eq!(f.val("s","ARM_RESULT"),(-1_i32) as u32);
 assert_eq!(f.val("s","ARM_DIAG"),21);assert_eq!(f.val("s","ARM_DIAG_VALUE"),1);
 assert_eq!(f.val("nb","ARMS"),0);assert_eq!(f.val("nb","STARTS"),0);f.screen("clock-scale-refusal");
 f.e.poke(ptr+0x1db7a,&header[6..7]).unwrap();
 f.until("clock recovers from scale control",|f|f.val("nb","VALID")==1,2000);
 f.until("cancel ARM away from bar",|f|(3..=12).contains(&(f.absolute(0x43164f98)>>16)),8000);
 f.chord(17,24);assert_eq!(f.val("nb","PHASE"),1);assert_eq!(f.val("nb","STARTS"),0);
 f.tap(12);f.until("cancel before start",|f|f.val("nb","PHASE")==0&&f.val("nb","OWN")==0,4000);
 assert_eq!(f.val("nb","STARTS"),0);assert_eq!(f.val("nb","USES"),0);f.sketch(true);
 f.capture_before(1,12);f.wait(400);
 for (field,value) in [("ARMS",2),("STARTS",1),("STOPS",1),("USES",1),("CANCELS",1),("PHASE",0),("OWN",0)] {assert_eq!(f.val("nb",field),value,"{field}");}
 assert_eq!(f.slots(),initial);let dest=f.symbol("w","DEST");assert_eq!(f.absolute(dest),0);
 let meta:Value=serde_json::from_slice(&read(out.join("native-patches.json"))).unwrap();
 for g in meta["guards"].as_array().unwrap(){let at=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(f.e.peek(at,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()) {if w["kind"]=="code"||w["kind"]=="stock-trampoline" {let bytes=unhex(w["after"].as_str().unwrap());assert_eq!(f.e.peek(w["address"].as_u64().unwrap() as u32,bytes.len()).unwrap(),bytes);}}
 let sh=f.shared.borrow();assert_eq!(sh.missing_blocks,0);assert_eq!(sh.lp0_pending,0);assert!(sh.pcm.iter().all(|v|v.is_finite()));
 let d=descriptor(&f.dsp,300);assert!(d[2]>0);let events=&f.e.recorder_peer().unwrap().events;
 assert!(events.iter().any(|e|e.command==Some(4)));
 save(out.join("flow.json"),&json!({"status":"passed","scope":"Focused native clock/one-capture slice; modeled stereo recorder input; no voice/reuse/FREEZE qualification",
  "clock_fix":true,"pattern_header":header,"bar_edges":steps,"two_real_bar_receipts":true,"host_positive_clock_writes":false,
  "negative_control":"One test-only scale byte changed and restored; actual IRQ refusal and native FUNC+SONG diagnostic",
  "scale_refusal":{"label":"CLK SCALE 1","no_capture":true},"cancelled_before_start":true,"cycles":f.cycles,
  "recordings":1,"starts":1,"stops":1,"publications":1,"assignments_preserved":true,"normal_recorder_DEST":0,
  "descriptor":d,"CPU_canaries_and_code_intact":true,"missing_blocks":sh.missing_blocks,"LP0_units":sh.lp0_units,
  "events":events,"frames":f.ob.borrow().frames,"DSP_ROM_executed":false,"hardware":false}));
 eprintln!("focused native clock/capture passed in {:.1}s",f.start.elapsed().as_secs_f64());
}

fn flow(spec:&Value,out:&Path,repeat:bool){
 let dir=out.join(if repeat{"repeat"}else{"flow"});fs::create_dir(&dir).unwrap();let start=Instant::now();
 let input=out.join("reset-inputs");let mut eng=Engine::from_image(&read(input.join("image.bin"))).unwrap();eng.import(&read(input.join("reset.state"))).unwrap();
 for(k,v)in[(1,0),(4,1),(5,1),(9,1),(21,1),(22,1)]{assert_eq!(eng.set_option(k,v),0);}
 let mut idle=0;while eng.s.icount<400_000_000{eng.step(250_000);assert!(eng.halt.is_none());if (DT2_IDLE.range.0..DT2_IDLE.range.1).contains(&(eng.s.pc_sw as u32)){idle+=1;}else{idle=0;}if idle==8{break;}}
 assert_eq!(idle,8);eprintln!("DSP initialized in {} native instructions",eng.s.icount);for(k,v)in[(23,DT2_IDLE.head),(24,DT2_IDLE.range.0),(25,DT2_IDLE.range.1)]{assert_eq!(eng.set_option(k,v as i64),0);}
 let dsp=SharedDsp::new(eng);let ob=Rc::new(RefCell::new(Observed::default()));
 let engine=Observer{dsp:dsp.clone(),ob:ob.clone(),clock_only:spec["clock_only"]==true};let(mut peer,shared)=SharcPeer::new(engine,666_667);peer.set_idle_range(DT2_IDLE.range);peer.enable_sample_link();
 let card=elektron_native_boot::card_file::card_from_image(Path::new(spec["card"].as_str().unwrap())).unwrap();
 let mut e=Emulator::new_patched_with_reference(&read(spec["candidate"].as_str().unwrap()),Some(card),&read(spec["stock_syx"].as_str().unwrap())).unwrap();
 assert_eq!(e.icount(),0);assert_eq!(e.peek(0x40000400,read(spec["main"].as_str().unwrap()).len()).unwrap(),read(spec["main"].as_str().unwrap()));
 e.enable_ssi_diagnostic(96_000).unwrap();e.set_dspi2_peer(peer.boxed());e.set_recorder_peer(RecorderPeer::new(source(1)).unwrap()).unwrap();
 let symbols=serde_json::from_slice(&read(out.join("symbols.json"))).unwrap();
 let mut f=Flow{e,dsp,shared,ob,symbols,out:dir.clone(),start,heartbeat:Instant::now(),checks:vec![],cycles:vec![]};
 f.until("native application ready",|f|f.e.status().ready&&f.shared.borrow().lp0_units>0&&f.shared.borrow().lp0_pending==0,12000);f.wait(400);
 fs::write(dir.join("prepared.state"),f.dsp.export()).unwrap();
 f.tap(12);f.tap(19);f.chord(17,20);f.chord(17,22);f.tap(22);f.tap(12);f.tap(2);f.tap(19);f.tap(20);
 f.until("normal pattern clock",|f|f.val("nb","VALID")==1,8000);f.sketch(true);f.choose_len(4);
 if spec["clock_only"]==true {clock_slice(&mut f,out);return;}
 f.until("setup arm away from boundary",|f|f.absolute(0x43164f98)>>16==3,8000);f.chord(17,24);f.tap(12);
 f.until("pre-start cancellation",|f|f.val("nb","PHASE")==0&&f.val("nb","OWN")==0,4000);assert_eq!(f.val("nb","STARTS"),0);
 f.tap(21);f.tap(21);let w=f.symbol("w","STATE");assert_eq!(f.absolute(w+96),300);assert_eq!(f.absolute(0x405b1368+300*16+8),0);
 for track in [0u32,4,5]{
  f.chord(16,25+track as u8);f.tap(2);let kit=f.absolute(0x80004704);
  if f.e.peek(kit+track*0x450+0xd6,1).unwrap()!=[0]{f.chord(17,2);for _ in 0..8{f.tap(11);}f.tap(10);f.tap(10);}
  let kit=f.absolute(0x80004704);assert_eq!(f.e.peek(kit+track*0x450+0xd6,1).unwrap(),[0]);
 }
 for track in [0u32,4]{f.choose_slot(track,300);f.tap(19);for step in if track==0{vec![1,5,9,13]}else{vec![1,9]}{f.tap(24+step);}f.tap(19);}
 let initial=f.slots();f.tap(20);f.until("clock for A",|f|f.val("nb","VALID")==1,8000);f.sketch(true);f.capture(1);f.wait(1000);
 f.edge(24,true,850);f.edge(24,false,90);
 let q=f.symbol("q","STATE");f.until("native held SONG FREEZE",|f|f.absolute(q+32)==1,5000);f.wait(240);
 assert_eq!(f.absolute(q+12),312);assert_eq!(f.slots(),initial);
 let snap=f.symbol("n","SNAP");let frozen=f.e.peek(snap,64).unwrap();let frozen_descriptor=descriptor(&f.dsp,312);assert_eq!(frozen_descriptor,descriptor(&f.dsp,300));
 f.dump_pages("pages-A-frozen.bin");f.screen("frozen-A");
 f.choose_slot(5,312);f.tap(19);f.tap(25);f.tap(33);f.tap(19);f.sketch(true);f.capture(2);f.wait(1600);
 assert_eq!(f.e.peek(snap,64).unwrap(),frozen);assert_eq!(descriptor(&f.dsp,312),frozen_descriptor);assert_ne!(descriptor(&f.dsp,300),frozen_descriptor);
 let slots=f.slots();assert_eq!(slots[0],300);assert_eq!(slots[4],300);assert_eq!(slots[5],312);
 assert_eq!(f.val("nb","STARTS"),2);assert_eq!(f.val("nb","STOPS"),2);assert_eq!(f.val("nb","USES"),2);assert_eq!(f.absolute(q+36),1);
 f.dump_pages("pages-B.bin");let pages=f.e.recorder_peer().unwrap().pages.len();
 let generations=f.symbol("n","GEN");let registry=f.e.peek(generations,8*64).unwrap();let current_header=f.e.peek(0x405b1368+300*16,16).unwrap();
 // Cancel a third candidate while recording; no additional commit or pages.
 f.choose_len(6);f.until("cancel ARM away from bar",|f|f.absolute(0x43164f98)>>16==3,8000);f.chord(17,24);
 f.until("cancel candidate starts",|f|f.val("nb","STARTS")==3&&f.val("nb","PHASE")==2,8000);f.tap(12);
 f.until("active capture discarded",|f|f.val("nb","PHASE")==0&&f.val("nb","OWN")==0,4000);
 assert_eq!(f.val("nb","USES"),2);assert_eq!(f.val("nb","RESULT"),(-2i32) as u32);
 assert_eq!(f.e.peek(snap,64).unwrap(),frozen);assert_eq!(f.e.peek(generations,8*64).unwrap(),registry);assert_eq!(f.slots(),slots);
 assert_eq!(f.e.peek(0x405b1368+300*16,16).unwrap(),current_header);assert_eq!(f.e.recorder_peer().unwrap().pages.len(),pages);
 assert_eq!(f.absolute(f.symbol("w","DEST")),0);f.screen("cancelled");
 let meta:Value=serde_json::from_slice(&read(out.join("native-patches.json"))).unwrap();
 for g in meta["guards"].as_array().unwrap(){let at=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(f.e.peek(at,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()) {if w["kind"]=="code"||w["kind"]=="stock-trampoline"{let b=unhex(w["after"].as_str().unwrap());assert_eq!(f.e.peek(w["address"].as_u64().unwrap() as u32,b.len()).unwrap(),b);}}
 let sh=f.shared.borrow();assert_eq!(sh.missing_blocks,0);assert_eq!(sh.lp0_pending,0);assert!(sh.pcm.iter().all(|v|v.is_finite()));assert!(sh.raw.iter().any(|v|*v!=0));
 let ring:Vec<u8>=sh.raw.iter().flat_map(|v|v.to_le_bytes()).collect();fs::write(dir.join("final-ring.q31"),&ring).unwrap();
 let o=f.ob.borrow();fs::write(dir.join("wire.bin"),&o.wire).unwrap();
 fs::write(dir.join("wire-frames.bin"),&o.tx).unwrap();fs::write(dir.join("reply-frames.bin"),&o.rx).unwrap();
 let events=&f.e.recorder_peer().unwrap().events;assert!(events.iter().any(|e|e.command==Some(4)));assert!(o.sounding.iter().all(|&v|v>0));assert_eq!(o.publications.len(),2);assert!(!o.publications[1]["retained"].as_array().unwrap().is_empty(),"B publication did not overlap A readers");
 let report=json!({"status":"passed","checks":f.checks,"cycles":f.cycles,"starts":3,"publications":o.publications,"freeze_jobs":1,"cancelled_active_candidate":true,"assignments":slots,"frames":o.frames,"wire_sha256":hash(&o.tx),"reply_sha256":hash(&o.rx),"LP0_units":sh.lp0_units,"voice_sha256":format!("{:x}",o.voice.clone().finalize()),"master_mix_sha256":format!("{:x}",o.mix.clone().finalize()),"final_ring_sha256":hash(&ring),"sounding_blocks":o.sounding,"events":events,"CPU_canaries_and_code_intact":true,"source_model":"stereo PCM16, one sample tick per frame; normalization acknowledged without gain pass","hardware":false});
 save(out.join(if repeat{"repeat.json"}else{"flow.json"}),&report);
 if repeat {let first:Value=serde_json::from_slice(&read(out.join("flow.json"))).unwrap();assert_eq!(report,first,"native workflow exact repeat");}
 eprintln!("native flow completed {} frames in {:.1}s",o.frames,start.elapsed().as_secs_f64());
}
fn replay(out:&Path){
 let image=read(out.join("reset-inputs/image.bin"));let stock=read(out.join("stock-dsp.image"));let state=read(out.join("replay.state"));
 let options:Vec<(u32,i64)>=serde_json::from_slice(&read(out.join("replay-options.json"))).unwrap();
 let folder=out.join("stock-oracle");let a=read(folder.join("A.lp0"));let b=read(folder.join("B.lp0"));
 let ra=read(folder.join("reference-1.lp0"));let rb=read(folder.join("reference-2.lp0"));
 let mut frozen_ra=ra.clone();for p in frozen_ra.chunks_exact_mut(4100){if p[..4]==[255;4]{p[4..8].copy_from_slice(&312u32.to_le_bytes());}}
 let wire=read(out.join("flow/wire.bin"));assert_eq!(wire.len(),0xabc);
 let mut first=vec![];let mut repeat_hashes=vec![];
 for repeat in 0..2 {
  let mut actual=NativeBuf::prepared(&image,&state,&options);let mut oracle=NativeBuf::prepared(&stock,&state,&options);let mut wrong=NativeBuf::prepared(&stock,&state,&options);
  actual.publish(&a);for e in [&mut oracle,&mut wrong]{e.publish(&ra);e.publish(&frozen_ra);}
  assert_eq!(actual.descriptor(300),actual.descriptor(312));let frozen=actual.descriptor(312);
  let mut results=vec![];let mut differing=false;
  for(name,count,mask)in [("A-frozen-A",12,49u16),("retained-A",12,0),("B-frozen-A",48,49),("late-frozen-A",24,32)]{
   if name=="retained-A"{
    let ptr=actual.pointers();assert!(ptr.iter().all(|v|*v!=0));actual.publish(&b);assert_eq!(ptr,actual.pointers());assert_eq!(actual.descriptor(312),frozen);
    oracle.publish(&rb);wrong.publish(&rb);
    let mut frozen_b=rb.clone();for p in frozen_b.chunks_exact_mut(4100){if p[..4]==[255;4]{p[4..8].copy_from_slice(&312u32.to_le_bytes());}}wrong.publish(&frozen_b);
   }
   let mut data=vec![];let mut replies=vec![];let mut reference_replies=vec![];let mut rings=vec![];
   for i in 0..count {
    let mut packet=wire.clone();for off in [0x22,0x24,0x26,0x28,0x2a]{packet[off..off+2].copy_from_slice(&(if i==0&&(off==0x22||off==0x26){mask}else{0u16}).to_be_bytes());}
    for(track,slot)in [(0,300u16),(4,300),(5,312)]{packet[0xe0+track*0x60..0xe2+track*0x60].copy_from_slice(&slot.to_be_bytes());}
    let(r,p)=actual.frame(&packet);let(ro,po)=oracle.frame(&packet);let(_,pw)=wrong.frame(&packet);
    assert_eq!(p,po,"stock-file voice PCM {name} block {i}");
    // Timing word reflects different callback instruction counts. Preserve all
    // reply bytes and compare signal rows separately, without mutating them.
    assert_eq!(&r[..0x14],&ro[..0x14],"stock-file reply header {name} block {i}");
    assert_eq!(&r[0x18..],&ro[0x18..],"stock-file reply signal/trailer {name} block {i}");
    let mut ring=vec![];for base in [0x25f180u64,0x261cc8,0x261dc8]{for j in 0..64{
     let x=actual.word(base+j*4,4);let y=oracle.word(base+j*4,4);assert_eq!(x,y,"stock-file final output {name} block {i}");ring.extend(x.to_le_bytes());
    }}
    if name=="B-frozen-A"&&p!=pw{differing=true;}data.extend(p);replies.extend(r);reference_replies.extend(ro);rings.extend(ring);
   }
   if repeat==0{fs::write(out.join(format!("{name}.voice")),&data).unwrap();fs::write(out.join(format!("{name}.reply")),&replies).unwrap();fs::write(out.join(format!("{name}.reference-reply")),&reference_replies).unwrap();fs::write(out.join(format!("{name}.mix-ring")),&rings).unwrap();}
   results.push(json!({"phase":name,"voice":hash(&data),"reply":hash(&replies),"stock_reply":hash(&reference_replies),"reply_differing_bytes":replies.iter().zip(&reference_replies).filter(|(a,b)|a!=b).count(),"mix_and_ring":hash(&rings)}));
  }
  assert!(differing,"wrong-frozen-source control not detected");if repeat==0{first=results.clone();}else{assert_eq!(first,results,"native replay exact repeat");}repeat_hashes.push(results);
 }
 save(out.join("replay.json"),&json!({"status":"passed","blocks_per_repeat":96,"repeats":repeat_hashes,"stock_file_voice_exact":true,"stock_file_reply_signal_exact":true,"stock_file_master_and_ring_exact":true,"wrong_frozen_source_detected":true,"retained_readers_preserved":true,"recordings":0,"scope":"Saved native pages and independent stock CPU file loads; final output uses current native semantics"}));
}
fn main(){let a:Vec<_>=env::args().collect();let spec:Value=serde_json::from_slice(&read(&a[1])).unwrap();let out=Path::new(spec["output"].as_str().unwrap());match a[2].as_str(){"model"=>model(out),"flow"=>flow(&spec,out,false),"repeat"=>flow(&spec,out,true),"replay"=>replay(out),_=>panic!("mode not implemented")};}
