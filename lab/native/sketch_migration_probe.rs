//! First opt-in native migration: authenticated anchors, saved BUF replay, panel.
mod buf_adapter;
use buf_adapter::NativeBuf;
use elektron_native_boot::{Emulator,sharc_peer::{SharedDsp,SharcPeer,DT2_IDLE}};
mod sketch_arm_diagnostic;
mod sketch_startup_operations;
use sha2::{Digest,Sha256};
use sharc_native::Engine;
use std::{env,fs,path::Path,time::Instant};

fn read(path:&Path)->Vec<u8>{fs::read(path).unwrap()}
fn hash(b:&[u8])->String{format!("{:x}",Sha256::digest(b))}
fn save(path:&Path,data:&serde_json::Value){fs::write(path,serde_json::to_vec_pretty(data).unwrap()).unwrap();}
fn spec_file(s:&serde_json::Value,key:&str)->Vec<u8>{read(Path::new(s[key].as_str().unwrap()))}
fn same(a:&[u8],b:&[u8],what:&str) {
    assert_eq!(a.len(),b.len(),"{what}: length mismatch");
    if let Some(i)=a.iter().zip(b).position(|(x,y)|x!=y) {
        panic!("{what}: first mismatch @{i:#x}, native={:#x}, old={:#x}, native hash={}, old hash={}",a[i],b[i],hash(a),hash(b));
    }
}

fn constructors(s:&serde_json::Value,out:&Path){
    let stock=spec_file(s,"stock_syx");let candidate=spec_file(s,"candidate");let main=spec_file(s,"main");
    let mut original=Emulator::new(&stock,None).unwrap();
    let mut reference=Emulator::new_patched_with_reference(&stock,None,&stock).unwrap();
    assert_eq!(original.state_digest_arch().unwrap(),reference.state_digest_arch().unwrap(),"stock constructor state differs");
    let error=Emulator::new_patched(&candidate,None,&hash(&stock)).err().expect("old constructor unexpectedly accepted hooked anchor");
    assert_eq!(error,"mainloop signature ambiguous");
    let mut emu=Emulator::new_patched_with_reference(&candidate,None,&stock).expect("candidate reference constructor");
    assert_eq!(emu.icount(),0);assert_eq!(emu.peek(0x40000400,main.len()).unwrap(),main,"candidate MAIN differs before first instruction");
    let mut unknown=stock.clone();unknown[100]^=1;
    assert!(Emulator::new_patched_with_reference(&candidate,None,&unknown).is_err(),"tampered reference accepted");
    save(&out.join("constructors.json"),&serde_json::json!({"status":"passed","stock_initial_state_exact":true,"candidate_MAIN_loaded_from_container":true,"host_MAIN_overlay":false,"unknown_reference_refused":true,"old_constructor_error":error,"cause":"stock main-loop entry is intentionally hooked; zero signature matches"}));
}

