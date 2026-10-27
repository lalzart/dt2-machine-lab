//! Stopped finite-LEN BUF capture through native panel input and existing publisher.
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
// Sample the native bitmap immediately after Sketch draw returns. The general
// panel latch can retain an intermediate comparison buffer (changed pixels only).
// Observe target-generated pixels; never combine frames or paint missing labels.
fn sketch_frame(e:&mut Emulator,t:&mut Operations,out:&Path,name:&str,draw:u32){
 assert!(e.run_until_pc(draw,26_400_000),"Sketch draw not reached");
 let (_,a,_,_)=e.cpu_regs();let ret=e.peek32(a[7]).unwrap();let canvas=e.peek32(a[7]+8).unwrap();
 assert_eq!(e.peek32(canvas+4),Some(128));assert_eq!(e.peek32(canvas+8),Some(64));assert_eq!(e.peek32(canvas+12),Some(2));
 let pixels=e.peek32(canvas+16).unwrap();
 assert!(e.run_until_pc(ret,2_640_000),"Sketch draw did not return");
 t.sample(e,name,false);
 let b=e.peek(pixels,1024).unwrap();
 assert!(b.iter().filter(|&&v|v!=0).count()>150,"Incomplete native Sketch bitmap: {name}");
 fs::write(out.join(format!("{name}.draw.frame")),b).unwrap();
}
fn advance(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,n:u64,label:&str){
 let end=e.icount()+n;while e.icount()<end{let s=e.step_chunk((end-e.icount()).min(250_000) as u32).status;assert!(s.error.is_none(),"CPU fault {:?}",s.error);assert!(shared.borrow().halted.is_none());t.sample(e,label,s.ready);}
}
fn tap(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,key:u8,label:&str){
 e.button(key,true).unwrap();advance(e,t,shared,2_640_000,label);e.button(key,false).unwrap();advance(e,t,shared,2_640_000,label);
}
fn overlay(e:&Emulator,out:&Path){let mut b=vec![];for s in e.card_overlay(){b.extend(s.sector.to_le_bytes());b.extend(s.written);b.extend(s.data);}fs::write(out.join("verified-card.overlay"),b).unwrap();}

// Resolve physical navigation from authenticated OS1.16 MAIN, rather than
// repeating the frontend's constants or labeling a numeric key by assumption.
fn button(main:&[u8],name:&str)->u8 {
 for code in 1..51usize {
  let at=0x4020aba8usize-0x40000400+code*4;
  let ptr=u32::from_be_bytes(main[at..at+4].try_into().unwrap()).wrapping_sub(0x40000400) as usize;
  if ptr>=main.len(){continue;}
  let len=main[ptr..].iter().position(|&b|b==0).unwrap();
  if &main[ptr..ptr+len]==name.as_bytes(){return code as u8;}
 }
 panic!("Missing physical button {name}");
}

