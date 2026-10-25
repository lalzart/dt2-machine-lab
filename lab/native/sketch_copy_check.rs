//! Native panel COPY/PASTE after the established startup take, with one replacement.
use elektron_native_boot::{Emulator, sharc_peer::Shared};
use serde_json::{Value,json};
use std::{cell::RefCell,rc::Rc,path::Path,fs};
use crate::startup_capture_trace::Operations;

pub fn run(e:&mut Emulator,t:&mut Operations,shared:&Rc<RefCell<Shared>>,spec:&Value){
 let out=Path::new(spec["output"].as_str().unwrap());
 let symbols=&spec["symbols"];
 let field=|layer:&str,name:&str| symbols[layer][name].as_u64().unwrap() as u32;
 let cs=field("clip","STATE");let ss=field("s","STATE");let ns=field("nb","STATE");let ws=field("w","STATE");
 let addr=|name:&str|cs+field("clip",name);
 let advance=|e:&mut Emulator,t:&mut Operations,n:u64,label:&str|crate::advance(e,t,shared,n,label);
 let tap=|e:&mut Emulator,t:&mut Operations,key:u8,label:&str|crate::tap(e,t,shared,key,label);
 let chord=|e:&mut Emulator,t:&mut Operations,key:u8,label:&str|{
  e.button(17,true).unwrap();crate::advance(e,t,shared,2_640_000,label);
  crate::tap(e,t,shared,key,label);e.button(17,false).unwrap();crate::advance(e,t,shared,2_640_000,label);
 };
 let slot=|e:&mut Emulator,kit:u32,track:u32|{let b=e.peek(kit+track*0x450+0x80,2).unwrap();u16::from_be_bytes([b[0],b[1]])};
 let kit=e.peek32(0x80004704).unwrap();let before=e.peek(kit,16*0x450).unwrap();
 let meta:Value=serde_json::from_slice(&fs::read(spec["metadata"].as_str().unwrap()).unwrap()).unwrap();
 let arena=|name:&str|meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]==name).unwrap()["destination"].as_u64().unwrap() as u32;
 let snapshots=arena("generations")+4;let queued=arena("freeze_queue")+36;
 chord(e,t,19,"Sketch-COPY-A");
 for _ in 0..400 {if e.peek32(addr("VALID"))==Some(1){break;}advance(e,t,250_000,"wait-COPY");}
 let observed_slot=e.peek32(addr("SLOT")).unwrap();let observed_desc=e.peek32(addr("DESCRIPTOR")).unwrap();let observed_pool=e.peek32(ws+68).unwrap();
 fs::write(out.join("copy-checkpoint.json"),serde_json::to_vec_pretty(&json!({"clipboard":e.peek(cs,48).unwrap(),"action":e.peek32(ss+field("s","ACTION")),"snapshot":e.peek(observed_desc,64).ok(),"pool_key":e.peek(observed_pool+observed_slot*16,16).ok(),"cache_key":e.peek(0x405b1368+observed_slot*16,16).ok()})).unwrap()).unwrap();
 assert_eq!(e.peek32(addr("VALID")),Some(1),"COPY must complete through native worker");
 let take=e.peek32(addr("SLOT")).unwrap();let snap=e.peek32(addr("DESCRIPTOR")).unwrap();let frozen=e.peek(snap,64).unwrap();
 assert!((1..1020).contains(&take));
 assert_eq!(e.peek32(snapshots),Some(1));assert_eq!(e.peek32(queued),Some(1));
 assert_eq!(before,e.peek(kit,16*0x450).unwrap(),"COPY may not assign tracks");
 crate::frame(e,out,"copy-ready");
 let transport=||[0x43164f94u32,0x43165010u32];
 assert!(transport().into_iter().any(|a|e.peek32(a).unwrap()!=0));
 // Select T1 through native TRK+trig. This closes Sketch, whose clipboard survives.
 e.button(16,true).unwrap();advance(e,t,2_640_000,"TRK-down");tap(e,t,25,"select-T1");e.button(16,false).unwrap();advance(e,t,2_640_000,"TRK-up");
 tap(e,t,24,"reopen-Sketch-for-PASTE");
 chord(e,t,21,"Sketch-PASTE-T1");
 fs::write(out.join("paste-checkpoint.json"),serde_json::to_vec_pretty(&json!({"clipboard":e.peek(cs,48).unwrap(),"action":e.peek32(ss+field("s","ACTION")),"actual_slot":slot(e,kit,0)})).unwrap()).unwrap();
 assert_eq!(slot(e,kit,0),take as u16,"PASTE uses native parameter context/setter");
 assert_eq!(e.peek32(ss+field("s","ACTION")),Some(field("clip","PASTED")));
 assert!(transport().into_iter().any(|a|e.peek32(a).unwrap()!=0),"FUNC+STOP must preserve PLAY");
 crate::frame(e,out,"paste-track-1");
 // Replace BUF with different modeled input; COPY's immutable snapshot remains.
 e.recorder_peer_mut().unwrap().source=crate::source().chunks_exact(2).flat_map(|b|(-i16::from_be_bytes([b[0],b[1]])).to_be_bytes()).collect();
 let starts=e.peek32(ns+field("nb","STARTS")).unwrap();let uses=e.peek32(ns+field("nb","USES")).unwrap();
 chord(e,t,24,"ARM-replacement-B");
 assert_eq!(e.peek32(ns+field("nb","STARTS")),Some(starts+1));
 let cancels=e.peek32(ns+field("nb","CANCELS")).unwrap();
 chord(e,t,21,"busy-PASTE-during-capture");
 assert_eq!(e.peek32(ns+field("nb","CANCELS")),Some(cancels),"PASTE must not cancel the capture");
 assert_eq!(e.peek32(ss+field("s","ACTION")),Some(field("clip","PASTE_BUSY")));
 for _ in 0..1600 {if e.peek32(ns)==Some(0)&&e.peek32(ns+field("nb","USES"))==Some(uses+1){break;}advance(e,t,250_000,"wait-replacement-B");}
 assert_eq!(e.peek32(ns+field("nb","USES")),Some(uses+1));
 assert_eq!(e.peek(snap,64).unwrap(),frozen,"recording B must preserve snapshot A");
 assert_ne!(e.recorder_peer().unwrap().completed.as_ref().unwrap().as_slice(),fs::read(out.join("captured.pcm")).unwrap().as_slice(),"replacement input must differ from A");
 assert_eq!(e.peek32(addr("SLOT")),Some(take));
 e.button(16,true).unwrap();advance(e,t,2_640_000,"TRK-down");tap(e,t,29,"select-T5");e.button(16,false).unwrap();advance(e,t,2_640_000,"TRK-up");
 // Outside Sketch, the original SRC page must own COPY/PASTE. Observe its
 // authentic service entries; do not substitute a clipboard or success value.
 tap(e,t,2,"stock-SRC");t.add_clipboard_watches(e);
 for (key,label) in [(19,"stock-SRC-COPY"),(21,"stock-SRC-PASTE")] {
  e.button(2,true).unwrap();advance(e,t,2_640_000,"hold-SRC-for-page-clipboard");tap(e,t,key,label);e.button(2,false).unwrap();advance(e,t,2_640_000,"release-SRC");
 }
 assert_eq!(t.clipboard_calls("clipboard/SRC-copy"),1);assert_eq!(t.clipboard_calls("clipboard/SRC-paste"),1);
 assert_eq!(e.peek32(snapshots),Some(1));assert_eq!(e.peek32(queued),Some(1));
 tap(e,t,24,"reopen-Sketch-T5");chord(e,t,21,"Sketch-PASTE-A-T5");chord(e,t,21,"repeat-PASTE-A-T5");
 assert_eq!(slot(e,kit,4),take as u16);assert_eq!(slot(e,kit,0),take as u16);
 assert_eq!(e.peek32(addr("TARGET")),Some(5));
 assert_eq!(e.peek(snap,64).unwrap(),frozen);
 assert_eq!(e.peek32(snapshots),Some(1));assert_eq!(e.peek32(queued),Some(1));
 assert_eq!(e.peek32(field("w","DEST")),Some(0));
 for track in 0..16u32 {if track!=0&&track!=4 {assert_eq!(&before[track as usize*0x450+0x80..track as usize*0x450+0x82],&(slot(e,kit,track).to_be_bytes()),"unrelated assignment");}}
 assert_eq!(e.peek32(ws+80),Some(2));
 assert!(transport().into_iter().any(|a|e.peek32(a).unwrap()!=0));
 crate::frame(e,out,"paste-track-5-after-B");
 advance(e,t,26_400_000,"copy-flow-settle");
 fs::write(out.join("copy-flow.json"),serde_json::to_vec_pretty(&json!({"status":"passed","copied_slot":take,"snapshot_descriptor":snap,"two_native_captures":true,"paste_tracks":[1,5],"repeat_paste":true,"one_snapshot_and_one_job":true,"stock_SRC_clipboard_copy_and_paste_executed":true,"busy_paste_preserves_capture":true,"NORMAL_preserved":true,"other_assignments_preserved":true,"snapshot_A_survives_B":true,"snapshot_A":frozen,"hardware":false,"layer":"Native CPU/DSP application with modeled recorder/card/cadence; native input, worker and stock parameter setter"})).unwrap()).unwrap();
}
