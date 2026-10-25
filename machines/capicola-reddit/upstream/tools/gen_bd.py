"""gen_bd.py -- render.asm's plan B read code, generated: cc_brun's loops and the
clean reads they use (the SIMD stereo read .bs and its inline copy in .bn_lp, the
SISD stereo read .bd for a right channel of the other word alignment).

  python3 tools/gen_bd.py capicola_c99/sharc/render.asm

Rewrites the text between the "gen_bd.py: begin/end" marker comments (the first
run, without markers, replaces the hand-written regions and adds them).

The reads compute .clean's Catmull-Rom with .clean's products and order of
evaluation, so every result is bit-identical to rec_clean_read (dt2gen.c's host
model). The SIMD read runs the unpack and the interpolation once for both
channels: the left in PEx (R registers), the right in PEy (S registers; scratch,
as the firmware's own SIMD code treats them), with no immediate loads inside the
SIMD section (every constant is set in both register files first), MODE1's PEYEN
set and cleared around it with a NOP after each change, as the firmware does."""
import sys

path = sys.argv[1]
a = open(path).read()


def unpack(s):
    """SISD: R2's parity flags set, R0 = 16, R3 = 0xFFFF0000, R1 = -31, I4 the
    words' address -> F4..F6, F2 = y0..y3 (as .clean: a high half as is, a low
    half shifted up, both FLOAT BY -31)."""
    return f'''      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_{s} (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_{s} (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_{s}:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_{s}:
'''


# .clean's Catmull-Rom with 0.5 (F12) the only constant: 1.5 d as d + 0.5 d, 2.5 y1
# as 2 y1 + 0.5 y1, 2 y2 as y2 + y2 -- each product exact (16-bit samples), the
# sums in .clean's order, so the same result; no product used by the very next
# instruction but in the Horner steps. F4..F6, F2 = y0..y3, F7 = f -> F0.
CR_H = '''      F1 = F2 - F4;                 // y3 - y0
      F3 = F5 - F6;                 // d = y1 - y2
      F2 = F12 * F2;                // 0.5 y3
      F0 = F12 * F3;                // 0.5 d
      F1 = F12 * F1;                // 0.5 (y3 - y0)
      F3 = F3 + F0;                 // 1.5 d
      F0 = F5 + F5;                 // 2 y1
      F3 = F1 + F3;                 // c3 = 0.5 (y3 - y0) + 1.5 (y1 - y2)
      F1 = F12 * F5;                // 0.5 y1
      F3 = F3 * F7;                 // c3 f
      F0 = F0 + F1;                 // 2.5 y1
      F1 = F4 - F0;                 // y0 - 2.5 y1
      F0 = F6 + F6;                 // 2 y2
      F6 = F6 - F4;                 // y2 - y0
      F1 = F1 + F0;
      F1 = F1 - F2;                 // c2 = y0 - 2.5 y1 + 2 y2 - 0.5 y3
      F2 = F12 * F6;                // c1 = 0.5 (y2 - y0)
      F0 = F3 + F1;                 // c3 f + c2
      F0 = F0 * F7;
      F0 = F0 + F2;                 // + c1
      F0 = F0 * F7;
      F0 = F0 + F5;                 // + y1
'''


def slow(s, ret):
    """.fcl_slow on each recorder (R6 the index; r back from DM(-25, I6))."""
    return f'''.rt_{s}:
      R12 = 0;
      {ret}
.sl_{s}:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_{s};
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      {ret}
'''


def head(s):
    """the index (F1) -> the slow path's R6, the bounds, k = floor, F7 = f,
    R12 = 2k, R2 = the left sample i - 1's byte address."""
    return f'''      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_{s};
      COMP(F1, F15);
      IF GE JUMP .sl_{s};
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
'''


