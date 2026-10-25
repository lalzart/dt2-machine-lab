"""labelcheck.py FILE.asm...: fail on a label defined twice in one file (selas
accepts it silently and resolves jumps to either; render.asm hit it 2026-10-09).
#if/#else halves may define the same label: those are allowed."""
import re, sys
bad = 0
for path in sys.argv[1:]:
    seen, stack = {}, []
    for n, line in enumerate(open(path), 1):
        s = line.strip()
        if s.startswith('#if'):
            stack.append(0)
        elif s.startswith('#else') and stack:
            stack[-1] += 1
        elif s.startswith('#endif') and stack:
            stack.pop()
        m = re.match(r'^([.A-Za-z_][A-Za-z0-9_.]*):', line)
        if m:
            key = (m.group(1), tuple(stack))
            if key in seen:
                print(f"{path}:{n}: label {m.group(1)} also at line {seen[key]}")
                bad = 1
            seen[key] = n
sys.exit(bad)
