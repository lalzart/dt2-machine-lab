"""Four-mode G control on real OS1.16 UI; emulator-only placement and clock."""
from unicorn import UC_HOOK_CODE, m68k_const as r

from lab import arp_modes as native
from lab.arp_emulation import CODE, STATE
from lab.arp_ui import ArpUI, ON, OFF, KEY
from lab.emit import Code
from lab.project import require

ENCODER, DRAW_RETURN, MENU_KEY = 0x4010186C, 0x40102616, 0x4010206C
PROJECT_LOAD = 0x40043F74
PROJECT_LOAD_RETURN = 0x400442B2
PROJECT_CACHE, PROJECT_CACHE_RETURN = 0x400F4D50, 0x400F4E2A
PROJECT_READ, PROJECT_READ_RETURN = 0x4012F1D8, 0x4012F324
MENU_LOAD, MENU_LOAD_RETURN = 0x400F5050, 0x400F511A
MENU_DECODE = 0x400DF7F6
TEXT, SMALL_FONT = 0x40113AE8, 0x44D2E70C
STRINGS, DRAW = CODE + 0x3800, CODE + 0x3600
EDIT, REQUEST = CODE + 0x3A00, CODE + 0x3900
FRAME_PTR = 0x402B6058  # Resolved OS1.16 front-buffer pointer.
DISPLAY_NAMES = ("OFF","UP","ORD","RND")


def draw_tail(address):
    """Draw inside G with the stock text renderer, then resume stock drawing."""
    c = Code(); c.emit("4fefffc0 48d77fff 40c0 2f40003c 2642")
    c.imm("2039",STATE+native.FIELDS["ui_active"]);c.emit("4a80");c.branch(7,"restore")
    # Keep the existing cell border; compact values fit its interior.
    # Native raster Y increases upward.
    for text,y in ((STRINGS,27),(None,12),(STRINGS+16,2)):
        if text is None:
            c.imm("2039",STATE); c.emit("d080 d080")
            c.imm("41f9",STRINGS+32); c.emit("d1c0 2010 2f00")
        else:
            c.imm("4879",text)
        for value in (0x22,y,80,SMALL_FONT):
            c.imm("203c",value); c.emit("2f00")
        c.emit("2f0b"); c.imm("4eb9",TEXT); c.emit("4fef0018")
    c.label("restore");c.emit("202f003c 44c0 4cd77fff 4fef0040")
    c.emit("2ebc402a96a0")  # Exact displaced stock instruction.
    c.imm("4ef9",DRAW_RETURN+6)
    return c.finish(address)


def edit_mode(address,mode_function):
    """Mode change and refresh in the original encoder callback's UI context."""
    c=Code();c.emit("4fefffdc 48d71cfc 266f0028")
    c.imm("2039",REQUEST);c.emit("2f00");c.imm("4879",STATE)
    c.imm("4eb9",mode_function);c.emit("508f 4a80");c.branch(7,"refresh")
    c.emit("7000 2f00 48780040");c.imm("2039",STATE+native.FIELDS["off"])
    c.emit("2f00 7000 2f00");c.imm("4eb9",OFF);c.emit("4fef0010")
    c.label("refresh");c.emit("2f0b");c.imm("4eb9",0x4011AE46);c.emit("588f")
    c.emit("7001 4cd71cfc 4fef0024 4e75")
    return c.finish(address)


