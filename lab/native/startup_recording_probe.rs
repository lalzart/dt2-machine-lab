//! Startup recorder reachability survey. No guest jobs or guard writes.
mod startup_recording_trace;
use elektron_native_boot::{Emulator, RecorderPeer, sharc_peer::{SharedDsp, SharcPeer, DT2_IDLE}};
use sharc_native::Engine;
use serde_json::{Value,json};
use std::{env,fs,path::Path,time::Instant};
use startup_recording_trace::Operations;
use sha2::{Digest,Sha256};

fn read(p:impl AsRef<Path>)->Vec<u8>{fs::read(p).unwrap()}
fn save(p:impl AsRef<Path>,v:&Value){fs::write(p,serde_json::to_vec_pretty(v).unwrap()).unwrap()}
fn source()->Vec<u8>{(0..240_000i32).flat_map(|i|{let l=((i*53)%20001-10000) as i16;let r=((i*89)%16001-8000) as i16;[l.to_be_bytes(),r.to_be_bytes()].concat()}).collect()}
fn frame(e:&mut Emulator,out:&Path,name:&str){if let Some((_,b))=e.current_frame(){fs::write(out.join(format!("{name}.frame")),b).unwrap();}}
fn advance(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,n:u64,label:&str){
 let end=e.icount()+n;while e.icount()<end{let s=e.step_chunk((end-e.icount()).min(250_000) as u32).status;assert!(s.error.is_none(),"CPU fault {:?}",s.error);assert!(shared.borrow().halted.is_none());t.sample(e,label,s.ready);}
}
fn tap(e:&mut Emulator,t:&mut Operations,shared:&std::rc::Rc<std::cell::RefCell<elektron_native_boot::sharc_peer::Shared>>,key:u8,label:&str){
 e.button(key,true).unwrap();advance(e,t,shared,5_280_000,label);e.button(key,false).unwrap();advance(e,t,shared,5_280_000,label);
}
fn overlay(e:&Emulator,out:&Path){let mut b=vec![];for s in e.card_overlay(){b.extend(s.sector.to_le_bytes());b.extend(s.written);b.extend(s.data);}fs::write(out.join("verified-card.overlay"),b).unwrap();}

