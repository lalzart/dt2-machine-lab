"""Guarded stock OS1.16 native arp overlay; no Python runtime feature services."""
import hashlib
import struct
from lab import arp_modes as core
from lab.emit import Code
from lab.dt2_116 import BASE, STOCK_SHA, CANDIDATE_GAPS, OWNERSHIP_GAPS
from lab.coldfire import audit_code
from lab.project import require
from lab.resources import PaddingAllocator

SIZE=8192
MODES=2120
KEYS=2632
PLAY=2696
TRACK=2700
PATTERN=2704
KEYBOARD=2708
LASTKEY=2712
DIRECT=2716
BUSY=2720
VIEW=2724
SAVE_MODES=2728
STATUS=3240
# Optional D1 diagnostic state, beyond the journal's final word at 4340.
DIAG_CLOCK,DIAG_NOTES,DIAG_API=4344,4348,4352
DIAG_CALLER=4356
DIAG_TOP,DIAG_MIDDLE,DIAG_BOTTOM,DIAG_ID=4384,4400,4416,4432
DIAG_CALLER_TEXT=4448
DIAG_CALLER_LOW_TEXT=4464
ON,OFF=0x4011FE12,0x4012020C
TICK=0x40966500
MAINLOOP=0x40033D00
KEY,MENU_KEY,ENCODER,DRAW_RETURN=0x4005DC58,0x4010206C,0x4010186C,0x40102616
PRESAVE='4fefffdc 48d71cfc'
RESTORE='4cd71cfc 4fef0024'


def ptr(c,p):
    c.imm('2479',p['pointer']);c.emit('200a 4a80')


def load(c,off,reg=0):c.emit(f'{0x202a|(reg<<9):04x}{off:04x}')
def store(c,off,reg=0):c.emit(f'{0x2540|reg:04x}{off:04x}')
def setv(c,off,value):
    c.imm('203c',value);store(c,off)
def call(c,p,name):c.imm('4eb9',p[name])
def corecall(c,p,name,args=()):
    for arg in reversed(args):
        if isinstance(arg,int):c.imm('4879',arg)
        else:c.emit(arg)
    c.emit('2f0a');call(c,p,name);c.emit(f'4fef{4*(len(args)+1):04x}')
def events(c,p):call(c,p,'events')
def panic(c,p):corecall(c,p,'panic');events(c,p)


