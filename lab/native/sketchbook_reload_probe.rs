//! Independent stock CPU cold boot and original loader from a durable card image.
use elektron_native_boot::{Emulator,GuestCall};
use serde_json::{Value,json};
use std::{env,fs,path::Path,time::Instant};
fn main(){
 let args:Vec<_>=env::args().collect();let p=Path::new(&args[1]);let s:Value=serde_json::from_slice(&fs::read(p.join("spec.json")).unwrap()).unwrap();
 let card=elektron_native_boot::card_file::card_from_image(Path::new(s["card"].as_str().unwrap())).unwrap();
 let mut e=Emulator::new(&fs::read(s["stock_syx"].as_str().unwrap()).unwrap(),Some(card)).unwrap();e.relax_fs_check();
 let start=Instant::now();let mut first=None;
 loop {let r=e.step_chunk(250_000).status;assert!(r.error.is_none(),"{:?}",r.error);if r.main_ui_reached&&first.is_none(){first=Some(e.icount());}
 if first.is_some_and(|n|e.icount()>n+500_000_000)&&e.peek32(0x405b1360)==Some(0){break;}assert!(e.icount()<1_800_000_000);}
 eprintln!("Independent stock CPU ready at {} in {:.1}s",e.icount(),start.elapsed().as_secs_f64());
 let mut reports=vec![];
 for (i,r) in s["saves"].as_array().unwrap().iter().take(2).enumerate(){
  let reference:Vec<u8>=r["reference"]["Ok"].as_array().unwrap().iter().map(|v|v.as_u64().unwrap() as u8).collect();let slot=1000+i as u32;
  e.capture_at(&[(0x400cd638,1,4096)]);let before=e.calls_pending().1;
  e.queue_call(GuestCall{at:0x40033d00,func:0x40154540,args:vec![GuestCall::STACK,slot],data:vec![(GuestCall::STACK,reference.clone())]});
  let began=e.icount();while e.calls_pending().1==before {let r=e.step_chunk(250_000).status;assert!(r.error.is_none(),"{:?}",r.error);assert!(e.icount()-began<500_000_000);}
  let key=e.peek(0x405b1368+slot*16,16).unwrap();assert_eq!(key,reference);
  let captures=e.take_captures();assert!(!captures.is_empty());let mut pages=vec![];
  for c in &captures {pages.extend(c.args[0].to_be_bytes());pages.extend(c.args[2].to_be_bytes());assert_eq!(c.bytes.len(),4096);pages.extend(&c.bytes);}
  fs::write(p.join(format!("load-{i}.pages")),&pages).unwrap();
  reports.push(json!({"slot":slot,"key":key,"length":e.peek32(0x405ba768+slot*4),"rate":e.peek32(0x405bb768+slot*4),"stereo":e.peek(0x405ba368+slot,1),"pages":captures.len(),"call_returned":true}));
 }
 fs::write(p.join("reload.json"),serde_json::to_vec_pretty(&json!({"status":"native-loads-returned","stock_CPU_cold_boot":true,"loads":reports,"elapsed_seconds":start.elapsed().as_secs_f64(),"scope":"Independent stock CPU with modeled card/DSPI2 (zero reply). Original loader bytes/pages are observed, not supplied by the host."})).unwrap()).unwrap();
}
