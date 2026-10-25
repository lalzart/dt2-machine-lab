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

 let chord=|e:&mut Emulator,t:&mut Operations,key:u8,label:&str|{
  e.button(17,true).unwrap();advance(e,t,&shared,2_640_000,label);tap(e,t,&shared,key,label);e.button(17,false).unwrap();advance(e,t,&shared,2_640_000,label);
 };
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
 for _ in 0..8 {if e.peek32(view+field("s","BUF"))==Some(2){break;}let delta=if e.peek32(view+field("s","BUF")).unwrap()>2{-10}else{10};e.turn(1,delta).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-BUF2");}
 assert_eq!(e.peek32(view+field("s","BUF")),Some(2));
 for _ in 0..8 {if e.peek32(view+field("s","START_MODE"))==Some(1){break;}e.turn(6,10).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"select-NOW");}
 for _ in 0..20 {let object=e.peek32(view+field("s","VIEW")).unwrap();let wrap=e.peek32(object+field("s","SETTINGS")).unwrap();let inner=e.peek32(wrap+16).unwrap();let len=e.peek32(inner+0x1ba).unwrap();if len==4{break;}e.turn(4,if len>4{-10}else{10}).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"LEN16");}
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
 tap(&mut e,&mut trace,&shared,24,"show-manual-recording");frame(&mut e,out,"manual-recording");
 // Switch ordinary track while recording, then finish globally from T1.
 e.button(16,true).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"TRK");tap(&mut e,&mut trace,&shared,25,"select-T1");e.button(16,false).unwrap();advance(&mut e,&mut trace,&shared,2_640_000,"release-TRK");tap(&mut e,&mut trace,&shared,2,"SRC-T1");
 chord(&mut e,&mut trace,24,"manual-finish-from-T1");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(1){break;}advance(&mut e,&mut trace,&shared,250_000,"manual-publication");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(1));assert_eq!(e.peek32(dest),Some(0));assert!(!play(&mut e));
 let captured=trace.completed_pcm().to_vec();assert!((141*4..96_000*4).contains(&captured.len()));assert!(captured.iter().any(|&v|v!=0));
 fs::write(out.join("captured.pcm"),&captured).unwrap();
 let descriptor=e.peek32(w+36).unwrap();let published=e.peek(descriptor,64).unwrap();fs::write(out.join("published-descriptor.bin"),&published).unwrap();
 assert_eq!(e.peek32(w+100),Some(1021));
 tap(&mut e,&mut trace,&shared,24,"show-manual-ready");frame(&mut e,out,"manual-ready");
 // A second stopped take ends automatically through the stock LEN guard.
 chord(&mut e,&mut trace,24,"stopped-automatic-LEN");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(2){break;}advance(&mut e,&mut trace,&shared,250_000,"stopped-auto-publication");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(2));assert!(!play(&mut e));
 let full=trace.completed_pcm().to_vec();assert!(full.len()>captured.len());assert!(full.iter().any(|&v|v!=0));fs::write(out.join("automatic-stopped.pcm"),&full).unwrap();
 // Regression: native LEN completion must release the recording command so
 // another automatic take starts, rather than inheriting old completion state.
 chord(&mut e,&mut trace,24,"repeat-after-automatic-LEN");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(3){break;}advance(&mut e,&mut trace,&shared,250_000,"repeat-auto-publication");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(3));assert!(!play(&mut e));
 assert!(trace.completed_pcm().iter().any(|&v|v!=0));
 let descriptor=e.peek32(w+36).unwrap();let published=e.peek(descriptor,64).unwrap();
 frame(&mut e,out,"stopped-automatic-ready");
 // A canceled replacement preserves the previously published take.
 chord(&mut e,&mut trace,24,"start-cancelled-replacement");advance(&mut e,&mut trace,&shared,26_400_000,"replacement-input");tap(&mut e,&mut trace,&shared,12,"NO-cancel");
 for _ in 0..200 {if e.peek32(nb)==Some(0){break;}advance(&mut e,&mut trace,&shared,250_000,"cancel-settle");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(3));assert_eq!(e.peek(descriptor,64).unwrap(),published);
 // A real stopped NORMAL take must block BUF and retain its captured bytes.
 tap(&mut e,&mut trace,&shared,50,"NORMAL-sampler");tap(&mut e,&mut trace,&shared,10,"NORMAL-start");advance(&mut e,&mut trace,&shared,26_400_000,"NORMAL-input");tap(&mut e,&mut trace,&shared,10,"NORMAL-finish");advance(&mut e,&mut trace,&shared,26_400_000,"NORMAL-normalization");
 let normal=e.recorder_peer().unwrap().completed.as_ref().unwrap().clone();tap(&mut e,&mut trace,&shared,12,"close-NORMAL-trim");
 let arms=e.peek32(nb+field("nb","ARMS")).unwrap();chord(&mut e,&mut trace,24,"BUF-refuses-pending-NORMAL");assert_eq!(e.peek32(nb+field("nb","ARMS")),Some(arms));assert_eq!(e.recorder_peer().unwrap().completed.as_ref().unwrap(),&normal);
 // Explicitly discard only this test-created NORMAL take through stock UI.
 tap(&mut e,&mut trace,&shared,50,"reopen-NORMAL-trim");chord(&mut e,&mut trace,12,"discard-test-NORMAL");tap(&mut e,&mut trace,&shared,12,"close-NORMAL");
 // Running NOW still finishes by LEN and publishes without a second chord.
 tap(&mut e,&mut trace,&shared,20,"PLAY");advance(&mut e,&mut trace,&shared,26_400_000,"running-clock");assert_eq!(e.peek32(nb+field("nb","VALID")),Some(1));
 chord(&mut e,&mut trace,24,"running-NOW-after-manual");
 for _ in 0..1800 {if e.peek32(nb)==Some(0)&&e.peek32(nb+field("nb","USES"))==Some(4){break;}advance(&mut e,&mut trace,&shared,250_000,"running-NOW-publication");}
 assert_eq!(e.peek32(nb+field("nb","USES")),Some(4));assert!(play(&mut e));
 let after=e.peek(kit,16*0x450).unwrap();for t in 0..16{assert_eq!(&assignments[t*0x450+0x80..t*0x450+0x82],&after[t*0x450+0x80..t*0x450+0x82]);}
 for g in meta["guards"].as_array().unwrap(){let a=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(e.peek(a,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 trace.checkpoint(&mut e,out,true);
 save(out.join("flow.json"),&json!({"status":"passed","stopped_audio_clock":stopped_clock,"manual_frames":captured.len()/4,"manual_input_sha256":format!("{:x}",Sha256::digest(&captured)),"manual_start_track":5,"manual_finish_track":1,"target_BUF":2,"backing_slot":1021,"automatic_stopped_frames":full.len()/4,"automatic_LEN_completion":true,"repeat_automatic_LEN_completion":true,"cancel_preserves_previous":true,"pending_NORMAL_preserved":true,"running_NOW_still_publishes":true,"all_track_assignments_preserved":true,"NORMAL_DEST_preserved":e.peek32(dest)==Some(0),"all_memory_canaries_preserved":true,"hardware":false,"scope":"Native CPU/DSP execution with modeled external recorder PCM, card and cadence. Internal keyboard audio and physical timing unverified."}));
 eprintln!("stopped flow complete in {:.1}s",start.elapsed().as_secs_f64());
}