def initialize(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(6,'done')
    c.imm('4879',SIZE);c.imm('4eb9',0x4011E674);c.emit('588f 4a80');c.branch(7,'done')
    c.emit('2440 2040 7200');c.imm('203c',SIZE//4)
    c.label('zero');c.emit('20c1 5380');c.branch(6,'zero')
    corecall(c,p,'init',('2f39'+f'{TICK:08x}',0))
    if p.get('tempo_ui'):
        from lab import arp_tempo as t
        setv(c,t.RATE,-1);corecall(c,p,'rate',(2,))
        c.emit('41ea'+f'{MODES:04x}'+' 7008');c.imm('223c',128)
        c.label('default_configs');c.emit('20c0');c.imm('0681',-1);c.branch(6,'default_configs')
    setv(c,PATTERN,-1);setv(c,TRACK,-1);setv(c,LASTKEY,-1)
    c.emit('200a');c.imm('23c0',p['pointer'])
    c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def output(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'done')
    load(c,core.FIELDS['flags'],2);c.emit('2002');c.imm('0280',1);c.branch(7,'on')
    c.emit('7000 2f00 48780040');load(c,40);c.emit('2f00')
    if p.get('any_track'):load(c,TRACK)
    else:c.emit('7000')
    c.emit('2f00');c.imm('4eb9',OFF);c.emit('4fef0010')
    c.label('on');c.emit('2002');c.imm('0280',2);c.branch(7,'done')
    if p.get('diagnostics'):
        load(c,DIAG_NOTES);c.emit('5280');store(c,DIAG_NOTES)
    for x in (-1,-1,-1,-1,0,0x40):c.imm('4879',x)
    load(c,48);c.emit('2f00');load(c,44);c.emit('2f00')
    if p.get('any_track'):load(c,TRACK)
    else:c.emit('7000')
    c.emit('2f00');c.imm('4eb9',ON);c.emit('4fef0024')
    c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def synchronize(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'done')
    load(c,BUSY);c.emit('4a80');c.branch(6,'done')
    c.imm('4eb9',0x401988A2);c.emit('2f00');c.imm('4eb9',0x40041D18)
    # Read the stock project's keyboard setting, including restored state.
    # 4004AF88 returns a byte boolean; normalize it before any long test.
    c.emit('2800 2f00');c.imm('4eb9',0x4004AF88);c.emit('588f');c.imm('0280',255)
    load(c,KEYBOARD,1);store(c,KEYBOARD);c.emit('4a80');c.branch(6,'keyboard_synced');c.emit('4a81');c.branch(7,'keyboard_synced');panic(c,p)
    c.label('keyboard_synced');c.emit('2f04');c.imm('4eb9',0x4004ABE8);c.emit('508f 2400')
    c.imm('4eb9',0x40199680);c.emit('2f00');c.imm('4eb9',0x400F541C);c.emit('588f 2600')
    invalid_context = 'invalid_context' if p.get('any_track') else 'done'
    c.imm('0c82',15);c.branch(2,invalid_context);c.imm('0c83',127);c.branch(2,invalid_context)
    load(c,TRACK);c.emit('b082');c.branch(6,'change');load(c,PATTERN);c.emit('b083');c.branch(7,'view')
    c.label('change');panic(c,p);store(c,TRACK,2);store(c,PATTERN,3)
    if not p.get('any_track'):
        c.emit('7000 4a82');c.branch(6,'apply')
    c.emit('2003 d080 d080 41ea'+f'{MODES:04x}'+' d1c0 2010')
    if p.get('tempo_ui'):c.emit('2800');c.imm('0280',3)
    c.label('apply');corecall(c,p,'mode',('2f00',));events(c,p)
    if p.get('tempo_ui'):
        # Non-T1 destinations remain disabled; retain the T1 rate until return.
        if not p.get('any_track'):
            c.emit('4a82');c.branch(6,'view')
        c.emit('2004 e488');c.imm('0280',3)
        corecall(c,p,'rate',('2f00',));events(c,p)
    c.label('view')
    if p.get('any_track'):c.emit('7001')
    else:
        c.emit('7000');load(c,TRACK,1);c.emit('4a81');c.branch(6,'active');c.emit('7001')
    c.label('active');store(c,core.FIELDS['ui_active'])
    if p.get('any_track'):
        c.branch(0,'done');c.label('invalid_context');panic(c,p)
        corecall(c,p,'mode',(0,));setv(c,TRACK,-1);setv(c,core.FIELDS['ui_active'],0)
    c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def heartbeat(a,p):
    c=Code();c.emit('4fefffc0 48d77fff 40c0 2f40003c')
    call(c,p,'ensure');call(c,p,'sync');ptr(c,p);c.branch(7,'done')
    load(c,BUSY);c.emit('4a80');c.branch(6,'done')
    if p.get('diagnostics'):
        load(c,PLAY);c.emit('4a80');c.branch(7,'clock_observed')
        c.imm('2039',TICK);load(c,core.FIELDS['tick'],1);c.emit('b081');c.branch(7,'clock_observed')
        setv(c,DIAG_CLOCK,1)
        c.label('clock_observed')
    if p.get('tempo_ui'):
        from lab.arp_tempo import TEMPO,TEMPO_GET
        c.imm('4eb9',TEMPO_GET);store(c,TEMPO)
    load(c,PLAY)
    if p.get('stopped_playback'):
        # Share the audio sample clock and tempo core in both transport states.
        # STOP still panics/clears held input; fresh keyboard notes can re-arm.
        c.emit('4a80');c.branch(6,'arp_clock_enabled')
        load(c,KEYBOARD);c.emit('4a80');c.branch(7,'arp_clock_enabled')
        load(c,core.FIELDS['held']);c.emit('4a80');c.branch(7,'arp_clock_enabled')
        c.emit('7001');c.label('arp_clock_enabled')
    corecall(c,p,'clock',('2f39'+f'{TICK:08x}','2f00'));events(c,p)
    c.label('done');c.emit('202f003c 44c0 4cd77fff 4fef0040')
    c.imm('4879',0x40966F3C);c.imm('4ef9',MAINLOOP+6);return c.finish(a)


def input_event(a,p):
    # (view,event,is_main), return nonzero only for a consumed physical release.
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'no')
    if p.get('tempo_ui'):
        c.emit('2f2f0030 2f2f0030 2f2f0030');call(c,p,'rate_focus');c.emit('4fef000c 4a80');c.branch(6,'done')
    c.emit('266f002c 242b000c 262b0010')
    c.emit('202f0030 4a80');c.branch(7,'key');c.emit('202f0028');store(c,VIEW)
    c.label('key');store(c,LASTKEY,2)
    c.emit('2003');c.imm('0280',1);c.branch(6,'press')
    c.imm('0c82',25);c.branch(5,'no');c.imm('0c82',40);c.branch(2,'no')
    c.emit('2002');c.imm('0680',-25);c.emit('d080 d080 47ea'+f'{KEYS:04x}'+' d7c0 2013 4a80');c.branch(7,'no')
    c.emit('5380 2400 7000 2680');corecall(c,p,'release',('2f02',));events(c,p);c.emit('7001');c.branch(0,'done')
    c.label('press');load(c,BUSY);c.emit('4a80');c.branch(6,'no');c.emit('2003');c.imm('0280',8);c.branch(6,'no')
    c.imm('0c82',20);c.branch(6,'stop');c.imm('4879',17);c.imm('4eb9',0x4011DE70);c.emit('588f 4a80');c.branch(6,'no');setv(c,PLAY,1)
    if p.get('diagnostics'):setv(c,DIAG_CLOCK,0)
    c.branch(0,'no')
    c.label('stop');c.imm('0c82',21);c.branch(6,'exit');setv(c,PLAY,0);panic(c,p);c.branch(0,'no')
    c.label('exit');c.imm('0c82',18);c.branch(6,'other')
    c.emit('2003');c.imm('0280',2);c.branch(6,'no')
    panic(c,p);c.branch(0,'no')
    c.label('other')
    for k in (16,23,24):
        c.imm('0c82',k);c.branch(7,'flush')
    c.branch(0,'no');c.label('flush');panic(c,p)
    c.label('no');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def key_hook(a,p,site,ismain):
    c=Code();c.emit(PRESAVE);c.imm('4879',int(ismain));c.emit('2f2f0030 2f2f0030');call(c,p,'input');c.emit('4fef000c 4a80');c.branch(7,'stock')
    c.emit('7001 '+RESTORE+' 4e75');c.label('stock');c.emit(RESTORE)
    if ismain:c.emit('4e56ffa4 48d73cfc')
    else:c.emit('4fefffe4 48d73c1c')
    c.imm('4ef9',site+8)
    # Exact displaced stock prologues include LINK not part of Code's subset.
    return finish_stock(c,a)


def note_hook(a,p,release=False):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'stock')
    if p.get('diagnostics') and not release:
        # Counts every T1 note-on API entry except our own generated output.
        # Caller filtering remains unchanged; observing cannot collect a note.
        c.emit('202f0028 4a80');c.branch(6,'api_observed')
        c.emit('202f0024');c.imm('0c80',p['events']);c.branch(5,'api_count')
        c.imm('0c80',p['events']+len(output(0,p)));c.branch(5,'api_observed')
        c.label('api_count');store(c,DIAG_CALLER);load(c,DIAG_API);c.emit('5280');store(c,DIAG_API)
        c.label('api_observed')
    c.emit('202f0024');c.imm('0c80',0x4005C718 if release else 0x4005C666);c.branch(6,'stock')
    if p.get('any_track') and not release:call(c,p,'sync')
    c.emit('202f0028')
    if p.get('any_track'):
        if not release:
            load(c,TRACK,1);c.emit('b081');c.branch(6,'stock')
        c.imm('0c80',15);c.branch(2,'stock')
    else:
        c.emit('4a80');c.branch(6,'stock')
    c.emit('242f002c');c.imm('0c82',127);c.branch(2,'stock')
    if release:
        c.emit('2002 d080 d080 41ea'+f'{core.OWNERS:04x}'+' d1c0 2010 4a80');c.branch(7,'direct')
        corecall(c,p,'release',('2f02',));events(c,p);c.branch(0,'consumed')
    else:
        if not p.get('any_track'):call(c,p,'sync')
        load(c,KEYBOARD);c.emit('4a80');c.branch(7,'direct');load(c,0);c.emit('4a80');c.branch(7,'direct')
        corecall(c,p,'press',('2f02','2f2f0030'));c.imm('0c80',-1);c.branch(7,'consumed')
        load(c,LASTKEY);c.imm('0c80',25);c.branch(5,'consumed');c.imm('0c80',40);c.branch(2,'consumed')
        c.imm('0680',-25);c.emit('d080 d080 41ea'+f'{KEYS:04x}'+' d1c0 2002 5280 2080');c.branch(0,'consumed')
    c.label('direct');load(c,DIRECT)
    if release:
        c.emit('4a80');c.branch(7,'stock');c.emit('5380')
    else:c.emit('5280')
    store(c,DIRECT);c.branch(0,'stock')
    c.label('consumed');c.emit('7000 '+RESTORE+' 4e75')
    c.label('stock');c.emit(RESTORE);c.emit('4e56ff84 707f' if release else '4e56ff88 707f');c.imm('4ef9',(OFF if release else ON)+6)
    return finish_stock(c,a)


