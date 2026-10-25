//! Two bounded admission-fault UI controls after native application startup.
//! Test-only flag injection; no actual recorder, loader, commit or DSP jobs.
use elektron_native_boot::Emulator;
use serde_json::{Value, json};
use std::{fs, path::Path};

fn advance(emu: &mut Emulator, instructions: u64) {
    let end = emu.icount() + instructions;
    while emu.icount() < end {
        assert!(emu.step_chunk(250_000).status.error.is_none(), "CPU fault in diagnostic control");
    }
}

pub fn check(emu: &mut Emulator, spec: &Value, out: &Path) {
    let meta: Value = serde_json::from_slice(&fs::read(spec["metadata"].as_str().unwrap()).unwrap()).unwrap();
    assert_eq!(meta["arm_diagnostics"], true);
    let arena = |name: &str| meta["arenas"].as_array().unwrap().iter()
        .find(|a| a["name"] == name).unwrap()["destination"].as_u64().unwrap() as u32;
    let ui = arena("sketch");
    let nb = arena("next_bar");
    let worker = arena("worker");
    assert_ne!(emu.peek32(ui + 4).unwrap(), 0, "Sketch must already be open");
    assert_eq!(emu.peek32(nb).unwrap(), 0);
    let counts = emu.peek(nb + 8, 20).unwrap();
    let mut wait_ui = Value::Null;
    if meta["clock_fix"] == true {
        let q=arena("freeze_queue");assert_eq!(emu.peek32(q+56),Some(0));assert_eq!(emu.peek32(ui+36),Some(0));
        emu.poke(q+56,&1_u32.to_be_bytes()).unwrap();advance(emu,10_000_000);
        assert_eq!(emu.peek32(ui+36),Some(0));assert_eq!(emu.peek(nb+8,20).unwrap(),counts);
        let (_,frame)=emu.current_frame().unwrap();fs::write(out.join("diagnostic-wait-samples.frame"),frame).unwrap();
        emu.poke(q+56,&[0;4]).unwrap();advance(emu,10_000_000);
        let (_,frame)=emu.current_frame().unwrap();fs::write(out.join("diagnostic-samples-idle.frame"),frame).unwrap();
        assert_eq!(emu.peek32(ui+36),Some(0));assert_eq!(emu.peek(nb+8,20).unwrap(),counts);
        wait_ui=json!({"status":"passed","test_only_busy_count":true,"ARM_requested":false,"state_changed":false});
    }
    let mut cases = Vec::new();
    for (name, at, value, reason) in [("worker", worker + 12, 66_u32, 3_u32), ("loader", 0x405b1360, 1_u32, 6_u32)] {
        let original = emu.peek32(at).unwrap();
        assert_eq!(original, 0, "fault control requires an idle guard");
        emu.poke(at, &value.to_be_bytes()).unwrap();
        emu.button(17, true).unwrap(); advance(emu, 5_000_000);
        emu.button(24, true).unwrap(); advance(emu, 5_000_000);
        emu.button(24, false).unwrap(); advance(emu, 5_000_000);
        emu.button(17, false).unwrap(); advance(emu, 10_000_000);
        assert_eq!(emu.peek32(ui + 36).unwrap(), 9, "real FUNC+SONG must show busy");
        assert_eq!(emu.peek32(ui + 72).unwrap(), (-7_i32) as u32);
        assert_eq!(emu.peek32(ui + 108).unwrap(), reason, "wrong first-failure reason");
        assert_eq!(emu.peek32(ui + 112).unwrap(), value, "wrong observed value");
        assert_eq!(emu.peek32(nb).unwrap(), 0, "no BUF transaction may start");
        assert_eq!(emu.peek(nb + 8, 20).unwrap(), counts, "admission/capture counters changed");
        emu.poke(at, &original.to_be_bytes()).unwrap();
        // Changing the backend diagnostic cannot relabel the latched UI result.
        emu.poke(nb + 0x12c, &[0; 8]).unwrap(); advance(emu, 5_000_000);
        assert_eq!(emu.peek32(ui + 108).unwrap(), reason);
        assert_eq!(emu.peek32(ui + 112).unwrap(), value);
        let (_, frame) = emu.current_frame().expect("native diagnostic frame");
        let filename = format!("diagnostic-{name}.frame"); fs::write(out.join(&filename), frame).unwrap();
        cases.push(json!({"guard": name, "reason": reason, "observed_value": value, "frame": filename, "result": -7, "no_jobs": true, "latched": true}));
    }
    let mut operations = Vec::new();
    if meta["operation_diagnostics"] == true {
        let q = arena("freeze_queue"); let t = arena("retirement");
        let saved = emu.peek(q + 0x80, 44).unwrap();
        assert_eq!(emu.peek32(q + 56), Some(0));
        for (name, index, site, returned, expected_reason, slot) in [
            ("load",0_u32,t+0x400e,0_u32,16_u32,42_u32),
            ("unload",1,t+0x410e,0,17,43),
            ("clear",2,t+0x420e,0,18,44),
            ("returned",0,t+0x400e,1,4,0),
            ("unknown",0,0,0,4,0),
        ] {
            let mut context = [0_u32;11]; context[0]=site; context[1]=0x4004eaae;
            context[2]=if index==0 {0x42900000} else {slot}; context[3]=slot;
            context[7]=returned;
            let bytes:Vec<_>=context.into_iter().flat_map(u32::to_be_bytes).collect();
            emu.poke(q+0x80,&bytes).unwrap(); emu.poke(q+56,&1_u32.to_be_bytes()).unwrap();
            emu.button(17,true).unwrap();advance(emu,5_000_000);
            emu.button(24,true).unwrap();advance(emu,5_000_000);
            emu.button(24,false).unwrap();advance(emu,5_000_000);
            emu.button(17,false).unwrap();advance(emu,10_000_000);
            assert_eq!(emu.peek32(ui+36),Some(9)); assert_eq!(emu.peek32(ui+72),Some((-7_i32) as u32));
            assert_eq!(emu.peek32(nb+0x12c),Some(4)); assert_eq!(emu.peek32(nb+0x130),Some(1));
            assert_eq!(emu.peek32(ui+108),Some(expected_reason));
            let displayed=if expected_reason==4 {1} else {slot};
            assert_eq!(emu.peek32(ui+112),Some(displayed));
            assert_eq!(emu.peek(nb+0x140,44).unwrap(),bytes,"atomic backend snapshot differs");
            assert_eq!(emu.peek(ui+116,44).unwrap(),bytes,"UI context differs");
            assert_eq!(emu.peek32(nb),Some(0)); assert_eq!(emu.peek(nb+8,20).unwrap(),counts);
            emu.poke(q+56,&[0;4]).unwrap(); emu.poke(q+0x80,&saved).unwrap();
            emu.poke(nb+0x140,&[0;44]).unwrap(); advance(emu,5_000_000);
            assert_eq!(emu.peek32(ui+108),Some(expected_reason)); assert_eq!(emu.peek32(ui+112),Some(displayed));
            let (_,frame)=emu.current_frame().unwrap();let filename=format!("diagnostic-sample-{name}.frame");
            fs::write(out.join(&filename),frame).unwrap();
            operations.push(json!({"operation":name,"reason":expected_reason,"displayed_value":displayed,
                "observed_count":1,"latched":true,"no_jobs":true,"frame":filename,"injected_test_context":true}));
        }
    }
    fs::write(out.join("arm-diagnostics.json"), serde_json::to_vec_pretty(&json!({"status":"passed", "scope":"Test-only injected guard values through native FUNC+SONG after full-container application startup; these are controls, not the device diagnosis", "cases":cases,"operation_cases":operations,"waiting_samples_UI":wait_ui,"recordings":0, "hardware":false})).unwrap()).unwrap();
}
