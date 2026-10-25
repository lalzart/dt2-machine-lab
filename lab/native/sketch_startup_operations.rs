//! Read-only observation of stock sample-operation guards during cold startup.
//! Guest code, count, task state and sample data are never changed here.
use elektron_native_boot::Emulator;
use serde_json::{Value, json};
use std::{collections::HashMap, fs, path::Path};

pub struct Operations {
    count: u32,
    watch: Vec<u32>,
    names: HashMap<u32, String>,
    pending: HashMap<u32, Value>,
    active: HashMap<u32, Value>,
    events: Vec<Value>,
    timeline: Vec<Value>,
    depth: i32,
    peak: i32,
    completed: usize,
    unmatched: usize,
    last_count: Option<u32>,
    ready: Option<Value>,
    diagnostics: bool,
}

impl Operations {
    pub fn new(emu: &mut Emulator, meta: &Value) -> Self {
        let arena = |name: &str| meta["arenas"].as_array().unwrap().iter()
            .find(|a| a["name"] == name).unwrap()["destination"].as_u64().unwrap() as u32;
        let q = arena("freeze_queue");
        let mut names = HashMap::new();
        names.insert(q + 0x1c00, "enter".into());
        names.insert(q + 0x1d00, "leave".into());
        for (base, layer) in [(arena("retirement") + 0x4000, "retirement"), (q + 0x3100, "freeze")] {
            for (i, name) in ["load", "unload", "clear"].iter().enumerate() {
                names.insert(base + i as u32 * 0x100, format!("{layer}/{name}"));
            }
        }
        let mut watch: Vec<_> = names.keys().copied().collect(); watch.sort();
        emu.record_regs_at(&watch);
        Self {count: q + 56, watch, names, pending: HashMap::new(), active: HashMap::new(),
            events: vec![], timeline: vec![], depth: 0, peak: 0, completed: 0,
            unmatched: 0, last_count: None, ready: None, diagnostics: meta["operation_diagnostics"] == true}
    }

    pub fn sample(&mut self, emu: &mut Emulator, stage: &str, ready: bool) {
        let (hits, dropped) = emu.reg_log();
        assert_eq!(dropped, 0, "startup operation trace overflow");
        let hits = hits.to_vec();
        emu.record_regs_at(&self.watch);
        for hit in hits {
            let name = &self.names[&hit.pc];
            let sp = hit.a[7];
            if name != "enter" && name != "leave" {
                self.pending.insert(sp, json!({"operation":name,"caller":hit.stack[0],
                    "arguments":&hit.stack[1..],"stack":sp,"icount":hit.icount}));
                continue;
            }
            // The guarded wrapper reserves 16 bytes and JSR pushes four.
            let key = sp + 20;
            if name == "enter" {
                self.depth += 1; self.peak = self.peak.max(self.depth);
                let context = self.pending.remove(&key).unwrap_or_else(|| {
                    self.unmatched += 1; json!({"operation":"unknown","stack":key})
                });
                assert!(self.active.insert(key, context.clone()).is_none(), "duplicate active operation frame");
                self.events.push(json!({"event":name,"icount":hit.icount,"depth":self.depth,"context":context}));
            } else {
                self.depth -= 1;
                assert!(self.depth >= 0, "sample-operation counter underflow");
                let context = self.active.remove(&key).unwrap_or_else(|| {
                    self.unmatched += 1; json!({"operation":"unknown","stack":key})
                });
                self.completed += 1;
                self.events.push(json!({"event":name,"icount":hit.icount,"depth":self.depth,
                    "context":context,"return_value":hit.d[2]}));
            }
        }
        let count = emu.peek32(self.count).unwrap();
        if self.last_count != Some(count) || self.timeline.last().is_none_or(|r| r["stage"] != stage) {
            self.timeline.push(json!({"icount":emu.icount(),"stage":stage,"count":count,
                "event_depth":self.depth,"task":emu.peek32(0x47db3f64),
                "stock_loader_busy":emu.peek32(0x405b1360),"active":self.active.values().collect::<Vec<_>>()}));
            self.last_count = Some(count);
        }
        if ready && self.ready.is_none() {
            self.ready = Some(json!({"icount":emu.icount(),"count":count,
                "active":self.active.values().collect::<Vec<_>>()}));
        }
    }

    pub fn finish(&self, emu: &mut Emulator, out: &Path) {
        let count = emu.peek32(self.count).unwrap();
        let diagnostic = if self.diagnostics {
            let base = self.count - 56;
            let enters = emu.peek32(base + 0xa0).unwrap(); let exits = emu.peek32(base + 0xa4).unwrap();
            assert_eq!(enters as usize, self.completed); assert_eq!(enters, exits);
            assert_eq!(emu.peek32(base + 0x9c), Some(1));
            json!({"enters":enters,"exits":exits,"outer_returned":true,"matches_read_only_trace":true})
        } else { Value::Null };
        let report = json!({"status":"observed","scope":"Read-only native CPU guard observation from application reset; modeled card/DSP transport and instruction cadence",
            "firmware_modified":false,"host_count_writes":false,"recordings":0,"hardware":false,
            "events":self.events,"timeline":self.timeline,"first_CPU_ready":self.ready,
            "completed_operations":self.completed,"maximum_nested_depth":self.peak,
            "unmatched_events":self.unmatched,"remaining_active":self.active.values().collect::<Vec<_>>(),
            "final_count":count,"final_event_depth":self.depth,"diagnostic_metadata":diagnostic});
        fs::write(out.join("startup-operations.json"), serde_json::to_vec_pretty(&report).unwrap()).unwrap();
        assert_eq!(self.unmatched, 0, "unmatched sample operation events");
        assert_eq!(count as i32, self.depth, "count and event depth disagree");
        assert_eq!(count, 0, "sample operation remains active after startup quiet");
        assert!(self.active.is_empty());
    }
}
