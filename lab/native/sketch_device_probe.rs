//! Isolated Sketch reset and panel check using the inspected, read-only CPU adapter.
use elektron_native_boot::Emulator;
use sha2::{Digest, Sha256};
use std::{env, fs};

fn advance(emu: &mut Emulator, instructions: u64) {
    let stop = emu.icount() + instructions;
    while emu.icount() < stop {
        let s = emu.step_chunk(250_000).status;
        assert!(s.error.is_none(), "{:?}", s);
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(args.len(), 5, "stock SYX, MAIN, metadata, output folder");
    let stock = fs::read(&args[1]).unwrap();
    assert_eq!(format!("{:x}", Sha256::digest(&stock)),
        "278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec");
    let main = fs::read(&args[2]).unwrap();
    let meta: serde_json::Value = serde_json::from_slice(&fs::read(&args[3]).unwrap()).unwrap();
    assert_eq!(format!("{:x}", Sha256::digest(&main)), meta["sha256"].as_str().unwrap());
    assert_eq!(meta["profile"], "isolated-sketch-buf");
    assert_eq!(main.len() % 4, 0);
    let mut emu = Emulator::new(&stock, None).unwrap();
    for (i, b) in main.chunks_exact(4).enumerate() {
        emu.poke32(0x40000400 + i as u32 * 4, u32::from_be_bytes(b.try_into().unwrap())).unwrap();
    }
    let lo = meta["reservation"][0].as_u64().unwrap() as u32;
    let hi = meta["reservation"][1].as_u64().unwrap() as u32;
    assert!(lo >= 0x47e9b000 && hi <= 0x47fe0000);
    for a in (lo..hi).step_by(4) {
        emu.poke32(a, 0xa5a5a5a5).unwrap();
    }
    assert!(emu.run_until_pc(0x40000546, 100_000_000), "reset return missing");
    let chain = meta["chain_address"].as_u64().unwrap() as u32;
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
        assert_eq!(emu.peek32(chain + i).unwrap(), 0, "appended reset source not cleared");
    }
    let mut ready = None;
    loop {
        let s = emu.step_chunk(250_000).status;
        assert!(s.error.is_none(), "{:?}", s);
        if s.ready && ready.is_none() { ready = Some(s.icount); }
        if ready.is_some_and(|r| s.icount >= r + 20_000_000) { break; }
        assert!(s.icount < 2_000_000_000, "ready not reached");
    }
    let arena = meta["arenas"].as_array().unwrap().iter()
        .find(|a| a["name"] == "sketch").unwrap();
    let sketch = arena["destination"].as_u64().unwrap() as u32;
    emu.probe_pcs(&[sketch + 0x1000, sketch + 0x2000, 0x4005dc58, 0x400649c4]);
    advance(&mut emu, 100_000_000);
    if let Some((_, frame)) = emu.current_frame() {
        fs::write(format!("{}/before-panel.frame", args[4]), frame).unwrap();
        eprintln!("before frame bytes={}", frame.len());
    }
    assert_eq!(emu.peek32(sketch).unwrap(), 1, "independent BUF default");
    assert_eq!(emu.peek32(sketch + 4).unwrap(), 0, "unexpected view before SONG");
    // The cold-boot adapter intentionally leaves FILE SYSTEM OK open.
    // SONG must respect that modal owner. Close it through the normal NO key.
    emu.button(24, true).unwrap(); advance(&mut emu, 5_000_000);
    emu.button(24, false).unwrap(); advance(&mut emu, 5_000_000);
    assert_eq!(emu.peek32(sketch + 4).unwrap(), 0, "Sketch stole stock modal");
    emu.button(12, true).unwrap(); advance(&mut emu, 5_000_000);
    emu.button(12, false).unwrap(); advance(&mut emu, 30_000_000);
    // Physical panel code comes from this pinned adapter's DTII port table.
    emu.button(24, true).unwrap();
    advance(&mut emu, 15_000_000);
    emu.button(24, false).unwrap();
    advance(&mut emu, 15_000_000);
    let view = emu.peek32(sketch + 4).unwrap();
    let draws = emu.peek32(sketch + 52).unwrap();
    assert_ne!(view, 0, "SONG did not open native Sketch");
    assert!(draws > 0, "Sketch did not draw");
    if let Some((_, frame)) = emu.current_frame() {
        fs::write(format!("{}/sketch.frame", args[4]), frame).unwrap();
    }
    // A encoder changes the single session preference; recorder DEST stays 0.
    for _ in 0..8 {
        emu.turn(1, 10).unwrap();
        advance(&mut emu, 5_000_000);
        if emu.peek32(sketch).unwrap() != 1 { break; }
    }
    let selected = emu.peek32(sketch).unwrap();
    assert!((2..=4).contains(&selected), "A encoder did not change BUF selection");
    emu.button(24, true).unwrap(); advance(&mut emu, 5_000_000);
    emu.button(24, false).unwrap(); advance(&mut emu, 5_000_000);
    assert_eq!(emu.peek32(sketch + 4).unwrap(), 0, "SONG did not close Sketch");
    emu.button(24, true).unwrap(); advance(&mut emu, 5_000_000);
    emu.button(24, false).unwrap(); advance(&mut emu, 5_000_000);
    assert_eq!(emu.peek32(sketch).unwrap(), selected, "BUF preference lost after reopen");
    for g in meta["guards"].as_array().unwrap() {
        let a = g[0].as_u64().unwrap() as u32;
        let n = g[1].as_u64().unwrap() as u32;
        for i in (0..n).step_by(8) {
            assert_eq!(emu.peek32(a + i).unwrap(), 0xc057a11c);
            assert_eq!(emu.peek32(a + i + 4).unwrap(), 0x5afe1160);
        }
    }
    for w in meta["writes"].as_array().unwrap().iter().chain(meta["hooks"].as_array().unwrap()) {
        if w["kind"] != "code" && w["kind"] != "stock-trampoline" { continue; }
        let a = w["address"].as_u64().unwrap() as u32;
        let h = w["after"].as_str().unwrap();
        let bytes: Vec<u8> = (0..h.len()).step_by(2)
            .map(|i| u8::from_str_radix(&h[i..i + 2], 16).unwrap()).collect();
        assert_eq!(emu.peek_bytes(a, bytes.len()).unwrap(), bytes, "runtime code changed");
    }
    println!("{}", serde_json::json!({"status":"passed", "main_sha256":meta["sha256"],
        "ready_at":ready, "instructions":emu.icount(), "sketch_view":view, "draws":draws,
        "stock_modal_ownership_preserved":true,
        "selection_survives_reopen":true, "segments_exact_after_clear":true,
        "poisoned_bss_cleared":true, "source_erased":true, "guards_intact":true,
        "code_preserved":true, "hardware":false, "coupled_dsp":false}));
}
