"""Native AR16 journal using original OS1.16 SHA-256 and filesystem APIs."""
from lab.emit import Code
from lab.arp_firmware import (PRESAVE,RESTORE,ptr,load,store,setv,call,events,panic,corecall,MODES,SAVE_MODES,PLAY,BUSY,PATTERN,STATUS)
SLOT,DEST,BUFFER,LOADING=3244,3248,3252,3256
HASH,PATH,RECORD,B0,B1,HANDLE,FOUND,TEMP=3264,3300,3344,3560,3772,3984,4000,4288
RAW0,RAW1,VALID0,VALID1,WINNER,TARGET=4320,4324,4328,4332,4336,4340
PROJECT_LENGTH=0xDD9604

def addr(c,offset,reg=0):c.emit(f'{0x41ea|(reg<<9):04x}{offset:04x}')
def sha(c,p,source,length,dest):
    # SHA256(data,size,append,append_size), result pointer in A0 per native ABI.
    c.emit('7000 2f00 2f00');c.imm('4879',length);c.emit(source);addr(c,dest);c.imm('4eb9',0x4011CD30);c.emit('4fef0010')
def eqcall(c,p,x,y,n):
    c.imm('4879',n);c.emit(y+' 2f08 '+x+' 2f08');call(c,p,'equal');c.emit('4fef000c')

def equal(a,p):
    c=Code();c.emit('2f02 206f0008 226f000c 242f0010')
    c.label('loop');c.emit('7000 7200 1018 1219 b081');c.branch(6,'no');c.imm('0682',-1);c.branch(6,'loop');c.emit('7001');c.branch(0,'done')
    c.label('no');c.emit('7000');c.label('done');c.emit('241f 4e75');return c.finish(a)

def path(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.emit('2f2f0028');load(c,HASH+4);c.emit('2f00');load(c,HASH);c.emit('2f00');load(c,SLOT);c.emit('2f00');c.imm('4879',p['path_format']);addr(c,PATH);c.emit('2f08');c.imm('4eb9',0x40000E82);c.emit('4fef0018');addr(c,PATH+8,3);c.emit('7410')
    # The stock formatter uppercases %x. Match the existing AR16 codec
    # exactly, including its lowercase digest characters.
    c.label('hex');c.emit('7000 1013');c.imm('0c80',65);c.branch(5,'next');c.imm('0c80',70);c.branch(2,'next');c.imm('0680',32);c.emit('1680')
    c.label('next');c.emit('528b 5382');c.branch(6,'hex');addr(c,PATH);c.emit('2008 '+RESTORE+' 4e75');return c.finish(a)

def read(a,p):
    # read(record,bank) -> 0 absent, 1 exact-size file read, -1 unrecognized/error.
    c=Code();c.emit(PRESAVE);ptr(c,p);c.emit('266f0028 2f2f002c');call(c,p,'path');c.emit('588f 2040 5288');addr(c,FOUND,1);c.emit('2f09 2f08 48780002');c.imm('4eb9',0x401572E0);c.emit('4fef000c 4a80');c.branch(7,'done');c.imm('0c80',1);c.branch(6,'bad')
    load(c,FOUND);c.emit('2f00');c.imm('4eb9',0x4015BA22);c.emit('588f');c.imm('0c80',210);c.branch(6,'bad')
    addr(c,HANDLE);c.emit('2f08');c.imm('4879',p['read_mode']);addr(c,PATH);c.emit('2f08');c.imm('4eb9',0x40158626);c.emit('4fef000c 4a80');c.branch(6,'bad')
    addr(c,HANDLE);c.emit('2f08 487800d2 2f0b');c.imm('4eb9',0x4015832E);c.emit('4fef000c 2400');addr(c,HANDLE);c.emit('2f08');c.imm('4eb9',0x401585E4);c.emit('588f 4a80');c.branch(6,'bad');c.imm('0c82',210);c.branch(6,'bad');c.emit('7001');c.branch(0,'done')
    c.label('bad');c.emit('70ff');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)

