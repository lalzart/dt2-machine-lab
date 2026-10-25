"""Versioned mode journal on the modeled native filesystem, bound to a project.

Stock project bytes remain unchanged. Two checked banks preserve the previous
configuration if an inactive-bank write fails. The caller owns the native
project save/load transaction and supplies its exact serialized bytes.
"""
import hashlib
import struct

from lab.project import require

HEADER = struct.Struct(">4sBBHQ32sH")
COUNT = 128
LENGTH = HEADER.size + COUNT + 32


def encode(slot, sequence, project, modes):
    require(0 <= slot <= 128 and 0 < sequence < 1 << 64, "Invalid arp journal identity")
    require(len(modes) == COUNT and all(type(x) is int and 0 <= x <= 3 for x in modes),
            "Invalid saved arp modes")
    payload = HEADER.pack(b"AR16",1,0,slot,sequence,hashlib.sha256(project).digest(),COUNT) + bytes(modes)
    return payload + hashlib.sha256(payload).digest()


def decode(blob, slot, project):
    if blob is None or len(blob) != LENGTH:
        return None
    payload,check = blob[:-32],blob[-32:]
    if hashlib.sha256(payload).digest() != check:
        return None
    magic,version,reserved,saved_slot,sequence,digest,count = HEADER.unpack_from(payload)
    modes = list(payload[HEADER.size:])
    if (magic != b"AR16" or version != 1 or reserved or saved_slot != slot or not sequence
            or digest != hashlib.sha256(project).digest() or count != COUNT
            or any(m > 3 for m in modes)):
        return None
    return {"sequence":sequence,"modes":modes}


class ModeJournal:
    def __init__(self, files):
        self.files = files

    def paths(self, slot, project):
        require(0 <= slot <= 128, "Unknown project slot")
        key = hashlib.sha256(project).hexdigest()[:16]
        return [f"/ARP{slot:03d}-{key}{bank}" for bank in "AB"]

    def inspect(self, slot, project):
        paths = self.paths(slot,project)
        raw = [self.files.read(p) for p in paths]
        valid = [decode(b,slot,project) for b in raw]
        return paths,raw,valid

    def load(self, slot, project):
        _,_,valid = self.inspect(slot,project)
        records = [r for r in valid if r is not None]
        if not records:
            return [0]*COUNT
        highest = max(r["sequence"] for r in records)
        winners = [r for r in records if r["sequence"] == highest]
        if any(r["modes"] != winners[0]["modes"] for r in winners):
            return [0]*COUNT
        return winners[0]["modes"]

    def save(self, slot, project, modes):
        paths,raw,valid = self.inspect(slot,project)
        # Never overwrite an unrecognised existing file, including a corrupt
        # journal bank. A known good bank remains available for recovery.
        choices = [i for i in range(2) if raw[i] is None or valid[i] is not None]
        require(choices, "No recognised arp journal bank available")
        current = max((r["sequence"] for r in valid if r),default=0)
        active = next((i for i,r in enumerate(valid) if r and r["sequence"]==current),None)
        choices = [i for i in choices if i != active]
        require(choices, "Inactive arp bank is unavailable; preserve active bank")
        i = min(choices,key=lambda n: valid[n]["sequence"] if valid[n] else 0)
        blob = encode(slot,current+1,project,modes)
        self.files.write(paths[i],blob)
        require(self.files.read(paths[i]) == blob,"Arp mode readback differed")
        require(self.load(slot,project) == list(modes),"Arp mode journal did not commit")
        return {"path":paths[i],"sequence":current+1,"sha256":hashlib.sha256(blob).hexdigest()}


class NativeFiles:
    """Bounded stock file calls on a Firmware whose card writes use an overlay."""
    def __init__(self, firmware):
        self.fw = firmware

    def alloc(self, data):
        data = bytes(data)
        start = self.fw._scratch
        for page in range(start & ~4095,(start+len(data)+4095)&~4095,4096):
            self.fw.m.ensure(page)
        return self.fw.alloc(data)

    def read(self, path):
        fw=self.fw
        found=self.alloc(bytes(0x120));name=self.alloc(path[1:].encode()+b"\0")
        status=fw.call(0x401572E0,[2,name,found])
        if status == 0:
            return None
        require(status == 1,"Native arp file lookup failed")
        identity=fw.u32(found)
        length=fw.call(0x4015BA22,[identity])
        require(0 <= length <= 4096,"Unrecognised oversized arp file; preserve it")
        handle=self.alloc(bytes(16));p=self.alloc(path.encode()+b"\0");mode=self.alloc(b"r\0")
        require(fw.call(0x40158626,[p,mode,handle]) == 0,"Native arp open-read failed")
        try:
            buf=self.alloc(bytes(length))
            require(fw.call(0x4015832E,[buf,length,handle]) == length,"Native arp read failed")
            return fw.read(buf,length)
        finally:
            require(fw.call(0x401585E4,[handle]) == 0,"Native arp close-read failed")

    def write(self,path,blob):
        fw=self.fw
        require(len(blob)==LENGTH,"Invalid arp record extent")
        handle=self.alloc(bytes(16));p=self.alloc(path.encode()+b"\0");mode=self.alloc(b"w\0")
        require(fw.call(0x40158626,[p,mode,handle]) == 0,"Native arp open-write failed")
        try:
            require(fw.call(0x40158534,[handle,0,len(blob)]) == 0,"Native arp resize failed")
            buf=self.alloc(blob)
            require(fw.call(0x4015838E,[buf,len(blob),handle]) == len(blob),"Native arp write failed")
            require(fw.call(0x4015B0CE,[handle]) == 0,"Native arp file hash failed")
        finally:
            require(fw.call(0x401585E4,[handle]) == 0,"Native arp close-write failed")
