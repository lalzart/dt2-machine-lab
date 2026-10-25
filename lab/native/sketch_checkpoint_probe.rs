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

 let val=|e:&mut Emulator,layer:&str,key:&str|e.peek32(symbols[layer]["STATE"].as_u64().unwrap() as u32+field(layer,key)).unwrap();
 let open=|e:&mut Emulator,t:&mut Operations|{if val(e,"s","VIEW")==0 {tap(e,t,&shared,24,"open-Sketch");}assert_ne!(val(e,"s","VIEW"),0);};
 let set_mode=|e:&mut Emulator,t:&mut Operations,want:u32|{for _ in 0..10{if val(e,"s","START_MODE")==want {break;}e.turn(6,if want==1{10}else{-10}).unwrap();advance(e,t,&shared,5_280_000,"F-BAR-NOW");}assert_eq!(val(e,"s","START_MODE"),want);advance(e,t,&shared,26_400_000,"settle-mode-title");};
 let kit=e.peek32(0x80004704).unwrap();let assignments=e.peek(kit,16*0x450).unwrap();
 open(&mut e,&mut trace);assert_eq!(val(&mut e,"s","START_MODE"),0);assert_eq!(val(&mut e,"s","BUF"),1);
 for _ in 0..20 {let object=val(&mut e,"s","VIEW");let wrap=e.peek32(object+field("s","SETTINGS")).unwrap();let inner=e.peek32(wrap+16).unwrap();let len=e.peek32(inner+0x1ba).unwrap();if len==4{break;}e.turn(4,if len>4{-10}else{10}).unwrap();advance(&mut e,&mut trace,&shared,3_960_000,"LEN16");}

 let mut led_checks=vec![];
 let observe=|e:&mut Emulator,label:&str,want:u8,checks:&mut Vec<Value>| {
  let(rev,hex,rgb)=e.current_leds();let actual=u8::from_str_radix(&hex[8..10],16).unwrap();
  save(out.join("last-led.json"),&json!({"label":label,"song":actual,"leds":hex,"phase":val(e,"nb","PHASE")}));
  assert_eq!(actual,want,"SONG LED at {label}");checks.push(json!({"label":label,"song":actual,"revision":rev,"leds":hex,"rgb":rgb,"phase":val(e,"nb","PHASE"),"view":val(e,"s","VIEW")}));
 };
 tap(&mut e,&mut trace,&shared,2,"SRC-stopped");advance(&mut e,&mut trace,&shared,26_400_000,"idle-LED");observe(&mut e,"idle",1,&mut led_checks);
 chord(&mut e,&mut trace,24,"stopped-capture-from-SRC");advance(&mut e,&mut trace,&shared,26_400_000,"capture-LED");assert_eq!(val(&mut e,"nb","PHASE"),2);observe(&mut e,"stopped-capture-outside-Sketch",0x11,&mut led_checks);
 open(&mut e,&mut trace);advance(&mut e,&mut trace,&shared,26_400_000,"Sketch-capture-LED");observe(&mut e,"stopped-capture-inside-Sketch",0x11,&mut led_checks);
 tap(&mut e,&mut trace,&shared,25,"leave-Sketch-during-capture");advance(&mut e,&mut trace,&shared,26_400_000,"exit-capture-LED");assert_eq!(val(&mut e,"nb","PHASE"),2);observe(&mut e,"capture-after-trig-exit",0x11,&mut led_checks);
 tap(&mut e,&mut trace,&shared,12,"cancel-capture");advance(&mut e,&mut trace,&shared,26_400_000,"cancel-LED");assert_eq!(val(&mut e,"nb","PHASE"),0);assert_eq!(val(&mut e,"nb","USES"),0);observe(&mut e,"cancelled",1,&mut led_checks);

 // Exercise real BAR admission from outside Sketch and complete one take.
 open(&mut e,&mut trace);set_mode(&mut e,&mut trace,0);tap(&mut e,&mut trace,&shared,2,"leave-Sketch-for-BAR");
 tap(&mut e,&mut trace,&shared,20,"PLAY");advance(&mut e,&mut trace,&shared,26_400_000,"qualify-running-clock");assert_eq!(val(&mut e,"nb","VALID"),1);
 open(&mut e,&mut trace);set_mode(&mut e,&mut trace,1);frame(&mut e,out,"05a-playing-NOW");set_mode(&mut e,&mut trace,0);frame(&mut e,out,"05b-playing-BAR");tap(&mut e,&mut trace,&shared,2,"SRC-global-BAR");
 for _ in 0..1600 {let step=e.peek32(0x43164f98).unwrap()>>16;if (4..=8).contains(&step){break;}advance(&mut e,&mut trace,&shared,250_000,"middle-of-bar");}
 let serial=val(&mut e,"nb","SERIAL");let starts=val(&mut e,"nb","STARTS");chord(&mut e,&mut trace,24,"global-next-BAR");assert_eq!(val(&mut e,"nb","PHASE"),1);assert_eq!(val(&mut e,"nb","STARTS"),starts);assert_eq!(val(&mut e,"nb","START_MODE"),0);
 observe(&mut e,"waiting-for-BAR",1,&mut led_checks);
 for _ in 0..2500 {if val(&mut e,"nb","STARTS")==starts+1{break;}advance(&mut e,&mut trace,&shared,250_000,"wait-next-native-bar");}
 assert_eq!(val(&mut e,"nb","STARTS"),starts+1);assert!(val(&mut e,"nb","SERIAL")>serial);open(&mut e,&mut trace);frame(&mut e,out,"05-BAR-recording");tap(&mut e,&mut trace,&shared,25,"leave-during-BAR-capture");assert_eq!(val(&mut e,"s","VIEW"),0);assert_eq!(val(&mut e,"nb","PHASE"),2);
 advance(&mut e,&mut trace,&shared,26_400_000,"BAR-capture-LED");assert_eq!(val(&mut e,"nb","PHASE"),2);observe(&mut e,"BAR-capture-outside-Sketch",0x11,&mut led_checks);
 for _ in 0..3000 {if val(&mut e,"nb","USES")==1&&val(&mut e,"nb","PHASE")==0{break;}advance(&mut e,&mut trace,&shared,250_000,"BAR-record-and-publish");}
 assert_eq!(val(&mut e,"nb","USES"),1);let pcm=trace.completed_pcm().to_vec();assert!(pcm.len()>100_000*4&&pcm.iter().any(|&b|b!=0));fs::write(out.join("BAR-capture.pcm"),&pcm).unwrap();assert!(e.recorder_peer().unwrap().completed.is_none());
 advance(&mut e,&mut trace,&shared,26_400_000,"published-LED");observe(&mut e,"published",1,&mut led_checks);
 tap(&mut e,&mut trace,&shared,21,"STOP-after-publication");open(&mut e,&mut trace);advance(&mut e,&mut trace,&shared,26_400_000,"final-ready-LCD");frame(&mut e,out,"06-ready-BAR-remembered");assert_eq!(val(&mut e,"s","START_MODE"),0);assert_eq!(e.peek32(dest),Some(0));
 let after=e.peek(kit,16*0x450).unwrap();for track in 0..16 {assert_eq!(&assignments[track*0x450+0x80..track*0x450+0x82],&after[track*0x450+0x80..track*0x450+0x82]);}
 for g in meta["guards"].as_array().unwrap(){let a=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(e.peek(a,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 trace.checkpoint(&mut e,out,true);

 save(out.join("flow.json"),&json!({"status":"passed","BAR_waits_for_native_next_bar":true,"BAR_capture_published":true,"BAR_frames":pcm.len()/4,"global_BAR_from_SRC":true,"playing_BAR_NOW_changes":true,"exit_during_capture_preserved":true,"NORMAL_preserved":true,"assignments_preserved":true,"canaries_intact":true,"starts":val(&mut e,"nb","STARTS"),"uses":val(&mut e,"nb","USES"),"cancels":val(&mut e,"nb","CANCELS"),"hardware":false,"LED_checks":led_checks,"SONG_red_only_during_capture":true,"scope":"Native CPU/DSP capture with UART8 LED records; recorder PCM/card/cadence modeled. Physical panel color and timing unverified."}));
 eprintln!("SONG LED flow passed in {:.1}s",start.elapsed().as_secs_f64());
}