def validate(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.emit('266f0028 2013');c.imm('0c80',0x41523136);c.branch(6,'bad')
    load(c,SLOT);c.imm('0080',0x01000000);c.emit('222b0004 b081')
    if p.get('tempo_ui'):
        c.branch(7,'version1');c.imm('0680',0x01000000);c.emit('b081');c.branch(6,'bad');c.emit('760f');c.branch(0,'version_ok')
        c.label('version1');c.emit('7603');c.label('version_ok')
    else:c.branch(6,'bad')
    c.emit('202b0008 222b000c');c.imm('0c80',0);c.branch(6,'seq');c.emit('4a81');c.branch(7,'bad')
    c.label('seq');c.emit('7000 302b0030');c.imm('0c80',128);c.branch(6,'bad')
    eqcall(c,p,'41eb0010','41ea'+f'{HASH:04x}',32);c.emit('4a80');c.branch(7,'bad')
    c.emit('41eb0032 747f')
    c.label('modes');c.emit('7000 1018')
    if p.get('tempo_ui'):c.emit('b083')
    else:c.imm('0c80',3)
    c.branch(2,'bad');c.emit('5382');c.branch(10,'modes')
    sha(c,p,'2f0b',178,TEMP)
    eqcall(c,p,'41eb00b2','41ea'+f'{TEMP:04x}',32);c.branch(0,'done')
    c.label('bad');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)

def inspect(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p)
    for bank,buf,raw,valid in ((65,B0,RAW0,VALID0),(66,B1,RAW1,VALID1)):
        setv(c,valid,0);c.imm('4879',bank);addr(c,buf);c.emit('2f08');call(c,p,'file_read');c.emit('508f');store(c,raw);c.imm('0c80',1);c.branch(6,f'next{bank}')
        addr(c,buf);c.emit('2f08');call(c,p,'validate');c.emit('588f');store(c,valid);c.label(f'next{bank}')
    load(c,VALID0);c.emit('4a80');c.branch(7,'onlyb');load(c,VALID1);c.emit('4a80');c.branch(7,'a')
    load(c,B0+8);load(c,B1+8,1);c.emit('b081');c.branch(2,'a');c.branch(5,'b')
    load(c,B0+12);load(c,B1+12,1);c.emit('b081');c.branch(2,'a');c.branch(5,'b')
    if p.get('tempo_ui'):
        # Equal sequences from different wire versions can contain identical
        # bytes with different rates (v1 mode1 vs v2 mode1/quarter).
        load(c,B0+4);load(c,B1+4,1);c.emit('b081');c.branch(6,'conflict')
    eqcall(c,p,'41ea'+f'{B0+50:04x}','41ea'+f'{B1+50:04x}',128);c.emit('4a80');c.branch(6,'a')
    c.label('conflict');c.emit('70fe');c.branch(0,'done')
    c.label('onlyb');load(c,VALID1);c.emit('4a80');c.branch(6,'b');c.emit('70ff');c.branch(0,'done')
    c.label('a');c.emit('7000');c.branch(0,'done');c.label('b');c.emit('7001');c.label('done');store(c,WINNER);c.emit(RESTORE+' 4e75');return c.finish(a)