def read_simd(s, ret, loop=None):
    """F1 = index -> F0 the left read, DM(-21, I6) the right (R11 its recorder;
    0: mono, the left alone). The right samples' offset R14 must keep a word's
    halves (cc_brun: R14 & 2 == 0, else .bd). The constants come from M0-M3
    (cc_brun sets them: 16, 0xFFFF0000, -31, 0.5): in SIMD a move from an
    uncomplementary register loads both PEs' registers (PRM p.28, "R5 = I8 loads
    R5 and S5"). With `loop` (.bn_lp's inline copy) a stereo read stores both
    samples and steps to the next itself."""
    simd_in = '''      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
'''
    if loop:
        tail = f'''      DM(0, I1) = R0;               // both samples out, and the next (.bn_got, .bn_nx)
      DM(0, I5) = R1;
      I1=MODIFY (I1,0x1)(NW);
      I5=MODIFY (I5,0x1)(NW);
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP {loop};
      JUMP .bu_end;
'''
    else:
        tail = f'''      DM(-21, I6) = R1;
      {ret}
'''
    return head(s) + f'''      R11 = PASS R11;
      IF EQ JUMP .mo_{s};
      R4 = R2 + R14;                // the right one's
      R3 = -4;
      R5 = R2 AND R3;
      I4 = R5;                      // the left words
      R5 = R4 AND R3;
      I3 = R5;                      // the right words
      S7 = R7;                      // f for PEy
      R5 = 2;
      R2 = R2 AND R5;               // 0: sample i - 1 in a word's low half, 2: its high half
      R4 = DM(0, I4);               // (loads leave the flags)
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      S4 = DM(0, I3);
      S5 = DM(1, I3);
      S6 = DM(2, I3);
      IF NE JUMP .so_{s};           // (decided in SISD: no MODE1 change in a delay slot)
''' + simd_in + f'''      R2 = R5 AND R3;               // y3
      F2 = FLOAT R2 BY R1;
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .sp_{s} (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.so_{s}:
''' + simd_in + f'''      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.sp_{s}:
''' + CR_H + f'''      BIT CLR MODE1 0x200000;       // SISD again
      NOP;
      R1 = S0;                      // the right read (PEy's F0)
      R12 = 0;                      // (memory three instructions after the change: MODE1's latency)
''' + tail + f'''.mo_{s}:                            // mono: the left channel alone, SISD
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
''' + unpack(s + 'm') + CR_H + f'''      R12 = 0;
      {ret}
''' + slow(s, ret)


def read_sisd(s, ret):
    """F1 = index -> F0 the left read, DM(-21, I6) the right, both SISD (any
    alignment of the right samples)."""
    return head(s) + f'''      R11 = PASS R11;
      IF EQ JUMP .mo_{s};
      R4 = R2 + R14;
      R3 = -4;
      R5 = R4 AND R3;
      DM(-26, I6) = R5;             // the right words
      DM(-27, I6) = R4;             // and byte address
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
''' + unpack(s + 'l') + CR_H + f'''      DM(-22, I6) = R0;             // the left read
      R4 = DM(-27, I6);
      R1 = 2;
      R2 = R4 AND R1;
      R3 = DM(-26, I6);
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R1 = -31;
''' + unpack(s + 'r') + CR_H + f'''      DM(-21, I6) = R0;             // the right read
      R0 = DM(-22, I6);
      R12 = 0;
      {ret}
.mo_{s}:
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
''' + unpack(s + 'm') + CR_H + f'''      R12 = 0;
      {ret}
''' + slow(s, ret)


def loop_plain(t, body, got):
    """not splicing: actual's read, each sample (`body`: the read, ending at `got`)."""
    return f'''.{t}n_lp:                            // not splicing: actual's read
      R1 = PASS R8;
''' + body + f'''{got}:
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .{t}n_nx;
      R0 = DM(-21, I6);
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.{t}n_nx:
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .{t}n_lp;
      JUMP .bu_end;
'''