fn replay(s:&serde_json::Value,out:&Path){
    let old=out.join("legacy");let oracle:serde_json::Value=serde_json::from_slice(&read(&old.join("oracle.json"))).unwrap();
    let image=read(&out.join("dsp.image"));let state=read(&out.join("prepared.state"));
    let options:Vec<(u32,i64)>=serde_json::from_slice(&read(&out.join("prepared-options.json"))).unwrap();
    let a=read(&old.join("A.lp0"));let b=read(&old.join("B.lp0"));
    let stock_image=read(&out.join("stock-dsp.image"));
    let mut first=Vec::new();let mut first_replies=Vec::new();let mut correct_b=Vec::new();let mut phases=Vec::new();
    let mut reply_exact=true;let mut stock_replies_exact=true;
    for repeat in 0..4 {
        let wrong=repeat==2;
        let stock=repeat==3;
        let mut e=NativeBuf::prepared(if stock {&stock_image} else {&image},&state,&options);e.publish(&a);
        let frozen=e.descriptor(312);assert_eq!(frozen,e.descriptor(300));
        let mut run=Vec::new();let mut reply_run=Vec::new();
        for action in oracle["actions"].as_array().unwrap(){
            let name=action["name"].as_str().unwrap();
            if action["publish_b"]==true {
                let ptr=e.pointers();assert!(ptr.iter().all(|&v|v!=0));e.publish(&b);
                assert_eq!(e.pointers(),ptr,"native publication moved retained readers");
                assert_eq!(e.descriptor(312),frozen,"native publication changed frozen A");
                assert_ne!(e.descriptor(300),frozen,"BUF did not advance to B");
            }
            let mut wire=read(&old.join(format!("{name}.wire")));
            if wrong && (name=="B-frozen-A" || name=="late-frozen-A") {
                for w in wire.chunks_exact_mut(0xabc){w[0xe0+5*0x60..0xe2+5*0x60].copy_from_slice(&300u16.to_be_bytes());}
            }
            let mut replies=Vec::new();let mut pcm=Vec::new();
            for w in wire.chunks_exact(0xabc){let (r,p)=e.frame(w);replies.extend(r);pcm.extend(p);}
            if !wrong && !stock {
                fs::write(out.join(format!("native-{name}.reply")),&replies).unwrap();
                fs::write(out.join(format!("native-{name}.pcm")),&pcm).unwrap();
                let old_reply=read(&old.join(format!("{name}.reply")));
                if replies!=old_reply {reply_exact=false;}
                same(&pcm,&read(&old.join(format!("{name}.pcm"))),&format!("voice PCM {name}"));
            }
            if name=="B-frozen-A" {
                if wrong {assert_ne!(pcm,correct_b,"wrong frozen source was not detected");}
                else if repeat==0 {correct_b=pcm.clone();}
            }
            if repeat==0 {
                let old_reply=read(&old.join(format!("{name}.reply")));
                phases.push(serde_json::json!({"name":name,"pcm_sha256":hash(&pcm),"reply_sha256":hash(&replies),"legacy_reply_sha256":hash(&old_reply),"reply_diff_bytes":replies.iter().zip(&old_reply).filter(|(x,y)|x!=y).count(),"first_reply_difference":replies.iter().zip(&old_reply).position(|(x,y)|x!=y),"pointers":e.pointers()}));
            }
            run.extend(pcm);reply_run.extend(replies);
        }
        if repeat==0 {first=run;first_replies=reply_run;}
        else if !wrong {
            same(&run,&first,if stock {"stock/candidate native voice PCM"} else {"native exact repeat PCM"});
            if stock {stock_replies_exact=reply_run==first_replies;} else {same(&reply_run,&first_replies,"native exact repeat replies");}
        }
    }
    save(&out.join("replay.json"),&serde_json::json!({"status":if reply_exact {"passed"} else {"passed-voice-controls-reply-parity-open"},"blocks_per_run":96,"positive_runs":2,"wrong_frozen_source_control":true,"legacy_voice_PCM_exact":true,"legacy_replies_exact":reply_exact,"current_stock_voice_PCM_exact":true,"current_stock_replies_exact":stock_replies_exact,"retained_pointers_preserved":true,"frozen_allocation_preserved":true,"phases":phases,"private_FEXT_or_MODIFY_adapters":false,"recordings":0,"scope":"Prepared state and modeled LP0 callback boundaries; saved A/B/FREEZE generations, voice work buffers. Old/new reply differences keep default migration gate closed."}));
    let _=s;
}

fn code_and_guards(emu:&mut Emulator,meta:&serde_json::Value){
    for g in meta["guards"].as_array().unwrap(){
        let at=g[0].as_u64().unwrap() as u32;let n=g[1].as_u64().unwrap() as usize;
        assert_eq!(emu.peek(at,n).unwrap(),[0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n/8),"CPU canary changed");
    }
    for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()) {
        if w["kind"]!="code" && w["kind"]!="stock-trampoline" {continue;}
        let h=w["after"].as_str().unwrap();let b:Vec<_>=(0..h.len()).step_by(2).map(|i|u8::from_str_radix(&h[i..i+2],16).unwrap()).collect();
        assert_eq!(emu.peek(w["address"].as_u64().unwrap() as u32,b.len()).unwrap(),b,"CPU code changed");
    }
}