def encode(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);addr(c,RECORD,3);c.imm('203c',0x41523136);c.emit('2680');load(c,SLOT);c.imm('0080',0x02000000 if p.get('tempo_ui') else 0x01000000);c.emit('27400004')
    c.emit('7400 7600');load(c,WINNER);c.emit('4a80');c.branch(11,'increment');addr(c,B0);c.emit('4a80');c.branch(7,'sequence');addr(c,B1)
    c.label('sequence');c.emit('24280008 2628000c')
    c.label('increment');c.emit('2003 5280 2600');c.branch(6,'sequence_ok');c.emit('2002 5280 2400');c.branch(7,'bad')
    c.label('sequence_ok');c.emit('27420008 2743000c');addr(c,HASH);c.emit('43eb0010 7408')
    c.label('hashcopy');c.emit('22d8 5382');c.branch(6,'hashcopy')
    c.emit('203c00800000 27400030');addr(c,SAVE_MODES);c.emit('43eb0032');c.imm('243c',128)
    c.label('modecopy');c.emit('2018 12c0 5382');c.branch(6,'modecopy')
    sha(c,p,'2f0b',178,TEMP);addr(c,TEMP);c.emit('43eb00b2 7408')
    c.label('checksum');c.emit('22d8 5382');c.branch(6,'checksum');c.emit('7001');c.branch(0,'done')
    c.label('bad');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)

def write(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);load(c,TARGET);c.imm('0680',65);c.emit('2f00');call(c,p,'path');c.emit('588f')
    addr(c,HANDLE);c.emit('2f08');c.imm('4879',p['write_mode']);addr(c,PATH);c.emit('2f08');c.imm('4eb9',0x40158626);c.emit('4fef000c 4a80');c.branch(6,'bad')
    c.emit('7400 487800d2 7000 2f00');addr(c,HANDLE);c.emit('2f08');c.imm('4eb9',0x40158534);c.emit('4fef000c 4a80');c.branch(6,'close')
    addr(c,HANDLE);c.emit('2f08 487800d2');addr(c,RECORD);c.emit('2f08');c.imm('4eb9',0x4015838E);c.emit('4fef000c');c.imm('0c80',210);c.branch(6,'close')
    addr(c,HANDLE);c.emit('2f08');c.imm('4eb9',0x4015B0CE);c.emit('588f 4a80');c.branch(6,'close');c.emit('7401')
    c.label('close');addr(c,HANDLE);c.emit('2f08');c.imm('4eb9',0x401585E4);c.emit('588f 4a80');c.branch(6,'bad');c.emit('4a82');c.branch(7,'bad')
    load(c,TARGET);c.imm('0680',65);c.emit('2f00');addr(c,B0);c.emit('2f08');call(c,p,'file_read');c.emit('508f');c.imm('0c80',1);c.branch(6,'bad')
    eqcall(c,p,'41ea'+f'{B0:04x}','41ea'+f'{RECORD:04x}',210);c.branch(0,'done')
    c.label('bad');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)

def journal(a,p):
    # journal(save): loaded records authenticate the same SLOT/HASH as caller.
    c=Code();c.emit(PRESAVE);ptr(c,p);c.emit('262f0028');call(c,p,'inspect');c.emit('2400 4a83');c.branch(6,'save')
    c.emit('4a82');c.branch(11,'bad');addr(c,B0+50);c.emit('4a82');c.branch(7,'copy');addr(c,B1+50)
    c.label('copy')
    if p.get('tempo_ui'):
        # A0 points to modes at record+50. Version is 46 bytes before it.
        c.emit('7600 7000 1028ffd2');c.imm('0c80',1);c.branch(6,'packed');c.emit('7608');c.label('packed')
    addr(c,MODES,1);c.imm('243c',128)
    c.label('copyloop');c.emit('7000 1018')
    if p.get('tempo_ui'):c.emit('2640 2003 d7c0 200b')
    c.emit('22c0 5382');c.branch(6,'copyloop');c.emit('7001');c.branch(0,'done')
    c.label('save');c.imm('0c82',-2);c.branch(6,'choose');setv(c,WINNER,0);c.emit('7400')
    c.label('choose');c.emit('4a82');c.branch(11,'empty');c.branch(7,'targetb')
    c.label('targeta');c.emit('7000');store(c,TARGET);load(c,RAW0);c.emit('4a80');c.branch(7,'commit');load(c,VALID0);c.emit('4a80');c.branch(6,'commit');c.branch(0,'bad')
    c.label('targetb');c.emit('7001');store(c,TARGET);load(c,RAW1);c.emit('4a80');c.branch(7,'commit');load(c,VALID1);c.emit('4a80');c.branch(6,'commit');c.branch(0,'bad')
    c.label('empty');load(c,RAW0);c.emit('4a80');c.branch(7,'targeta');load(c,RAW1);c.emit('4a80');c.branch(7,'targetb');c.branch(0,'bad')
    c.label('commit');call(c,p,'encode');c.emit('4a80');c.branch(7,'bad');call(c,p,'file_write');c.branch(0,'done')
    c.label('bad');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def project_hash(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);load(c,BUFFER);c.emit('2040 2010');c.imm('0c80',0xBEEFBACE);c.branch(6,'bad');c.emit('20280004');c.imm('0c80',5);c.branch(6,'bad')
    sha(c,p,'2f08',PROJECT_LENGTH,HASH);c.emit('7001');c.branch(0,'done');c.label('bad');c.emit('7000');c.label('done');c.emit(RESTORE+' 4e75');return c.finish(a)


