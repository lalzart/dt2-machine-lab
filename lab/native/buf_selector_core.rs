//! Small instruction-test bridge to unmodified DigiKit ColdFire (std only).
//! No peripheral models or feature implementations live in this bridge.
use coldfire::{Bus, BusError, Cpu};
use std::collections::BTreeMap;

struct Memory(BTreeMap<u32, Box<[u8; 4096]>>);
impl Bus for Memory {
    fn read8(&mut self, a: u32) -> Result<u8, BusError> {
        self.0.get(&(a & !4095)).map(|p| p[(a & 4095) as usize])
            .ok_or(BusError { addr: a, write: false })
    }
    fn read16(&mut self, a: u32) -> Result<u16, BusError> {
        Ok(u16::from_be_bytes([self.read8(a)?, self.read8(a + 1)?]))
    }
    fn read32(&mut self, a: u32) -> Result<u32, BusError> {
        Ok(u32::from_be_bytes([self.read8(a)?, self.read8(a+1)?,
                              self.read8(a+2)?, self.read8(a+3)?]))
    }
    fn write8(&mut self, a: u32, v: u8) -> Result<(), BusError> {
        let p = self.0.get_mut(&(a & !4095)).ok_or(BusError {addr:a,write:true})?;
        p[(a & 4095) as usize] = v; Ok(())
    }
    fn write16(&mut self, a: u32, v: u16) -> Result<(), BusError> {
        for (i,b) in v.to_be_bytes().iter().enumerate() {self.write8(a+i as u32,*b)?;} Ok(())
    }
    fn write32(&mut self, a: u32, v: u32) -> Result<(), BusError> {
        for (i,b) in v.to_be_bytes().iter().enumerate() {self.write8(a+i as u32,*b)?;} Ok(())
    }
}
pub struct Machine { cpu: Cpu, memory: Memory }
#[unsafe(no_mangle)] pub extern "C" fn cf_new() -> *mut Machine {
    Box::into_raw(Box::new(Machine {cpu:Cpu::new(),memory:Memory(BTreeMap::new())}))
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_drop(p: *mut Machine) {
    if !p.is_null() {drop(unsafe {Box::from_raw(p)});}
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_map(p:*mut Machine,a:u32,n:u32) {
    let m=unsafe {&mut *p};for i in (a..a+n).step_by(4096) {
        m.memory.0.entry(i).or_insert_with(|| Box::new([0;4096]));
    }
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_write(p:*mut Machine,a:u32,b:*const u8,n:usize)->i32 {
    let m=unsafe {&mut *p};for (i,v) in unsafe {std::slice::from_raw_parts(b,n)}.iter().enumerate() {
        if m.memory.write8(a+i as u32,*v).is_err(){return -1;}
    }m.cpu.invalidate_external_write(a,n);0
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_read(p:*mut Machine,a:u32,b:*mut u8,n:usize)->i32 {
    let m=unsafe {&mut *p};for (i,v) in unsafe {std::slice::from_raw_parts_mut(b,n)}.iter_mut().enumerate() {
        match m.memory.read8(a+i as u32) {Ok(x)=>*v=x,Err(_)=>return -1}
    }0
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_reg(p:*mut Machine,r:u32,v:u32,write:bool)->u32 {
    let m=unsafe {&mut *p};let slot=match r {0..=7=>&mut m.cpu.d[r as usize],
        8..=15=>&mut m.cpu.a[(r-8) as usize],16=>&mut m.cpu.pc,_=>{
            if write {m.cpu.sr=v as u16;}return m.cpu.sr as u32;
        }};if write {*slot=v;}*slot
}
#[unsafe(no_mangle)] pub unsafe extern "C" fn cf_run(p:*mut Machine,start:u32,end:u32,limit:u32)->i32 {
    let m=unsafe {&mut *p};m.cpu.pc=start;
    for _ in 0..limit {
        if m.cpu.pc==end {return 0;}
        if let Err(e)=m.cpu.step(&mut m.memory) {eprintln!("ColdFire stop: {e:?}");return -1;}
    }1
}
