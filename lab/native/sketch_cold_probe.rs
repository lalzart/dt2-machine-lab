//! Coupled cold application startup. No ready snapshot, direct DSP calls or jobs.
use elektron_native_boot::{Emulator, sharc_peer::{SharedDsp, SharcPeer, DT2_IDLE}};
use sha2::{Digest, Sha256};
use sharc_native::Engine;
use std::{env, fs, path::Path, time::Instant};

fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
fn read(path: &Path) -> Vec<u8> { fs::read(path).unwrap() }

fn check_cpu(emu: &mut Emulator, main: &[u8], meta: &serde_json::Value, reset: bool) {
    if reset {
        let mut cursor = meta["chain_address"].as_u64().unwrap() as usize - 0x40000400;
        for s in meta["segments"].as_array().unwrap() {
            let at = s["destination"].as_u64().unwrap() as u32;
            let n = s["data_bytes"].as_u64().unwrap() as usize;
            let bss = s["bss"].as_u64().unwrap() as usize;
            assert_eq!(emu.peek(at, n).unwrap(), main[cursor + 12..cursor + 12 + n], "reset segment mismatch");
            assert_eq!(emu.peek(at + n as u32, bss).unwrap(), vec![0; bss], "reset BSS mismatch");
            cursor += 12 + n;
        }
        let chain = meta["chain_address"].as_u64().unwrap() as u32;
        assert!(emu.peek(chain, meta["appended_bytes"].as_u64().unwrap() as usize).unwrap().iter().all(|&b| b == 0), "reset source not erased");
    }
    for g in meta["guards"].as_array().unwrap() {
        let at = g[0].as_u64().unwrap() as u32;
        let n = g[1].as_u64().unwrap() as usize;
        assert_eq!(emu.peek(at, n).unwrap(), [0xc0,0x57,0xa1,0x1c,0x5a,0xfe,0x11,0x60].repeat(n / 8), "CPU canary changed");
    }
    for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()) {
        if w["kind"] != "code" && w["kind"] != "stock-trampoline" { continue; }
        let at = w["address"].as_u64().unwrap() as u32;
        let h = w["after"].as_str().unwrap();
        let expected: Vec<_> = (0..h.len()).step_by(2).map(|i| u8::from_str_radix(&h[i..i+2],16).unwrap()).collect();
        assert_eq!(emu.peek(at, expected.len()).unwrap(), expected, "CPU code changed");
    }
}

