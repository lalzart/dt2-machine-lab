"""List hardware DO loops in a linked .dxe (seldump disassembly) and any jump
inside a loop body whose target is outside it (an exit that leaves the loop
and PC stacks unpopped). Usage: python3 doscan.py FILE.dxe"""
import os, re, subprocess, sys
SELACHE = os.environ.get("SELACHE") or os.path.join(os.environ.get("DT2_WORKSPACE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."), "work", "selache")   # (as build_gen.sh)
txt = subprocess.run([os.path.join(SELACHE, "target/release/seldump"), "-ns", "*", sys.argv[1]], capture_output=True, text=True,
                     check=True).stdout
rows, fn = [], "?"
for line in txt.splitlines():
    m = re.match(r"^(\S+):\s*$", line)
    if m: fn = m.group(1); continue
    m = re.match(r"^\s+([0-9a-f]{8})\s+[0-9a-f]+\s+(.*)$", line)
    if m and int(m.group(1), 16) >= 0x10000:   # (below: data sections seldump also disassembles, from 0)
        rows.append((int(m.group(1), 16), m.group(2), fn))
bad = 0
for i, (a, t, fn) in enumerate(rows):
    m = re.search(r"do \(pc,(-?0x[0-9a-f]+|-?\d+)\)\s*until", t)
    if not m: continue
    end = a + int(m.group(1), 16)
    exits = []
    for b, u, _ in rows[i + 1:]:
        if b > end: break
        j = re.search(r"jump (0x[0-9a-f]+)", u)
        if j and not (a < int(j.group(1), 16) <= end + 1) and "(db)" not in u.split("jump")[0]:
            exits.append(f"{b:#x}: {u}")
        if re.search(r"\b(cjump|call)\b", u):
            exits.append(f"{b:#x}: {u}  (a call inside the loop)")
    print(f"{fn:28s} DO at {a:#x}..{end:#x}" + ("" if not exits else "  EXITS: " + "; ".join(exits)))
    bad += bool(exits)
print(f"{bad} loop(s) with an exit or call")