def encoder_hook(a,p):
    if p.get('tempo_ui'):
        from lab.arp_tempo import encoder
        return encoder(a,p)
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'stock');call(c,p,'sync')
    load(c,TRACK);c.emit('4a80');c.branch(6,'stock');c.emit('266f002c 202b000c');c.imm('0c80',7);c.branch(6,'stock')
    load(c,BUSY);c.emit('4a80');c.branch(6,'handled');load(c,DIRECT);c.emit('4a80');c.branch(6,'handled')
    c.emit('242b0010');c.imm('0c82',3);c.branch(15,'lower');c.emit('7403')
    c.label('lower');c.imm('0c82',-3);c.branch(12,'delta');c.emit('74fd')
    c.label('delta');load(c,0);c.emit('2042 d1c0 2408 4a82');c.branch(10,'upper');c.emit('7400')
    c.label('upper');c.imm('0c82',3);c.branch(15,'apply');c.emit('7403')
    c.label('apply');corecall(c,p,'mode',('2f02',));events(c,p)
    load(c,PATTERN);c.emit('d080 d080 41ea'+f'{MODES:04x}'+' d1c0 2082')
    c.label('handled');c.emit('2f2f0028');c.imm('4eb9',0x4011AE46);c.emit('588f 7001 '+RESTORE+' 4e75')
    c.label('stock');c.emit(RESTORE+' 4fefffe0 48d73c3c');c.imm('4ef9',ENCODER+8);return finish_stock(c,a)


