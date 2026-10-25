"""Map addresses of one Digitakt II MAIN OS build to another (1.16 -> 1.17).

    uv run --python 3.12 --no-project python firmware/addrmap.py OLD.bin NEW.bin ADDR...

The two builds hold the same code; functions and data move as code before them
grows (1.17: 356 to 1344 bytes), and every absolute address inside them moves
with them. So an address is found by its surroundings, with the address-sized
words in them left out of the comparison:

  code and initialised data (in the image): the bytes around it, every 32-bit
    word that looks like an address (0x40000000-0x4fffffff) a wildcard, must
    match at exactly one place within MAX_SHIFT of where it was;
  RAM (BSS 0x42..., heap 0x44...: not in the image): the image's references to it
    (abs.l operands), each mapped as above, must all read the same new address.

A mapping that is not unique, or references that disagree, is an error: the
builder must never patch a guessed address.
"""

from __future__ import annotations

import struct
import sys

BASE = 0x40000400
MAX_SHIFT = 0x1000
WINDOW = 24            # bytes either side


def _is_addr(w):
    return 0x40000000 <= w < 0x50000000


class Mapper:
    def __init__(self, old: bytes, new: bytes):
        self.a, self.b = old, new
        self.end = BASE + len(old)
        self._refs = None

    def _pattern(self, off):
        """(bytes, mask) around off in the old image: address-like words masked out"""
        lo, hi = max(0, off - WINDOW), min(len(self.a), off + WINDOW)
        pat = self.a[lo:hi]
        keep = [True] * len(pat)
        for k in range(0, len(pat) - 3):
            if _is_addr(struct.unpack(">I", pat[k:k + 4])[0]):
                for j in range(k, k + 4):
                    keep[j] = False
        return lo, pat, keep

    def _match(self, off):
        lo, pat, keep = self._pattern(off)
        sig = [(j, pat[j]) for j in range(len(pat)) if keep[j]]
        if len(sig) < 12 or len({v for _, v in sig}) < 4:
            raise ValueError(f"{BASE + off:#x}: too little fixed content around it to place it")
        first_j, first_v = sig[0]
        hits = []
        start = max(0, lo - MAX_SHIFT)
        stop = min(len(self.b) - len(pat), lo + MAX_SHIFT)
        i = self.b.find(bytes([first_v]), start + first_j)
        while 0 <= i - first_j <= stop:
            cand = i - first_j
            if all(self.b[cand + j] == v for j, v in sig):
                hits.append(cand)
            i = self.b.find(bytes([first_v]), i + 1)
        if len(hits) != 1:
            raise ValueError(f"{BASE + off:#x}: {len(hits)} places match in the new image")
        return hits[0] - lo           # the shift

    def _verify(self, off, shift, window=64):
        """the old bytes around off equal the new ones at off + shift, address-like
        words aside, over +-window bytes (with at least 16 fixed bytes compared)"""
        lo, hi = max(0, off - window), min(len(self.a), off + window)
        if lo + shift < 0 or hi + shift > len(self.b):
            return False
        pat, got = self.a[lo:hi], self.b[lo + shift:hi + shift]
        keep = [True] * len(pat)
        for k in range(0, len(pat) - 3):
            if _is_addr(struct.unpack(">I", pat[k:k + 4])[0]):
                for j in range(k, k + 4):
                    keep[j] = False
        # (ColdFire opcodes 0x40xx-0x4fxx look like addresses too, so few bytes stay
        # fixed in a run of abs.l operands: also ask half the window to be identical)
        same = sum(1 for j in range(len(pat)) if pat[j] == got[j])
        return all(pat[j] == got[j] for j in range(len(pat)) if keep[j]) and same * 2 >= len(pat) >= 64

    def _near_shift(self, off):
        """the shift of the nearest uniquely placed neighbours (within 8 KB), if they agree"""
        shifts = set()
        for d in range(0x40, 0x2000, 0x40):
            for o in (off - d, off + d):
                if 0 <= o < len(self.a):
                    try:
                        shifts.add(self._match(o))
                    except ValueError:
                        pass
            if shifts:
                break
        return shifts

    def code(self, addr):
        """an address inside the image (code or initialised data): placed uniquely, or
        at its neighbours' shift if the bytes around it match there"""
        off = addr - BASE
        try:
            return addr + self._match(off)
        except ValueError:
            for sh in sorted(self._near_shift(off)):
                if self._verify(off, sh):
                    return addr + sh
            raise

    def refs(self, addr):
        """the old image's abs.l references to addr: their offsets"""
        pat = struct.pack(">I", addr)
        out, i = [], self.a.find(pat)
        while i >= 0:
            out.append(i)
            i = self.a.find(pat, i + 1)
        return out

    def ram(self, addr, need=1):
        """an address outside the image, through the image's references to it"""
        news = set()
        n = 0
        for off in self.refs(addr):
            try:
                shift = self.code(BASE + off) - (BASE + off)
            except ValueError:
                continue
            news.add(struct.unpack(">I", self.b[off + shift:off + shift + 4])[0])
            n += 1
        if n < need or len(news) != 1:
            raise ValueError(f"{addr:#x}: {n} placed references, new values {sorted(hex(x) for x in news)}")
        return news.pop()

    def map(self, addr):
        if BASE <= addr < self.end:
            try:
                return self.code(addr)
            except ValueError:
                return self.ram(addr)       # (a zero run: placed by what refers to it)
        return self.ram(addr)


def main(argv):
    old, new = (open(p, "rb").read() for p in argv[1:3])
    m = Mapper(old, new)
    for a in argv[3:]:
        a = int(a, 0)
        try:
            print(f"{a:#010x} -> {m.map(a):#010x}")
        except ValueError as e:
            print(f"{a:#010x}: {e}")


if __name__ == "__main__":
    main(sys.argv)
