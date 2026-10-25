"""Optional stock-clock/rate continuation of the native T1 arp on OS1.16."""
import struct
from lab import arp_modes as core
from lab.emit import Code
from lab.arp_firmware import (PRESAVE,RESTORE,ptr,load,store,setv,call,events,corecall,
                             MODES,TRACK,PATTERN,PLAY,BUSY,DIRECT,STATUS,ENCODER)
TEMPO,STEP,HALF,RATE,FOCUS=4480,4484,4488,4492,4496
TEMPO_GET=0x4002D744
DEFAULT=8 # OFF, sixteenths; packed mode | rate<<2.
STEPS=(345600000,172800000,86400000,43200000)
RATE_NAMES=('1/4','1/8','1/16','1/32')
# Original enum scaler and the existing view's ten-encoder accumulator.
# The stock view timer already services this state; no arp-owned timer/state.
ENCODER_SCALE,ENUM_CONFIG=0x40111B62,0x44D2E600
ENCODER_STATE=0x74
G_MOTION=ENCODER_STATE+0x20+6*0x14


def rate(address,p):
    """rate(state,index): close output/reset phase, preserve held/order."""
    c=Code();core.prefix(c);c.emit('242f002c');c.imm('0c82',3);c.branch(2,'invalid')
    core.constant(c,'flags',0);load(c,RATE);c.emit('b082');c.branch(7,'done')
    core.close_gate(c,'closed');store(c,RATE,2);core.constant(c,'phase',0)
    c.emit('2002 d080 d080 d080');c.imm('41f9',p['rate_steps']);c.emit('d1c0 2010 22280004');store(c,STEP);store(c,HALF,1)
    c.label('done');core.result(c);core.invalid(c);return c.finish(address)


def clock(address,p):
    """clock(state,sample_tick,playing), integer beat phase in BPM*120 units."""
    c=Code();core.prefix(c);c.emit('242f002c 262f0030');c.imm('0c83',1);c.branch(2,'invalid')
    core.constant(c,'flags',0);core.get(c,'tick',1);c.emit('2002 9081');core.put(c,'tick',2);c.emit('2a00')
    core.get(c,'enabled');c.emit('4a80');c.branch(7,'done');c.emit('4a83');c.branch(6,'play')
    core.get(c,'playing');c.emit('4a80');c.branch(7,'done');c.branch(0,'flush')
    c.label('play');load(c,TEMPO);c.imm('0c80',3600);c.branch(5,'flush');c.imm('0c80',36000);c.branch(2,'flush')
    core.get(c,'playing');c.emit('4a80');c.branch(6,'running');core.constant(c,'playing',1);core.constant(c,'phase',0);c.branch(0,'done')
    c.label('running');c.emit('2005');c.imm('0c80',48000);c.branch(2,'flush')
    load(c,TEMPO,1);c.emit('4c010800 2a00')
    core.get(c,'active');c.imm('0c80',-1);c.branch(7,'phase')
    core.get(c,'gate');c.emit('2205 9081');c.branch(15,'gate_expired');core.put(c,'gate');c.branch(0,'phase')
    c.label('gate_expired');core.close_gate(c,'gate_closed')
    c.label('phase');core.get(c,'phase',1);c.emit('2005 2041 d1c0 2008');load(c,STEP,1);c.emit('b081');c.branch(5,'store_phase')
    c.label('modulo');c.emit('9081 b081');c.branch(4,'modulo');core.put(c,'phase')
    core.get(c,'held');c.emit('4a80');c.branch(7,'done');core.close_gate(c,'step_closed')
    c.emit('2f0a');call(c,p,'select');c.emit('588f 2400');c.imm('0c82',-1);c.branch(7,'flush')
    for name in ('last','active','on'):core.put(c,name,2)
    core.pointer(c,core.VELOCITIES);c.emit('2010');core.put(c,'velocity');core.put(c,'on_velocity')
    load(c,HALF);core.put(c,'gate');core.get(c,'flags');c.imm('0080',2);core.put(c,'flags');c.branch(0,'done')
    c.label('store_phase');core.put(c,'phase');c.branch(0,'done')
    c.label('flush');core.close_gate(c,'panic_closed');core.clear_active(c,'clear')
    c.label('done');core.result(c);core.invalid(c);return c.finish(address)


def focus(address,p):
    # (view,event,is_main). Only unmodified G push in T1 Keyboard Settings.
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'no');c.emit('202f0030 4a80');c.branch(6,'no')
    load(c,TRACK)
    if p.get('any_track'):
        c.imm('0c80',15);c.branch(2,'no')
    else:
        c.emit('4a80');c.branch(6,'no')
    c.emit('266f002c 202b000c');c.imm('0c80',47);c.branch(6,'no')
    c.imm('4879',17);c.imm('4eb9',0x4011DE70);c.emit('588f 4a80');c.branch(6,'no')
    load(c,BUSY);c.emit('4a80');c.branch(6,'handled');c.emit('202b0010');c.imm('0280',1);c.branch(7,'handled')
    c.emit('202b0010');c.imm('0280',8);c.branch(6,'handled')
    load(c,FOCUS);c.emit('4a80');c.branch(7,'rate');setv(c,FOCUS,0);c.branch(0,'refresh')
    c.label('rate');setv(c,FOCUS,1)
    c.label('refresh')
    # Do not carry a partly turned mode gesture into the rate selector.
    # Keep the stock timestamp/cooldown; clear only acceleration and remainder.
    c.emit('206f0028 7000 '+f'2140{G_MOTION+8:04x} 2140{G_MOTION+12:04x}')
    c.emit('2f2f0028');c.imm('4eb9',0x4011AE46);c.emit('588f')
    # Let the original menu process the physical push/release as well.
    # It owns stock encoder/view bookkeeping even for this unused slot.
    c.label('handled');c.emit('7000');c.branch(0,'done');c.label('no');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(address)