class ArpIntegration(ArpUI):
    def __init__(self, gui, clock_state, main, card_path=None):
        super().__init__(gui,clock_state,main,enabled=False)
        self.entries = native.build(CODE)
        self.press_entry,self.release_entry = CODE+0x3000,CODE+0x3400
        self.menu_events=[]; self.pending_mode=None
        self.pending_view=None
        self.menu_view=None
        self.pattern_modes=[0]*128
        self.pattern_id=None; self.selected_track=None
        self.keyboard_active=False
        self.func_down=False
        self.direct_keys={}
        self.last_key=None
        self.key_owners={}
        self.menu_releases=[]
        self.card_path=card_path;self.card_firmware=None
        self.storage_events=[];self.pending_storage=[];self.save_slot=None;self.save_modes_snapshot=None
        self.pending_unknown_load=False
        self.cache_request=None;self.load_binding=None;self.loading=None
        self.read_request=None
        self.project_data=None;self.menu_loading=None
        self.pending_recall=[]

    def raw(self):
        return bytes(self.uc.mem_read(STATE,native.SIZE))

    def field(self,name):
        return self.u32(STATE+native.FIELDS[name])

    def install(self,main):
        super().install(main)
        from emu import symbols
        require(symbols.resolve(main).fb_front==FRAME_PTR,"Arp panel layout changed")
        import struct
        data=bytearray(128)
        data[:4]=b"ARP\0"; data[16:20]=b"(G)\0"
        for i,name in enumerate(DISPLAY_NAMES):
            ptr=STRINGS+64+i*16
            struct.pack_into(">I",data,32+i*4,ptr)
            data[64+i*16:64+i*16+len(name)+1]=name.encode()+b"\0"
        self.uc.mem_write(STRINGS,bytes(data))
        self.uc.mem_write(DRAW,draw_tail(DRAW))
        self.uc.mem_write(EDIT,edit_mode(EDIT,self.entries["mode"][0]))
        expected=bytes.fromhex("2ebc402a96a0")
        require(bytes(self.uc.mem_read(DRAW_RETURN,6))==expected,"Arp draw patch drift")
        self.uc.mem_write(DRAW_RETURN,bytes.fromhex("4ef9")+DRAW.to_bytes(4,"big"))
        for address in (ENCODER,MENU_KEY):
            expected=main[address-0x40000400:address-0x40000400+2]
            require(bytes(self.uc.mem_read(address,2))==expected,"Arp menu hook drift")
            self.hooks.append(self.uc.hook_add(UC_HOOK_CODE,self.menu,
                                              begin=address,end=address))
        for address in (0x40043A30,0x40043B26,PROJECT_LOAD,PROJECT_LOAD_RETURN,
                        PROJECT_CACHE,PROJECT_CACHE_RETURN,PROJECT_READ,PROJECT_READ_RETURN,
                        MENU_LOAD,MENU_LOAD_RETURN,MENU_DECODE):
            expected=main[address-0x40000400:address-0x40000400+8]
            require(bytes(self.uc.mem_read(address,8))==expected,"Arp storage hook drift")
            self.hooks.append(self.uc.hook_add(UC_HOOK_CODE,self.storage_hook,
                                              begin=address,end=address))

    def destination(self):
        project=self.call(0x401988A2,[])
        settings=self.call(0x40041D18,[project])
        track=self.call(0x4004ABE8,[settings])
        manager=self.call(0x40199680,[])
        pattern=self.call(0x400F541C,[manager])
        require(0<=track<16 and 0<=pattern<128,"Unknown arp destination")
        return track,pattern

    def load_blob(self,buffer):
        import tools.plusdrive as pd
        return bytes(self.uc.mem_read(buffer,pd.PROJECT_CONTAINER_SIZE))

    def arm(self):
        super().arm()
        project=self.call(0x401988A2,[])
        self.project_data=self.call(self.u32(self.u32(project)+0x28),[project])
        self.selected_track,self.pattern_id=self.destination()
        self.uc.mem_write(STATE+native.FIELDS["ui_active"],int(self.selected_track==0).to_bytes(4,"big"))
        self.keyboard_active=True

    def menu(self,uc,pc,size,data):
        if self.direct or not self.collecting:
            return
        sp=uc.reg_read(r.UC_M68K_REG_A7)
        event=self.u32(sp+8)
        if pc==MENU_KEY:
            code,flags=self.u32(event+12),self.u32(event+16)
            if code==17:self.func_down=bool(flags&1)
            if not flags&1 and code in self.key_owners:
                self.menu_releases.append((code,self.key_owners[code]))
            return
        if self.selected_track != 0:return
        if self.u32(event+12)!=7:
            return
        delta=self.u32(event+16)
        delta=delta-(1<<32) if delta & (1<<31) else delta
        mode=self.pending_mode if self.pending_mode is not None else self.field("enabled")
        self.pending_mode=max(0,min(3,mode+delta))
        self.pending_view=self.u32(sp+4)
        self.menu_view=self.pending_view
        self.menu_events.append({"tick":self.tick(),"delta":delta,"requested":self.pending_mode})
        if self.direct_keys and self.pending_mode:
            self.menu_events[-1]["rejected"]="Release direct keys before enabling"
            self.pending_mode=None
            return
        self.uc.mem_write(REQUEST,self.pending_mode.to_bytes(4,"big"))
        uc.reg_write(r.UC_M68K_REG_PC,EDIT)

    def observe(self,uc,pc,size,data):
        if pc==KEY and not self.direct:
            sp=uc.reg_read(r.UC_M68K_REG_A7); event=self.u32(sp+8)
            code,flags=self.u32(event+12),self.u32(event+16)
            if 25<=code<=40:
                self.last_key=code
                if not flags&1 and code in self.key_owners:
                    self.menu_releases.append((code,self.key_owners[code]))
            if code==17:
                self.func_down=bool(flags&1)
            if self.collecting and code==18 and flags&1:
                if self.func_down:
                    self.pending_panic=True
                else:
                    self.keyboard_active=not self.keyboard_active
                    if not self.keyboard_active:self.pending_panic=True
        before=len(self.inputs)
        original=self.collecting
        if pc==ON and not self.keyboard_active:
            self.collecting=False
        try: super().observe(uc,pc,size,data)
        finally:self.collecting=original
        if len(self.inputs)>before:
            e=self.inputs[-1]
            if e["consumed"]:
                if e["kind"]=="on" and self.last_key is not None:
                    self.key_owners[self.last_key]=e["note"]
                elif e["kind"]=="off":
                    matches=[k for k,n in self.key_owners.items() if n==e["note"]]
                    if self.last_key in matches:self.key_owners.pop(self.last_key)
                    elif matches:self.key_owners.pop(matches[0])
            if e["track"]==0 and not e["consumed"]:
                n=e["note"]; count=self.direct_keys.get(n,0)+(1 if e["kind"]=="on" else -1)
                if count>0:self.direct_keys[n]=count
                else:self.direct_keys.pop(n,None)

    def service(self):
        if not self.collecting:return
        if self.pending_unknown_load:
            self.pending_unknown_load=False
            self.pending_mode=None
            self.playing=False
            for e in self.core_call("panic"):self.stock_event(e)
            self.pattern_modes=[0]*128
            for e in self.core_call("mode",0):self.stock_event(e)
            self.storage_events.append({"op":"load","status":"unbound-default-off",
                                       "boundary":"GUI project slot is not authenticated; retain release owners"})
        while self.menu_releases:
            key,note=self.menu_releases.pop(0)
            if key in self.key_owners:
                self.key_owners.pop(key)
                for e in self.core_call("release",note):self.stock_event(e)
                self.menu_events.append({"tick":self.tick(),"released_key":key,"note":note})
        track,pattern=self.destination()
        if (track,pattern)!=(self.selected_track,self.pattern_id):
            for e in self.core_call("panic"):self.stock_event(e)
            self.selected_track,self.pattern_id=track,pattern
            self.uc.mem_write(STATE+native.FIELDS["ui_active"],int(track==0).to_bytes(4,"big"))
            mode=self.pattern_modes[pattern] if track==0 else 0
            for e in self.core_call("mode",mode):self.stock_event(e)
        if self.pending_mode is not None:
            mode=self.pending_mode;self.pending_mode=None
            if self.direct_keys and mode:
                self.menu_events[-1]["rejected"]="Release direct keys before enabling"
            else:
                for e in self.core_call("mode",mode):self.stock_event(e)
                self.pattern_modes[pattern]=mode
                self.menu_events[-1]["applied"]=mode
            self.pending_view=None
        super().service()
        while self.pending_recall:
            slot,blob=self.pending_recall.pop(0)
            try:
                from lab.arp_persistence import ModeJournal,NativeFiles
                with self.storage().transaction() as fw:
                    modes=ModeJournal(NativeFiles(fw)).load(slot,blob)
                self.recall_modes(modes)
                import hashlib
                self.storage_events.append({"op":"load","slot":slot,"status":"passed",
                    "boundary":"native-project-menu","modes":modes,
                    "project_sha256":hashlib.sha256(blob).hexdigest()})
            except Exception as error:
                self.recall_modes([0]*128)
                self.storage_events.append({"op":"load","slot":slot,"status":"failed",
                    "boundary":"native-project-menu","error":str(error)})
        while self.pending_storage:
            slot,modes=self.pending_storage.pop(0)
            op="save"
            try:
                with self.storage().transaction() as fw:
                    from lab.arp_storage import save_modes
                    result=save_modes(fw,slot,modes)
                self.storage_events.append({"op":op,"slot":slot,"status":"passed",**result})
            except Exception as error:
                self.storage_events.append({"op":op,"slot":slot,"status":"failed","error":str(error),
                                            "native_project_succeeded":True})

    def storage_hook(self,uc,pc,size,data):
        if not self.collecting:return
        sp=uc.reg_read(r.UC_M68K_REG_A7)
        if pc in (PROJECT_CACHE,PROJECT_CACHE_RETURN,PROJECT_READ,PROJECT_READ_RETURN,
                  PROJECT_LOAD,PROJECT_LOAD_RETURN,MENU_LOAD,MENU_LOAD_RETURN,MENU_DECODE):
            if self.card_firmware is not None and self.card_firmware.direct:return
        if pc==MENU_LOAD:
            self.menu_loading=None;self.loading=None;self.load_binding=None
            slot,destination=self.u32(sp+8),self.u32(sp+12)
            if 0<=slot<=128 and destination==self.project_data:
                self.pending_unknown_load=True
                self.menu_loading=(slot,destination)
            return
        if pc==MENU_DECODE:
            if self.menu_loading and self.u32(sp+4)==self.menu_loading[1]:
                binding=self.load_binding;self.load_binding=None
                if binding and binding==(self.menu_loading[0],self.u32(sp+8)):
                    blob=self.load_blob(binding[1])
                    if blob[:8]==bytes.fromhex('beefbace00000005'):
                        self.loading=(binding[0],blob)
            return
        if pc==MENU_LOAD_RETURN:
            loading=self.loading if self.menu_loading else None
            self.menu_loading=None;self.loading=None;self.load_binding=None
            if loading and uc.reg_read(r.UC_M68K_REG_D0)&255==1:
                self.pending_recall.append(loading)
            return
        if pc==PROJECT_READ:
            self.load_binding=None
            self.read_request=(self.u32(sp+12),self.u32(sp+8))
            return
        if pc==PROJECT_READ_RETURN:
            request=self.read_request;self.read_request=None
            if request and 0<=request[0]<=128 and uc.reg_read(r.UC_M68K_REG_D0)==0:
                self.load_binding=request
            return
        if pc==PROJECT_CACHE:
            self.load_binding=None
            self.cache_request=(self.u32(sp+4),self.u32(sp+8))
            return
        if pc==PROJECT_CACHE_RETURN:
            request=self.cache_request;self.cache_request=None
            node=uc.reg_read(r.UC_M68K_REG_D0)
            # The cache getter compares node+0. node+8 is a read stamp that
            # can remain stale when the stock save builder reuses a node.
            if request and node and 0<=request[1]<=128 and self.u32(node)==request[1]:
                self.load_binding=(request[1],node+12)
            return
        if pc==PROJECT_LOAD:
            self.pending_unknown_load=True
            binding=self.load_binding;self.load_binding=None
            self.loading=None
            if binding and binding[1]==self.u32(sp+8):
                blob=self.load_blob(binding[1])
                if blob[:8]==bytes.fromhex("beefbace00000005"):
                    self.loading=(binding[0],blob)
            return
        if pc==PROJECT_LOAD_RETURN:
            loading=self.loading;self.loading=None
            if loading and uc.reg_read(r.UC_M68K_REG_D0)&255==1:
                self.pending_recall.append(loading)
            return
        if self.card_path is None:return
        if pc==0x40043A30:
            self.load_binding=None
            require(self.save_slot is None,"Nested native project save")
            self.save_slot=self.u32(sp+8)
            self.save_modes_snapshot=list(self.pattern_modes)
        else:
            slot,modes=self.save_slot,self.save_modes_snapshot
            self.save_slot=self.save_modes_snapshot=None
            if uc.reg_read(r.UC_M68K_REG_D0)&255==1:
                require(slot is not None and 0<=slot<=128,"Unknown native project slot")
                self.pending_storage.append((slot,modes))

    def storage(self):
        require(self.card_path is not None,"Arp card persistence was not enabled")
        if self.card_firmware is None:
            from lab.arp_storage import AttachedCard
            self.card_firmware=AttachedCard(self.machine,self.clock_state["events"],self.card_path)
            with self.card_firmware.transaction() as fw:
                import plusdrive_check as check
                fw.call(check.MOUNT,[0],limit=200_000_000)
        return self.card_firmware

    def save_project(self,slot=128):
        require(self.field("owned")==0 and not self.direct_keys,"Release keys before project save")
        require(0<=slot<=128,"Unknown native project slot")
        with self.storage().transaction() as fw:
            project=fw.call(0x401988A2,[]);progress=fw.alloc(bytes(32))
            result=fw.call(0x40043A30,[project,slot,progress],limit=800_000_000)
        require(result&255==1,"Native project save failed")
        self.service()
        require(self.storage_events and self.storage_events[-1]["status"]=="passed",
                "Native notes saved, but arp settings did not save")
        return self.storage_events[-1]

    def load_project(self,slot=128):
        """Diagnostic recall through the stock saved-slot reader and Project loader.

        Normal GUI recall uses a one-shot cache-slot/buffer binding and the
        exact serialized bytes supplied to the successful native loader.
        """
        require(self.field("owned")==0 and not self.direct_keys,"Release keys before project load")
        self.load_binding=self.cache_request=self.read_request=None
        for event in self.core_call("panic"):self.stock_event(event)
        self.playing=False
        try:
            with self.storage().transaction() as fw:
                from lab.arp_storage import read_saved_project
                from lab.arp_persistence import ModeJournal,NativeFiles
                buffer,blob=read_saved_project(fw,slot)
                modes=ModeJournal(NativeFiles(fw)).load(slot,blob)
                project=fw.call(0x401988A2,[])
                require(fw.call(0x40043F74,[project,buffer,0],limit=800_000_000)&255==1,
                        "Native project load failed")
            self.recall_modes(modes)
            self.storage_events.append({"op":"load","slot":slot,"status":"passed","modes":modes})
        except Exception as error:
            self.recall_modes([0]*128)
            self.storage_events.append({"op":"load","slot":slot,"status":"failed","error":str(error)})
            raise
        return self.storage_events[-1]

    def recall_modes(self,modes):
        require(len(modes)==128 and all(0<=m<=3 for m in modes),"Invalid arp recall")
        for e in self.core_call("panic"):self.stock_event(e)
        self.playing=False;self.pattern_modes=list(modes)
        track,pattern=self.destination()
        self.selected_track,self.pattern_id=track,pattern
        self.uc.mem_write(STATE+native.FIELDS["ui_active"],int(track==0).to_bytes(4,"big"))
        for e in self.core_call("mode",modes[pattern] if track==0 else 0):self.stock_event(e)