def draw_hook(a,p):
    c=Code();c.emit('4fefffc0 48d77fff 40c0 2f40003c 2642');ptr(c,p);c.branch(7,'restore')
    load(c,core.FIELDS['ui_active']);c.emit('4a80');c.branch(7,'restore')
    if p.get('diagnostics'):
        call(c,p,'diag_draw')
        c.branch(0,'restore')
    elif p.get('tempo_ui'):
        c.emit('2f0b');call(c,p,'rate_draw');c.emit('588f');c.branch(0,'restore')
    else:
        draw_fields(c,p)
    c.label('restore');c.emit('202f003c 44c0 4cd77fff 4fef0040 2ebc402a96a0');c.imm('4ef9',DRAW_RETURN+6);return c.finish(a)


def draw_fields(c,p):
    for off,y in ((0,27),(None,12),(16,2)):
        if off is None:
            load(c,0);c.emit('d080 d080');c.imm('41f9',p['strings']+32);c.emit('d1c0 2010 2f00')
        elif off==0:
            load(c,STATUS);c.emit('4a80');c.branch(10,'titleok');c.imm('4879',p['strings']+128);c.branch(0,'titlepushed');c.label('titleok');c.imm('4879',p['strings']);c.label('titlepushed')
        else:c.imm('4879',p['strings']+off)
        for v in (0x22,y,80,0x44D2E70C):c.imm('4879',v)
        c.emit('2f0b');c.imm('4eb9',0x40113AE8);c.emit('4fef0018')