fn boot(s:&serde_json::Value,out:&Path){
    let t0=Instant::now();let input=out.join("reset-inputs");
    let mut e=Engine::from_image(&read(&input.join("image.bin"))).unwrap();e.import(&read(&input.join("reset.state"))).unwrap();
    assert_eq!(e.s.icount,0);for(k,v)in[(1,0),(4,1),(5,1),(9,1),(21,1),(22,1)]{assert_eq!(e.set_option(k,v),0);}
    let mut idle=0;while e.s.icount<400_000_000{
        e.step(250_000);assert!(e.halt.is_none(),"DSP initialization halt {:?}",e.halt);
        if(DT2_IDLE.range.0..DT2_IDLE.range.1).contains(&(e.s.pc_sw as u32)){idle+=1;}else{idle=0;}
        if idle==8{break;}
    }assert_eq!(idle,8,"DSP did not initialize");let cold=e.s.icount;
    for(k,v)in[(23,DT2_IDLE.head),(24,DT2_IDLE.range.0),(25,DT2_IDLE.range.1)]{assert_eq!(e.set_option(k,v as i64),0);}
    let dsp=SharedDsp::new(e);let(mut peer,shared)=SharcPeer::new(dsp.clone(),666_667);peer.set_idle_range(DT2_IDLE.range);peer.enable_sample_link();
    let stock=spec_file(s,"stock_syx");let candidate=spec_file(s,"candidate");let main=spec_file(s,"main");
    let card=elektron_native_boot::card_file::card_from_image(Path::new(s["card"].as_str().unwrap())).unwrap();
    let mut emu=Emulator::new_patched_with_reference(&candidate,Some(card),&stock).unwrap();
    assert_eq!(emu.peek(0x40000400,main.len()).unwrap(),main);assert_eq!(emu.icount(),0);
    emu.enable_ssi_diagnostic(96_000).unwrap();emu.set_dspi2_peer(peer.boxed());
    let meta:serde_json::Value=serde_json::from_slice(&spec_file(s,"metadata")).unwrap();
    let mut operations = if s["operation_trace"] == true { Some(sketch_startup_operations::Operations::new(&mut emu, &meta)) } else { None };
    assert!(emu.run_until_pc(0x40000546,100_000_000),"CPU reset did not finish");
    let mut at=meta["chain_address"].as_u64().unwrap() as usize-0x40000400;
    for seg in meta["segments"].as_array().unwrap(){
        let dest=seg["destination"].as_u64().unwrap() as u32;let n=seg["data_bytes"].as_u64().unwrap() as usize;let bss=seg["bss"].as_u64().unwrap() as usize;
        assert_eq!(emu.peek(dest,n).unwrap(),main[at+12..at+12+n]);assert_eq!(emu.peek(dest+n as u32,bss).unwrap(),vec![0;bss]);at+=12+n;
    }
    code_and_guards(&mut emu,&meta);
    if let Some(trace) = operations.as_mut() { trace.sample(&mut emu, "reset-initialized", false); }
    let mut ready=None;let mut last_lp=0;let mut quiet=0;let mut chunks=0;
    loop{
        let st=emu.step_chunk(250_000).status;assert!(st.error.is_none(),"CPU fault {:?}",st);
        if let Some(trace) = operations.as_mut() { trace.sample(&mut emu, "startup", st.ready); }
        let sh=shared.borrow();assert!(sh.halted.is_none(),"DSP halt {:?}",sh.halted);
        if sh.frames.len()>=8{assert!(sh.dsp_instructions>0 && sh.nonzero_replies>0,"native DSP coupling absent");}
        if sh.lp0_units!=last_lp{last_lp=sh.lp0_units;quiet=sh.frames.len();}
        if st.ready && ready.is_none(){ready=Some(st.icount);}
        if ready.is_some_and(|n|st.icount>=n+20_000_000)&&sh.lp0_pending==0&&sh.frames.len()>=quiet+100{break;}
        chunks+=1;if chunks%300==0{eprintln!("CPU={} ready={} frames={} LP0={} wall={:.1}s",st.icount,st.ready,sh.frames.len(),sh.lp0_units,t0.elapsed().as_secs_f64());}
        assert!(st.icount<2_000_000_000&&t0.elapsed().as_secs()<600,"bounded startup exceeded");
    }
    for(key,on,n)in[(12,true,5_000_000),(12,false,30_000_000),(24,true,15_000_000),(24,false,15_000_000)]{
        emu.button(key,on).unwrap();let end=emu.icount()+n;while emu.icount()<end{assert!(emu.step_chunk(250_000).status.error.is_none());assert!(shared.borrow().halted.is_none());
            if let Some(trace) = operations.as_mut() { trace.sample(&mut emu, "open-Sketch", true); }
        }
    }
    if let Some(trace) = operations.as_mut() {
        // Reproduce the reported order: reach Sketch, then start transport.
        // No ARM/FREEZE or recorder settings are changed in this observation.
        for (on, budget) in [(true, 5_000_000_u64), (false, 269_000_000_u64)] {
            emu.button(20, on).unwrap(); let end = emu.icount() + budget;
            while emu.icount() < end {
                assert!(emu.step_chunk(250_000).status.error.is_none());
                assert!(shared.borrow().halted.is_none());
                trace.sample(&mut emu, "PLAY-after-startup", true);
            }
        }
        trace.finish(&mut emu, out);
        if let Some((_, frame)) = emu.current_frame() { fs::write(out.join("startup-after-play.frame"), frame).unwrap(); }
    }
    let arena=meta["arenas"].as_array().unwrap().iter().find(|a|a["name"]=="sketch").unwrap();let state=arena["destination"].as_u64().unwrap() as u32;
    assert_ne!(emu.peek32(state+4).unwrap(),0,"Sketch did not open");assert!(emu.peek32(state+52).unwrap()>0,"Sketch did not render");
    code_and_guards(&mut emu,&meta);if let Some((_,f))=emu.current_frame(){fs::write(out.join("panel.frame"),f).unwrap();}
    let sh=shared.borrow();assert_eq!(sh.missing_blocks,0);assert!(sh.pcm.iter().all(|x|x.is_finite()));assert!(sh.lp0_units>0);assert_eq!(sh.lp0_pending,0);
    save(&out.join("boot.json"),&serde_json::json!({"status":"passed","candidate_container_loaded":true,"host_MAIN_overlay":false,"CPU_ready_at":ready,"DSP_cold_instructions":cold,"frames":sh.frames.len(),"native_replies":sh.nonzero_replies,"LP0_units":sh.lp0_units,"missing_blocks":sh.missing_blocks,"CPU_canaries_and_code_intact":true,"Sketch_rendered":true,"wall_seconds":t0.elapsed().as_secs_f64(),"DSP_ROM_executed":false,"hardware":false,"scope":"CPU application reset from candidate container; DSP independently initialized from its candidate loader entry; modeled SSI and instruction cadence"}));
    drop(sh);
    if s["arm_diagnostics"]==true {
        sketch_arm_diagnostic::check(&mut emu,s,out);
        code_and_guards(&mut emu,&meta);
    }
}

fn main(){let args:Vec<_>=env::args().collect();let s:serde_json::Value=serde_json::from_slice(&fs::read(&args[1]).unwrap()).unwrap();let out=Path::new(s["output"].as_str().unwrap());match args[2].as_str(){"constructors"=>constructors(&s,out),"replay"=>replay(&s,out),"boot"=>boot(&s,out),_=>panic!("unknown mode")};println!("passed {}",args[2]);}
