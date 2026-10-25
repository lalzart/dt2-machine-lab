"""Native project/companion transactions on a GUI Machine's private card overlay."""
from contextlib import contextmanager

from unicorn import UC_HOOK_CODE, m68k_const as r

from lab.arp_persistence import ModeJournal, NativeFiles
from lab.project import require

SCRATCH = 0x62000000
SCRATCH_END = 0x63000000
STACK_TOP = 0x61FFFF00
# Exact OS1.16 TaskCreate at 0x40033266..0x40033280 declares this stack.
# QueueCreate at 0x4003324e uses its END as UI queue storage. Protecting
# that entire last page incorrectly rejects legitimate queued UI messages.
UI_STACK = (0x4096775C, 0x4098F75C)


def protected_stack_spans(sp):
    page=sp&~4095
    lo,hi=page,page+4096
    if UI_STACK[0]<=sp<UI_STACK[1]:
        lo=max(lo,UI_STACK[0]);hi=min(hi,UI_STACK[1])
    spans=[(lo,hi)]
    if page!=0x100FF000:spans.append((0x100FF000,0x10100000))
    return spans

class DirtyOverlay(dict):
    """Byte overlay with sector invalidation, including snapshot replacement."""
    def __init__(self, values=()):
        super().__init__(values)
        self.dirty = {offset // 512 for offset in self}

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.dirty.add(key // 512)

    def update(self, values=(), **kwargs):
        for key, value in dict(values, **kwargs).items():
            self[key] = value

    def __delitem__(self, key):
        super().__delitem__(key)
        self.dirty.add(key // 512)

    def pop(self, key, *default):
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default: return default[0]
        raise KeyError(key)

    def clear(self):
        self.dirty.update(offset // 512 for offset in self)
        super().clear()

    def setdefault(self, key, default=None):
        if key not in self: self[key] = default
        return self[key]

    def popitem(self):
        key, value = super().popitem()
        self.dirty.add(key // 512)
        return key, value

    def __ior__(self, values):
        self.update(values)
        return self


class OverlaySync:
    """Synchronize only dirty guest sectors and changed native sectors."""
    def __init__(self, model, card):
        self.model, self.card = model, card
        self.overlay = None
        self.imported = self.published = 0

    def before(self):
        if self.model.overlay is not self.overlay:
            # A restored snapshot replaces the entire overlay. Native-only
            # cached sectors must not survive that replacement.
            self.overlay = self.model.overlay = DirtyOverlay(self.model.overlay)
            self.card.overlay.clear()
        for sector in self.overlay.dirty:
            self.card.overlay.pop(sector, None)
            data = bytearray(self.card.read(sector, 512))
            present = False
            for i in range(512):
                value = self.overlay.get(sector * 512 + i)
                if value is not None:
                    data[i] = value
                    present = True
            if present: self.card.overlay[sector] = bytes(data)
            self.imported += 1
        self.overlay.dirty.clear()
        return dict(self.card.overlay)

    def after(self, previous, sectors=None):
        rows=self.card.overlay.items() if sectors is None else (
            (sector,self.card.overlay[sector]) for sector in sectors if sector in self.card.overlay)
        for sector, data in rows:
            if previous.get(sector) != data:
                # Bypass invalidation for bytes already synchronized.
                dict.update(self.overlay, ((sector * 512 + i, v) for i, v in enumerate(data)))
                self.published += 1
        for sector in previous.keys() - self.card.overlay.keys():
            for i in range(512): dict.pop(self.overlay, sector * 512 + i, None)
            self.published += 1


class AttachedCard:
    def __init__(self,machine,events,path,*,scratch_start=SCRATCH,scratch_end=SCRATCH_END,stack_top=STACK_TOP):
        import plusdrive_check as check
        from emu.harness import PAGE
        self.check=check;self.m=machine;self.uc=machine.uc
        self.model=events["esdhc"].card
        self.card=check.Card(path)
        self.sync=OverlaySync(self.model,self.card)
        require(stack_top<scratch_start<scratch_end and scratch_start%PAGE==scratch_end%PAGE==0
                and (stack_top&~(PAGE-1))+PAGE==scratch_start,'Invalid isolated diagnostic extent')
        self._scratch_start,self._scratch_end,self._stack_top=scratch_start,scratch_end,stack_top
        self._scratch=scratch_start
        self.traps=[];self.pages=[];self.events=[];self.direct=False;self.hooks=[]
        self.gui_io=False
        self.stack_checks=0
        require(not any(lo < scratch_end and hi >= (stack_top&~(PAGE-1)) for lo,hi,_ in self.uc.mem_regions()),
                'Arp storage diagnostic memory already mapped')
        machine.ensure(scratch_start);machine.ensure(stack_top)
        for at,fn in ((check.EMMC_READ,self.read_sectors),(check.EMMC_WRITE,self.write_sectors),
                      (check.MUTEX_LOCK,lambda a:1),(check.MUTEX_UNLOCK,lambda a:0),
                      (check.RMUTEX_LOCK,lambda a:1),(check.RMUTEX_UNLOCK,lambda a:0)):
            def hook(uc,pc,size,data,fn=fn,at=at):
                if not self.direct and not (self.gui_io and at in (check.EMMC_READ,check.EMMC_WRITE)):return
                sp=uc.reg_read(r.UC_M68K_REG_A7)
                result=fn(lambda i:self.u32(sp+4+i*4))
                uc.reg_write(r.UC_M68K_REG_D0,(result or 0)&0xffffffff)
                uc.reg_write(r.UC_M68K_REG_A7,sp+4)
                uc.reg_write(r.UC_M68K_REG_PC,self.u32(sp))
            self.hooks.append(self.uc.hook_add(UC_HOOK_CODE,hook,begin=at,end=at))

    def read(self,address,n):return bytes(self.uc.mem_read(address,n))
    def write(self,address,data):self.uc.mem_write(address,bytes(data))
    def u32(self,address):return int.from_bytes(self.read(address,4),"big")
    def alloc(self,data):
        data=bytes(data);at=self._scratch
        require(at+((len(data)+15)&~15) <= self._scratch_end,'Arp storage scratch capacity exceeded')
        for page in range(at&~4095,(at+len(data)+4095)&~4095,4096):self.m.ensure(page)
        self._scratch+=(len(data)+15)&~15;self.write(at,data);return at
    def call(self,address,args,limit=20_000_000):
        require(self.direct,"Use a bounded card transaction")
        from emu import harness
        result=harness.call(self.m,address,args,stack_top=self._stack_top,limit=limit)
        require(self.uc.reg_read(r.UC_M68K_REG_PC)==0xDEADBEE0,
                f'Native card call {address:#x} did not return within {limit} instructions')
        return result
    def read_sectors(self,arg):
        if not self.direct:self.sync_guest()
        self.write(arg(2),self.card.read(arg(0),arg(1)));return 0
    def write_sectors(self,arg):
        if not self.direct:self.sync_guest()
        sector,length=arg(0),arg(1)
        sectors=range(sector,sector+(length+511)//512)
        previous={s:self.card.overlay.get(s) for s in sectors} if not self.direct else None
        self.card.writes.append((sector,length))
        self.card.write(sector,self.read(arg(2),length))
        if previous is not None:self.sync.after(previous,sectors)
        return 0

    def sync_guest(self):
        if self.sync.overlay is not self.model.overlay or self.sync.overlay.dirty:
            self.sync.before()

    @contextmanager
    def transaction(self):
        require(not self.direct,"Nested card transaction")
        previous=self.sync.before()
        sp=self.uc.reg_read(r.UC_M68K_REG_A7)
        regions=list(self.uc.mem_regions())
        protected={(lo,hi):self.read(lo,hi-lo) for lo,hi in protected_stack_spans(sp)
                   if any(a<=lo and b>=hi-1 for a,b,_ in regions)}
        require(any(lo<=sp<hi for lo,hi in protected),
                'Current guest stack is not mapped')
        context=self.uc.context_save();self.direct=True;self._scratch=self._scratch_start
        self.uc.reg_write(r.UC_M68K_REG_SR,0x2700)
        try:yield self
        finally:
            try:self.sync.after(previous)
            finally:
                self.uc.context_restore(context);self.direct=False
            require(all(self.read(lo,hi-lo)==data for (lo,hi),data in protected.items()),
                    'Native card helper changed live guest stack bytes')
            self.stack_checks+=1

    def close(self):
        for hook in self.hooks:self.uc.hook_del(hook)
        self.hooks=[];self.card.close()


def serialized_project(firmware,slot):
    import tools.plusdrive as pd
    context=firmware.call(0x4019E41C,[])
    node=firmware.call(0x400F4A74,[context,slot])
    require(node != 0,"Native project buffer missing")
    buffer=node+12
    blob=firmware.read(buffer,pd.PROJECT_CONTAINER_SIZE)
    require(blob[:8]==bytes.fromhex("beefbace00000005"),"Unrecognised native saved project")
    return blob


def save_modes(firmware,slot,modes):
    return ModeJournal(NativeFiles(firmware)).save(slot,serialized_project(firmware,slot),modes)


def load_modes(firmware,slot):
    return ModeJournal(NativeFiles(firmware)).load(slot,serialized_project(firmware,slot))


def read_saved_project(firmware, slot):
    """Bypass stale boot/cache contents and read this native project slot afresh."""
    import tools.plusdrive as pd
    require(0 <= slot <= 128, 'Unknown native project slot')
    buffer = NativeFiles(firmware).alloc(bytes(pd.PROJECT_CONTAINER_SIZE))
    manager = firmware.call(0x4019D8FE, [])
    require(firmware.call(0x4012F1D8, [manager, buffer, slot], limit=300_000_000) == 0,
            'Native saved slot is missing, invalid or not current-format')
    blob = firmware.read(buffer, pd.PROJECT_CONTAINER_SIZE)
    require(blob[:8] == bytes.fromhex('beefbace00000005'), 'Unknown saved project format')
    return buffer, blob
