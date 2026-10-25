//! Lab-owned reset adapter; upstream is an explicit, read-only source pin.
use elektron_native_boot::Emulator;
use sha2::{Digest, Sha256};
use std::{env, fs};

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(args.len(), 4, "expected stock SYX, experimental MAIN and metadata");
    let stock = fs::read(&args[1]).unwrap();
    assert_eq!(format!("{:x}", Sha256::digest(&stock)),
        "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec");
    let main = fs::read(&args[2]).unwrap();
    let meta: serde_json::Value = serde_json::from_slice(&fs::read(&args[3]).unwrap()).unwrap();
    assert_eq!(format!("{:x}", Sha256::digest(&main)), meta["sha256"].as_str().unwrap());
    assert_eq!(main.len() % 4, 0);
    assert_eq!(meta["reservation"], serde_json::json!([0x47e8b000u32, 0x47e9b000u32]));

    // Resolve host markers against authenticated stock, then replace guest bytes
    // before the very first reset instruction. No guest hook is bypassed.
    let mut emu = Emulator::new(&stock, None).unwrap();
    for (i, b) in main.chunks_exact(4).enumerate() {
        emu.poke32(0x40000400 + i as u32 * 4, u32::from_be_bytes(b.try_into().unwrap())).unwrap();
    }
    let counter_address = meta["heartbeat_counter"].as_u64().unwrap() as u32;
    for a in (counter_address..counter_address + 4096).step_by(4) {
        emu.poke32(a, 0xa5a5a5a5).unwrap();
    }
    assert!(emu.run_until_pc(0x40000546, 100_000_000));
    let chain = meta["chain_address"].as_u64().unwrap_or(0x4031ff60) as u32;
    let mut cursor = chain as usize - 0x40000400;
    for s in meta["segments"].as_array().unwrap() {
        let dest = s["destination"].as_u64().unwrap() as u32;
        let n = s["data_bytes"].as_u64().unwrap() as usize;
        let bss = s["bss"].as_u64().unwrap() as usize;
        for i in (0..n).step_by(4) {
            assert_eq!(emu.peek32(dest + i as u32).unwrap(),
                u32::from_be_bytes(main[cursor + 12 + i..cursor + 16 + i].try_into().unwrap()),
                "reset segment mismatch");
        }
        for i in (n..n + bss).step_by(4) {
            assert_eq!(emu.peek32(dest + i as u32).unwrap(), 0, "reset BSS mismatch");
        }
        cursor += 12 + n;
    }
    for i in (0..meta["appended_bytes"].as_u64().unwrap() as u32).step_by(4) {
        assert_eq!(emu.peek32(chain + i).unwrap(), 0);
    }
    let mut ready = None;
    loop {
        let s = emu.step_chunk(250_000).status;
        assert!(s.error.is_none(), "{:?}", s.error);
        if s.ready && ready.is_none() {
            ready = Some(s.icount);
        }
        if ready.is_some_and(|r| s.icount >= r + 20_000_000) {
            break;
        }
        assert!(s.icount < 2_000_000_000, "ready not reached");
    }
    let counter = emu.peek32(counter_address).unwrap();
    let state = emu.peek32(meta["arp"]["locations"]["pointer"].as_u64().unwrap() as u32).unwrap();
    assert!(counter > 0 && (0x44f39c40..0x46f39c40).contains(&state));
    for g in meta["guards"].as_array().unwrap() {
        let a = g[0].as_u64().unwrap() as u32;
        let n = g[1].as_u64().unwrap() as u32;
        for i in (0..n).step_by(8) {
            assert_eq!(emu.peek32(a + i).unwrap(), 0xc057a11c);
            assert_eq!(emu.peek32(a + i + 4).unwrap(), 0x5afe1160);
        }
    }
    for w in meta["writes"].as_array().unwrap() {
        if w["kind"] != "code" && w["kind"] != "stock-trampoline" && w["kind"] != "validated-base" {
            continue;
        }
        let a = w["runtime_address"].as_u64().unwrap_or_else(|| w["address"].as_u64().unwrap()) as u32;
        let h = w["after"].as_str().unwrap();
        let bytes: Vec<u8> = (0..h.len()).step_by(2)
            .map(|i| u8::from_str_radix(&h[i..i + 2], 16).unwrap()).collect();
        for (i, chunk) in bytes.chunks(4).enumerate() {
            let actual = emu.peek32(a + i as u32 * 4).unwrap().to_be_bytes();
            assert_eq!(&actual[..chunk.len()], chunk);
        }
    }
    println!("{}", serde_json::json!({
        "status": "passed", "backend": "native ColdFire",
        "profile": "authenticated stock, replaced MAIN before reset",
        "main_sha256": meta["sha256"], "ready_at": ready,
        "instructions": emu.icount(), "heartbeat_calls": counter,
        "arp_heap_state": state, "segments_exact_at_after_clear": true,
        "poisoned_bss_cleared": true, "source_erased": true,
        "guards_intact": true, "code_preserved": true,
        "hardware": false, "coupled_dsp": false
    }));
}