fn main(){
 let args:Vec<_>=env::args().collect();
 let spec:Value=serde_json::from_slice(&read(&args[1])).unwrap();
 let out=Path::new(spec["output"].as_str().unwrap());
 let start=Instant::now();let mut heartbeat=Instant::now();
 assert_eq!(spec["mode"], "publish");

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
 let key=|name:&str|button(&main,name);
 assert_eq!((key("UP"),key("LEFT"),key("DOWN"),key("RIGHT")),(11,13,14,15));
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
 let managed=spec["managed_buffers"]==true;
 let assign_popup=spec["assign_popup"]==true;
 let panel_draw=meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]=="sketch").unwrap()["destination"].as_u64().unwrap() as u32+0x6000;

 let chord=|e:&mut Emulator,t:&mut Operations,key:u8,label:&str|{
  e.button(17,true).unwrap();advance(e,t,&shared,2_640_000,label);tap(e,t,&shared,key,label);e.button(17,false).unwrap();advance(e,t,&shared,2_640_000,label);
 };
 let early_setup=spec["early_buf_setup"]==true;
 if early_setup {
  assert!(e.run_until_pc(0x4004e97c,1_500_000_000),"Project load batch not reached");
  trace.sample(&mut e,"before-early-BUF-setup",false);
  assert_eq!(e.peek32(w+64),Some(0));
  let before=e.icount();
  assert!(e.run_until_pc(0x4004e984,2_640_000),"Early setup did not return");
  trace.sample(&mut e,"after-early-BUF-setup",false);
  assert_eq!(e.peek32(field("loading","ATTEMPTS")),Some(1));
  assert_eq!(e.peek32(field("loading","RESULT")),Some(1));
  assert_eq!(e.peek32(w+64),Some(1));
  for i in 0..4 {assert_eq!(e.peek32(w+96+i*4),Some(1020+i));}
  assert_eq!(e.peek32(nb+field("pending","BATCH_ACTIVE")),Some(1));
  assert_eq!(trace.project_loads(),0);
  save(out.join("early-BUF-setup.json"),&json!({"status":"passed","before":before,"after":e.icount(),"project_loads_completed":0,"slots":[1020,1021,1022,1023],"batch_active":true,"setup_ready":true,"hardware":false}));
 }
 let mut prepared=false;
 while !trace.batch_returned() || !prepared || !trace.is_quiet(){
  let st=e.step_chunk(250_000).status;assert!(st.error.is_none());trace.sample(&mut e,"read-only-startup",st.ready);
  assert!(shared.borrow().halted.is_none());
  if st.main_ui_reached&&!prepared{
   prepared=true;tap(&mut e,&mut trace,&shared,12,"prepare-NO");tap(&mut e,&mut trace,&shared,19,"prepare-grid");
   chord(&mut e,&mut trace,20,"prepare-clear-pattern");chord(&mut e,&mut trace,22,"prepare-scale");
   tap(&mut e,&mut trace,&shared,22,"normal-scale");tap(&mut e,&mut trace,&shared,12,"close-scale");tap(&mut e,&mut trace,&shared,2,"SRC");tap(&mut e,&mut trace,&shared,19,"leave-grid");
  }
  if heartbeat.elapsed().as_secs()>=30{eprintln!("CPU={} loads={} wall={:.1}s",e.icount(),trace.project_loads(),start.elapsed().as_secs_f64());heartbeat=Instant::now();}
  assert!(e.icount()<1_500_000_000);
 }
 advance(&mut e,&mut trace,&shared,26_400_000,"settle-stopped");
 let play=|e:&mut Emulator|e.peek32(0x43164f94).unwrap()!=0||e.peek32(0x43165010).unwrap()!=0;
 assert!(!play(&mut e));let t0=e.peek32(0x40966500).unwrap();advance(&mut e,&mut trace,&shared,26_400_000,"stopped-audio-clock");let t1=e.peek32(0x40966500).unwrap();assert!(t1.wrapping_sub(t0)>0);
 let stopped_clock=json!({"before":t0,"after":t1,"delta":t1.wrapping_sub(t0),"playing":false,"bar_clock_valid":e.peek32(nb+field("nb","VALID"))});
 // Select BUF 2/NOW/LEN16 using the menu, then leave it for T5 SRC.
 tap(&mut e,&mut trace,&shared,24,"open-Sketch");
 let settings_view=e.peek32(view+field("s","VIEW")).unwrap();
 let settings_wrap=e.peek32(settings_view+field("s","SETTINGS")).unwrap();
 let settings_inner=e.peek32(settings_wrap+16).unwrap();
 let normal_values=|e:&mut Emulator|->Vec<u32>{[0x1ae,0x1be,0x1ba,0x1b6].iter().map(|off|e.peek32(settings_inner+off).unwrap()).collect()};
 let normal_before=normal_values(&mut e);
 for _ in 0..8 {if e.peek32(view+field("s","BUF"))==Some(2){break;}let delta=if e.peek32(view+field("s","BUF")).unwrap()>2{-10}else{10};e.turn(1,delta).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-BUF2");}
 assert_eq!(e.peek32(view+field("s","BUF")),Some(2));
 let start_at=if managed{field("managed","SETTINGS")+32+16}else{view+field("s","START_MODE")};
 for _ in 0..8 {if e.peek32(start_at)==Some(1){break;}e.turn(6,10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-NOW");}
 assert_eq!(e.peek32(start_at),Some(1));
 for _ in 0..20 {let len=if managed{e.peek32(field("managed","SETTINGS")+32+8).unwrap()}else{e.peek32(settings_inner+0x1ba).unwrap()};if len==4{break;}e.turn(4,if len>4{-10}else{10}).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"LEN16");}
 if managed{
  let prefs=field("managed","SETTINGS");let buf2=e.peek(prefs+32,20).unwrap();
  for _ in 0..8{if e.peek32(view+field("s","BUF"))==Some(3){break;}e.turn(1,10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-BUF3");}
  assert_eq!(e.peek32(view+field("s","BUF")),Some(3));assert_eq!(e.peek32(prefs+64+16),Some(0));
  for _ in 0..8{if e.peek32(prefs+64+8)==Some(5){break;}e.turn(4,10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"BUF3-LEN32");}
  assert_eq!(e.peek32(prefs+64+8),Some(5));assert_eq!(e.peek(prefs+32,20).unwrap(),buf2);assert_eq!(normal_values(&mut e),normal_before);
  frame(&mut e,out,"managed-BUF3-independent-length");if managed{sketch_frame(&mut e,&mut trace,out,"managed-BUF3-independent-length",panel_draw);}
  for _ in 0..8{if e.peek32(view+field("s","BUF"))==Some(2){break;}e.turn(1,-10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"return-BUF2");}
  assert_eq!(e.peek32(view+field("s","BUF")),Some(2));assert_eq!(e.peek(prefs+32,20).unwrap(),buf2);frame(&mut e,out,"managed-BUF2-preferences");if managed{sketch_frame(&mut e,&mut trace,out,"managed-BUF2-preferences",panel_draw);}
 }
 e.button(16,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"TRK");tap(&mut e,&mut trace,&shared,29,"select-T5");e.button(16,false).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"release-TRK");tap(&mut e,&mut trace,&shared,2,"SRC-T5");
 assert_eq!(e.peek32(view+field("s","VIEW")),Some(0));
 let kit=e.peek32(0x80004704).unwrap();let assignments=e.peek(kit,16*0x450).unwrap();let assigned=u16::from_be_bytes([assignments[4*0x450+0x80],assignments[4*0x450+0x81]]);assert!(!(1020..=1023).contains(&assigned));

 // Start globally from ordinary T5, then finish early from T1.
 chord(&mut e,&mut trace,24,"stopped-start-BUF2-from-T5");
 assert_eq!(e.peek32(nb+field("nb","STARTS")),Some(1));
 assert_eq!(e.peek32(nb+field("nb","START_MODE")),Some(2));
 assert_eq!(e.peek32(nb+field("nb","DEST")),Some(2));
 advance(&mut e,&mut trace,&shared,66_000_000,"early-stopped-take");
 save(out.join("early-stopped-checkpoint.json"),&json!({"nb":e.peek(nb,0x200).unwrap(),"Sketch":e.peek(view,0x140).unwrap(),"events":e.recorder_peer().unwrap().events,"active":e.recorder_peer().unwrap().active}));
 assert_eq!(e.peek32(nb+field("nb","PHASE")),Some(2),"early take must still be active");
 assert!(e.recorder_peer().unwrap().active);
 tap(&mut e,&mut trace,&shared,24,"show-manual-recording");frame(&mut e,out,"manual-recording");if managed{sketch_frame(&mut e,&mut trace,out,"manual-recording",panel_draw);}
 // Switch ordinary track while recording, then finish globally from T1.
 e.button(16,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"TRK");tap(&mut e,&mut trace,&shared,25,"select-T1");e.button(16,false).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"release-TRK");tap(&mut e,&mut trace,&shared,2,"SRC-T1");
 chord(&mut e,&mut trace,24,"manual-finish-from-T1");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(1){break;}advance(&mut e,&mut trace,&shared,250_000,"manual-publication");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(1));assert_eq!(e.peek32(dest),Some(0));assert!(!play(&mut e));
 if managed{
  advance(&mut e,&mut trace,&shared,5_280_000,"restore-normal-settings");
  assert_eq!(e.peek32(field("managed","STATE")+field("managed","BORROWED")),Some(0));
  assert_eq!(normal_values(&mut e),normal_before,"Sketch capture changed normal sampler preferences");
 }
 let captured=trace.completed_pcm().to_vec();assert!((141*4..96_000*4).contains(&captured.len()));assert!(captured.iter().any(|&v|v!=0));
 fs::write(out.join("captured.pcm"),&captured).unwrap();
 let descriptor=e.peek32(w+36).unwrap();let published=e.peek(descriptor,64).unwrap();fs::write(out.join("published-descriptor.bin"),&published).unwrap();
 assert_eq!(e.peek32(w+100),Some(1021));
 if assign_popup{
  let prompt=field("assign","STATE");
  for _ in 0..80{if e.peek32(prompt+field("assign","SHOWN"))==Some(1){break;}advance(&mut e,&mut trace,&shared,250_000,"wait-assignment-prompt-A");}
  let q=meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]=="freeze_queue").unwrap()["destination"].as_u64().unwrap() as u32;
  let brain=e.peek32(0x44f37098).unwrap();let node=e.peek32(brain+0x58).unwrap();let top=e.peek32(node+8).unwrap();let vt=e.peek32(top).unwrap();let name=e.peek32(top+0x28).unwrap();
  let mut stack=vec![];let mut cursor=node;for _ in 0..32{if cursor==brain+0x54{break;}let v=e.peek32(cursor+8).unwrap();let table=e.peek32(v).unwrap();let view_name=e.peek32(v+0x28).unwrap();stack.push(json!({"view":v,"vtable":table,"key":e.peek32(table+8),"name":e.peek(view_name,64)}));cursor=e.peek32(cursor+4).unwrap();}
  save(out.join("assign-A-checkpoint.json"),&json!({"stack":stack,"state":e.peek(prompt,256),"sketch":e.peek(view,0x140),"brain":brain,"node":node,"top":top,"vtable":vt,"key":e.peek32(vt+8),"name":e.peek(name,64),"busy":e.peek32(0x405b1360),"jobs_lease":e.peek32(q+56),"worker_lease":e.peek32(w+12),"borrowed":e.peek32(field("managed","STATE")+field("managed","BORROWED"))}));
  assert_ne!(e.peek32(prompt+field("assign","VIEW")),Some(0),"Successful capture must open assignment prompt from normal SRC page");
  assert_eq!(e.peek32(prompt+field("assign","BUF")),Some(2));assert_eq!(e.peek32(prompt+field("assign","SLOT")),Some(1021));
  sketch_frame(&mut e,&mut trace,out,"assign-A-stock-prompt",field("assign","STOCK_DRAW"));
  let before=e.peek(kit,16*0x450).unwrap();
  tap(&mut e,&mut trace,&shared,12,"NO-skip-assign-A");
  assert_eq!(e.peek32(prompt+field("assign","VIEW")),Some(0));assert_eq!(e.peek32(prompt+field("assign","SKIPPED")),Some(1));
  assert_eq!(e.peek(kit,16*0x450).unwrap(),before,"NO must not change any track");
  assert_eq!(e.peek32(view+field("s","VIEW")),Some(0),"NO must return to original SRC page");
 }
 tap(&mut e,&mut trace,&shared,24,"show-manual-ready");frame(&mut e,out,"manual-ready");if managed{sketch_frame(&mut e,&mut trace,out,"manual-ready",panel_draw);}
 // Freeze through the existing held-SONG event. The first snapshot is H123.
 let arena=|name:&str|meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]==name).unwrap()["destination"].as_u64().unwrap() as u32;
 let generations=arena("generations");let snaps=generations+0x1800;let jobs=arena("freeze_queue");let pool=e.peek32(w+68).unwrap();
 let hold_song=|e:&mut Emulator,t:&mut Operations,label:&str|{e.button(24,true).unwrap();advance(e,t,&shared,264_000_000,label);e.button(24,false).unwrap();advance(e,t,&shared,5_280_000,label);};
 let dslot=|slot:u32|->Vec<u32>{(0..5).map(|i|dsp.0.borrow().peek((0x257810+slot*20+i*4) as u64,if i==4{1}else{4}).unwrap().unwrap()).collect()};
 let source_a=dslot(1021);assert!(source_a[2]>0);
 let assignments_before=e.peek(kit,16*0x450).unwrap();
 hold_song(&mut e,&mut trace,"hold-SONG-FREEZE-A");
 for _ in 0..400 {if e.peek32(jobs+32)==Some(1){break;}advance(&mut e,&mut trace,&shared,250_000,"wait-FREEZE-A");}
 save(out.join("freeze-A-checkpoint.json"),&json!({"result":e.peek32(jobs+12),"count":e.peek32(generations+4),"snapshot":e.peek(snaps,64),"action":e.peek32(view+field("s","ACTION")),"pool_ref":e.peek(pool+1019*16,16)}));
 assert_eq!(e.peek32(jobs+12),Some(1019));assert_eq!(e.peek32(generations+4),Some(1));assert_eq!(e.peek32(snaps+36),Some(1019));assert_eq!(e.peek(kit,16*0x450).unwrap(),assignments_before,"FREEZE must not assign a track");
 advance(&mut e,&mut trace,&shared,26_400_000,"settle-FREEZE-A");frame(&mut e,out,"01-frozen-to-H123");if managed{sketch_frame(&mut e,&mut trace,out,"01-frozen-to-H123",panel_draw);}assert_eq!(dslot(1019),source_a);
 let frozen_a=e.peek(snaps,64).unwrap();let key_a=e.peek(pool+1019*16,16).unwrap();let hdr_a=dslot(1019);
 let sample_bytes=|hdr:&[u32]|->Vec<u8>{assert!(hdr[2]>0&&hdr[2]<=1_920_000);let mut b=vec![];for off in (0..hdr[2]).step_by(4){let v=dsp.0.borrow().peek((0x8422b9c8u64+hdr[0] as u64+off as u64),4).unwrap().unwrap();b.extend(v.to_le_bytes());}b.truncate(hdr[2] as usize);b};
 let pcm_a=sample_bytes(&hdr_a);assert!(pcm_a.iter().any(|&b|b!=0));fs::write(out.join("frozen-A-DSP-PCM.bin"),&pcm_a).unwrap();
 tap(&mut e,&mut trace,&shared,10,"show-frozen-takes");advance(&mut e,&mut trace,&shared,26_400_000,"settle-take-list");frame(&mut e,out,"02-frozen-list-H123");tap(&mut e,&mut trace,&shared,10,"back-to-Sketch");
 // A new take changes BUF 2 while the H123 frozen association stays immutable.
 e.recorder_peer_mut().unwrap().source=source().chunks_exact(2).flat_map(|b|(-i16::from_be_bytes([b[0],b[1]])).to_be_bytes()).collect();
 let before=e.peek32(nb+field("nb","USES")).unwrap();chord(&mut e,&mut trace,24,"record-replacement-B");
 advance(&mut e,&mut trace,&shared,66_000_000,"replacement-B-input");chord(&mut e,&mut trace,24,"finish-replacement-B");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(before+1){break;}advance(&mut e,&mut trace,&shared,250_000,"B-publish");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(before+1));assert_eq!(e.peek(snaps,64).unwrap(),frozen_a);assert_eq!(e.peek(pool+1019*16,16).unwrap(),key_a);assert_eq!(dslot(1019),hdr_a);assert_eq!(sample_bytes(&hdr_a),pcm_a,"frozen A PCM must remain exact after B");assert_ne!(sample_bytes(&dslot(1021)),pcm_a,"replacement B PCM must differ");
 if assign_popup{
  let prompt=field("assign","STATE");
  for _ in 0..80{if e.peek32(prompt+field("assign","SHOWN"))==Some(2){break;}advance(&mut e,&mut trace,&shared,250_000,"wait-assignment-prompt-B");}
  assert_ne!(e.peek32(prompt+field("assign","VIEW")),Some(0));assert_eq!(e.peek32(prompt+field("assign","SHOWN")),Some(2));
  let sketch=e.peek32(view+field("s","VIEW")).unwrap();assert_ne!(sketch,0);
  sketch_frame(&mut e,&mut trace,out,"assign-B-stock-prompt",field("assign","STOCK_DRAW"));
  let before=e.peek(kit,16*0x450).unwrap();
  e.button(40,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"assign-B-T16-press");
  assert_eq!(e.peek(kit,16*0x450).unwrap(),before,"Assignment waits for release");
  e.button(40,false).unwrap();advance(&mut e,&mut trace,&shared,5_280_000,"assign-B-T16-release");
  save(out.join("assign-B-checkpoint.json"),&json!({"state":e.peek(prompt,256),"before":before,"after":e.peek(kit,16*0x450)}));
  assert_eq!(e.peek32(prompt+field("assign","VIEW")),Some(0));assert_eq!(e.peek32(prompt+field("assign","RESULT")),Some(1));
  assert_eq!(e.peek32(prompt+field("assign","ASSIGNED")),Some(1));assert_eq!(e.peek32(prompt+field("assign","TARGET")),Some(16));
  assert_eq!(e.peek(kit,15*0x450).unwrap(),before[..15*0x450],"Other fifteen tracks unchanged");
  assert_eq!(e.peek(kit+15*0x450+0x80,2).unwrap(),1021u16.to_be_bytes());
  assert_eq!(e.peek32(view+field("s","VIEW")),Some(sketch),"Track choice release must not close underlying Sketch");
  advance(&mut e,&mut trace,&shared,5_280_000,"assignment-once");assert_eq!(e.peek32(prompt+field("assign","SHOWN")),Some(2));
 }

 let book=field("book","STATE");let meta_base=field("book","META");
 save(out.join("metadata-before-save.json"),&json!({"meta":e.peek(meta_base,1024),"generations":e.peek(generations+0x1000,512),"key_A":e.peek(0x405b1368+1019*16,16),"key_B":e.peek(0x405b1368+1021*16,16),"worker":e.peek(w,256)}));
 let file_for=|e:&mut Emulator,slot:u32,pcm:&[u8]|->Vec<u8>{
  let token=e.peek32(0x405b1368+slot*16).unwrap();let bytes=e.peek(meta_base,1024).unwrap();
  let seat=bytes.chunks_exact(128).find(|b|u32::from_be_bytes(b[4..8].try_into().unwrap())==token).unwrap();
  assert_eq!(&seat[20..24],&[0,0,0,0]);assert_eq!(u32::from_be_bytes(seat[12..16].try_into().unwrap()) as usize,pcm.len()+80);
  [&seat[32..96],pcm,&seat[96..112]].concat()
 };
 let expected_a=file_for(&mut e,1019,&captured);let expected_b=file_for(&mut e,1021,trace.completed_pcm());
 fs::write(out.join("expected-A.native"),&expected_a).unwrap();fs::write(out.join("expected-B.native"),&expected_b).unwrap();
 let protected_pool=e.peek(pool,16384).unwrap();let protected_tracks=e.peek(kit,16*0x450).unwrap();let protected_snap=e.peek(snaps,512).unwrap();
 // The original Samples UI remains intact; Sketch owns its own save list.
 let ui=field("ui","STATE");let ui_field=|name:&str|field("ui",name);
 if e.peek32(view+field("s","VIEW"))!=Some(0){tap(&mut e,&mut trace,&shared,key("NO"),"close-Sketch-before-Samples");}
 chord(&mut e,&mut trace,50,"FUNC-SAMPLING-Samples");advance(&mut e,&mut trace,&shared,13_200_000,"Samples-list-settle");
 tap(&mut e,&mut trace,&shared,key("LEFT"),"LEFT-Samples-root");advance(&mut e,&mut trace,&shared,13_200_000,"Samples-root-settle");
 assert_eq!(e.peek32(ui+ui_field("VIEW")),Some(0));frame(&mut e,out,"10-stock-Samples-root");
 tap(&mut e,&mut trace,&shared,key("NO"),"NO-close-Samples-root");
 tap(&mut e,&mut trace,&shared,24,"SONG-open-Sketch");frame(&mut e,out,"10b-Sketch-save-entry");if managed{sketch_frame(&mut e,&mut trace,out,"10b-Sketch-save-entry",panel_draw);}
 assert_ne!(e.peek32(view+field("s","VIEW")),Some(0));
 tap(&mut e,&mut trace,&shared,key("LEFT"),"LEFT-must-not-open-Sketchbook");assert_eq!(e.peek32(ui+ui_field("MODE")),Some(0));
 tap(&mut e,&mut trace,&shared,key("DOWN"),"DOWN-open-Sketchbook");assert_eq!(e.peek32(ui+ui_field("MODE")),Some(1));frame(&mut e,out,"11-Sketchbook-buffers");
 let sketch_view=e.peek32(view+field("s","VIEW")).unwrap();
 tap(&mut e,&mut trace,&shared,key("DOWN"),"DOWN-select-BUF2");assert_eq!(e.peek32(ui+ui_field("ROW")),Some(1));
 tap(&mut e,&mut trace,&shared,key("UP"),"UP-select-BUF1");assert_eq!(e.peek32(ui+ui_field("ROW")),Some(0));
 tap(&mut e,&mut trace,&shared,key("LEFT"),"LEFT-back-to-Sketch");assert_eq!(e.peek32(ui+ui_field("MODE")),Some(0));assert_eq!(e.peek32(view+field("s","VIEW")),Some(sketch_view));
 tap(&mut e,&mut trace,&shared,key("DOWN"),"DOWN-after-LEFT");assert_eq!(e.peek32(ui+ui_field("MODE")),Some(1));
 tap(&mut e,&mut trace,&shared,key("NO"),"NO-back-to-Sketch");
 assert_eq!(e.peek32(ui+ui_field("MODE")),Some(0));assert_eq!(e.peek32(view+field("s","VIEW")),Some(sketch_view),"Back release dismissed Sketch");
 tap(&mut e,&mut trace,&shared,key("DOWN"),"DOWN-reopen-Sketchbook");
 tap(&mut e,&mut trace,&shared,key("YES"),"YES-empty-BUF1");frame(&mut e,out,"12-empty-BUF-warning");assert_eq!(e.peek32(w+12),Some(0));tap(&mut e,&mut trace,&shared,key("NO"),"close-empty-warning");
 // Preview the frozen take, which is larger than the stock first read and
 // therefore also exercises the original asynchronous preview reader close.
 for _ in 0..4 {tap(&mut e,&mut trace,&shared,key("DOWN"),"DOWN-to-frozen-A");}
 assert_eq!(e.peek32(ui+ui_field("ROW")),Some(4));frame(&mut e,out,"13-Sketchbook-frozen-take");save(out.join("frozen-row-text.json"),&json!({"text":e.peek(field("ui","LINE"),64)}));
 let canceled_before=e.peek32(book+field("book","COMPLETIONS")).unwrap();
 tap(&mut e,&mut trace,&shared,key("RIGHT"),"RIGHT-start-cancel-preview");tap(&mut e,&mut trace,&shared,21,"STOP-cancel-preview-download");
 for _ in 0..2000 {if e.peek32(book+field("book","COMPLETIONS"))!=Some(canceled_before){break;}advance(&mut e,&mut trace,&shared,250_000,"cancel-preview-drain");}
 assert_eq!(e.peek32(book+field("book","RESULT")),Some(u32::MAX));assert_eq!(e.peek32(field("preview","STATE")),Some(0));assert_eq!(e.peek32(w+12),Some(0));
 tap(&mut e,&mut trace,&shared,key("NO"),"close-preview-cancel-message");
 let completed=e.peek32(book+field("book","COMPLETIONS")).unwrap();let pcm_start=shared.borrow().pcm.len();let writes_before=e.card_write_count();
 tap(&mut e,&mut trace,&shared,key("RIGHT"),"RIGHT-audition-frozen-A");frame(&mut e,out,"14-loading-preview");
 for i in 0..4000 {if e.peek32(book+field("book","COMPLETIONS"))!=Some(completed){break;}advance(&mut e,&mut trace,&shared,250_000,"preview-download");if i%400==0{eprintln!("Preview job={:?} phase={:?} position={:?}",e.peek32(book+field("book","JOB")),e.peek32(book+field("book","PHASE")),e.peek32(book+field("book","POSITION")));}}
 save(out.join("preview-checkpoint.json"),&json!({"state":e.peek(book,128),"preview":e.peek(field("preview","STATE"),128),"native_preview_state":e.peek(0x405a0f70,48)}));
 assert_eq!(e.peek32(book+field("book","RESULT")),Some(0),"Preview failed");assert_eq!(e.peek32(w+12),Some(0));
 advance(&mut e,&mut trace,&shared,26_400_000,"preview-playing");
 assert!(shared.borrow().pcm[pcm_start..].iter().any(|v|v.abs()>1e-8),"No modeled final output from preview");
 for _ in 0..400 {if e.peek32(field("preview","STATE"))==Some(0){break;}advance(&mut e,&mut trace,&shared,250_000,"preview-reader-close");}
 assert_eq!(e.peek32(field("preview","STATE")),Some(0),"temporary preview snapshot was not freed");assert_eq!(e.card_write_count(),writes_before,"Audition wrote to disk");
 assert_eq!(e.peek(pool,16384).unwrap(),protected_pool);assert_eq!(e.peek(kit,16*0x450).unwrap(),protected_tracks);assert_eq!(e.peek(snaps,512).unwrap(),protected_snap);frame(&mut e,out,"15-preview-complete");
 tap(&mut e,&mut trace,&shared,21,"STOP-preview");
 let mut results=vec![];
 for (slot,name) in [(1019u32,"Sketch"),(1021,"Buffer-B"),(1019,"Sketch"),(1019,"NoReadback"),(1019,"NoReadback")] {
  if results.len()==3 {assert_eq!(dsp.0.borrow_mut().poke(0x200f847c,&1u32.to_le_bytes(),4),1);}
  if results.len()==4 {assert_eq!(dsp.0.borrow_mut().poke(0x200f847c,&0u32.to_le_bytes(),4),1);}
  let done_before=e.peek32(book+field("book","COMPLETIONS")).unwrap();
  if results.is_empty(){
   let job_before=e.peek32(book+field("book","JOB"));
   tap(&mut e,&mut trace,&shared,key("YES"),"YES-name-Sketchbook-save");advance(&mut e,&mut trace,&shared,13_200_000,"name-editor-settle");frame(&mut e,out,"16-stock-filename-dialog");
   assert_eq!(e.peek32(book+field("book","JOB")),job_before,"Opening the name editor submitted a save");
   assert_eq!(e.peek32(book+field("book","COMPLETIONS")),Some(done_before));
   tap(&mut e,&mut trace,&shared,key("NO"),"NO-cancel-name-editor");assert_eq!(e.peek32(book+field("book","JOB")),job_before);assert_eq!(e.peek32(view+field("s","VIEW")),Some(sketch_view));assert_eq!(e.peek32(ui+ui_field("MODE")),Some(1));
   tap(&mut e,&mut trace,&shared,key("YES"),"YES-reopen-name-editor");tap(&mut e,&mut trace,&shared,key("YES"),"YES-save-default-name");
  }else{
  let command=e.peek32(book+field("book","COMMAND")).unwrap()+1;
  e.poke(field("book","COMMAND_NAME"),format!("{name}\0").as_bytes()).unwrap();
  e.poke32(book+field("book","COMMAND_SLOT"),slot).unwrap();e.poke32(book+field("book","COMMAND"),command).unwrap();
  for _ in 0..160 {if e.peek32(book+field("book","HANDLED"))==Some(command){break;}advance(&mut e,&mut trace,&shared,250_000,"GUI-Sketchbook-submit");}
  save(out.join(format!("submit-{}.json",results.len())),&json!({"command":command,"admission":e.peek32(book+field("book","COMMAND_RESULT")),"state":e.peek(book,128),"meta":e.peek(meta_base,1024)}));
  assert_eq!(e.peek32(book+field("book","HANDLED")),Some(command));assert_eq!(e.peek32(book+field("book","COMMAND_RESULT")),Some(0),"save admission failed");
  }
  for i in 0..8000 {
   if e.peek32(book+field("book","COMPLETIONS"))!=Some(done_before){break;}
   advance(&mut e,&mut trace,&shared,250_000,"native-Sketchbook-save");
   if i%400==0 {eprintln!("save {name} CPU={} job={:?} phase={:?} pos={:?} got={:?} age={:?}",e.icount(),e.peek32(book+field("book","JOB")),e.peek32(book+field("book","PHASE")),e.peek32(book+field("book","POSITION")),e.peek32(book+field("book","RECEIVED")),e.peek32(book+field("book","AGE")));}
  }
  let result=e.peek32(book+field("book","RESULT")).unwrap();let state=e.peek(book,128).unwrap();
  results.push(json!({"slot":slot,"name":name,"result":result,"reference":e.peek(field("book","NODE"),16),"state":state}));
  save(out.join("save-progress.json"),&json!(results));overlay(&e,out);
  assert_ne!(e.peek32(book+field("book","COMPLETIONS")),Some(done_before),"save worker did not complete");
  assert_eq!(result,if results.len()==3||results.len()==4{u32::MAX}else{0},"native file write failed");
  assert_eq!(e.peek(pool,16384).unwrap(),protected_pool);assert_eq!(e.peek(kit,16*0x450).unwrap(),protected_tracks);assert_eq!(e.peek(snaps,512).unwrap(),protected_snap);
  assert_eq!(e.peek32(w+12),Some(0));assert_eq!(e.peek32(book+field("book","CLOSED")),Some(1));frame(&mut e,out,&format!("save-result-{}",results.len()));tap(&mut e,&mut trace,&shared,12,"close-save-result");
 }
 for guard in meta["guards"].as_array().unwrap(){
  let at=guard[0].as_u64().unwrap() as u32;let n=guard[1].as_u64().unwrap() as usize;
  assert_eq!(e.peek(at,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8),"CPU arena canary changed");
 }
 for write in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()){
  if write["kind"]!="code" && write["kind"]!="stock-trampoline"{continue;}
  let h=write["after"].as_str().unwrap();let b:Vec<_>=(0..h.len()).step_by(2).map(|i|u8::from_str_radix(&h[i..i+2],16).unwrap()).collect();
  assert_eq!(e.peek(write["address"].as_u64().unwrap() as u32,b.len()).unwrap(),b,"CPU code changed");
 }
 trace.checkpoint(&mut e,out,true);
 save(out.join("flow.json"),&json!({"status":"passed","CPU_arena_canaries_intact":true,"CPU_code_intact":true,"managed_per_BUF_settings_and_normal_restore":managed,"managed_complete_native_draws":managed,"assignment_popup_NO_and_T16":assign_popup,"early_BUF_setup_before_project_samples":early_setup,"assignment_popup_stock_pixels":assign_popup,"saves":results,"source_CPU_PCM_released":true,"native_menu_preview_filename_flow":true,"STOP_cancels_pending_preview":true,"preview_nonzero_modeled_output":true,"preview_temporary_CPU_snapshot_freed":true,"audition_makes_no_disk_writes":true,"disabled_data_emitter_fails_and_retry_succeeds":true,"associations_unchanged":true,"scope":"Target CPU/SHARC instructions and original LP0/DSPI2 modeled peripherals. Host supplies selection/name commands and comparison observations only; no host readback completion or PCM supply.","hardware":false,"elapsed_seconds":start.elapsed().as_secs_f64()}));
 eprintln!("Sketchbook backend flow passed in {:.1}s",start.elapsed().as_secs_f64());
}
