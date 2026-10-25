//! Pending Sketch startup capture. Panel input only; no guest guard writes.
mod startup_capture_trace;
use elektron_native_boot::{Emulator, RecorderPeer, sharc_peer::{SharedDsp, SharcPeer, DT2_IDLE}};
use sharc_native::Engine;
use serde_json::{Value,json};
use std::{env,fs,path::Path,time::Instant};
use startup_capture_trace::Operations;
use sha2::{Digest,Sha256};

fn read(p:impl AsRef<Path>)->Vec<u8>{fs::read(p).unwrap()}
fn save(p:impl AsRef<Path>,v:&Value){fs::write(p,serde_json::to_vec_pretty(v).unwrap()).unwrap()}
fn source()->Vec<u8>{(0..240_000i32).flat_map(|i|{let l=((i*53)%20001-10000) as i16;let r=((i*89)%16001-8000) as i16;[l.to_be_bytes(),r.to_be_bytes()].concat()}).collect()}
fn frame(e:&mut Emulator,out:&Path,name:&str){if let Some((_,b))=e.current_frame(){fs::write(out.join(format!("{name}.frame")),b).unwrap();}}
fn advance(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,n:u64,label:&str){
 let end=e.icount()+n;while e.icount()<end{let s=e.step_chunk((end-e.icount()).min(250_000) as u32).status;assert!(s.error.is_none(),"CPU fault {:?}",s.error);assert!(shared.borrow().halted.is_none());t.sample(e,label,s.ready);}
}
fn tap(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,key:u8,label:&str){
 e.button(key,true).unwrap();advance(e,t,shared,2_640_000,label);e.button(key,false).unwrap();advance(e,t,shared,2_640_000,label);
}
fn overlay(e:&Emulator,out:&Path){let mut b=vec![];for s in e.card_overlay(){b.extend(s.sector.to_le_bytes());b.extend(s.written);b.extend(s.data);}fs::write(out.join("verified-card.overlay"),b).unwrap();}

