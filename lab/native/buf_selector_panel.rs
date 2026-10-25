//! Native CPU menu navigation with the preserved, independently started DSP.
use elektron_native_boot::{Emulator,RecorderPeer,sharc_peer::{SharedDsp,SharcPeer,DT2_IDLE,Shared}};
use sharc_native::Engine;
use serde_json::{Value,json};
use std::{fs,path::{Path,PathBuf},env,rc::Rc,cell::RefCell,time::Instant};
fn read(p:impl AsRef<Path>)->Vec<u8>{fs::read(p).unwrap()}
struct Panel {e:Emulator,shared:Rc<RefCell<Shared>>,out:PathBuf,checks:Vec<Value>,start:Instant,w:u32,g:u32,watch:Vec<u32>,encoder_inputs:Vec<Value>}
impl Panel {
 fn wait(&mut self,n:u64){let end=self.e.icount()+n;while self.e.icount()<end{
  let s=self.e.step_chunk((end-self.e.icount()).min(250_000) as u32).status;
  assert!(s.error.is_none(),"CPU error {s:?}");assert!(self.shared.borrow().halted.is_none());
  assert!(self.start.elapsed().as_secs()<600,"bounded panel survey timed out");
 }}
 fn tap(&mut self,k:u8){self.e.button(k,true).unwrap();self.wait(5_280_000);self.e.button(k,false).unwrap();self.wait(5_280_000);}
 fn turn(&mut self,d:i32){self.encoder_inputs.push(json!({"icount":self.e.icount(),"encoder":4,"packet_delta":d}));self.e.turn(4,d).unwrap();self.wait(10_560_000);}
 fn slot(&mut self)->u32{let kit=self.e.peek32(0x80004704).unwrap();u16::from_be_bytes(self.e.peek(kit+0x80,2).unwrap().try_into().unwrap()) as u32}
 fn check(&mut self,label:&str,want:u32){let got=self.slot();self.screen(label);
  let(hits,dropped)=self.e.reg_log();let hits=hits.to_vec();let rows:Vec<_>=hits.iter().take(2000).map(|h|json!({"pc":h.pc,"d":h.d,"a":h.a,"stack":h.stack})).collect();self.e.record_regs_at(&self.watch);
  let row=json!({"name":label,"actual_slot":got,"setup":self.e.peek32(self.w+64),"logical_n":(0..4).map(|i|self.e.peek32(self.g+32+i*4)).collect::<Vec<_>>(),"trace":rows,"dropped":dropped,"view_snapshot":hits.iter().find(|h|h.pc==self.watch[4]).map(|h|self.e.peek(h.stack[1],0xe0))});
  self.checks.push(row);fs::write(self.out.join("live.json"),serde_json::to_vec_pretty(&self.checks).unwrap()).unwrap();assert_eq!(got,want,"{label}");eprintln!("{label}: {got}");}
 fn screen(&mut self,n:&str){if let Some((_,f))=self.e.current_frame(){fs::write(self.out.join(format!("{n}.frame")),f).unwrap();}}
 fn opening(&mut self,label:&str,want:u32,rank:u32){
  let(hits,_)=self.e.reg_log();
  let view=hits.iter().rev().find(|h|h.pc==self.watch[5]).expect("constructor initial cursor").a[2];
  let cursor=hits.iter().rev().find(|h|h.pc==0x40114d80&&h.stack[1]==view+0x4c).expect("native initial menu cursor");
  assert_eq!(cursor.stack[2],rank,"{label} cursor");assert_eq!(cursor.stack[3],0,"{label} must not notify sample assignment");
  self.check(label,want);
 }
}
fn main(){let args:Vec<_>=env::args().collect();let spec:Value=serde_json::from_slice(&read(&args[1])).unwrap();let out=PathBuf::from(spec["output"].as_str().unwrap());
 let input=Path::new(spec["reset_input"].as_str().unwrap());let mut eng=Engine::from_image(&read(input.join("image.bin"))).unwrap();eng.import(&read(input.join("reset.state"))).unwrap();
 for(k,v)in[(1,0),(4,1),(5,1),(9,1),(21,1),(22,1)]{assert_eq!(eng.set_option(k,v),0);}
 let mut idle=0;while eng.s.icount<400_000_000{eng.step(250_000);assert!(eng.halt.is_none());if (DT2_IDLE.range.0..DT2_IDLE.range.1).contains(&(eng.s.pc_sw as u32)){idle+=1;}else{idle=0;}if idle==8{break;}}assert_eq!(idle,8);
 for(k,v)in[(23,DT2_IDLE.head),(24,DT2_IDLE.range.0),(25,DT2_IDLE.range.1)]{assert_eq!(eng.set_option(k,v as i64),0);}
 let dsp=SharedDsp::new(eng);let(mut peer,shared)=SharcPeer::new(dsp,666_667);peer.set_idle_range(DT2_IDLE.range);peer.enable_sample_link();
 let card=elektron_native_boot::card_file::card_from_image(Path::new(spec["card"].as_str().unwrap())).unwrap();
 let mut e=Emulator::new_patched_with_reference(&read(spec["candidate"].as_str().unwrap()),Some(card),&read(spec["stock_syx"].as_str().unwrap())).unwrap();
 e.enable_ssi_diagnostic(96_000).unwrap();e.set_dspi2_peer(peer.boxed());e.set_recorder_peer(RecorderPeer::new(vec![0;48000*4]).unwrap()).unwrap();
 let meta:Value=serde_json::from_slice(&read(spec["metadata"].as_str().unwrap())).unwrap();
 let arena=|name:&str|meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]==name).unwrap()["destination"].as_u64().unwrap() as u32;
 let w=arena("worker");let g=arena("generations");let b=arena("next_bar");let dest=arena("destination");let watch=vec![b+0x6100,b+0x6400,b+0x6700,b+0x6900,b+0x6a00,b+0x6c00,b+0x6d00,b+0x6f00,b+0x7200,b+0x7600,b+0x7800,b+0x7c00,b+0x78b4,b+0x7900,0x400187c4,0x400173ba,0x40111b62,b+0x7c64,b+0x7c76,0x40114d80];
 let mut p=Panel{e,shared,out:out.clone(),checks:vec![],start:Instant::now(),w,g,watch,encoder_inputs:vec![]};
 for _ in 0..6000 {p.wait(250_000);if p.e.status().ready&&p.shared.borrow().lp0_units>0&&p.shared.borrow().lp0_pending==0{break;}}
 assert!(p.e.status().ready);
 for h in meta["hooks"].as_array().unwrap(){if h["label"].as_str().unwrap().starts_with("buf-selector/"){let hex=h["after"].as_str().unwrap();let bytes:Vec<u8>=(0..hex.len()).step_by(2).map(|i|u8::from_str_radix(&hex[i..i+2],16).unwrap()).collect();assert_eq!(p.e.peek(h["address"].as_u64().unwrap() as u32,bytes.len()).unwrap(),bytes);}}
 p.wait(52_800_000);eprintln!("ready at {}",p.e.icount());p.tap(12);p.tap(2);
 let original=p.slot();assert!(original<128,"fixture T1 bank changed");assert_eq!(p.e.peek32(dest),Some(0),"recorder default must be NORMAL");p.e.record_regs_at(&p.watch);p.tap(44);p.opening("01-open",original,original+4);let scaler_timer=p.e.peek(b+0x7314,8).unwrap();assert_eq!(p.e.peek32(b+0x7484),Some(1));
 for _ in 0..original {p.tap(11);}p.check("02-A00",0);
 let logical:Vec<_>=(0..4).map(|i|p.e.peek32(w+96+i*4).unwrap()).collect();assert!(logical.iter().all(|&s|s>0&&s<1024));
 for i in 0..4{p.tap(11);p.check(&format!("03-BUF-{}",i+1),logical[i]);}p.tap(11);p.check("04-clamp-BUF4",logical[3]);
 for i in (0..3).rev(){p.tap(14);p.check(&format!("05-down-BUF-{}",i+1),logical[i]);}
 p.tap(14);p.check("06-A00",0);p.tap(14);p.check("07-A01",1);p.tap(12);p.check("08-NO-restores-original",original);
 p.tap(44);for _ in 0..original+1{p.tap(11);}p.check("09-BUF1-again",logical[0]);p.tap(10);p.check("10-YES-retains-BUF1",logical[0]);p.tap(44);p.opening("11-reopen-BUF1",logical[0],3);p.tap(14);p.check("12-reopen-down-to-A00",0);
 p.tap(15);p.check("13-B00",128);p.tap(13);p.check("14-back-A00",0);p.tap(12);p.check("15-NO-restores-BUF1",logical[0]);
 p.tap(44);p.tap(13);p.check("20-BUF-left-clamps",logical[0]);p.tap(15);p.check("21-BUF-right-B00",128);p.tap(13);p.check("22-B00-left-A00",0);p.tap(12);p.check("23-bank-NO-restores-BUF1",logical[0]);
 p.tap(44);for _ in 0..8 {p.turn(-10);if p.slot()!=logical[0]{break;}}p.check("16-encoder-BUF2",logical[1]);for _ in 0..8 {p.turn(-40);if p.slot()==logical[3]{break;}}p.check("17-fast-clamp-BUF4",logical[3]);for _ in 0..8 {p.turn(40);if p.slot()<128{break;}}let fast=p.slot();assert!(fast<128);p.check("18-fast-valid-A",fast);p.tap(12);p.check("19-encoder-NO-restores-BUF1",logical[0]);
 p.tap(44);p.tap(14);p.tap(15);let normal_b=p.slot();assert!(normal_b>=128&&normal_b<256);for _ in 0..8 {p.turn(10);if p.slot()>normal_b {break;}}let moved_b=p.slot();assert!(moved_b>normal_b&&moved_b<256);p.check("24-native-B-encoder",moved_b);p.tap(12);p.check("25-B-encoder-NO-restores-BUF1",logical[0]);
 p.tap(44);p.tap(14);p.tap(10);p.check("26-YES-keeps-OFF",0);p.tap(44);p.opening("27-reopen-OFF",0,4);p.tap(12);p.check("28-NO-keeps-OFF",0);assert_eq!(p.e.peek32(dest),Some(0),"browsing must preserve recorder NORMAL");
 for w in meta["writes"].as_array().unwrap(){if w["label"].as_str().unwrap().starts_with("buf-selector/")&&w["kind"]=="code"{let hex=w["after"].as_str().unwrap();let bytes:Vec<u8>=(0..hex.len()).step_by(2).map(|i|u8::from_str_radix(&hex[i..i+2],16).unwrap()).collect();assert_eq!(p.e.peek(w["address"].as_u64().unwrap() as u32,bytes.len()).unwrap(),bytes);}}

 assert_eq!(p.e.peek(b+0x7314,8).unwrap(),scaler_timer,"scaler timer replaced during menu rebuild");
 assert_eq!(p.e.peek32(w+80),Some(0));assert!(!p.e.recorder_peer().unwrap().active);assert!(p.e.recorder_peer().unwrap().completed.is_none());
 for g in meta["guards"].as_array().unwrap(){let at=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;assert_eq!(p.e.peek(at,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8));}
 fs::write(out.join("panel.json"),serde_json::to_vec_pretty(&json!({"status":"passed-native-selector-panel","checks":p.checks,"encoder_inputs":p.encoder_inputs,"logical":logical,"recordings":0,"publications":0,"hardware":false,"scope":"Native CPU/DSP application startup, modeled card and transport; no ROM or physical timing claim"})).unwrap()).unwrap();
}
