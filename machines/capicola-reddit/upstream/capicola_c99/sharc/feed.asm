// feed.asm -- CC_SOURCE analysis for the C99 Capicola core (-DCC_F32 -DCC_ASM):
// src_feed's loop with cc_analyzer_analyze and cc_analyzer_guard_keyframe inline,
// operation for operation as capicola.c. GNU AGPL-3.0, as Capicola.
//
//   void cc_feed(cc_recorder *r);     R4; r->feed_target, feed_gap, feed_cap set
//
// Per sample, up to feed_cap: stop once the newest keyframe's time reaches
// feed_target; read the next 16-bit source sample (or silence past the end,
// looping if asked); analyse it (8-sample ring, B-spline value and slope, a
// keyframe at a slope sign change with enough value change, timed by linear
// interpolation and valued by the 4-tap B-spline); then the guard keyframe.
//
// cc_recorder words (-DCC_F32 -char-size-8): sparse.buf 0, .write_pos 1, .size 2,
// .origin 3; analyzer: raw.buf 5..12, raw.wp 13, most_recent value 14, d1 15,
// d2 16, tkeo 17, raw_count 18, sparse_count 19, threshold 20, first_analysis 22,
// arm_final 23; src 205, src_pos 206, src_end 207, src_loop 208, src_state 209,
// src_t_end 211, feed_target 214, feed_gap 215, feed_cap 216. cc_keyframe: value,
// time (8 bytes).
//
// Registers for the call: I0 = r, I1 = the newest keyframe, R8 = target,
// R9 = samples left, R10 = raw.wp, R11 = raw_count, R12 = write_pos,
// R13 = raw.buf[wp - 1] and R15 = raw.buf[wp - 2] (the two samples before the
// next, so the B-spline taps need no ring loads), R14 = the address of raw.buf,
// I5 = this sample's ring slot. No calls out, so R0-R7 and I2-I4 are free in
// between; R8-R15, I0-I3, I5 are restored. The same instruction forms as
// render.asm. The SHARC+ stalls 4 cycles when an I register written by the
// previous instruction addresses memory (ubench kernel 4): I4 and I5 are set
// several instructions before their loads and stores.

#ifdef GEN_WSOLA   /* plan B never runs Capicola's analysis: L2 (l1l2.ldf) */
.SECTION/PM seg_cold_pm;
#else
.SECTION/PM seg_pmco;
#endif

.GLOBAL cc_feed.;
cc_feed.:
      I7=MODIFY (I7,-0x12)(NW);
      DM(-3, I6) = R8;
      DM(-4, I6) = R9;
      DM(-5, I6) = R10;
      DM(-6, I6) = R11;
      DM(-7, I6) = R12;
      DM(-8, I6) = R13;
      DM(-9, I6) = R14;
      DM(-10, I6) = R15;
      R0 = I0;
      DM(-11, I6) = R0;
      R0 = I1;
      DM(-12, I6) = R0;
      R0 = I2;
      DM(-13, I6) = R0;
      R0 = I3;
      DM(-14, I6) = R0;
      R0 = I5;
      DM(-15, I6) = R0;             // -16: a keyframe time in hand

      I0 = R4;
      R15 = DM(0, I0);
      R1 = 1;
      R0 = DM(2, I0);
      R13 = R0 - R1;                // mask
      R12 = DM(1, I0);              // write_pos
      R11 = DM(18, I0);             // raw_count
      R10 = DM(13, I0);             // raw.wp
      R0 = 20;
      R14 = R4 + R0;                // &raw.buf[0]
      R9 = DM(216, I0);             // feed_cap
      R8 = DM(214, I0);             // feed_target
      R0 = 0;
      R12 = PASS R12;
      IF LE JUMP .latest0;
      R1 = 1;
      R0 = R12 - R1;
      R0 = R0 AND R13;
.latest0:
      R1 = 3;
      R0 = LSHIFT R0 BY R1;
      R0 = R0 + R15;
      I1 = R0;                      // the newest keyframe (slot 0 when empty)
      R1 = 7;                       // the two samples before raw.buf[wp]
      R0 = 1;
      R0 = R10 - R0;                // wp - 1
      R0 = R0 AND R1;
      R2 = 2;
      R0 = LSHIFT R0 BY R2;
      R0 = R0 + R14;
      I4 = R0;
      R0 = 2;
      R0 = R10 - R0;
      R0 = R0 AND R1;
      R0 = LSHIFT R0 BY R2;
      R0 = R0 + R14;
      R13 = DM(0, I4);              // raw.buf[wp - 1]
      I4 = R0;
      R15 = DM(0, I4);              // raw.buf[wp - 2] (once a call: the stall does not matter)

