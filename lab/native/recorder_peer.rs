//! OS1.16 recorder service peer, ported from lab.flex_recorder. Opt-in only.
//! Models external capture/readback, never sample loading or BUF publication.
use super::*;

const RESPONSE: u32 = 0x4fe7_9340;
const TICK: u32 = 0x4096_6500;
const LOCK: u32 = 0x4096_5b74;
pub(super) const SITES: [u32; 8] = [
    0x4001_5fda, 0x4001_61fe, 0x4001_5ff8, 0x400c_d6ce,
    0x4001_24a0, 0x4000_1608, 0x4000_172a, 0x400c_d638,
];

#[derive(Clone, Debug, Serialize)]
pub struct RecorderEvent {
    pub event: String, pub tick: u32, pub frames: u32,
    pub command: Option<u16>, pub start: u32, pub count: u32,
}

#[derive(Clone)]
pub struct RecorderPeer {
    pub source: Vec<u8>, pub active: bool, pub started: u32,
    pub captured: u32, pub completed: Option<Vec<u8>>,
    pub events: Vec<RecorderEvent>, pub lock_depth: i32,
    pub pages: Vec<(u32, Vec<u8>, u32)>,
}

impl RecorderPeer {
    pub fn new(source: Vec<u8>) -> Result<Self, String> {
        if source.len()%4 != 0 || !(141*4..=480_000*4).contains(&source.len()) {
            return Err("expected 141..480000 stereo PCM16 frames".into());
        }
        Ok(Self {source, active:false, started:0, captured:0, completed:None,
            events:vec![], lock_depth:0, pages:vec![]})
    }
    pub fn begin(&mut self,tick:u32) -> Result<(),String> {
        if self.active {return Err("already recording".into());}
        self.started=tick;self.active=true;self.captured=0;self.completed=None;
        self.event("record",tick,None,0,0);Ok(())
    }
    pub fn count(&mut self,tick:u32)->u32 {
        if self.active {self.captured=tick.wrapping_sub(self.started).max(1).min((self.source.len()/4) as u32);}
        self.captured
    }
    pub fn finish(&mut self,tick:u32) {
        self.count(tick);self.active=false;
        self.completed=Some(self.source[..self.captured as usize*4].to_vec());
        self.event("stop",tick,None,0,0);
    }
    pub fn discard(&mut self,tick:u32) {
        self.active=false;self.completed=None;self.captured=0;
        self.event("discard",tick,None,0,0);
    }
    fn event(&mut self,name:&str,tick:u32,command:Option<u16>,start:u32,count:u32) {
        self.events.push(RecorderEvent{event:name.into(),tick,frames:self.captured,command,start,count});
    }
    pub fn response(&mut self,descriptor:&[u8],size:usize,tick:u32)->Result<Vec<u8>,String> {
        if ![2,4,12].contains(&descriptor.len()) || size>0xb40 {return Err("recorder peer request bounds".into());}
        let cmd=u16::from_be_bytes(descriptor[..2].try_into().unwrap());
        let mut start=0;let mut count=0;let mut out=vec![0;size];
        match cmd {
            3=>{
                if descriptor.len()!=12 || size!=16 {return Err("waveform request extent".into());}
                start=u32::from_be_bytes(descriptor[4..8].try_into().unwrap());
                let end=u32::from_be_bytes(descriptor[8..12].try_into().unwrap());
                let data=self.completed.as_ref().unwrap_or(&self.source);
                let limit=if self.completed.is_some(){self.captured}else{(data.len()/4) as u32};
                let end=end.min(limit);count=end.saturating_sub(start);
                if start<end {
                    let mut peaks=[i16::MAX,i16::MIN,i16::MAX,i16::MIN];
                    for f in start..end {for ch in 0..2 {
                        let at=f as usize*4+ch*2;let v=i16::from_be_bytes(data[at..at+2].try_into().unwrap());
                        peaks[ch*2]=peaks[ch*2].min(v);peaks[ch*2+1]=peaks[ch*2+1].max(v);
                    }}
                    for(i,v)in peaks.into_iter().enumerate(){out[i*4..i*4+4].copy_from_slice(&(v as i32).to_be_bytes());}
                }
            }
            4=>{
                if descriptor.len()!=12 || size!=2048 || self.lock_depth!=2 {return Err("PCM readback bounds or lost outer lock".into());}
                let mono=u16::from_be_bytes(descriptor[2..4].try_into().unwrap());
                start=u32::from_be_bytes(descriptor[4..8].try_into().unwrap());
                count=u32::from_be_bytes(descriptor[8..12].try_into().unwrap());
                let end=start.checked_add(count).ok_or("PCM range overflow")?;
                if self.active || mono!=0 || end>self.captured || count>512 {return Err("PCM outside completed stereo take".into());}
                let data=self.completed.as_ref().ok_or("PCM before STOP")?;
                out[..count as usize*4].copy_from_slice(&data[start as usize*4..end as usize*4]);
            }
            0|1|2|5=>{},
            _=>return Err(format!("unknown recorder command {cmd}")),
        }
        self.event("command",tick,Some(cmd),start,count);Ok(out)
    }
}