def loop_splice(t, call, inline=False):
    """splicing: temp's and actual's reads (CALL `call`, or with `inline` two
    copies of the SIMD read), mixed by smooth_step."""
    if inline:
        r1 = read_simd(t + '1', f'JUMP .{t}s_g1;') + f'.{t}s_g1:\n'
        r2 = read_simd(t + '2', f'JUMP .{t}s_g2;') + f'.{t}s_g2:\n'
    else:
        r1 = f'      CALL {call};\n'
        r2 = f'      CALL {call};                  // F0 = o\n'
    return f'''.{t}s_set:
      R2 = DM(55, I2);              // adaptive_increment
      R3 = DM(49, I2);              // pitch
      F2 = F2 * F3;
      DM(-19, I6) = R2;
.{t}s_lp:                            // splicing: temp's and actual's reads, mixed
      R1 = DM(27, I2);              // temp.index
''' + r1 + f'''      DM(-16, I6) = R0;             // in
      R0 = DM(-21, I6);
      DM(-24, I6) = R0;             // the right channel's in
      R1 = PASS R8;
''' + r2 + f'''      R1 = DM(56, I2);              // w = smooth_step(splice_phase)
      F2 = F1 * F1;
      F3 = F1 + F1;
      R4 = 0x40400000;
      F3 = F4 - F3;
      F2 = F2 * F3;
      R4 = 0x3F800000;
      F4 = F4 - F2;                 // 1 - w
      DM(-17, I6) = R2;
      DM(-18, I6) = R4;
      R7 = DM(-16, I6);             // in
      F3 = F7 * F2;                 // in * w
      F4 = F0 * F4;                 // o * (1 - w)
      F0 = F3 + F4;
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .{t}s_nx;
      R7 = DM(-24, I6);             // the right channel's in
      R0 = DM(-21, I6);             // and o
      R2 = DM(-17, I6);
      R4 = DM(-18, I6);
      F3 = F7 * F2;
      F4 = F0 * F4;
      F0 = F3 + F4;
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.{t}s_nx:
      R1 = DM(27, I2);              // temp.index += actual.speed
      F1 = F1 + F9;
      DM(27, I2) = R1;
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = DM(56, I2);              // splice_phase += its step
      R2 = DM(-19, I6);
      F1 = F1 + F2;
      DM(56, I2) = R1;
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .{t}s_lp;
      DM(29, I2) = R9;              // temp.speed = actual.speed
      JUMP .bu_end;
'''


LOOPS = '''.bu_go:
      R8 = DM(17, I2);              // actual.index
      R9 = DM(19, I2);              // actual.speed
      R1 = 2;
      R1 = R14 AND R1;
      IF NE JUMP .bx_go;            // the right samples across a word's halves: SISD reads
      R0 = DM(57, I2);              // splicing
      R0 = PASS R0;
      IF NE JUMP .bss_set;
''' + loop_plain('b', read_simd('bn', 'JUMP .bn_got;', loop='.bn_lp'), '.bn_got') + loop_splice('bs', '.bs', inline=True) + '''.bx_go:
      R0 = DM(57, I2);
      R0 = PASS R0;
      IF NE JUMP .bxs_set;
''' + loop_plain('bx', '      CALL .bd;\n', '.bxn_got') + loop_splice('bx', '.bd')

READS = '''// .bs: index F1 -> F0 the left channel's clean read and, with a right recorder
// (R11), the right channel's to DM(-21, I6), the two in SIMD (gen_bd.py); .bd the
// same in SISD, for right samples across a word's halves. .fcl's fast path on both
// channels' samples (k and f found once), else .fcl_slow on each recorder.
// cc_brun's frame (-21..-27) and registers; clobber R0-R7, R12 (0 again for
// .fcl_slow), I3, I4, S0-S7, S12.
.bs:
''' + read_simd('bs', 'RTS;') + '''.bd:
''' + read_sisd('bd', 'RTS;')

MARK = "// ---- gen_bd.py: {} {} (generated: edit work/gen_bd.py)\n"


def replace(text, name, new, first_lo, first_hi):
    lo_m, hi_m = MARK.format("begin", name), MARK.format("end", name)
    if lo_m in text:
        i = text.index(lo_m) + len(lo_m)
        j = text.index(hi_m)
        return text[:i] + new + text[j:]
    i = text.index(first_lo)
    j = text.index(first_hi, i)
    return text[:i] + lo_m + new + hi_m + text[j:]


a = replace(a, "loops", LOOPS, ".bu_go:\n", ".bu_end:\n")
a = replace(a, "reads", READS, "// .bd (and .bn_lp's copy of it)", "#endif\n#endif\n#ifndef GEN_WSOLA   /* (dt2entry.asm calls these")
if "      I3 = R4;\n" in a:
    a = a.replace("      I3 = R4;\n", "      DM(-25, I6) = R4;             // r (the slow path's I0 back)\n", 1)
open(path, "w").write(a)
print("gen_bd: loops", LOOPS.count("\n"), "lines, reads", READS.count("\n"), "lines")