.loop:
      R9 = PASS R9;
      IF LE JUMP .done;
      R0 = DM(19, I0);              // sparse_count
      R0 = PASS R0;
      IF LE JUMP .read;
      R1 = DM(1, I1);
      COMP(F1, F8);
      IF GE JUMP .done;             // far enough ahead

.read:                              // F2 = the next input
      R0 = 2;                       // I5 = &raw.buf[wp], stored to in .analyse
      R0 = LSHIFT R10 BY R0;
      R0 = R0 + R14;
      I5 = R0;
      R2 = 0;
      R0 = DM(209, I0);             // src_state
      R0 = PASS R0;
      IF NE JUMP .analyse;
      R0 = DM(206, I0);             // src_pos
      R1 = DM(205, I0);             // src
      R3 = R0 + R0;
      R3 = R1 + R3;                 // the sample's byte address (not R3 + R1: digikit's width heuristic)
      R4 = -4;
      R4 = R3 AND R4;
      I4 = R4;
      R1 = 1;
      R0 = R0 + R1;                 // ++src_pos
      R1 = DM(207, I0);             // src_end
      R4 = 2;
      R6 = 16;
      R7 = 0;
      R5 = DM(0, I4);               // its aligned word
      R4 = R3 AND R4;
      IF NE R6 = PASS R7;           // the low half to the top (shift 16), the high half stays
      R5 = LSHIFT R5 BY R6;
      R6 = -16;
      R5 = ASHIFT R5 BY R6;         // sign-extended
      R6 = -15;
      F2 = FLOAT R5 BY R6;          // / 32768
      COMP(R0, R1);
      IF GE JUMP .pos_end;          // (out of line: the common case falls through)
.pos_ok:
      DM(206, I0) = R0;

.analyse:                           // cc_analyzer_analyze(a, F2)
      DM(0, I5) = R2;               // raw.buf[wp] = x
      R0 = 1;
      R10 = R10 + R0;
      R0 = 7;
      R10 = R10 AND R0;             // wp = (wp + 1) & 7
      R3 = PASS R2;                 // the three newest: x0 = x,
      R4 = PASS R13;                // x1 = the one before,
      R5 = PASS R15;                // x2 = the one before that
      R15 = PASS R13;
      R13 = PASS R2;
      R6 = 0x40800000;              // value = (x0 + 4 x1 + x2) / 6
      F6 = F4 * F6;
      F6 = F3 + F6;
      F6 = F6 + F5;
      R7 = 0x3E2AAAAB;
      F6 = F6 * F7;
      F7 = F5 - F3;                 // d1 = (x2 - x0) / 2
      R0 = 0x3F000000;
      F7 = F7 * F0;
      R1 = DM(15, I0);              // older d1
      DM(14, I0) = R6;
      DM(15, I0) = R7;              // (d2 and tkeo: 0, stored once at .done)
      R0 = 0;                       // F0 = 0 for the sign tests below

      R5 = 0;                       // crossed
      R4 = 1;
      COMP(F1, F0);
      IF LE JUMP .neg;
      COMP(F7, F0);
      IF LE R5 = PASS R4;
      JUMP .crossed;
.neg:
      COMP(F1, F0);
      IF GE JUMP .crossed;
      COMP(F7, F0);
      IF GE R5 = PASS R4;
.crossed:                           // the common case falls through to .guard and .next
      R0 = DM(22, I0);              // first_analysis
      R0 = PASS R0;
      IF NE JUMP .first;
      R0 = DM(23, I0);              // arm_final
      R0 = PASS R0;
      IF NE JUMP .final;
      R5 = PASS R5;
      IF NE JUMP .xing;
.no_push:
      R0 = 1;
      R11 = R11 + R0;

.guard:                             // cc_analyzer_guard_keyframe(a, feed_gap)
      R1 = DM(3, I0);
      R0 = R11 - R1;
      F0 = FLOAT R0;
      R1 = DM(1, I1);
      F0 = F0 - F1;
      R1 = DM(215, I0);
      COMP(F0, F1);
      IF GT JUMP .guard_push;
.next:
      R0 = 1;
      R9 = R9 - R0;
      JUMP .loop;

.first:
      R0 = 0;
      DM(22, I0) = R0;
      JUMP .push_now;