def save_hook(a,p):
    c=Code();c.emit(PRESAVE);ptr(c,p);c.branch(7,'original')
    setv(c,PLAY,0);panic(c,p);setv(c,BUSY,1);c.emit('202f002c');store(c,SLOT);addr(c,MODES);addr(c,SAVE_MODES,1);c.imm('243c',128)
    c.label('snapshot');c.emit('22d8 5382');c.branch(6,'snapshot')
    c.label('original');c.emit('2f2f0030 2f2f0030 2f2f0030');call(c,p,'save_trampoline');c.emit('4fef000c 2800');ptr(c,p);c.branch(7,'done')
    c.emit('2004');c.imm('0280',255);c.imm('0c80',1);c.branch(6,'clear')
    load(c,SLOT);c.imm('0c80',128);c.branch(2,'failure');c.emit('2f00 7000 2f00');c.imm('4eb9',0x400F4A74);c.emit('508f 4a80');c.branch(7,'failure');c.emit('2040 2010');load(c,SLOT,1);c.emit('b081');c.branch(6,'failure')
    c.emit('2008');c.imm('0680',12);store(c,BUFFER);call(c,p,'project_hash');c.emit('4a80');c.branch(7,'failure');c.emit('7001 2f00');call(c,p,'journal');c.emit('588f 4a80');c.branch(7,'failure');setv(c,STATUS,1);c.branch(0,'clear')
    c.label('failure');setv(c,STATUS,-1)
    c.label('clear');setv(c,BUSY,0)
    c.label('done');c.emit('2004 '+RESTORE+' 4e75');return c.finish(a)


def load_hook(a,p,project=False):
    c=Code();c.emit(PRESAVE+' 7600');call(c,p,'ensure');ptr(c,p);c.branch(7,'original');load(c,BUSY);c.emit('4a80');c.branch(6,'original')
    if project:
        c.imm('2039',p['binding']);c.emit('222f002c b081');c.branch(6,'original')
        c.imm('2039',p['binding']+4);c.imm('0c80',128);c.branch(2,'original');store(c,SLOT)
        c.emit('202f002c');store(c,BUFFER);c.emit('7000');c.imm('23c0',p['binding'])
        c.imm('4eb9',0x401988A2);c.emit('222f0028 b081');c.branch(6,'original')
    else:
        c.emit('202f002c');c.imm('0c80',128);c.branch(2,'original')
        c.imm('4eb9',0x401988A2);c.emit('2040 2250 22690028 2f08 4e91 588f 222f0030 b081');c.branch(6,'original')
        store(c,DEST);c.emit('202f002c');store(c,SLOT);setv(c,BUFFER,0)
    c.emit('7601');setv(c,LOADING,1);setv(c,PLAY,0);panic(c,p);corecall(c,p,'mode',(0,));events(c,p);setv(c,BUSY,1);addr(c,MODES);c.emit('7208' if p.get('tempo_ui') else '7200');c.imm('243c',128)
    c.label('zero');c.emit('20c1 5382');c.branch(6,'zero')
    c.label('original')
    if project:c.emit('2f2f0030 2f2f0030 2f2f0030');call(c,p,'project_trampoline');c.emit('4fef000c 2800')
    else:c.emit('2f2f0034 2f2f0034 2f2f0034 2f2f0034');call(c,p,'load_trampoline');c.emit('4fef0010 2800')
    ptr(c,p);c.branch(7,'done');c.emit('4a83');c.branch(7,'done')
    setv(c,LOADING,0);c.emit('2004');c.imm('0280',255);c.imm('0c80',1);c.branch(6,'clear');load(c,BUFFER);c.emit('4a80');c.branch(7,'clear');call(c,p,'project_hash');c.emit('4a80');c.branch(7,'clear');c.emit('7000 2f00');call(c,p,'journal');c.emit('588f')
    c.label('clear');setv(c,PATTERN,-1);setv(c,BUSY,0)
    c.label('done');c.emit('2004 '+RESTORE+' 4e75');return c.finish(a)