fn main(){
 let args:Vec<_>=env::args().collect();
 let spec:Value=serde_json::from_slice(&read(&args[1])).unwrap();
 let out=Path::new(spec["output"].as_str().unwrap());
 let start=Instant::now();let mut heartbeat=Instant::now();
 let cancel=spec["mode"]=="cancel";

 let w=spec["symbols"]["w"]["STATE"].as_u64().unwrap() as u32;
 let dest=spec["symbols"]["w"]["DEST"].as_u64().unwrap() as u32;
 let input=Path::new(spec["reset_inputs"].as_str().unwrap());
 let mut eng=Engine::from_image(&read(input.join("image.bin"))).unwrap();
 eng.import(&read(input.join("reset.state"))).unwrap();assert_eq!(eng.s.icount,0);
 for(k,v)in[(1,0),(4,1),(5,1),(9,1),(21,1),(22,1)]{assert_eq!(eng.set_option(k,v),0);}
 let mut idle=0;
 while eng.s.icount<400_000_000{eng.step(250_000);assert!(eng.halt.is_none());if (DT2_IDLE.range.0..DT2_IDLE.range.1).contains(&(eng.s.pc_sw as u32)){idle+=1;}else{idle=0;}if idle==8{break;}}
 assert_eq!(idle,8);eprintln!("DSP application initialized in {} instructions",eng.s.icount);
 for(k,v)in[(23,DT2_IDLE.head),(24,DT2_IDLE.range.0),(25,DT2_IDLE.range.1)]{assert_eq!(eng.set_option(k,v as i64),0);}
 let dsp=SharedDsp::new(eng);let(mut peer,shared)=SharcPeer::new(dsp.clone(),666_667);peer.set_idle_range(DT2_IDLE.range);peer.enable_sample_link();
 let card=elektron_native_boot::card_file::card_from_image(Path::new(spec["card"].as_str().unwrap())).unwrap();
 let main=read(spec["main"].as_str().unwrap());
 let meta:Value=serde_json::from_slice(&read(spec["metadata"].as_str().unwrap())).unwrap();
 let mut e=Emulator::new_patched_with_reference(&read(spec["candidate"].as_str().unwrap()),Some(card),&read(spec["stock_syx"].as_str().unwrap())).unwrap();
 assert_eq!(e.icount(),0);assert_eq!(e.peek(0x40000400,main.len()).unwrap(),main);
 if spec["main_panel_contract"]==true{e.relax_fs_check();}
 e.enable_ssi_diagnostic(96_000).unwrap();e.set_dspi2_peer(peer.boxed());
 assert!(e.run_until_pc(0x40000546,100_000_000));
 e.set_recorder_peer(RecorderPeer::new(source()).unwrap()).unwrap();
 let mut trace=Operations::new(&mut e,&meta);trace.add_copy_watch(&mut e,spec["copy_return_pc"].as_u64().unwrap() as u32);trace.sample(&mut e,"reset-initialized",false);
 let symbols=&spec["symbols"];
 let nb=symbols["nb"]["STATE"].as_u64().unwrap() as u32;
 let view=symbols["s"]["STATE"].as_u64().unwrap() as u32;
 let field=|layer:&str,name:&str| symbols[layer][name].as_u64().unwrap() as u32;
 let mut prepared=false;let mut armed=false;let mut cancelled=false;
 let mut assignment=None;let mut first_start=None;let mut first_stop=None;
 let mut milestones=vec![];let mut last_phase=99;
 loop{
  let st=e.step_chunk(250_000).status;assert!(st.error.is_none(),"CPU fault {:?}",st.error);
  trace.sample(&mut e,"startup-Sketch",st.ready);assert!(shared.borrow().halted.is_none());
  let phase=e.peek32(nb).unwrap();
  if phase!=last_phase {milestones.push(json!({"phase":phase,"icount":e.icount(),"loads":trace.project_loads(),"active_load":trace.project_active(),"batch_active":e.peek32(nb+field("pending","BATCH_ACTIVE")),"batch_done":e.peek32(nb+field("pending","BATCH_DONE")),"setup":e.peek32(w+64),"uses":e.peek32(nb+field("nb","USES"))}));last_phase=phase;}
  if st.main_ui_reached&&!prepared{
   prepared=true;
   assert_eq!(e.peek32(dest),Some(0));
   // Native panel preparation from the established clock fixture: clear the
   // test pattern in grid-record mode, select normal scale, leave grid mode.
   tap(&mut e,&mut trace,&shared,12,"prepare-NO");
   tap(&mut e,&mut trace,&shared,19,"prepare-grid-record");
   for key in [20u8,22u8] {
    e.button(17,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"prepare-FUNC-down");
    tap(&mut e,&mut trace,&shared,key,"prepare-native-pattern");
    e.button(17,false).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"prepare-FUNC-up");
   }
   tap(&mut e,&mut trace,&shared,22,"prepare-normal-scale");
   tap(&mut e,&mut trace,&shared,12,"prepare-close-scale");
   tap(&mut e,&mut trace,&shared,2,"prepare-SRC");
   tap(&mut e,&mut trace,&shared,19,"prepare-leave-grid");
   tap(&mut e,&mut trace,&shared,24,"open-Sketch-before-loads");
   assert_ne!(e.peek32(view+field("s","VIEW")),Some(0),"native Sketch must open");
   assert_eq!(e.peek32(view+field("s","START_MODE")),Some(0));
   for _ in 0..8 {if e.peek32(view+field("s","START_MODE"))==Some(1){break;}e.turn(6,10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-NOW");}
   assert_eq!(e.peek32(view+field("s","START_MODE")),Some(1));
   // Set the menu's actual native LEN rather than assuming the project's default.
   for _ in 0..20 {
    let object=e.peek32(view+field("s","VIEW")).unwrap();
    let wrap=e.peek32(object+field("s","SETTINGS")).unwrap();
    let inner=e.peek32(wrap+16).unwrap();let length=e.peek32(inner+0x1ba).unwrap();
    if length==4 {break;}e.turn(4,if length>4{-10}else{10}).unwrap();
    advance(&mut e,&mut trace,&shared,3_960_000,"native-LEN16");
   }

   tap(&mut e,&mut trace,&shared,20,"native-PLAY");
   frame(&mut e,out,"startup-Sketch-ready");
  }
  if trace.project_loads()>0&&!armed{
   armed=true;
   let kit=e.peek32(0x80004704).unwrap();assignment=Some((kit,e.peek(kit,16*0x450).unwrap()));
   assert_eq!(e.peek32(w+64),Some(0));assert_eq!(e.peek32(nb+field("pending","BATCH_ACTIVE")),Some(1));
   e.button(17,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"FUNC-down");
   tap(&mut e,&mut trace,&shared,24,"native-FUNC-SONG-ARM");
   e.button(17,false).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"FUNC-up");
   frame(&mut e,out,"startup-Sketch-recording");
   save(out.join("arm-checkpoint.json"),&json!({"nb":e.peek(nb,0x200).unwrap(),"sketch":e.peek(view,0x140).unwrap(),"recorder_events":e.recorder_peer().unwrap().events,"loads":trace.project_loads(),"milestones":milestones}));
   assert_eq!(e.peek32(nb+field("nb","STARTS")),Some(1),"Sketch early ARM must start; inspect arm-checkpoint.json");
   assert!(e.recorder_peer().unwrap().active);assert!(!trace.batch_returned(),"START must precede whole batch completion");
   first_start=Some(json!({"loads":trace.project_loads(),"active_load":trace.project_active(),"setup":e.peek32(w+64)}));
   assert_eq!(e.peek32(w+64),Some(0));assert_eq!(e.peek32(w+12),Some(0));
  }
  if armed&&cancel&&!cancelled{
   cancelled=true;tap(&mut e,&mut trace,&shared,12,"NO-cancel-Sketch-capture");frame(&mut e,out,"startup-Sketch-cancelled");
  }
  if armed&&e.peek32(nb+field("nb","STOPS"))==Some(1)&&first_stop.is_none(){
   first_stop=Some(json!({"loads":trace.project_loads(),"batch_returned":trace.batch_returned(),"setup":e.peek32(w+64),"phase":e.peek32(nb)}));frame(&mut e,out,"startup-Sketch-stopped");
  }
  if armed&&trace.batch_returned()&&e.peek32(nb)==Some(0)&&shared.borrow().lp0_pending==0&&trace.is_quiet(){
   if cancel {assert_eq!(e.peek32(nb+field("nb","CANCELS")),Some(1));assert_eq!(e.peek32(w+80),Some(0));assert_eq!(e.peek32(nb+field("nb","USES")),Some(0));}
   else {assert_eq!(e.peek32(nb+field("nb","USES")),Some(1));}
   break;
  }
  if heartbeat.elapsed().as_secs()>=30{
   eprintln!("CPU={} loads={} phase={} arm={} wall={:.1}s",e.icount(),trace.project_loads(),phase,armed,start.elapsed().as_secs_f64());heartbeat=Instant::now();
   trace.checkpoint(&mut e,out,false);
  }
  assert!(e.icount()<2_500_000_000&&start.elapsed().as_secs()<600,"bounded native startup");
 }
 advance(&mut e,&mut trace,&shared,26_400_000,"settle-final-Sketch");frame(&mut e,out,"startup-Sketch-final");
 let (kit,before)=assignment.unwrap();let after=e.peek(kit,16*0x450).unwrap();
 for t in 0..16 {assert_eq!(&before[t*0x450+0x80..t*0x450+0x82],&after[t*0x450+0x80..t*0x450+0x82],"track assignment changed");}
 assert_eq!(e.peek32(dest),Some(0));
 let mut pcm_hash=Value::Null;let mut descriptor=vec![];
 if !cancel {
  let data=e.recorder_peer().unwrap().completed.as_ref().unwrap();assert!(!data.is_empty());assert_eq!(data.as_slice(),&source()[..data.len()]);fs::write(out.join("captured.pcm"),data).unwrap();pcm_hash=json!(format!("{:x}",Sha256::digest(data)));
  assert_eq!((0..4).map(|i|e.peek32(w+96+i*4).unwrap()).collect::<Vec<_>>(),vec![1020,1021,1022,1023]);
  descriptor=(0..5).map(|i|dsp.0.borrow().peek((0x257810+1020*20+i*4) as u64,if i==4{1}else{4}).unwrap().unwrap()).collect();assert!(descriptor[2]>0);
  let mut pages=vec![];for(tag,b,h)in &e.recorder_peer().unwrap().pages{pages.extend(tag.to_be_bytes());pages.extend(h.to_be_bytes());pages.extend(b);}fs::write(out.join("publication-pages.bin"),pages).unwrap();
 } else {assert!(!e.recorder_peer().unwrap().active);assert!(e.recorder_peer().unwrap().completed.is_none());assert_eq!(e.peek32(w+80),Some(0));}
 trace.checkpoint(&mut e,out,true);
 for g in meta["guards"].as_array().unwrap(){let a=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(e.peek(a,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 for row in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()){
  if row["kind"]!="code"&&row["kind"]!="stock-trampoline"{continue;}
  let a=row["address"].as_u64().unwrap() as u32;let s=row["after"].as_str().unwrap();let bytes:Vec<_>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();assert_eq!(e.peek(a,bytes.len()).unwrap(),bytes,"CPU code changed");
 }
 save(out.join("flow.json"),&json!({"status":"passed-native-startup-Sketch","mode":spec["mode"],"start":first_start,"stop":first_stop,"project_loads":trace.project_loads(),"milestones":milestones,"normal_DEST":0,"assignments_preserved":true,"descriptor":descriptor,"PCM_sha256":pcm_hash,"recorder_events":e.recorder_peer().unwrap().events,"CPU_code_and_canaries_intact":true,"host_guard_writes":false,"hardware":false,"scope":"CPU application reset, independently initialized native DSP, modeled external input/card/peripheral cadence; no physical timing or listening claim"}));
 eprintln!("native startup Sketch complete in {:.1}s",start.elapsed().as_secs_f64());
}
