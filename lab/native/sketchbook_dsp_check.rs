//! Direct instruction fixtures for the target readback emitter.
//! Fixture headers/PCM are injected here; whole-recording save proof is separate.
use sharc_native::{Engine,rt::V};
use serde_json::{Value,json};
use std::{env,fs,path::Path};
fn word(e:&Engine,a:u64,n:u32)->u32 {e.peek(a,n).unwrap().unwrap()}
fn put(e:&mut Engine,a:u64,v:u32){assert_eq!(e.poke(a,&v.to_le_bytes(),4),1);}
fn segment(e:&mut Engine,start:u32,stop:u32){e.set_option(8,stop as i64);e.fresh_call(start,None);e.step(1_000_000);assert_eq!(e.s.pc_sw,stop as i128,"at {start:#x}, {:?}",e.halt);e.set_option(8,-1);}
fn fnv(a:&[u8])->u32{a.iter().fold(2166136261u32,|h,b|(h^*b as u32).wrapping_mul(16777619))}
fn main(){
 let args:Vec<_>=env::args().collect();let p=Path::new(&args[1]);let spec:Value=serde_json::from_slice(&fs::read(p.join("spec.json")).unwrap()).unwrap();
 let input=Path::new(spec["inputs"].as_str().unwrap());let mut e=Engine::from_image(&fs::read(input.join("image.bin")).unwrap()).unwrap();
 e.import(&fs::read(input.join("reset.state")).unwrap()).unwrap();for(k,v)in[(1,0),(4,1),(5,1),(21,1),(22,1)]{assert_eq!(e.set_option(k,v),0);}
 for v in e.s.r.iter_mut(){*v=V::c(0);}
 let state=0x200f8400u64;let req=0x268244u64;let slot=1019u32;let desc=0x257810u64+slot as u64*20;
 put(&mut e,req-4,0x534b5231);
 let frame=spec["symbols"]["readback_frame_hook"].as_u64().unwrap() as u32;let event=spec["symbols"]["readback_event_hook"].as_u64().unwrap() as u32;
 let mut cases=vec![];let mut serial=0u32;
 for stereo in [0u32,1]{
  let frames=3000u32;let len=frames*2;let left=0x2020u32;let right=0x4020u32;
  let mut expected=vec![];let mut l=vec![];let mut r=vec![];
  for i in 0..frames as i32 {let a=((i*53)%20001-10000) as i16;let b=((i*89)%16001-8000) as i16;l.extend(a.to_le_bytes());r.extend(b.to_le_bytes());expected.extend(a.to_be_bytes());if stereo==1{expected.extend(b.to_be_bytes());}}
  assert_eq!(e.poke(0x8422b9c8+left as u64,&l,1),l.len() as i32);assert_eq!(e.poke(0x8422b9c8+right as u64,&r,1),r.len() as i32);
  for(i,v)in[left,right,len,48000,stereo].iter().enumerate(){put(&mut e,desc+i as u64*4,*v);}
  for(pos,count)in[(0,4096),(1,1),(13,17),(2,225),(511,512),(0,224)]{
   serial+=1;let q=[0x534b5231,1,2,0x7ffb0003,serial,slot,0x2400,0x8000,len,48000,stereo,pos,count,!serial,0,0x534b4342];
   for(i,v)in q.iter().enumerate(){put(&mut e,req+i as u64*4,*v);}
   e.set_reg(4,V::c(0));segment(&mut e,event,0x1c7e43);
   assert_eq!(word(&e,state+4*4,4),serial,"latch rejected valid request");
   let mut got:Vec<u8>=vec![];while got.len()<count as usize{
    let reply=if got.len()%448==0{0x266220u64}else{0x267220u64};
    let original=vec![0xa5u8;2748];e.poke(reply,&original,1);e.set_reg(20,V::c(reply as i128));segment(&mut e,frame,0xbe0000);
    let prefix:Vec<_>=(0..2748).map(|i|word(&e,reply+i,1) as u8).collect();assert_eq!(prefix,original,"stock prefix was modified");
    let physical:Vec<_>=(0..260).map(|i|word(&e,reply+2748+i,1) as u8).collect();let wire:Vec<_>=physical.chunks_exact(2).flat_map(|b|[b[1],b[0]]).collect();
    let w=|o:usize|u32::from_be_bytes(wire[o..o+4].try_into().unwrap());
    assert_eq!([w(0),w(4),w(8),w(12),w(16),w(20),w(28)],[0x534b5231,serial,2,0x7ffb0003,pos,got.len() as u32,0]);
    let n=w(24) as usize;assert!(n>0&&n<=224);assert_eq!(w(32),fnv(&[&wire[..32],&wire[36..36+n]].concat()));got.extend(&wire[36..36+n]);
   }
   assert_eq!(got,expected[pos as usize..(pos+count) as usize],"PCM mismatch stereo={stereo} pos={pos} count={count}");
   cases.push(json!({"stereo":stereo,"position":pos,"count":count,"exact_pcm":true}));
  }
 }
 let before=word(&e,state,4);put(&mut e,req+4*4,serial);e.set_reg(4,V::c(0));segment(&mut e,event,0x1c7e43);assert_eq!(word(&e,state,4),before,"stale request mutated revision");
 put(&mut e,desc+8,0);e.set_reg(20,V::c(0x266220));segment(&mut e,frame,0xbe0000);
 let raw:Vec<_>=(0..260).map(|i|word(&e,0x266220+2748+i,1) as u8).collect();let wire:Vec<_>=raw.chunks_exact(2).flat_map(|b|[b[1],b[0]]).collect();
 assert_eq!(u32::from_be_bytes(wire[24..28].try_into().unwrap()),0);assert_ne!(u32::from_be_bytes(wire[28..32].try_into().unwrap()),0);
 put(&mut e,state+31*4,1);e.set_reg(20,V::c(0x266220));segment(&mut e,frame,0xbe0000);assert_eq!(word(&e,0x266220+2748,4),0,"disabled emitter published data");
 serial+=1;let q=[0x534b5231,2,2,0x7ffb0003,serial,u32::MAX,0,0,0,0,0,0,0,!serial,0,0x534b4342];
 for(i,v)in q.iter().enumerate(){put(&mut e,req+i as u64*4,*v);}
 e.set_reg(4,V::c(0));segment(&mut e,event,0x1c7e43);
 e.set_reg(20,V::c(0x266220));segment(&mut e,frame,0xbe0000);
 let raw:Vec<_>=(0..260).map(|i|word(&e,0x266220+2748+i,1) as u8).collect();let wire:Vec<_>=raw.chunks_exact(2).flat_map(|b|[b[1],b[0]]).collect();
 assert_eq!(u32::from_be_bytes(wire[4..8].try_into().unwrap()),serial);
 assert_eq!(u32::from_be_bytes(wire[24..28].try_into().unwrap()),0);assert_eq!(u32::from_be_bytes(wire[28..32].try_into().unwrap()),2);
 assert_eq!(u32::from_be_bytes(wire[32..36].try_into().unwrap()),fnv(&wire[..32]));
 fs::write(p.join("dsp-check.json"),serde_json::to_vec_pretty(&json!({"status":"passed","cases":cases,"stale_request_preserved":true,"changed_header_refuses":true,"stock_prefix_exact":true,"scope":"Native SHARC instructions with explicit resident PCM/header fixtures. No host reads supply reply data."})).unwrap()).unwrap();
 println!("Native DSP readback fixtures passed ({} cases)",cases.len());
}