.final:
      R0 = 0;
      DM(23, I0) = R0;
      JUMP .push_now;
.guard_push:
      R4 = DM(14, I0);              // most_recent.value
      CALL .now;
      CALL .push;                   // (no raw_count++ for a guard keyframe)
      JUMP .next;
.pos_end:                           // past the sample's end: loop back, or silence
      R3 = DM(208, I0);             // src_loop
      R3 = PASS R3;
      IF LT JUMP .ended;
      COMP(R3, R1);
      IF GE JUMP .ended;
      R0 = PASS R3;                 // loop back
      JUMP .pos_ok;
.ended:
      R3 = 1;
      DM(209, I0) = R3;             // src_state = 1
      R3 = R11 + R3;
      DM(211, I0) = R3;             // src_t_end = raw_count + 1
      JUMP .pos_ok;

.xing:                              // a slope sign change: a keyframe if it moved enough
      R0 = DM(0, I1);               // |value - last.value| > threshold
      F0 = F6 - F0;
      F0 = ABS F0;
      R3 = DM(20, I0);
      COMP(F0, F3);
      IF LE JUMP .no_push;
      F2 = ABS F1;                  // alpha = |od1| / (|od1| + |d1|), as selcc divides
      F3 = ABS F7;
      F3 = F2 + F3;
      R4 = 0x40000000;
      F5 = RECIPS F3;
      F0 = F3 * F5;
      F0 = F4 - F0;
      F5 = F5 * F0;
      F0 = F3 * F5;
      F0 = F4 - F0;
      F5 = F5 * F0;
      F4 = F2 * F5;
      F0 = F3 * F4;
      F0 = F2 - F0;
      F0 = F0 * F5;
      F4 = F4 + F0;                 // alpha
      R0 = 2;                       // index = (raw_count - 2 - origin) + alpha
      R0 = R11 - R0;
      R1 = DM(3, I0);
      R0 = R0 - R1;
      F0 = FLOAT R0;
      F0 = F0 + F4;
      R1 = DM(1, I1);
      F1 = F0 - F1;
      F1 = ABS F1;
      R2 = 0x3F800000;
      COMP(F1, F2);
      IF LE JUMP .no_push;          // within a sample of the last keyframe
      DM(-16, I6) = R0;             // kf.time = index

      // kf.value = cc_dline8_bspline(&raw, 3 - alpha)
      R1 = 0x40400000;
      F0 = F1 - F4;                 // delay
      R2 = 1;                       // di = (int)delay, delay in [1, 4)
      R7 = 1;
      R3 = 0x40000000;
      COMP(F0, F3);
      IF GE R2 = R2 + R7;
      COMP(F0, F1);
      IF GE R2 = R2 + R7;
      F3 = FLOAT R2;
      F0 = F0 - F3;                 // f
      R1 = R10 - R2;                // wp - di
      R3 = 7;
      R5 = 2;
      R4 = 1;
      R4 = R1 + R4;                 // x0 at wp - di + 1
      R4 = R4 AND R3;
      R4 = LSHIFT R4 BY R5;
      R4 = R4 + R14;
      I2 = R4;
      R4 = R1 AND R3;               // x1 at wp - di
      R4 = LSHIFT R4 BY R5;
      R4 = R4 + R14;
      I3 = R4;
      R4 = 1;
      R4 = R1 - R4;                 // x2 at wp - di - 1
      R4 = R4 AND R3;
      R4 = LSHIFT R4 BY R5;
      R4 = R4 + R14;
      I4 = R4;
      R4 = 2;
      R4 = R1 - R4;                 // x3 at wp - di - 2
      R4 = R4 AND R3;
      R4 = LSHIFT R4 BY R5;
      R4 = R4 + R14;
      I5 = R4;
      F1 = F0 * F0;                 // t2
      R6 = 0x40400000;
      F6 = F6 * F0;                 // 3 f
      R3 = 0x40400000;              // B0 = 1 + f (-3 + f (3 - f))
      F3 = F3 - F0;
      F3 = F0 * F3;
      R4 = 0xC0400000;
      F3 = F4 + F3;
      F3 = F0 * F3;
      R4 = 0x3F800000;
      F3 = F4 + F3;
      R4 = DM(0, I2);
      F2 = F4 * F3;                 // x0 B0
      R3 = 0xC0C00000;              // B1 = 4 + t2 (-6 + 3 f)
      F3 = F3 + F6;
      F3 = F1 * F3;
      R4 = 0x40800000;
      F3 = F4 + F3;
      R4 = DM(0, I3);
      F3 = F4 * F3;
      F2 = F2 + F3;                 // + x1 B1
      R3 = 0x40400000;              // B2 = 1 + f (3 + f (3 - 3 f))
      F3 = F3 - F6;
      F3 = F0 * F3;
      R4 = 0x40400000;
      F3 = F4 + F3;
      F3 = F0 * F3;
      R4 = 0x3F800000;
      F3 = F4 + F3;
      R4 = DM(0, I4);
      F3 = F4 * F3;
      F2 = F2 + F3;                 // + x2 B2
      F3 = F1 * F0;                 // B3 = t3
      R4 = DM(0, I5);
      F3 = F4 * F3;
      F2 = F2 + F3;                 // + x3 B3
      R3 = 0x3E2AAAAB;
      F4 = F2 * F3;                 // kf.value
      R5 = DM(-16, I6);             // kf.time
      CALL .push;
      JUMP .counted;

