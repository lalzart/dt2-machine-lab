//! Native OS1.16 CPU sender, with a host-driven GPIO ready/busy model.
//! The real ROM and SPI RX FIFO are not executed. No dependency source edits.
use elektron_native_boot::{Emulator, WatchConfig};
use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, time::Instant};

const LOOP: u32 = 0x400cd22a;
const READY: u32 = 0xec094018;
fn digest(b: &[u8]) -> String { format!("{:x}",Sha256::digest(b)) }

fn hold(emu: &mut Emulator, base: u32) -> serde_json::Value {
    emu.poke(READY,&[0x10]).unwrap();
    let pointer = emu.cpu_regs().1[0];
    let writes = emu.write_watch_totals().0;
    let start = emu.icount();
    let state = emu.step_chunk(100_000).status;
    assert!(state.error.is_none(),"CPU fault during busy hold: {:?}",state);
    assert!((0x400cd232..=0x400cd23e).contains(&emu.cpu_regs().2),"sender left ready poll while busy");
    assert_eq!(emu.cpu_regs().1[0],pointer,"sender advanced while busy");
    assert_eq!(emu.write_watch_totals().0,writes,"sender wrote while busy");
    emu.poke(READY,&[0]).unwrap();
    serde_json::json!({"bytes_already_consumed":pointer-base,"held_cpu_instructions":emu.icount()-start,"no_pointer_advance":true,"no_push_writes":true,"released":true})
}