def packed(c):
    load(c,RATE);c.emit('d080 d080');load(c,0,1);c.emit('2041 d1c0 2408')
    load(c,PATTERN);c.emit('d080 d080 41ea'+f'{MODES:04x}'+' d1c0 2082')


def encoder(address,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'stock');call(c,p,'sync');load(c,TRACK)
    if p.get('any_track'):
        c.imm('0c80',15);c.branch(2,'stock')
    else:
        c.emit('4a80');c.branch(6,'stock')
    c.emit('266f002c 202b000c');c.imm('0c80',7);c.branch(6,'stock')
    c.imm('4879',17);c.imm('4eb9',0x4011DE70);c.emit('588f 4a80');c.branch(6,'stock')
    load(c,BUSY);c.emit('4a80');c.branch(6,'consumed');load(c,DIRECT);c.emit('4a80');c.branch(6,'consumed')
    # Use exactly the stock enum response, including original event decoding.
    c.emit('286f0028');c.imm('4879',ENUM_CONFIG);c.emit('2f0b 41ec'+f'{ENCODER_STATE:04x}'+' 2f08')
    c.imm('4eb9',ENCODER_SCALE);c.emit('4fef000c 4a80');c.branch(7,'consumed');c.emit('2400')
    c.imm('0c82',3);c.branch(15,'lower');c.emit('7403');c.label('lower');c.imm('0c82',-3);c.branch(12,'delta');c.emit('74fd')
    c.label('delta');load(c,FOCUS);c.emit('4a80');c.branch(6,'rate_value');load(c,0);c.branch(0,'sum')
    c.label('rate_value');load(c,RATE)
    c.label('sum');c.emit('2600 2042 d1c0 2408 4a82');c.branch(10,'upper');c.emit('7400')
    c.label('upper');c.imm('0c82',3);c.branch(15,'apply');c.emit('7403')
    c.label('apply');c.emit('2002 b083');c.branch(7,'consumed')
    load(c,FOCUS);c.emit('4a80');c.branch(6,'rate_apply');corecall(c,p,'mode',('2f02',));c.branch(0,'applied')
    c.label('rate_apply');corecall(c,p,'rate',('2f02',))
    c.label('applied');events(c,p);packed(c)
    c.emit('2f2f0028');c.imm('4eb9',0x4011AE46);c.emit('588f')
    c.label('consumed');c.emit('7001 '+RESTORE+' 4e75')
    c.label('stock');c.emit(RESTORE+' 4fefffe048d73c3c');c.imm('4ef9',ENCODER+8);return c.finish(address)


def draw(address,p):
    c=Code();c.emit(PRESAVE)
    load(c,0);c.emit('d080 d080');c.imm('41f9',p['strings']+32);c.emit('d1c0 2410') # D2 mode string.
    load(c,RATE);c.emit('d080 d080');c.imm('41f9',p['rate_names']);c.emit('d1c0 2610') # D3 rate string.
    # A3 was the original draw context; D3 is caller saved by PRESAVE, but
    # retain context in A4 while D3 holds the text pointer.
    # The caller passes its draw context on the stack to avoid register alias.
    c.emit('286f0028')
    load(c,FOCUS);c.emit('4a80');c.branch(6,'rate_focus');c.imm('2a3c',p['ui_labels']);c.emit('2c02 2e03');c.branch(0,'values')
    c.label('rate_focus');c.imm('2a3c',p['ui_labels']+16);c.emit('2c03 2e02')
    c.label('values');load(c,STATUS);c.emit('4a80');c.branch(10,'status_ok');c.imm('2a3c',p['strings']+128);c.label('status_ok')
    for source,y,font in (('2f05',27,0x44D2E70C),('2f06',12,0x44D2E6C4),('2f07',2,0x44D2E70C)):
        c.emit(source)
        for v in (0x22,y,80,font):c.imm('4879',v)
        c.emit('2f0c');c.imm('4eb9',0x40113AE8);c.emit('4fef0018')
    c.emit(RESTORE+' 4e75');return c.finish(address)


def payload(p):
    out={}
    for name,fn in (('rate',rate),('rate_focus',focus),('rate_draw',draw)):
        out[name]=(fn(p.get(name,0),p),'code')
    out['rate_steps']=(b''.join(struct.pack('>II',x,x//2) for x in STEPS),'data')
    names=bytearray(48)
    for i,n in enumerate(RATE_NAMES):
        struct.pack_into('>I',names,4*i,p.get('rate_names',0)+16+8*i);names[16+8*i:16+8*i+len(n)+1]=n.encode()+b'\0'
    # Stock masked blit reads the sixth word at +20. Legacy output is kept
    # byte-identical; dense relocatable layouts require an explicit mask pointer
    # instead of accidentally reading the next payload as that pointer.
    bitmap=struct.pack('>5I',0x4021CB40,17,17,1,p.get('g_pixels',0))
    if p.get('bitmap_mask'):bitmap+=struct.pack('>I',p.get('g_pixels',0))
    out['g_blank']=(bitmap,'data');out['g_pixels']=(bytes(68),'data')
    out['rate_names']=(bytes(names),'data');out['ui_labels']=(b'ARP\0'+bytes(12)+b'RATE\0'+bytes(11),'data')
    return out