.push_now:                          // kf = {most_recent.value, now}
      R4 = PASS R6;
      CALL .now;
      CALL .push;
.counted:
      R0 = 1;
      R11 = R11 + R0;               // an_push's raw_count++
      JUMP .guard;
.done:
      R0 = 0;
      DM(16, I0) = R0;              // most_recent.d2
      DM(17, I0) = R0;              // most_recent.tkeo
      DM(13, I0) = R10;
      DM(18, I0) = R11;
      DM(1, I0) = R12;
      R0 = DM(-11, I6);
      I0 = R0;
      R0 = DM(-12, I6);
      I1 = R0;
      R0 = DM(-13, I6);
      I2 = R0;
      R0 = DM(-14, I6);
      I3 = R0;
      R0 = DM(-15, I6);
      I5 = R0;
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-7, I6);
      R13 = DM(-8, I6);
      R14 = DM(-9, I6);
      R15 = DM(-10, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

// F5 = (raw_count > 0) ? (float)(raw_count - 1 - origin) : 0; clobbers R0, R1
.now:
      R5 = 0;
      R11 = PASS R11;
      IF LE JUMP .now_ret;
      R0 = 1;
      R0 = R11 - R0;
      R1 = DM(3, I0);
      R0 = R0 - R1;
      F5 = FLOAT R0;
.now_ret:
      RTS;

// write {F4 value, F5 time} at write_pos; write_pos++, sparse_count++; I1 = it
.push:
      R0 = DM(2, I0);               // size
      R1 = 1;
      R0 = R0 - R1;                 // mask
      R0 = R12 AND R0;
      R1 = 3;
      R0 = LSHIFT R0 BY R1;
      R1 = DM(0, I0);               // ring base
      R0 = R0 + R1;
      I1 = R0;
      R0 = 1;                       // (the counts first: I1 is not used right after its write)
      R12 = R12 + R0;
      R1 = DM(19, I0);
      R1 = R0 + R1;                 // not R1 + R0: its 16-bit form here trips digikit's width heuristic
      DM(19, I0) = R1;
      DM(0, I1) = R4;
      DM(1, I1) = R5;
      RTS;
.cc_feed..end:
      .type cc_feed.,STT_FUNC;

// void cc_shift_times(cc_keyframe *buf, int n, float d): buf[i].time -= d for
// i < n (n a multiple of 4), four keyframes a pass: CC_F32's rebase of the whole
// ring. selcc's loop reloads its address register every keyframe (a 4-cycle
// stall each, ubench kernel 4). R4 = buf, R8 = n, R12 = d; R9 kept in R2.
.GLOBAL cc_shift_times.;
cc_shift_times.:
      R2 = R9;
      R9 = PASS R8;
      I4 = R4;
      R1 = 4;
.st_loop:
      R0 = DM(1, I4);
      R3 = DM(3, I4);
      R5 = DM(5, I4);
      R6 = DM(7, I4);
      F0 = F0 - F12;
      F3 = F3 - F12;
      F5 = F5 - F12;
      F6 = F6 - F12;
      DM(1, I4) = R0;
      DM(3, I4) = R3;
      DM(5, I4) = R5;
      DM(7, I4) = R6;
      I4=MODIFY (I4,0x8)(NW);
      R9 = R9 - R1;
      IF GT JUMP .st_loop;
      R9 = R2;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
.cc_shift_times..end:
      .type cc_shift_times.,STT_FUNC;
