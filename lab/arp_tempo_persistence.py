"""AR16 v2 mode/rate journal; authenticated v1 imports as sixteenths."""
import hashlib
from lab.project import require
from lab.arp_persistence import HEADER,COUNT,LENGTH,ModeJournal
DEFAULT=8


def encode(slot,sequence,project,modes):
    require(0<=slot<=128 and 0<sequence<1<<64,'Invalid arp journal identity')
    require(len(modes)==COUNT and all(type(x) is int and 0<=x<=15 for x in modes),'Invalid arp mode/rate')
    payload=HEADER.pack(b'AR16',2,0,slot,sequence,hashlib.sha256(project).digest(),COUNT)+bytes(modes)
    return payload+hashlib.sha256(payload).digest()


def decode(blob,slot,project):
    if blob is None or len(blob)!=LENGTH:return None
    payload,check=blob[:-32],blob[-32:]
    if hashlib.sha256(payload).digest()!=check:return None
    magic,version,reserved,saved_slot,sequence,digest,count=HEADER.unpack_from(payload)
    modes=list(payload[HEADER.size:])
    if (magic!=b'AR16' or version not in (1,2) or reserved or saved_slot!=slot or not sequence
            or digest!=hashlib.sha256(project).digest() or count!=COUNT
            or any(m>(3 if version==1 else 15) for m in modes)):return None
    return dict(sequence=sequence,modes=[m|8 for m in modes] if version==1 else modes,
                version=version,raw_modes=bytes(modes))


class RateJournal(ModeJournal):
    def inspect(self,slot,project):
        paths=self.paths(slot,project);raw=[self.files.read(p) for p in paths]
        return paths,raw,[decode(b,slot,project) for b in raw]

    def load(self,slot,project):
        _,_,valid=self.inspect(slot,project);records=[r for r in valid if r]
        if not records:return [DEFAULT]*COUNT
        highest=max(r['sequence'] for r in records);winners=[r for r in records if r['sequence']==highest]
        # Match the native conservative same-sequence conflict check.
        if any(r['version']!=winners[0]['version'] or r['raw_modes']!=winners[0]['raw_modes'] for r in winners):return [DEFAULT]*COUNT
        return winners[0]['modes']

    def save(self,slot,project,modes):
        paths,raw,valid=self.inspect(slot,project)
        choices=[i for i in range(2) if raw[i] is None or valid[i] is not None]
        require(choices,'No recognised arp journal bank available')
        current=max((r['sequence'] for r in valid if r),default=0)
        active=next((i for i,r in enumerate(valid) if r and r['sequence']==current),None)
        choices=[i for i in choices if i!=active]
        require(choices,'Inactive arp bank is unavailable; preserve active bank')
        i=min(choices,key=lambda n:valid[n]['sequence'] if valid[n] else 0)
        blob=encode(slot,current+1,project,modes);self.files.write(paths[i],blob)
        require(self.files.read(paths[i])==blob,'Arp mode/rate readback differed')
        require(self.load(slot,project)==list(modes),'Arp mode/rate journal did not commit')
        return dict(path=paths[i],sequence=current+1,sha256=hashlib.sha256(blob).hexdigest())