def reader_hook(a,p):
    c=Code();c.emit(PRESAVE+' 7000');c.imm('23c0',p['binding'])
    c.emit('2f2f0030 2f2f0030 2f2f0030');call(c,p,'reader_trampoline');c.emit('4fef000c 2400 4a80');c.branch(6,'done')
    c.emit('202f0030');c.imm('0c80',128);c.branch(2,'done');c.imm('23c0',p['binding']+4);c.emit('202f002c');c.imm('23c0',p['binding'])
    c.label('done');c.emit('2002 '+RESTORE+' 4e75');return c.finish(a)


def decoder_hook(a,p):
    c=Code();c.emit('4fefffc0 48d77fff 40c0 2f40003c');ptr(c,p);c.branch(7,'done');load(c,LOADING);c.emit('4a80');c.branch(7,'done');load(c,DEST);c.emit('222f0044 b081');c.branch(6,'done')
    load(c,SLOT);c.emit('2f00 7000 2f00');c.imm('4eb9',0x400F4A74);c.emit('508f 4a80');c.branch(7,'done');c.emit('2040 2010');load(c,SLOT,1);c.emit('b081');c.branch(6,'done');c.emit('2008');c.imm('0680',12);c.emit('222f0048 b081');c.branch(6,'done');store(c,BUFFER)
    c.label('done');c.emit('202f003c 44c0 4cd77fff 4fef0040');c.emit(p['decode_prefix'].hex());c.imm('4ef9',0x400DF7F6+len(p['decode_prefix']));return c.finish(a)


def payload(p):
    at=lambda n:p.get(n,0)
    out={}
    for name,fn in (('equal',equal),('path',path),('file_read',read),('validate',validate),('inspect',inspect),('encode',encode),('file_write',write),('journal',journal),('project_hash',project_hash),('save',save_hook),('load',load_hook),('decoder',decoder_hook),('reader',reader_hook)):
        out[name]=(fn(at(name),p),'code')
    out['project']=(load_hook(at('project'),p,project=True),'code')
    out['binding']=(bytes(8),'data')
    out['path_format']=(b'/ARP%03u-%08x%08x%c\0','data');out['read_mode']=(b'r\0','data');out['write_mode']=(b'w\0','data')
    for name,site,prefix in (('save_trampoline',0x40043A30,bytes.fromhex('4fefffcc48d77c1c')),('load_trampoline',0x400F5050,bytes.fromhex('4fefffe048d7040c')),('reader_trampoline',0x4012F1D8,bytes.fromhex('4e56ffcc48d704fc')),('project_trampoline',0x40043F74,bytes.fromhex('4e56ff9048d73cfc'))):
        out[name]=(prefix+b'\x4e\xf9'+(site+len(prefix)).to_bytes(4,'big'),'code')
    return out