def diagnostic_draw(a,p):
    # A2=state, A3=the original draw context. Only formatting/rendering here:
    # diagnostics never service the clock, mutate modes or generate notes.
    c=Code();c.emit(PRESAVE)
    for fmt,dest,fields in ((0,DIAG_TOP,(PLAY,core.FIELDS['held'])),
                            (16,DIAG_MIDDLE,(DIAG_NOTES,0)),
                            (32,DIAG_BOTTOM,(DIAG_CLOCK,KEYBOARD)),
                            (48,DIAG_ID,(DIAG_API,)),
                            (64,DIAG_CALLER_TEXT,(DIAG_CALLER,)),
                            (80,DIAG_CALLER_LOW_TEXT,(DIAG_CALLER,))):
        for off in fields:
            load(c,off)
            if dest==DIAG_MIDDLE and off==0:
                c.emit('d080 d080');c.imm('41f9',p['diag_formats']+96);c.emit('d1c0 2010')
            if off==DIAG_CALLER:
                if fmt==64:c.emit('7000 302a'+f'{DIAG_CALLER:04x}')
                else:c.imm('0280',65535)
            if off in (DIAG_NOTES,DIAG_API):c.imm('0280',255)
            c.emit('2f00')
        c.imm('4879',p['diag_formats']+fmt);c.emit(f'41ea{dest:04x} 2f08')
        c.imm('4eb9',0x40000E82);c.emit(f'4fef{4*(len(fields)+2):04x}')
    # Caller halves use the blank strip right of the stock keyboard drawing.
    # The stock draw continuation repaints its key graphic after this hook.
    for off,x,y in ((DIAG_TOP,80,27),(DIAG_MIDDLE,80,12),(DIAG_BOTTOM,80,2),(DIAG_ID,112,54),(DIAG_CALLER_TEXT,112,44),(DIAG_CALLER_LOW_TEXT,112,35)):
        c.emit(f'41ea{off:04x} 2f08')
        for v in (0x22,y,x,0x44D2E70C):c.imm('4879',v)
        c.emit('2f0b');c.imm('4eb9',0x40113AE8);c.emit('4fef0018')
    c.emit(RESTORE+' 4e75');return c.finish(a)


def finish_stock(c,a):
    # LINK and exact stock MOVEM prologues are validated against original bytes
    # by patch_cpu. Audit all newly emitted instructions and the displaced
    # LINK separately; LINK.W An,#d16 is a native CF ISA_A instruction.
    from lab import coldfire
    return c.finish(a)