fn main(){
 let args:Vec<_>=env::args().collect();
 let spec:Value=serde_json::from_slice(&read(&args[1])).unwrap();
 let out=Path::new(spec["output"].as_str().unwrap());
 let start=Instant::now();let mut heartbeat=Instant::now();
 let publish=spec["mode"]=="publish";let panel=spec["mode"]=="panel"||publish;
 let sampling=spec["keys"]["SAMPLING"].as_u64().unwrap() as u8;
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
 e.enable_ssi_diagnostic(96_000).unwrap();e.set_dspi2_peer(peer.boxed());e.set_recorder_peer(RecorderPeer::new(source()).unwrap()).unwrap();
 assert!(e.run_until_pc(0x40000546,100_000_000));
 let mut trace=Operations::new(&mut e,&meta);trace.add_copy_watch(&mut e,spec["copy_return_pc"].as_u64().unwrap() as u32);trace.sample(&mut e,"reset-initialized",false);
 let mut milestones=vec![];let mut ready=None;let mut ui=None;let mut first_frame=false;let mut load_frame=false;let mut middle_frame=false;let mut early_sent=false;
 let mut retained_early:Option<Vec<u8>>=None;let mut publication=Value::Null;
 loop{
  let st=e.step_chunk(250_000).status;assert!(st.error.is_none(),"CPU fault {:?}",st.error);
  trace.sample(&mut e,"startup",st.ready);
  assert!(shared.borrow().halted.is_none(),"DSP halt");
  let loads=trace.project_loads();
  if st.frame_revision>0&&!first_frame{first_frame=true;milestones.push(json!({"event":"first_frame","icount":st.icount,"frame_source":st.frame_source,"project_loads_started":loads}));frame(&mut e,out,"first-frame");}
  if loads>0&&!load_frame{load_frame=true;milestones.push(json!({"event":"first_project_load","icount":st.icount,"main_ui_reached":st.main_ui_reached,"input_ready":st.input_ready,"input_pending":st.input_pending,"frame_source":st.frame_source}));frame(&mut e,out,"first-project-load");}
  if loads>=150&&!middle_frame{middle_frame=true;milestones.push(json!({"event":"project_load_150","icount":st.icount,"main_ui_reached":st.main_ui_reached,"input_ready":st.input_ready,"frame_source":st.frame_source}));frame(&mut e,out,"project-load-150");}
  if panel&&loads>0&&!early_sent{
   early_sent=true;milestones.push(json!({"event":"early_panel_attempt","icount":e.icount(),"project_loads_started":trace.project_loads(),"project_load_active":trace.project_active()}));
   tap(&mut e,&mut trace,&shared,sampling,"early-SAMPLING");frame(&mut e,out,"early-sampling");
   if publish {
    assert!(trace.sampler_draws()>0&&trace.external_source(),"external stock recorder must be reachable during loading");
    assert_eq!(e.peek32(dest),Some(0),"initial DEST must be NORMAL");
    for _ in 0..4{if e.peek32(dest)==Some(1){break;}e.turn(3,10).unwrap();advance(&mut e,&mut trace,&shared,7_920_000,"select-BUF1");}
    assert_eq!(e.peek32(dest),Some(1),"native C must select BUF1");frame(&mut e,out,"early-BUF1-destination");
   }
   tap(&mut e,&mut trace,&shared,10,"early-YES");frame(&mut e,out,"early-yes");
   if trace.sampler_draws()>0&&!e.recorder_peer().unwrap().active{tap(&mut e,&mut trace,&shared,10,"early-YES-manual-start");frame(&mut e,out,"early-manual-start");}
   if publish{
    assert!(e.recorder_peer().unwrap().active&&trace.external_source());
    assert_eq!(e.peek32(w+64),Some(0),"capture does not require initialized BUF playback slots");
    advance(&mut e,&mut trace,&shared,15_840_000,"early-capturing");tap(&mut e,&mut trace,&shared,10,"early-YES-stop");
    assert!(!trace.batch_returned(),"STOP must precede end of project load batch");
    assert!(!e.recorder_peer().unwrap().active);let data=e.recorder_peer().unwrap().completed.as_ref().unwrap().clone();assert!(data.len()>=141*4);retained_early=Some(data);
    frame(&mut e,out,"stopped-before-loads-finish");
    milestones.push(json!({"event":"stopped_before_batch_return","icount":e.icount(),"project_loads_started":trace.project_loads(),"completed_frames":e.recorder_peer().unwrap().captured,"BUF_playback_setup":e.peek32(w+64),"BUF_publications":e.peek32(w+80)}));
   }
   milestones.push(json!({"event":"early_panel_sent","icount":e.icount(),"input_pending":e.status().input_pending,"input_irqs":e.status().input_irqs,"project_loads_started":trace.project_loads(),"recorder_active":e.recorder_peer().unwrap().active}));
  }
  if st.main_ui_reached&&ui.is_none(){ui=Some(st.icount);milestones.push(json!({"event":"main_ui_reached","icount":st.icount,"project_loads_started":loads,"project_load_active":trace.project_active(),"frame_source":st.frame_source}));frame(&mut e,out,"main-ui-reached");}
  if st.ready&&ready.is_none(){ready=Some(st.icount);milestones.push(json!({"event":"application_ready","icount":st.icount,"project_loads_started":loads,"project_load_active":trace.project_active()}));frame(&mut e,out,"application-ready");}
  if ready.is_some_and(|n|st.icount>=n+20_000_000)&&trace.batch_returned()&&shared.borrow().lp0_pending==0&&trace.is_quiet(){break;}
  if heartbeat.elapsed().as_secs()>=30{eprintln!("CPU={} UI={} ready={} project loads={} wall={:.1}s",st.icount,st.main_ui_reached,st.ready,loads,start.elapsed().as_secs_f64());heartbeat=Instant::now();}
  assert!(st.icount<2_000_000_000&&start.elapsed().as_secs()<600,"bounded startup survey");
 }
 overlay(&e,out);
 trace.finish(&mut e,out);
 save(out.join("startup-checkpoint.json"),&json!({"milestones":milestones,"instructions":e.icount(),"project_loads":trace.project_loads(),"sampler_draws":trace.sampler_draws(),"recorder_events":e.recorder_peer().unwrap().events}));
 if panel{
  if publish{
   let data=retained_early.as_ref().unwrap();assert_eq!(e.recorder_peer().unwrap().completed.as_ref().unwrap(),data,"retained recorder take changed while remaining samples loaded");
   fs::write(out.join("captured.pcm"),data).unwrap();
   advance(&mut e,&mut trace,&shared,52_800_000,"await-native-trim");frame(&mut e,out,"retained-after-loads");
   assert_eq!(e.peek32(w+80),Some(0));assert!(trace.is_quiet());
   let kit=e.peek32(0x80004704).unwrap();let slots:Vec<_>=(0..16).map(|i|e.peek(kit+i*0x450+0x80,2).unwrap()).collect();
   let page_start=e.recorder_peer().unwrap().pages.len();
   tap(&mut e,&mut trace,&shared,10,"native-BUF-USE");
   for _ in 0..100{if e.peek32(w+80)==Some(1)&&e.peek32(w+12)==Some(0){break;}advance(&mut e,&mut trace,&shared,13_200_000,"await-BUF-publication");}
   frame(&mut e,out,"BUF-published");assert_eq!(e.peek32(w+80),Some(1),"native BUF USE did not publish");assert_eq!(e.peek32(w+12),Some(0));
   assert_eq!((0..4).map(|i|e.peek32(w+96+i*4).unwrap()).collect::<Vec<_>>(),vec![1020,1021,1022,1023]);
   let after:Vec<_>=(0..16).map(|i|e.peek(kit+i*0x450+0x80,2).unwrap()).collect();assert_eq!(slots,after,"publication must preserve track assignments");
   let descriptor:Vec<_>=(0..5).map(|i|dsp.0.borrow().peek((0x257810+1020*20+i*4) as u64,if i==4{1}else{4}).unwrap().unwrap()).collect();assert!(descriptor[2]>0);
   let mut pages=vec![];for(tag,b,h)in &e.recorder_peer().unwrap().pages[page_start..]{pages.extend(tag.to_be_bytes());pages.extend(h.to_be_bytes());pages.extend(b);}fs::write(out.join("publication-pages.bin"),pages).unwrap();
   publication=json!({"status":"passed-native-deferred-BUF-publication","BUF":1,"slot":1020,"descriptor":descriptor,"frames":data.len()/4,"PCM_sha256":format!("{:x}",Sha256::digest(data)),"assignments_preserved":true,"captured_before_BUF_setup":true,"publications":1});
  }else if e.recorder_peer().unwrap().active{
   tap(&mut e,&mut trace,&shared,10,"early-capture-STOP");
  }else{
   tap(&mut e,&mut trace,&shared,12,"postload-NO");advance(&mut e,&mut trace,&shared,52_800_000,"postload-settle");tap(&mut e,&mut trace,&shared,sampling,"postload-SAMPLING");
   for _ in 0..20{if trace.sampler_draws()>0{break;}advance(&mut e,&mut trace,&shared,13_200_000,"await-SamplerView");}
   frame(&mut e,out,"control-recorder-ready");assert!(trace.sampler_draws()>0,"SamplerView did not become accessible");
   assert!(trace.external_source(),"control needs native external-input selection");
   tap(&mut e,&mut trace,&shared,10,"postload-YES-start");
   if !e.recorder_peer().unwrap().active{frame(&mut e,out,"control-after-first-YES");tap(&mut e,&mut trace,&shared,10,"postload-YES-manual-start");}
   frame(&mut e,out,"control-after-YES");
   assert!(e.recorder_peer().unwrap().active,"postload normal recorder control failed");
   advance(&mut e,&mut trace,&shared,33_000_000,"postload-capturing");tap(&mut e,&mut trace,&shared,10,"postload-YES-stop");
  }
  advance(&mut e,&mut trace,&shared,100_000_000,"normalize-retain");frame(&mut e,out,"retained-take");
  if !publish {let peer=e.recorder_peer().unwrap();let data=peer.completed.as_ref().expect("native STOP did not retain modeled take");assert!(!data.is_empty());assert_eq!(data.as_slice(),&peer.source[..data.len()]);fs::write(out.join("captured.pcm"),data).unwrap();}
 }
 trace.finish(&mut e,out);
 let events=e.recorder_peer().unwrap().events.clone();
 if !panel{assert!(!events.iter().any(|x|x.event=="record"));}
 assert!(trace.project_loads()>=100,"fixture lacks real load batch");
 for g in meta["guards"].as_array().unwrap(){let a=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(e.peek(a,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()){
  if w["kind"]!="code"&&w["kind"]!="stock-trampoline"{continue;}
  let a=w["address"].as_u64().unwrap() as u32;let s=w["after"].as_str().unwrap();let b:Vec<_>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();assert_eq!(e.peek(a,b.len()).unwrap(),b,"CPU code changed");
 }
 save(out.join("survey.json"),&json!({"status":if publish{"completed-startup-retain-publish-probe"}else if panel{"completed-startup-panel-probe"}else{"passed-passive-startup-survey"},"milestones":milestones,"publication":publication,"instructions":e.icount(),"project_loads":trace.project_loads(),"recordings":events.iter().filter(|x|x.event=="record").count(),"recorder_events":events,"native_CPU_code_and_canaries_exact":true,"host_guard_writes":false,"card_write_commands":e.card_write_count(),"hardware":false,"scope":"Exact R4 CPU application reset, independently initialized DSP, modeled input/card/peripheral cadence; recorder-peer retention and observed owned CPU source copy are distinguished; no physical startup timing claim"}));
 eprintln!("passive startup survey complete in {:.1}s",start.elapsed().as_secs_f64());
}
