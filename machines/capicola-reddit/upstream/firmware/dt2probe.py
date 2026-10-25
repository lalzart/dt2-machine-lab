"""Talk to the Digitakt II USB probe (firmware/probe.S) over USB MIDI, on macOS or Linux.

    uv run --python 3.12 --no-project --with python-rtmidi python firmware/dt2probe.py ports
    ... dt2probe.py hello
    ... dt2probe.py peek 0x8000488c 64
    ... dt2probe.py load [--n 200] [--interval 0.02]

The probe answers F0 00 20 3C 7D 00 <pack7 body> F7 on USB only, with two
read-only commands. `load` reads the SHARC's reply word 0 (its per-frame
handler's cycle count, at 0x8000488c) N times and reports it as a share of one
frame: 666,667 cycles at 1 GHz and 1,500 frames/s.

Close Elektron Transfer / Overbridge first if they hold the port.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
import time

HDR = bytes([0xF0, 0x00, 0x20, 0x3C, 0x7D, 0x00])
C_HELLO, C_PEEK = 1, 3
REPLY0 = 0x8000488C
FRAME_CYCLES = 1_000_000_000 / 1500
STATUS = {0: "ok", 1: "refused argument", 2: "unknown command"}


def pack7(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 7):
        group = data[i:i + 7]
        head = 0
        for k, b in enumerate(group):
            if b & 0x80:
                head |= 0x40 >> k
        out.append(head)
        out.extend(b & 0x7F for b in group)
    return bytes(out)


def unpack7(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        head = data[i]
        i += 1
        for k in range(7):
            if i >= len(data):
                break
            b = data[i]
            i += 1
            out.append(b | 0x80 if head & (0x40 >> k) else b)
    return bytes(out)


class Probe:
    def __init__(self, match: str):
        import rtmidi
        self.out, self.inp = rtmidi.MidiOut(), rtmidi.MidiIn()
        self.inp.ignore_types(sysex=False, timing=True, active_sense=True)
        oi = self._pick(self.out.get_ports(), match)
        ii = self._pick(self.inp.get_ports(), match)
        self.out.open_port(oi)
        self.inp.open_port(ii)
        self.seq = 0

    @staticmethod
    def _pick(ports, match):
        hits = [i for i, n in enumerate(ports) if match.lower() in n.lower()]
        if not hits:
            raise SystemExit(f"no MIDI port matching {match!r}: {ports}")
        return hits[0]

    def ask(self, cmd: int, args: bytes = b"", timeout: float = 1.0):
        self.seq = (self.seq + 1) & 0xFFFF
        body = struct.pack(">HB", self.seq, cmd) + args
        while self.inp.get_message():
            pass
        self.out.send_message(list(HDR + pack7(body) + b"\xF7"))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = self.inp.get_message()
            if not msg:
                time.sleep(0.001)
                continue
            raw = bytes(msg[0])
            if not raw.startswith(HDR) or raw[-1] != 0xF7:
                continue
            reply = unpack7(raw[len(HDR):-1])
            seq, rcmd, status = struct.unpack_from(">HBB", reply)
            if seq != self.seq or rcmd != (cmd | 0x80):
                continue
            return status, reply[4:]
        raise SystemExit("no reply: is the probe build installed, and the port free?")

    def peek(self, addr: int, n: int) -> bytes:
        status, payload = self.ask(C_PEEK, struct.pack(">IH", addr, n))
        if status:
            raise SystemExit(f"PEEK 0x{addr:08x}+{n}: {STATUS.get(status, status)}")
        return payload[4:]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", default="Digitakt II", help="substring of the MIDI port name")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    sub.add_parser("hello")
    pk = sub.add_parser("peek")
    pk.add_argument("addr", type=lambda s: int(s, 0))
    pk.add_argument("len", type=lambda s: int(s, 0))
    ld = sub.add_parser("load")
    ld.add_argument("--n", type=int, default=200)
    ld.add_argument("--interval", type=float, default=0.02)
    sub.add_parser("globals", help="the command frame's unmapped global words, and their sources")
    trk = sub.add_parser("track", help="one track's words in the command frame: type, pitch, parameter page")
    trk.add_argument("n", type=int, help="track, 1-16 as on the panel")
    cdg = sub.add_parser("capdiag", help="dt2capdiag only: track 1 left voice's generator calls and trigs per second")
    cdg.add_argument("--n", type=int, default=5)
    cld = sub.add_parser("capload", help="dt2capicola_load only: Capicola's DSP cycles per frame, frame period, guards")
    cld.add_argument("--seconds", type=float, default=20.0)
    cmm = sub.add_parser("capmem", help="dt2capicola_memtest only: is the L2 test region left alone, and does code run from L2")
    cmm.add_argument("--seconds", type=float, default=20.0)
    cbn = sub.add_parser("capbench", help="dt2capicola_ubench only: SHARC+ cycles per operation kind")
    cbn.add_argument("--seconds", type=float, default=15.0)
    args = p.parse_args()

    if args.cmd == "ports":
        import rtmidi
        print("out:", rtmidi.MidiOut().get_ports())
        print("in: ", rtmidi.MidiIn().get_ports())
        return 0
    probe = Probe(args.port)
    if args.cmd == "hello":
        status, payload = probe.ask(C_HELLO)
        proto, word0 = struct.unpack_from(">HI", payload)
        tag = payload[6:].split(b"\0")[0].decode("ascii", "replace")
        print(f"status {STATUS.get(status, status)}; protocol 0x{proto:04x}; tag {tag!r}; "
              f"DSP reply word 0 = {word0:,} cycles ({100 * word0 / FRAME_CYCLES:.1f}% of a frame)")
    elif args.cmd == "peek":
        data = probe.peek(args.addr, args.len)
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            print(f"{args.addr + i:08x}  {chunk.hex(' ')}")
    elif args.cmd == "load":
        vals = []
        for _ in range(args.n):
            vals.append(struct.unpack(">I", probe.peek(REPLY0, 4))[0])
            time.sleep(args.interval)
        q = statistics.quantiles(vals, n=20)
        pct = lambda v: 100 * v / FRAME_CYCLES  # noqa: E731
        print(f"{len(vals)} reads of reply word 0 (SHARC handler cycles per frame):")
        print(f"  median {statistics.median(vals):,.0f} ({pct(statistics.median(vals)):.1f}%)  "
              f"p5 {q[0]:,.0f} ({pct(q[0]):.1f}%)  p95 {q[-1]:,.0f} ({pct(q[-1]):.1f}%)  "
              f"min {min(vals):,}  max {max(vals):,}")
    elif args.cmd == "globals":
        # The SPI command frame the ColdFire sends the SHARC each frame is at
        # 0x80005348 (big-endian 16-bit words). TX+0x2c..0x32 and +0x7dc..0x800
        # are global fields not yet mapped; 0x800047b8/bc and 0x42936866 feed some.
        tx = 0x80005348
        head = probe.peek(tx + 0x2C, 8)
        tail = probe.peek(tx + 0x7DC, 0x26)
        print("TX+0x02c..0x032:", " ".join(f"{int.from_bytes(head[i:i+2], 'big'):04x}" for i in range(0, 8, 2)))
        print("TX+0x7dc..0x800:", " ".join(f"{int.from_bytes(tail[i:i+2], 'big'):04x}" for i in range(0, 0x26, 2)))
        for name, a in (("0x800047b8", 0x800047B8), ("0x800047bc", 0x800047BC), ("0x42936866", 0x42936866)):
            v = int.from_bytes(probe.peek(a, 4), "big")
            print(f"{name}: {v:#010x} ({v})")
        # Per-track words TX+0x77c/0x79c/0x7bc + 2t, from 0x47db41d0 + t*0x14.
        for base in (0x77C, 0x79C, 0x7BC):
            d = probe.peek(tx + base, 32)
            print(f"TX+{base:#05x}+2t:", " ".join(f"{int.from_bytes(d[i:i+2], 'big'):04x}" for i in range(0, 32, 2)))
        src = probe.peek(0x47DB41D0, 0x14 * 4)
        for t in range(4):
            row = src[t * 0x14:(t + 1) * 0x14]
            print(f"0x47db41d0 track {t}:", " ".join(row[i:i+4].hex() for i in range(0, 0x14, 4)))
    elif args.cmd == "track":
        # Command frame at 0x80005348, big-endian words. Per track t (0-based):
        # 0x02+2t pitch (note<<8), 0x94+2t machine type, 0x73c+2t flag,
        # 0xda+0x60t.. the 48-word parameter page (0xe0 = sample slot).
        tx, t = 0x80005348, args.n - 1
        w = lambda off: int.from_bytes(probe.peek(tx + off, 2), "big")  # noqa: E731
        print(f"track {args.n}: type {w(0x94 + 2 * t)}  pitch {w(0x02 + 2 * t):#06x}  flag {w(0x73C + 2 * t)}")
        page = probe.peek(tx + 0xDA + 0x60 * t, 0x60)
        for row in range(0, 0x60, 16):
            words_ = " ".join(f"{int.from_bytes(page[row + i:row + i + 2], 'big'):04x}" for i in range(0, 16, 2))
            print(f"  +{0xDA + row:#05x}  {words_}")
    elif args.cmd == "capdiag":
        # dt2capdiag: reply word 0 = (calls << 16) | trigs for voice 0, possibly with
        # its halves swapped in the copy; both halves are shown as rates.
        def sample():
            t0 = time.monotonic()
            v = struct.unpack(">I", probe.peek(REPLY0, 4))[0]
            return (t0 + time.monotonic()) / 2, v >> 16, v & 0xFFFF
        prev = sample()
        for _ in range(args.n):
            time.sleep(1.0)
            cur = sample()
            dt = cur[0] - prev[0]
            hi = ((cur[1] - prev[1]) & 0xFFFF) / dt
            lo = ((cur[2] - prev[2]) & 0xFFFF) / dt
            print(f"  {dt:.3f} s: high half {hi:7.1f}/s   low half {lo:7.1f}/s   (raw {cur[1]:04x} {cur[2]:04x})")
            prev = cur
    elif args.cmd == "capload":
        # dt2capicola_load and later: reply word 0 rotates through up to 15 figures (item in the top
        # 4 bits, value in the low 28), each over a window of 1024 frames (0.68 s).
        names = ["our cycles, worst frame", "our cycles, mean frame", "worst single call",
                 "frame period, longest", "late frames (period > 700k), total",
                 "late frames (period > 101.5%), total", "analysed samples",
                 "setup (C blocks)", "search: ref + coarse", "search: worst", "searches", "render loop", "after render", "search: refine + fine",
                 "playing calls (window)"]
        cyc = {0, 1, 2, 3}
        latest, t_end, report = {}, time.monotonic() + args.seconds, time.monotonic() + 3.0
        while time.monotonic() < t_end:
            v = struct.unpack(">I", probe.peek(REPLY0, 4))[0]
            if v >> 28 >= len(names):
                v = ((v << 16) | (v >> 16)) & 0xFFFFFFFF
            if v and v >> 28 < len(names):
                latest[v >> 28] = v & 0x0FFFFFFF
            if time.monotonic() >= report:
                report += 3.0
                print(f"-- {len(latest)}/{len(names)} figures so far")
                n_play = latest.get(14)
                for k in sorted(latest):
                    x = latest[k]
                    if not names[k]:
                        continue
                    if not n_play and k in (6, 7, 8):   # the default build: the stock generators' figures
                        label = {6: "stock STRETCH, mean per frame", 7: "stock shared gen. (REPITCH...), mean",
                                 8: "all generators, worst frame"}[k]
                        print(f"  {label:38s} {x:>10,}  ({100 * x / FRAME_CYCLES:5.1f}% of a frame)")
                        continue
                    if k == 6:   # samples analysed over the window
                        if n_play:
                            per = f", {latest[9] / x:5.1f} analysis cycles a sample" if 9 in latest and x else ""
                            print(f"  per playing call: {names[k]:21s} {x / n_play:10,.1f}{per}")
                        continue
                    if 7 <= k <= 13:   # section sums over the window: per playing call (C-path calls:
                        if n_play:     # cc_bfast's are not timed); the search's per search, its worst and count raw
                            if k in (9, 10):
                                print(f"  in the window:    {names[k]:21s} {x:10,}")
                            elif k in (8, 13):
                                cnt = latest.get(10) or 0
                                if cnt:
                                    print(f"  per search:       {names[k]:21s} {x / cnt:10,.0f}")
                            else:
                                print(f"  per playing call: {names[k]:21s} {x / n_play:10,.0f}")
                        continue
                    extra = f"  ({100 * x / FRAME_CYCLES:5.1f}% of a frame)" if k in cyc else ""
                    print(f"  {names[k]:38s} {x:>10,}{extra}")
            time.sleep(0.05)
    elif args.cmd == "capmem":
        # dt2capicola_memtest: reply word 0 rotates through 10 items (memtest.c).
        names = ["pattern words checked (x1024)", "pattern words changed", "first changed word (index)",
                 "L2 function: right sums", "L2 function: wrong sums", "L2 function: cycles (fastest)",
                 "L1 copy: cycles (fastest)", "L1 copy: wrong sums", "generator calls (x1024)", "decoder check (0xabcdef)"]
        latest, t_end, report = {}, time.monotonic() + args.seconds, time.monotonic() + 4.0
        while time.monotonic() < t_end:
            v = struct.unpack(">I", probe.peek(REPLY0, 4))[0]
            if v >> 28 >= len(names):
                v = ((v << 16) | (v >> 16)) & 0xFFFFFFFF
            if v >> 28 < len(names):
                latest[v >> 28] = v & 0x0FFFFFFF
            if time.monotonic() >= report:
                report += 4.0
                print(f"-- {len(latest)}/{len(names)} items")
                for k in sorted(latest):
                    x = latest[k]
                    shown = f"{x:#x}" if k == 9 else ("none" if k == 2 and x == 0x0FFFFFFF else f"{x:,}")
                    print(f"  {names[k]:34s} {shown}")
            time.sleep(0.05)
    elif args.cmd == "capbench":
        # dt2capicola_ubench: reply word 0 rotates through 13 kernels' smallest
        # EMUCLK time for 64 iterations (item = kernel) and item 13 = runs.
        kinds = ["empty loop (per iteration)", "ALU add", "L1 load, block 1", "L1 load then use (pair)",
                 "I4 = R, then load via I4 (pair)", "DDR load, same line", "DDR load, new lines",
                 "L1 load, block 0", "compare + untaken jump (pair)", "compare + taken jump (pair)",
                 "CALL + RTS", "empty loop, delayed jump (per iteration)", "float multiply, add (pair)"]
        latest, t_end = {}, time.monotonic() + args.seconds
        while time.monotonic() < t_end:
            v = struct.unpack(">I", probe.peek(REPLY0, 4))[0]
            if v >> 28 > 13:
                v = ((v << 16) | (v >> 16)) & 0xFFFFFFFF
            if v >> 28 <= 13:
                latest[v >> 28] = v & 0x0FFFFFFF
            time.sleep(0.05)
        print(f"kernel runs: {latest.get(13, '?')}")
        base = latest.get(0)
        for k, name in enumerate(kinds):
            if k not in latest:
                print(f"  {k:2d} {name:40s} (not seen)")
                continue
            c = latest[k]
            if k in (0, 11):
                print(f"  {k:2d} {name:40s} {c:7,} cycles / 64 = {c / 64:5.2f} a loop pass")
            else:
                op = (c - base) / (64 * 8) if base is not None else float("nan")
                print(f"  {k:2d} {name:40s} {c:7,} cycles -> {op:5.2f} cycles each (loop overhead taken off)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