def payload(p):
    out={}
    at=lambda n:p.get(n,0)
    for name,fn in (('init',core.initialize),('press',core.press),('release',core.release),('panic',core.panic),('mode',core.mode),('select',core.select)):
        out[name]=(fn(at(name)),'code')
    if p.get('tempo_ui'):
        from lab.arp_tempo import clock as tempo_clock,payload as tempo_payload
        out['clock']=(tempo_clock(at('clock'),p),'code');out.update(tempo_payload(p))
    else:
        clock=core.clock(at('clock'));old=b'\x4e\xb9'+((at('clock')+1024)&0xffffffff).to_bytes(4,'big');require(clock.count(old)==1,'Core clock select relocation changed');clock=clock.replace(old,b'\x4e\xb9'+at('select').to_bytes(4,'big'));out['clock']=(clock,'code')
    for name,fn in (('ensure',initialize),('events',output),('sync',synchronize),('heartbeat',heartbeat),('input',input_event),('encoder',encoder_hook),('draw',draw_hook)):
        out[name]=(fn(at(name),p),'code')
    for name,site,is_main in (('key',KEY,True),('menu_key',MENU_KEY,False)):
        out[name]=(key_hook(at(name),p,site,is_main),'code')
    out['on']=(note_hook(at('on'),p),'code');out['off']=(note_hook(at('off'),p,True),'code')
    data=bytearray(144);data[128:133]=b'ARP!\0';data[:4]=b'ARP\0';data[16:20]=b'(G)\0'
    for i,name in enumerate(('OFF','UP','ORD','RND')):
        struct.pack_into('>I',data,32+4*i,at('strings')+64+i*16);data[64+16*i:64+16*i+len(name)+1]=name.encode()+b'\0'
    out['strings']=(bytes(data),'data');out['pointer']=(bytes(4),'data')
    if p.get('diagnostics'):
        out['diag_draw']=(diagnostic_draw(at('diag_draw'),p),'code')
        formats=bytearray(128)
        for off,fmt in ((0,b'H%uP%u\0'),(16,b'%sN%02x\0'),(32,b'K%uC%u\0'),(48,b'D1A%02x\0'),(64,b'R%04x\0'),(80,b'%04x\0')):
            formats[off:off+len(fmt)]=fmt
        for i,name in enumerate((b'OF\0',b'UP\0',b'OR\0',b'RN\0')):
            struct.pack_into('>I',formats,96+4*i,at('diag_formats')+112+4*i)
            formats[112+4*i:112+4*i+len(name)]=name
        out['diag_formats']=(bytes(formats),'data')
    from lab.arp_firmware_storage import payload as storage_payload
    out.update(storage_payload(p))
    if p.get('shared_save'):
        from lab.project_save import SavePhases, arp_callbacks, dispatcher
        out.update({name:(code,'code') for name,code in arp_callbacks(
            {key:at(key) for key in ('arp_prepare','arp_commit','arp_cleanup')},p).items()})
        phases=SavePhases(at('save_trampoline') or 0x1000,
                          (at('arp_prepare') or 0x1002,), (at('arp_commit') or 0x1004,),
                          (at('arp_cleanup') or 0x1006,))
        out['save']=(dispatcher(at('save'),phases),'code')
    return out