fn main() {
    let args: Vec<_> = env::args().collect();
    let spec:serde_json::Value=serde_json::from_slice(&fs::read(&args[1]).unwrap()).unwrap();
    let out=Path::new(spec["output"].as_str().unwrap());
    let t0=Instant::now();
    let blob=fs::read(spec["blob"].as_str().unwrap()).unwrap();
    assert!(patchkit::bootrom::check(&blob).is_empty(),"independent Rust ROM rules reject candidate");
    let old=fs::read(spec["legacy_blob"].as_str().unwrap()).unwrap();
    let old_errors=patchkit::bootrom::check(&old);
    assert!(old_errors.iter().any(|s|s.starts_with("H8 ")));
    assert!(old_errors.iter().any(|s|s.starts_with("H12 ")));
    let syx=fs::read(spec["test_container"].as_str().unwrap()).unwrap();
    let main=fs::read(spec["main"].as_str().unwrap()).unwrap();
    let candidate=fs::read(spec["candidate_container"].as_str().unwrap()).unwrap();
    let constructor_error=match Emulator::new_patched(&candidate,None,"278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec") {
        Ok(_)=>panic!("known constructor limitation changed; reassess full-container gate"),
        Err(error)=>error
    };
    assert_eq!(constructor_error,"mainloop signature ambiguous","unexpected candidate constructor failure");
    let mut emu=Emulator::new(&syx,None).expect("stock-MAIN/candidate-DSP sender fixture");
    assert_eq!(emu.icount(),0);
    emu.poke(0x40000400,&main).unwrap();
    assert_eq!(emu.peek(0x40000400,main.len()).unwrap(),main,"sealed MAIN installation differs");
    // All PUSHR writes, from reset through the sender return. CPU instruction
    // execution, section lookup, allocation and depack are unmodified.
    emu.set_write_watch(Some(WatchConfig{
        ranges:vec![(0xec038034,0xec038038)],
        out:Some(out.join("push.jsonl")),limit:400_000,..WatchConfig::default()
    }));
    emu.record_regs_at(&[0x400ccf74,0x400cd1c0,0x400cd204,0x400cd264,0x400cd2a4]);
    assert!(emu.run_until_pc(0x400ccf74,1_000_000_000),"CPU did not reach boot sender: {:?}",emu.status());
    let entry_icount=emu.icount();
    let sp=emu.cpu_regs().1[7];
    let return_pc=emu.peek32(sp).unwrap();
    assert_eq!(return_pc,0x400ccaf4,"unexpected boot call site");
    eprintln!("sender reached from CPU reset at {entry_icount}");
    assert!(emu.run_until_pc(LOOP,500_000_000),"CPU did not reach send loop: {:?}",emu.status());
    let regs=emu.cpu_regs();let base=regs.0[3];
    assert_eq!(regs.0[2] as usize,blob.len()+1,"native depacked length");
    assert_eq!(regs.1[0],base,"initial TX pointer");
    let expected=[vec![3],blob.clone()].concat();
    assert_eq!(emu.peek(base,expected.len()).unwrap(),expected,"CPU native section lookup/depack differs");
    let depack_icount=emu.icount();
    let mut holds=vec![hold(&mut emu,base)];
    assert!(emu.run_until_pc(0x400cd248,10_000),"ready release did not reach first push");
    assert_eq!(emu.cpu_regs().0[1],0x90010003,"first frame is not command 3");
    assert!(emu.run_until_pc(LOOP,10_000));
    // Exercise backpressure inside the transfer as well as before command 3.
    assert!(emu.step_chunk(200_000).status.error.is_none());
    assert!(emu.run_until_pc(0x400cd232,10_000));
    holds.push(hold(&mut emu,base));
    assert!(holds[1]["bytes_already_consumed"].as_u64().unwrap()>1);
    assert!(emu.run_until_pc(0x400cd264,20_000_000),"upload did not finish: {:?}",emu.status());
    assert_eq!(emu.cpu_regs().1[0],base+expected.len() as u32,"sender final pointer");
    assert_eq!(emu.write_watch_totals().0 as usize,expected.len(),"byte frame count");
    assert!(emu.run_until_pc(return_pc,20_000_000),"boot sender did not return: {:?}, regs={:?}",emu.status(),emu.cpu_regs());
    assert_eq!(emu.cpu_regs().0[0],0,"boot sender returned failure");
    emu.finish_write_watch();
    let mut transmitted=Vec::new();let mut terminal=0;
    for row in fs::read_to_string(out.join("push.jsonl")).unwrap().lines() {
        let j:serde_json::Value=serde_json::from_str(row).unwrap();
        if j["t"]!="w" {continue;}
        assert_eq!(j["size"],4);
        let v=u32::from_str_radix(j["value"].as_str().unwrap().trim_start_matches("0x"),16).unwrap();
        if j["pc"]=="0x400cd248" {
            assert_eq!(v&0xffffff00,0x90010000,"unexpected data frame control bits");
            transmitted.push(v as u8);
        } else {
            assert_eq!(j["pc"],"0x400cd26c","unexpected PUSHR writer");
            assert_eq!(v,0x18000000,"wrong terminal frame");
            assert_eq!(transmitted,expected,"terminal before full data stream");terminal+=1;
        }
    }
    assert_eq!(transmitted,expected,"native PUSHR stream mismatch");assert_eq!(terminal,1);
    fs::write(out.join("transmitted.bin"),&transmitted).unwrap();
    let (log,dropped)=emu.reg_log();assert_eq!(dropped,0);
    let registers:Vec<_>=log.iter().map(|h|serde_json::json!({"pc":h.pc,"icount":h.icount,"d":h.d,"a":h.a,"stack":h.stack})).collect();
    let result=serde_json::json!({"status":"passed-native-cpu-upload","dsp_sha256":digest(&blob),"transmitted_sha256":digest(&transmitted),"bytes_including_command":transmitted.len(),"terminal_frames":terminal,"cpu_entry_instructions":entry_icount,"cpu_depacked_instructions":depack_icount,"cpu_return_instructions":emu.icount(),"holds":holds,"registers":registers,"legacy_errors":old_errors,"independent_rust_boot_rules":true,"cpu_started_from_reset":true,"candidate_container_native_constructor_error":constructor_error,"cpu_and_dsp_from_same_candidate_container":false,"cpu_code_overlaid_by_host_before_first_instruction":true,"native_section_lookup_allocation_depack_sender":true,"dspi_status_model":"upstream forced transfer complete","gpio_model":"host driven active-low bit 4; two bounded busy holds","rom_executed":false,"spi_fifo_modelled":false,"physical_timing_verified":false,"hardware":false,"wall_seconds":t0.elapsed().as_secs_f64()});
    fs::write(out.join("native.json"),serde_json::to_vec_pretty(&result).unwrap()).unwrap();
    println!("passed-native-cpu-upload {} bytes, two busy holds, {:.1}s",transmitted.len(),t0.elapsed().as_secs_f64());
}