fn main() {
    let args: Vec<_> = env::args().collect();
    assert_eq!(args.len(), 3, "spec, stock|device|detached");
    let spec: serde_json::Value = serde_json::from_slice(&fs::read(&args[1]).unwrap()).unwrap();
    let mode = args[2].as_str();
    assert!(["stock", "device", "detached"].contains(&mode));
    let device = mode == "device";
    let out = Path::new(spec["output"].as_str().unwrap()).join(mode);
    fs::create_dir(&out).unwrap();
    let t0 = Instant::now();
    let input = Path::new(spec[if device {"device_inputs"} else {"stock_inputs"}].as_str().unwrap());
    let info: serde_json::Value = serde_json::from_slice(&read(&input.join("inputs.json"))).unwrap();
    let mut engine = Engine::from_image(&read(&input.join("image.bin"))).expect("DSP image");
    engine.import(&read(&input.join("reset.state"))).expect("DSP reset state");
    assert_eq!(engine.s.icount, 0, "DSP input was already executed");
    assert_eq!(engine.s.pc_sw, 0x1c1338);
    for (key, value) in [(1,0),(4,1),(5,1),(9,1),(21,1),(22,1)] {
        assert_eq!(engine.set_option(key,value),0,"DSP option rejected");
    }
    // Let the reset/application path initialize the DSP. No prepared checkpoint,
    // fresh_call, arbitrary PC change, unknown-MMR zeroing or cold-state overlay.
    let mut idle = 0;
    while engine.s.icount < 400_000_000 {
        engine.step(250_000);
        assert!(engine.halt.is_none(), "DSP cold halt pc={:#x}: {:?}",engine.s.pc_sw,engine.halt);
        if (DT2_IDLE.range.0..DT2_IDLE.range.1).contains(&(engine.s.pc_sw as u32)) { idle += 1; } else { idle = 0; }
        if idle == 8 { break; }
    }
    assert_eq!(idle,8,"DSP did not reach its RTOS idle task");
    let cold_icount = engine.s.icount;
    let cold_pc = engine.s.pc_sw;
    eprintln!("{mode}: DSP cold idle at {cold_pc:#x}, instructions={cold_icount}, wall={:.1}s",t0.elapsed().as_secs_f64());
    // Upstream's exact idle-loop acceleration preserves interrupt/timer events.
    // It is an emulator acceleration, never a physical DSP timing measurement.
    for (k,v) in [(23,DT2_IDLE.head),(24,DT2_IDLE.range.0),(25,DT2_IDLE.range.1)] {
        assert_eq!(engine.set_option(k,v as i64),0);
    }
    let dsp = SharedDsp::new(engine);
    let (mut peer, shared) = SharcPeer::new(dsp.clone(),666_667);
    peer.set_idle_range(DT2_IDLE.range);
    peer.enable_sample_link();
    shared.borrow_mut().attached = mode != "detached";
    let syx = read(Path::new(spec["syx"].as_str().unwrap()));
    assert_eq!(digest(&syx),"278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec");
    let card = elektron_native_boot::card_file::card_from_image(Path::new(spec["card"].as_str().unwrap())).unwrap();
    let mut emu = Emulator::new(&syx,Some(card)).expect("CPU stock container");
    let main = read(Path::new(spec["main"].as_str().unwrap()));
    let meta: serde_json::Value = serde_json::from_slice(&read(Path::new(spec["metadata"].as_str().unwrap()))).unwrap();
    if device {
        assert_eq!(digest(&main),meta["sha256"].as_str().unwrap());
        emu.poke(0x40000400,&main).unwrap();
        let lo = meta["reservation"][0].as_u64().unwrap() as u32;
        let hi = meta["reservation"][1].as_u64().unwrap() as u32;
        emu.poke(lo,&vec![0xa5;(hi-lo) as usize]).unwrap();
    }
    emu.enable_ssi_diagnostic(96_000).unwrap();
    emu.set_dspi2_peer(peer.boxed());
    assert_eq!(emu.icount(),0,"CPU peer attached after execution");
    if device {
        assert!(emu.run_until_pc(0x40000546,100_000_000),"CPU reset return absent");
        check_cpu(&mut emu,&main,&meta,true);
    }
    let mut ready_at = None;
    let mut quiet_at = 0;
    let mut last_lp = 0;
    let mut chunks = 0;
    loop {
        let s = emu.step_chunk(250_000).status;
        assert!(s.error.is_none(),"CPU fault: {:?}",s);
        let sh = shared.borrow();
        assert!(sh.halted.is_none(),"Coupled DSP halt: {:?}",sh.halted);
        // Apply the same measured coupling gate in every mode. The detached
        // control must fail on absent execution/replies, never on its label.
        if sh.frames.len() >= 8 {
            assert!(sh.dsp_instructions > 0 && sh.nonzero_replies > 0,
                "Native DSP coupling absent after 8 CPU frames");
        }
        if sh.lp0_units != last_lp { quiet_at = sh.frames.len(); last_lp = sh.lp0_units; }
        if s.ready && ready_at.is_none() { ready_at = Some(s.icount); }
        if ready_at.is_some_and(|n| s.icount >= n + 20_000_000) && sh.lp0_pending == 0 && sh.frames.len() >= quiet_at + 100 { break; }
        chunks += 1;
        if chunks % 100 == 0 { eprintln!("{mode}: CPU={} ready={} frames={} LP0={} pending={} wall={:.1}s",s.icount,s.ready,sh.frames.len(),sh.lp0_units,sh.lp0_pending,t0.elapsed().as_secs_f64()); }
        assert!(s.icount < 2_000_000_000,"CPU startup instruction bound");
        assert!(t0.elapsed().as_secs() < 600,"Startup wall-clock bound");
    }
    let view = if device {
        check_cpu(&mut emu,&main,&meta,false);
        let arena = meta["arenas"].as_array().unwrap().iter().find(|a| a["name"] == "sketch").unwrap();
        let state = arena["destination"].as_u64().unwrap() as u32;
        // Ordinary NO closes the stock filesystem modal, then SONG opens Sketch.
        for (key,on,n) in [(12,true,5_000_000),(12,false,30_000_000),(24,true,15_000_000),(24,false,15_000_000)] {
            emu.button(key,on).unwrap();
            let stop=emu.icount()+n;
            while emu.icount()<stop {
                let s=emu.step_chunk(250_000).status;assert!(s.error.is_none(),"panel fault: {:?}",s);
                assert!(shared.borrow().halted.is_none(),"DSP halted during panel input");
            }
        }
        check_cpu(&mut emu,&main,&meta,false);
        let view=emu.peek32(state+4).unwrap();
        assert_ne!(view,0,"SONG did not open Sketch after paired cold startup");
        assert!(emu.peek32(state+52).unwrap()>0,"Sketch did not render");
        assert_eq!(emu.peek32(state).unwrap(),1,"Sketch BUF default");
        view
    } else {0};
    if let Some((_,frame))=emu.current_frame() { fs::write(out.join("panel.frame"),frame).unwrap(); }
    let e=dsp.0.borrow();
    for c in info["code"].as_array().unwrap() {
        let a=c["start"].as_u64().unwrap();let n=c["size"].as_u64().unwrap();
        let bytes:Vec<_>=(0..n).map(|i| e.peek(a+i,1).unwrap().expect("DSP code became unknown") as u8).collect();
        assert_eq!(digest(&bytes),c["sha256"].as_str().unwrap(),"DSP code changed during startup");
    }
    let sh=shared.borrow();
    assert!(sh.frames.len()>128 && sh.dsp_instructions>0 && sh.nonzero_replies>0,"No proven native DSP coupling");
    assert_eq!(sh.missing_blocks,0,"Missing SPORT blocks");
    assert!(sh.pcm.iter().all(|x| x.is_finite()),"Nonfinite DSP output");
    let frame=emu.current_frame().map(|(_,f)|digest(f));
    let result=serde_json::json!({"status":"passed","mode":mode,"cold_dsp_instructions":cold_icount,"cold_dsp_pc":cold_pc,"cpu_ready_at":ready_at,"cpu_instructions":emu.icount(),"dsp_instructions":sh.dsp_instructions,"dsp_pc":e.s.pc_sw,"frames":sh.frames.len(),"native_nonzero_replies":sh.nonzero_replies,"missing_blocks":sh.missing_blocks,"lp0_units":sh.lp0_units,"lp0_pending":sh.lp0_pending,"pcm_samples":sh.pcm.len(),"sketch_view":view,"frame_sha256":frame,"dsp_blob_sha256":info["blob_sha256"],"cpu_reset_segments_checked":device,"cpu_code_canaries_intact":device,"dsp_code_intact":true,"ready_snapshot_used":false,"captures":0,"hardware":false,"dsp_rom_executed":false,"wall_seconds":t0.elapsed().as_secs_f64()});
    fs::write(out.join("report.json"),serde_json::to_vec_pretty(&result).unwrap()).unwrap();
    println!("{result}");
}