impl Emulator {
    /// Install only on the authenticated OS1.16 MAIN. No guest code is changed.
    pub fn set_recorder_peer(&mut self,peer:RecorderPeer)->Result<(),String> {
        if self.device!="dt2" || self.version!="1.16" {return Err("recorder adapter requires DT2 OS1.16".into());}
        let guards=[0x48780002206f0008u64,0x4fefffd448d70c04,0x2f0a246f000842a7,
            0x71f98000100473f9,0x4feffff448d7001c,0x2f0a2f02246f000c,
            0x2f0a2f02246f000c,0x4feffff448d70c04];
        for (pc,want) in SITES.into_iter().zip(guards) {
            let bytes=self.peek(pc,8)?;
            // The current device-layout BUF page wrapper is an authenticated
            // hook over this one entry; arguments retain the stock ABI.
            let page_hook=pc==0x400c_d638 && bytes==0x4ef947ea8f004e71u64.to_be_bytes();
            if bytes!=want.to_be_bytes() && !page_hook{return Err(format!("recorder ABI guard {pc:#x}"));}
        }
        self.recorder_peer=Some(peer);self.rebuild_watch();Ok(())
    }
    pub fn recorder_peer(&self)->Option<&RecorderPeer>{self.recorder_peer.as_ref()}
    pub fn recorder_peer_mut(&mut self)->Option<&mut RecorderPeer>{self.recorder_peer.as_mut()}
    pub(super) fn recorder_observe(&mut self,pc:u32)->Result<bool,String> {
        if self.recorder_peer.is_none() || !SITES.contains(&pc){return Ok(false);}
        let tick=self.stack_long(TICK);let sp=self.cpu.a[7];
        let arg0=self.stack_long(sp+4);let arg1=self.stack_long(sp+8);let arg2=self.stack_long(sp+12);
        let mut peer=self.recorder_peer.take().unwrap();
        let result=(|| {
            match pc {
                0x4001_5fda=>peer.begin(tick)?,
                0x4001_61fe=>peer.finish(tick),
                0x4001_5ff8=>peer.discard(tick),
                0x400c_d6ce=>{let n=peer.count(tick);self.recorder_return(n);return Ok(true);},
                0x4000_1608|0x4000_172a if arg0==LOCK=>{
                    peer.lock_depth+=if pc==0x4000_1608{1}else{-1};
                    if peer.lock_depth<0{return Err("recorder lock underflow".into());}
                    if peer.lock_depth==0 {self.poke(RESPONSE,&[0xa5;2048])?;}
                }
                0x400c_d638=>peer.pages.push((arg0,self.peek(arg1,4096)?,arg2)),
                0x4001_24a0=>{
                    if ![2,4,12].contains(&arg0) || arg2>0xb40 {return Err("recorder command bounds".into());}
                    let desc=self.peek(arg1,arg0 as usize)?;
                    let data=peer.response(&desc,arg2 as usize,tick)?;
                    self.poke(RESPONSE,&data)?;self.recorder_return(0);return Ok(true);
                }
                _=>{},
            }
            Ok(false)
        })();self.recorder_peer=Some(peer);result
    }
    fn recorder_return(&mut self,value:u32) {
        let sp=self.cpu.a[7];self.cpu.d[0]=value;
        self.cpu.pc=self.stack_long(sp);self.cpu.a[7]=sp+4;
    }
}