def plan_cpu(image,*,diagnostics=False,tempo_ui=False,shared_save=False,allocator=None,bitmap_mask=False,stopped_playback=False,any_track=False):
    from lab.cpu_plan import NativePlan
    require(not (diagnostics and tempo_ui),'Choose normal tempo UI or D1 diagnostics')
    require(not any_track or tempo_ui,'Selected-track arp requires tempo UI')
    require(not stopped_playback or tempo_ui,'Stopped arp requires the native tempo/rates clock')
    require(hashlib.sha256(image).hexdigest()==STOCK_SHA,'Arp requires exact stock OS1.16 MAIN')
    # Reuse already reviewed deep-reference caves, without Plaits/Flex payloads.
    if allocator is None:
        allocator=PaddingAllocator(CANDIDATE_GAPS+OWNERSHIP_GAPS+((0x403117C4,0x40312000),))
    names=('binding','reader_trampoline','project_trampoline','equal','path','file_read','validate','inspect','encode','file_write','journal','project_hash','save_trampoline','load_trampoline','path_format','read_mode','write_mode')
    defaults={k:0 for k in names}
    defaults['diagnostics']=bool(diagnostics)
    defaults['tempo_ui']=bool(tempo_ui)
    defaults['shared_save']=bool(shared_save)
    defaults['bitmap_mask']=bool(bitmap_mask)
    defaults['stopped_playback']=bool(stopped_playback)
    defaults['any_track']=bool(any_track)
    defaults.update(arp_prepare=0,arp_commit=0,arp_cleanup=0)
    defaults.update(diag_draw=0,diag_formats=0)
    defaults.update(rate=0,rate_focus=0,rate_draw=0,rate_steps=0,rate_names=0,ui_labels=0,g_blank=0,g_pixels=0)
    defaults['decode_prefix']=image[0x400DF7F6-BASE:0x400DF7F6-BASE+8]
    defaults.update({k:0 for k in ('pointer','events','ensure','sync','input','strings','init','press','release','panic','mode','clock','select')})
    template=payload(defaults)
    p={'decode_prefix':defaults['decode_prefix'],'diagnostics':bool(diagnostics),'tempo_ui':bool(tempo_ui),'shared_save':bool(shared_save),'bitmap_mask':bool(bitmap_mask),'stopped_playback':bool(stopped_playback),'any_track':bool(any_track)}
    for name,(data,_) in sorted(template.items(),key=lambda x:(-len(x[1][0]),x[0])):
        p[name]=allocator.allocate(name,len(data))
    plan=NativePlan(image,allocator)
    put=plan.put
    for name,(code,kind) in payload(p).items():
        require(len(code)==len(template[name][0]),'Arp relocation changed size '+name);put(p[name],bytes(len(code)),code,name,kind,payload=True)
    for a,before,name in ((MAINLOOP,'487940966f3c','heartbeat'),(KEY,'4e56ffa448d73cfc','key'),(MENU_KEY,'4fefffe448d73c1c','menu_key'),(ON,'4e56ff88707f','on'),(OFF,'4e56ff84707f','off'),(ENCODER,'4fefffe048d73c3c','encoder'),(DRAW_RETURN,'2ebc402a96a0','draw'),(0x40043A30,'4fefffcc48d77c1c','save'),(0x400F5050,'4fefffe048d7040c','load'),(0x400DF7F6,defaults['decode_prefix'].hex(),'decoder'),(0x4012F1D8,'4e56ffcc48d704fc','reader'),(0x40043F74,'4e56ff9048d73cfc','project')):
        before=bytes.fromhex(before);after=b'\x4e\xf9'+p[name].to_bytes(4,'big')+b'\x4e\x71'*((len(before)-6)//2);put(a,before,after,name+' hook','code')
    if tempo_ui:put(0x40102582,bytes.fromhex('487944f34a78'),bytes.fromhex('4879')+p['g_blank'].to_bytes(4,'big'),'Blank G placeholder bitmap','code')
    plan.metadata=dict(firmware='Digitakt II OS1.16',stock_sha256=STOCK_SHA,locations={k:v for k,v in p.items() if k not in ('decode_prefix','diagnostics','tempo_ui','shared_save','bitmap_mask','stopped_playback','any_track')},diagnostics=bool(diagnostics),tempo_ui=bool(tempo_ui),state_bytes=SIZE,writes=plan.writes,hardware_ready=False,scope='Native stock-only arp, G control, clock and AR16 project companion journal; hardware unverified')
    if stopped_playback:plan.metadata['stopped_playback']=True
    if any_track:plan.metadata['any_track']=True
    return plan


def patch_cpu(image,*,diagnostics=False,tempo_ui=False,shared_save=False,stopped_playback=False,any_track=False):
    plan=plan_cpu(image,diagnostics=diagnostics,tempo_ui=tempo_ui,shared_save=shared_save,stopped_playback=stopped_playback,any_track=any_track)
    data=plan.apply()
    require(data[0x40312000-BASE:]==image[0x40312000-BASE:],"Reset-copy data changed")
    return data,dict(plan.metadata,sha256=hashlib.sha256(data).hexdigest())
