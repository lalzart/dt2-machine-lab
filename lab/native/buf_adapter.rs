//! Opt-in OS1.16 saved-page adapter over the current native SHARC engine.
//! LP0 callback entry/exit and prepared state remain explicit harness inputs.
use sharc_native::{Engine, rt::V};

pub struct NativeBuf { pub engine: Engine }

impl NativeBuf {
    pub fn prepared(image: &[u8], state: &[u8], options:&[(u32,i64)]) -> Self {
        let mut e=Engine::from_image(image).expect("DSP loader image");
        e.import(state).expect("canonical prepared DSP state");
        for &(k,v) in options {
            assert_eq!(e.set_option(k,v),0,"native option {k}");
        }
        Self{engine:e}
    }
    pub fn segment(&mut self,start:u32,stop:u32,bound:u32) {
        let e=&mut self.engine;
        assert_eq!(e.set_option(8,stop as i64),0);
        e.fresh_call(start,None);e.step(bound);
        assert_eq!(e.s.pc_sw,stop as i128,"native segment {start:#x}, halt={:?}",e.halt);
        assert_eq!(e.set_option(8,-1),0);
    }
    pub fn word(&self,at:u64,width:u32)->u32 {
        self.engine.peek(at,width).expect("DSP peek trap").expect("unknown DSP word")
    }
    pub fn pointers(&self)->Vec<u32> {
        [0,1,8,9,10,11].iter().map(|v|self.word(0x2412cc+v*0x1d8,4)).collect()
    }
    pub fn descriptor(&self,slot:u64)->Vec<u32> {
        (0..5).map(|i|self.word(0x257810+slot*20+i*4,if i==4 {1} else {4})).collect()
    }
    pub fn publish(&mut self,packets:&[u8]) {
        assert_eq!(packets.len()%4100,0,"incomplete LP0 packet");
        let saved=self.engine.s.r.clone();
        self.segment(0x1c7ed7,0x1c83ff,128);
        self.engine.s.r=saved.clone();
        assert_eq!(self.word(0x268224,4),0x268240);
        assert_eq!(self.word(0x26822c,4),0x401);
        for packet in packets.chunks_exact(4100) {
            assert_eq!(self.engine.poke(0x268240,packet,1),4100);
            for (code,value) in [(4,0),(8,4),(12,0x268220)] {
                self.engine.set_reg(code,V::c(value));
            }
            self.segment(0x1c7e1f,0x1c834a,20_000);
            self.engine.s.r=saved.clone();
        }
    }
    pub fn frame(&mut self,wire:&[u8])->(Vec<u8>,Vec<u8>) {
        let reply=self.engine.spi2_exchange(wire).expect("native SPI2 delivery");
        self.segment(0x1c7756,0x1c775d,4_000_000);
        assert_eq!(self.word(0x31089a2c,4),0,"SEC not drained");
        assert_eq!(self.word(0x31089a34,4),0,"SEC not drained");
        let mut pcm=Vec::with_capacity(8192);
        for lane in 0..32 {
            for i in 0..64 {
                let word=self.word(0x2412cc+lane*0x1d8+4+i*4,4);
                assert!(f32::from_bits(word).is_finite(),"nonfinite voice PCM");
                pcm.extend_from_slice(&word.to_le_bytes());
            }
        }
        (reply,pcm)
    }
}
