// render.asm -- stage 3: the grain pair's per-sample loop for the C99 Capicola core
// (-DCC_F32 -DCC_ASM), in place of capicola.c's CC_FASTPATH model, which it follows
// line for line. GNU AGPL-3.0, as Capicola. Assembled with selache's selas.
//
//   void cc_render_pair(cc_recorder *r, float *out, int n);   R4, R8, R12
//
// Per sample: the live grain (and, during a pair crossfade, the other) steps its
// windows forward and reads; anything rarer -- a breach, or a front breach within
// a sample of the margin, a leash splice, a splice ending -- goes to the C
// cc_granule_read for that sample, which does the whole of it (its window steps
// are then no-ops).
//
// Layout (-DCC_F32 -char-size-8, all fields 4 bytes; offsets in words):
//   cc_recorder: sparse.buf 0, .write_pos 1, .size 2; granule[0] at byte 96,
//                granule[1] at byte 336; live_g 144, x_gain 145, x_step 146
//   cc_granule:  ideal 1, actual 11, temp 21 (cc_playhead, 10 words each);
//                leash 51: >= 0 in keyframes, < 0 in samples (capicola.c);
//                write_pos.sparse 31, live_edge.uniform 34, pitch 49, leash 51,
//                fixed_duration 52, fixed_increment 53, adaptive_duration 54,
//                adaptive_increment 55, splice_phase 56, splicing 57, adaptive 58,
//                block_size 59
//   cc_playhead: w.s1 0, w.s2 1, w.index 2, w.duration 3, w.inv_duration 4,
//                w.end_time 5, index 6, tau 7, speed 8, result 9
//   cc_keyframe: value 0, time 1 (8 bytes)
//
// selcc's convention: R0-R7, I4, I12 scratch; R8-R15 saved by the callee; selcc's
// code touches no other I or M register. Here, for the whole call:
//   I0 = r, R10 = r, R11 = out, R9 = samples left, R12 = back-breach safety
//   (size - size/8), R13 = ring mask, R14 = newest index, R15 = ring base;
//   per grain: R8 = I2 = the granule; I5 = the playhead in hand; I1 = out;
//   I3, I4 = the keyframe pair in .ph. The SHARC+ stalls 4 cycles when an I
//   register written by the previous instruction addresses memory, and a
//   CALL + RTS costs about 14 (ubench): the common path avoids both.
// Pointers are byte addresses; DM(k, Ix) offsets are in words (as s3_play.asm).
// No DO loops, no pre-modify, no M0-M3, no negative shift immediates.

.SECTION/PM seg_pmco;

#ifdef GEN_WSOLA   /* plan B never runs the keyframe path below: to L2 (l1l2.ldf), up to .fcl_set's helpers */
.SECTION/PM seg_cold_pm;
#endif
.GLOBAL cc_render_pair.;
cc_render_pair.:
      I7=MODIFY (I7,-0x11)(NW);
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
      R0 = I2;
      DM(-12, I6) = R0;
      R0 = I5;
      DM(-13, I6) = R0;             // -14: the live grain's sample in a crossfade
      R0 = I1;
      DM(-15, I6) = R0;
      R0 = I3;
      DM(-16, I6) = R0;

      I0 = R4;
      R10 = R4;
      R9 = R12;
#ifdef CC_CLEAN
// the stereo tape (dt2gen.c, CC_TAPE_BUF_AT/CC_TAPE_AT): R11 = this sample's slot, 0 off
      R11 = DM(0x2DEE34);
      DM(0x2DEE30) = R11;
#else
      R11 = 0;
#endif
      I1 = R8;                      // out, advanced a word a sample
      R15 = DM(0, I0);              // ring base
      R1 = 1;
      R0 = DM(1, I0);
      R14 = R0 - R1;                // newest = write_pos - 1
      R0 = DM(2, I0);               // size
      R13 = R0 - R1;                // mask
      R2 = -3;
      R1 = LSHIFT R0 BY R2;
      R12 = R0 - R1;                // safety = size - (size >> 3)
      R9 = PASS R9;
      IF LE JUMP .done;
#if defined(CC_CLEAN) && !defined(GEN_WSOLA)   /* (plan B has its own: cc_brun) */
// ---- the fast run (capicola.c rec_fast_count, gr_run, gr_catch_up): the block's
// first fast_n samples (recorder word 231) need no event check, so the live grain
// only reads and advances; then its windows are stepped once, and the per-sample
// loop does the rest. R8 = the samples left when the run ends.
      R8 = DM(231, I0);             // fast_n
      R8 = PASS R8;
      IF LE JUMP .loop;
      R0 = R9 - R8;
      R8 = PASS R0;
      R1 = 96;
      R0 = R10 + R1;                // granule[0]
      R1 = 240;
      R2 = DM(144, I0);             // live_g
      R2 = PASS R2;
      IF NE R0 = R0 + R1;
      I2 = R0;
      CALL .fcl_set;                // the note's constants for .fcl: R12-R15
      R0 = DM(57, I2);              // splicing (a run neither starts nor ends one)
      R0 = PASS R0;
      IF NE JUMP .fs_loop;
.fp_loop:                           // not splicing: actual's clean read
      R11 = PASS R11;
      IF EQ JUMP .fp_nt;
      I3 = R11;
.fp_nt:
      R0 = DM(7, I2);               // ideal.index += ideal.speed
      R1 = DM(9, I2);
      F0 = F0 + F1;
      DM(7, I2) = R0;
      R1 = DM(17, I2);              // actual.index
      R11 = PASS R11;
      IF EQ JUMP .fp_rd;
      R2 = 1;                       // the tape: one entry, (index, 1)
      DM(0, I3) = R2;
      DM(1, I3) = R1;
      R2 = 0x3F800000;
      DM(2, I3) = R2;
.fp_rd:                             // .fcl inline (F1 = the index -> F0)
      R6 = PASS R1;                 // the index, for .clean
      F1 = F1 - F12;                // rel = index - (t0 - origin)
      R2 = DM(236, I0);             // b_lo: 1 - b_k (dt2gen.c's plan B), else 1
      COMP(F1, F2);                 // the four samples i - 1 .. i + 2 inside the note:
      IF LT JUMP .fp_sl;            // b_lo <= rel (k = floor(rel) + b_k >= 1) ...
      COMP(F1, F15);
      IF GE JUMP .fp_sl;            // ... and rel < end - start - 2
      R0 = FIX F1;                  // k = floor(rel), f = rel - k (as .clean)
      F2 = FLOAT R0;
      COMP(F2, F1);
      IF LE JUMP .fl_p;
      R2 = 1;
      R0 = R0 - R2;
      F2 = FLOAT R0;
.fl_p:
      F7 = F1 - F2;                 // f
      R2 = R0 + R0;
      R2 = R13 + R2;                // the byte address of sample i - 1 (i = start + k)
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = -16;
      R1 = 2;
      R2 = R2 AND R1;               // 0: i - 1 in a word's low half, 2: its high half
      R4 = DM(0, I4);               // (loads leave the flags)
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      IF NE JUMP .od_p;
      R2 = ASHIFT R5 BY R3;         // y3
      R6 = LSHIFT R5 BY R0;
      R6 = ASHIFT R6 BY R3;         // y2
      R5 = ASHIFT R4 BY R3;         // y1
      R4 = LSHIFT R4 BY R0;
      R4 = ASHIFT R4 BY R3;         // y0
      JUMP .fp_p;
.od_p:
      R2 = LSHIFT R6 BY R0;
      R2 = ASHIFT R2 BY R3;         // y3
      R6 = ASHIFT R5 BY R3;         // y2
      R5 = LSHIFT R5 BY R0;
      R5 = ASHIFT R5 BY R3;         // y1
      R4 = ASHIFT R4 BY R3;         // y0
.fp_p:
      R1 = -15;                     // / 32768
      F4 = FLOAT R4 BY R1;
      F5 = FLOAT R5 BY R1;
      F6 = FLOAT R6 BY R1;
      F2 = FLOAT R2 BY R1;
// .clean's operations and order of evaluation, scheduled so that a product is
// rarely used by the very next instruction
      R0 = 0x3F000000;              // 0.5
      F1 = F2 - F4;                 // y3 - y0
      F2 = F0 * F2;                 // 0.5 y3 (y3 not needed after)
      F3 = F5 - F6;                 // y1 - y2
      F1 = F0 * F1;                 // 0.5 (y3 - y0)
      R0 = 0x3FC00000;              // 1.5
      F3 = F0 * F3;                 // 1.5 (y1 - y2)
      R0 = 0x40200000;              // 2.5
      F0 = F0 * F5;                 // 2.5 y1
      F3 = F1 + F3;                 // c3
      F1 = F4 - F0;                 // y0 - 2.5 y1
      R0 = 0x40000000;              // 2
      F0 = F0 * F6;                 // 2 y2
      F1 = F1 + F0;
      F1 = F1 - F2;                 // c2 = y0 - 2.5 y1 + 2 y2 - 0.5 y3
      F2 = F6 - F4;
      R0 = 0x3F000000;
      F2 = F0 * F2;                 // c1 = 0.5 (y2 - y0)
      F0 = F3 * F7;                 // c3 f
      F0 = F0 + F1;                 // + c2
      F0 = F0 * F7;
      F0 = F0 + F2;                 // + c1
      F0 = F0 * F7;
      F0 = F0 + F5;                 // + y1
      JUMP .fp_got;
.fp_sl:
      CALL .fcl_slow;
.fp_got:
      R1 = DM(17, I2);              // actual.index += actual.speed
      R2 = DM(19, I2);
      F1 = F1 + F2;
      DM(17, I2) = R1;
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .fp_n;
      R1 = 36;
      R11 = R11 + R1;               // the next sample's slot
.fp_n:
      R1 = 1;
      R9 = R9 - R1;
      COMP(R9, R8);
      IF NE JUMP .fp_loop;
      JUMP .fr_catch;

.fs_loop:                           // splicing: temp's and actual's reads, mixed
      R11 = PASS R11;
      IF EQ JUMP .fs_nt;
      I3 = R11;
.fs_nt:
      R0 = DM(7, I2);               // ideal.index += ideal.speed
      R1 = DM(9, I2);
      F0 = F0 + F1;
      DM(7, I2) = R0;
      R0 = DM(19, I2);
      DM(29, I2) = R0;              // temp.speed = actual.speed (the pitch, or minus it in reverse)
      R1 = DM(27, I2);              // temp.index
      R11 = PASS R11;
      IF EQ JUMP .fs_r1;
      R2 = 1;
      DM(0, I3) = R2;
      DM(1, I3) = R1;
      R2 = 0x3F800000;
      DM(2, I3) = R2;
.fs_r1:
      CALL .fcl;
      DM(-14, I6) = R0;             // in (.fcl uses R7)
      R1 = DM(17, I2);              // actual.index
      R11 = PASS R11;
      IF EQ JUMP .fs_r2;
      R2 = 2;
      DM(0, I3) = R2;
      DM(3, I3) = R1;
      R2 = 0x3F800000;
      DM(4, I3) = R2;
.fs_r2:
      CALL .fcl;                    // F0 = out
      R1 = DM(27, I2);              // temp.index += temp.speed
      R2 = DM(29, I2);
      F1 = F1 + F2;
      DM(27, I2) = R1;
      R1 = DM(17, I2);              // actual.index += actual.speed
      R2 = DM(19, I2);
      F1 = F1 + F2;
      DM(17, I2) = R1;
      R1 = DM(56, I2);              // w = smooth_step(splice_phase)
      F2 = F1 * F1;
      F3 = F1 + F1;
      R4 = 0x40400000;
      F3 = F4 - F3;
      F2 = F2 * F3;
      R7 = DM(-14, I6);             // in
      F3 = F7 * F2;                 // in * w
      R4 = 0x3F800000;
      F4 = F4 - F2;
      F4 = F0 * F4;                 // out * (1 - w)
      F0 = F3 + F4;
      R11 = PASS R11;
      IF EQ JUMP .fs_inc;
      DM(2, I3) = R2;               // the temp read's weight: w
      R5 = 0x3F800000;
      F5 = F5 - F2;
      DM(4, I3) = R5;               // the actual read's: 1 - w
.fs_inc:
      R2 = DM(53, I2);              // fixed_increment
      R3 = DM(58, I2);
      R3 = PASS R3;
      IF EQ JUMP .fs_i;
      R2 = DM(55, I2);              // adaptive_increment
.fs_i:
      R3 = DM(49, I2);
      F2 = F2 * F3;
      F1 = F1 + F2;
      DM(56, I2) = R1;              // splice_phase += inc * pitch
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .fs_n;
      R1 = 36;
      R11 = R11 + R1;
.fs_n:
      R1 = 1;
      R9 = R9 - R1;
      COMP(R9, R8);
      IF NE JUMP .fs_loop;

.fr_catch:                          // the windows where per-sample steps would have left them
      CALL .fcl_end;                // R12-R15 back for .step and the per-sample loop
      R0 = I2;
      R1 = 4;
      R1 = R0 + R1;
      I5 = R1;                      // ideal
      R4 = DM(7, I2);
      CALL .step;
      R0 = I2;
      R1 = 44;
      R1 = R0 + R1;
      I5 = R1;                      // actual
      R4 = DM(17, I2);
      CALL .step;
      R0 = DM(57, I2);
      R0 = PASS R0;
      IF EQ JUMP .fr_done;
      R0 = I2;
      R1 = 84;
      R1 = R0 + R1;
      I5 = R1;                      // temp
      R4 = DM(27, I2);
      CALL .step;
.fr_done:
      R9 = PASS R9;
      IF LE JUMP .done;
#endif

.loop:
#ifdef CC_CLEAN
      R11 = PASS R11;
      IF NE JUMP .lp_tape;
#endif
.lp_go:
      R1 = 96;
      R8 = R10 + R1;                // granule[0]
      R1 = 240;
      R0 = DM(144, I0);             // live_g
      R0 = PASS R0;
      IF NE R8 = R8 + R1;
      I2 = R8;                      // (re-set every sample: a crossfade switches it)
      R0 = DM(145, I0);             // x_gain
      R1 = 0x3F800000;
      COMP(F0, F1);
      IF LT JUMP .xfade;
      CALL .gr;
      JUMP .store;

.xfade:
      CALL .gr;
      DM(-14, I6) = R0;             // in
#ifdef CC_CLEAN
      R11 = PASS R11;
      IF EQ JUMP .xf_a;
      R2 = DM(0, I3);
      DM(-17, I6) = R2;             // the live grain's tape entries
#endif
.xf_a:
      R1 = 96;
      R8 = R10 + R1;
      R1 = 240;
      R0 = DM(144, I0);
      R0 = PASS R0;
      IF EQ R8 = R8 + R1;           // the other grain
      I2 = R8;
      CALL .gr;                     // F0 = o
      R1 = DM(145, I0);             // x_gain
      F2 = F1 * F1;
      F3 = F1 + F1;
      R4 = 0x40400000;              // 3.0
      F3 = F4 - F3;
      F2 = F2 * F3;                 // w = smooth_step(x_gain)
      R5 = DM(-14, I6);
      F5 = F5 * F2;                 // in * w
      R4 = 0x3F800000;
      F3 = F4 - F2;
      F3 = F0 * F3;                 // o * (1 - w)
      F0 = F5 + F3;
#ifdef CC_CLEAN
      R11 = PASS R11;
      IF EQ JUMP .xf_b;
      CALL .tape_xf;
#endif
.xf_b:
      R3 = DM(146, I0);             // x_step
      F1 = F1 + F3;
      COMP(F1, F4);
      IF GT R1 = PASS R4;
      DM(145, I0) = R1;

.store:
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
#ifdef CC_CLEAN
      R11 = PASS R11;
      IF EQ JUMP .st_go;
      R1 = 36;
      R11 = R11 + R1;               // the next sample's slot (9 words)
#endif
.st_go:
      R1 = 1;
      R9 = R9 - R1;
      IF NE JUMP .loop;

.done:
      R0 = DM(-11, I6);
      I0 = R0;
      R0 = DM(-12, I6);
      I2 = R0;
      R0 = DM(-13, I6);
      I5 = R0;
      R0 = DM(-15, I6);
      I1 = R0;
      R0 = DM(-16, I6);
      I3 = R0;
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

// ---- one grain's sample: R8 = I2 = the granule; returns F0 -----------------
.gr:                                // each playhead's window steps only past its end
      R4 = DM(7, I2);               // ideal.index
      R0 = DM(6, I2);               // ideal.w.end_time
      COMP(F4, F0);
      IF GT JUMP .gr_si;
.gr_a:
      R4 = DM(17, I2);              // actual.index
      R0 = DM(16, I2);              // actual.w.end_time
      COMP(F4, F0);
      IF GT JUMP .gr_sa;
.gr_t:
      R0 = DM(57, I2);              // splicing
      R0 = PASS R0;
      IF EQ JUMP .gr_chk;
      R4 = DM(27, I2);              // temp.index
      R0 = DM(26, I2);              // temp.w.end_time
      COMP(F4, F0);
      IF GT JUMP .gr_st;
.gr_ad:
      R0 = DM(58, I2);              // adaptive
      R0 = PASS R0;
      IF EQ JUMP .gr_lead;

.gr_chk:                            // front breach, conservatively
      R0 = DM(49, I2);              // pitch
      R1 = 0x3F800000;
      COMP(F0, F1);
      IF LE JUMP .gr_back;
      R3 = 0x40000000;              // k = 1 - 1/pitch (the margin covers RECIPS)
      F2 = RECIPS F0;
      F5 = F0 * F2;
      F5 = F3 - F5;
      F2 = F2 * F5;
      F5 = F0 * F2;
      F5 = F3 - F5;
      F2 = F2 * F5;
      F2 = F1 - F2;
      R5 = DM(52, I2);              // fixed_duration
      R0 = DM(57, I2);
      R0 = PASS R0;
      IF EQ JUMP .gr_close;
      R5 = DM(56, I2);              // splice_phase
      F5 = F1 - F5;
      R6 = DM(54, I2);              // adaptive_duration
      F5 = F5 * F6;
.gr_close:
      F5 = F5 * F2;                 // closing
      R6 = DM(59, I2);              // block_size
      F6 = FLOAT R6;
      F5 = F5 + F6;
      F5 = F5 + F1;                 // + 1 sample
      R6 = DM(34, I2);              // live_edge.uniform
      R7 = DM(17, I2);              // actual.index
      F6 = F6 - F7;                 // runway
      COMP(F6, F5);
      IF LE JUMP .gr_slow;
.gr_back:
      R0 = DM(31, I2);              // write_pos.sparse
      R1 = DM(3, I2);               // ideal.w.index
      R0 = R0 - R1;                 // backlog
      COMP(R0, R12);
      IF GE JUMP .gr_slow;

.gr_lead:
      R0 = DM(57, I2);
      R0 = PASS R0;
      IF NE JUMP .gr_splicing;
      R1 = DM(51, I2);              // leash
      R1 = PASS R1;
      IF LT JUMP .gr_tleash;
      R0 = DM(13, I2);              // keyframes: |actual.w.index - ideal.w.index| > leash
      R2 = DM(3, I2);
      R0 = R0 - R2;
      R0 = ABS R0;
      COMP(R0, R1);
      IF GT JUMP .gr_slow;
      JUMP .gr_plain;
.gr_tleash:                         // samples (leash < 0): |actual.index - ideal.index| > -leash
      R0 = DM(17, I2);
      R2 = DM(7, I2);
      F0 = F0 - F2;
      F0 = ABS F0;
      R1 = -R1;
      F1 = FLOAT R1;
      COMP(F0, F1);
      IF GT JUMP .gr_slow;
.gr_plain:
      R0 = 44;
      R0 = R0 + R8;
      I5 = R0;                      // actual (set early: no stall at .ph)
      R0 = DM(7, I2);               // ideal.index += ideal.speed
      R1 = DM(9, I2);
      F0 = F0 + F1;
      DM(7, I2) = R0;
      CALL .ph;                     // F0 = actual's sample
      R1 = DM(17, I2);              // actual.index += actual.speed
      R2 = DM(19, I2);
      F1 = F1 + F2;
      DM(17, I2) = R1;
      RTS;

.gr_splicing:
      R0 = DM(56, I2);              // splice_phase
      R1 = 0x3F800000;
      COMP(F0, F1);
      IF GT JUMP .gr_slow;          // the splice ends: C
      R0 = DM(7, I2);               // ideal.index += ideal.speed
      R1 = DM(9, I2);
      F0 = F0 + F1;
      DM(7, I2) = R0;
      R0 = 84;
      R0 = R0 + R8;
      I5 = R0;                      // temp (set early: no stall at .ph)
      R0 = DM(49, I2);
      DM(29, I2) = R0;              // temp.speed = pitch
      CALL .ph;
      R7 = R0;                      // in (.ph leaves R7 alone)
      R0 = 44;
      R0 = R0 + R8;
      I5 = R0;
      R0 = 0;                       // (I5 two instructions before its use)
      CALL .ph;                     // F0 = out
      R1 = DM(27, I2);              // temp.index += temp.speed
      R2 = DM(29, I2);
      F1 = F1 + F2;
      DM(27, I2) = R1;
      R1 = DM(17, I2);              // actual.index += actual.speed
      R2 = DM(19, I2);
      F1 = F1 + F2;
      DM(17, I2) = R1;
      R1 = DM(56, I2);              // w = smooth_step(splice_phase)
      F2 = F1 * F1;
      F3 = F1 + F1;
      R4 = 0x40400000;
      F3 = F4 - F3;
      F2 = F2 * F3;
      F3 = F7 * F2;                 // in * w
      R4 = 0x3F800000;
      F4 = F4 - F2;
      F4 = F0 * F4;                 // out * (1 - w)
      F0 = F3 + F4;
#ifdef CC_CLEAN
      R11 = PASS R11;
      IF EQ JUMP .gs_n;
      R3 = DM(0, I3);
      R4 = 3;
      R3 = LSHIFT R3 BY R4;
      R3 = R11 + R3;
// the slot + 8 n: the newest entry's weight at word 0, the one before at -2
      I4 = R3;
      R5 = 0x3F800000;
      F5 = F5 - F2;
      R4 = DM(0, I4);
      F4 = F4 * F5;
      DM(0, I4) = R4;
// (the actual read's entry times 1 - w, the temp read's times w)
      R4 = DM(-2, I4);
      F4 = F4 * F2;
      DM(-2, I4) = R4;
#endif
.gs_n:
      R2 = DM(53, I2);              // fixed_increment
      R3 = DM(58, I2);
      R3 = PASS R3;
      IF EQ JUMP .gr_inc;
      R2 = DM(55, I2);              // adaptive_increment
.gr_inc:
      R3 = DM(49, I2);
      F2 = F2 * F3;
      F1 = F1 + F2;
      DM(56, I2) = R1;              // splice_phase += inc * pitch
      RTS;

.gr_si:                             // (I5's write right before .step's use stalls; these are rare)
      R0 = 4;
      R0 = R0 + R8;
      I5 = R0;                      // ideal
      CALL .step;
      JUMP .gr_a;
.gr_sa:
      R0 = 44;
      R0 = R0 + R8;
      I5 = R0;                      // actual
      CALL .step;
      JUMP .gr_t;
.gr_st:
      R0 = 84;
      R0 = R0 + R8;
      I5 = R0;                      // temp
      CALL .step;
      JUMP .gr_ad;

.gr_slow:
      R4 = R8;
      R2 = I6;
      CJUMP cc_granule_read. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .gr_ret - 1;
.gr_ret:
      RTS;

// ---- step window I5 forward to index F4 (cc_sparse_step_window's first loop) --
.step:
      R0 = DM(5, I5);               // end_time
      COMP(F4, F0);
      IF LE JUMP .step_ret;
.step_loop:
      R1 = DM(2, I5);               // w.index
      COMP(R1, R14);
      IF GE JUMP .step_ret;         // at the newest keyframe
      R0 = 1;
      R1 = R1 + R0;
      DM(2, I5) = R1;
      R2 = DM(0, I5);
      DM(1, I5) = R2;               // s2 = s1
      R3 = R1 AND R13;
      DM(0, I5) = R3;               // s1 = index & mask
      R0 = 3;
      R3 = LSHIFT R3 BY R0;
      R3 = R3 + R15;
      I4 = R3;
      R5 = DM(1, I4);               // buf[s1].time
      R2 = LSHIFT R2 BY R0;
      R2 = R2 + R15;
      I4 = R2;
      R6 = DM(1, I4);               // buf[s2].time
      F7 = F5 - F6;                 // d
      DM(3, I5) = R7;
      R0 = 0x3727C5AC;              // 1e-5f
      COMP(F7, F0);
      R1 = 0;
      IF LE JUMP .step_inv;
      R3 = 0x40000000;              // 1/d, as selcc divides
      F1 = RECIPS F7;
      F2 = F7 * F1;
      F2 = F3 - F2;
      F1 = F1 * F2;
      F2 = F7 * F1;
      F2 = F3 - F2;
      F1 = F1 * F2;
      R3 = 0x3F800000;
      F0 = F3 * F1;
      F2 = F7 * F0;
      F2 = F3 - F2;
      F2 = F2 * F1;
      F1 = F0 + F2;
.step_inv:
      DM(4, I5) = R1;
      DM(5, I5) = R5;               // end_time
      COMP(F4, F5);
      IF GT JUMP .step_loop;
.step_ret:
      RTS;

// ---- ph_sample: playhead I5 -> F0 (and its tau and result); I0 = the recorder.
// clobbers R0-R6, I4 (not R7). blend (word 217) >= 1: keyframes only; <= 0: the
// source's samples only (.clean); between: c + blend * (k - c) (capicola.c).
.ph:
      R0 = DM(5, I5);               // w.end_time
      R1 = DM(6, I5);               // index
      F0 = F0 - F1;
      R2 = DM(4, I5);               // w.inv_duration
      F0 = F0 * F2;                 // tau
      DM(7, I5) = R0;
// (without CAPI the blend is always 1: keyframes only)
#ifdef CC_CLEAN
      R1 = DM(217, I0);             // blend
      R2 = 0x3F800000;
      COMP(F1, F2);
      IF GE JUMP .ph_kf_only;
      R1 = DM(6, I5);               // index
      CALL .clean;                  // F0 = c
      R1 = DM(217, I0);
      R2 = 0;
      COMP(F1, F2);
      IF LE JUMP .ph_tape;          // blend 0: the samples alone
      DM(9, I5) = R0;               // c, for a moment
      CALL .kf;                     // F0 = k
      R1 = DM(9, I5);
      F0 = F0 - F1;                 // k - c
      R2 = DM(217, I0);
      F0 = F2 * F0;                 // blend * (k - c)
      F0 = F1 + F0;                 // c + ...
.ph_tape:
// the stereo tape: this read's index, weight 1 (up to four entries)
      R11 = PASS R11;
      IF EQ JUMP .ph_out;
      R2 = DM(0, I3);
      R3 = 4;
      COMP(R2, R3);
      IF GE JUMP .ph_out;
      R3 = 3;
      R4 = LSHIFT R2 BY R3;
      R4 = R11 + R4;
      I4 = R4;
      R5 = DM(6, I5);
      R6 = 0x3F800000;
      R3 = 1;
      R2 = R3 + R2;
      DM(1, I4) = R5;
      DM(2, I4) = R6;
      DM(0, I3) = R2;
.ph_out:
      DM(9, I5) = R0;               // result
      RTS;

// ---- the stereo tape's crossfade: entries [0, k1) times w (F2), the rest times
// 1 - w; k1 at DM(-17, I6). Keeps R0-R2 (F2 is w), R4; clobbers R3, R5-R8, I4
// (R8, the granule, is set again at the next sample).
.tape_xf:
      R5 = 0x3F800000;
      F5 = F5 - F2;
      R6 = DM(0, I3);
      R8 = DM(-17, I6);
      R6 = R6 - R8;
      R7 = 8;
      R7 = R11 + R7;
.tx1:
      R8 = PASS R8;
      IF LE JUMP .tx2;
      I4 = R7;
      R3 = 8;
      R7 = R3 + R7;
      R3 = DM(0, I4);
      F3 = F3 * F2;
      DM(0, I4) = R3;
      R3 = 1;
      R8 = R8 - R3;
      JUMP .tx1;
.tx2:
      R6 = PASS R6;
      IF LE JUMP .tx_done;
      I4 = R7;
      R3 = 8;
      R7 = R3 + R7;
      R3 = DM(0, I4);
      F3 = F3 * F5;
      DM(0, I4) = R3;
      R3 = 1;
      R6 = R6 - R3;
      JUMP .tx2;
.tx_done:
      RTS;

// ---- the stereo tape: this sample's slot (R11) to I3 and the C fallback's word,
// no entries yet
.lp_tape:
      I3 = R11;
      DM(0x2DEE30) = R11;
      R0 = 0;
      R1 = 0;
      DM(0, I3) = R0;
      JUMP .lp_go;
#endif
.ph_kf_only:
#ifdef CC_CLEAN
      CALL .kf;
      DM(9, I5) = R0;
      RTS;
#else
      // (without CAPI: .kf inline, both keyframe addresses set before the polynomial)
      R6 = 3;
      R4 = DM(0, I5);               // s1
      R4 = LSHIFT R4 BY R6;
      R4 = R4 + R15;
      I4 = R4;
      R5 = DM(1, I5);               // s2
      R5 = LSHIFT R5 BY R6;
      R5 = R5 + R15;
      I3 = R5;
      R2 = 0;                       // tau (F0, just stored) into [0, 1]
      COMP(F0, F2);
      IF LT R0 = PASS R2;
      R2 = 0x3F800000;
      COMP(F0, F2);
      IF GT R0 = PASS R2;
      F1 = F0 * F0;                 // t2
      F2 = F0 + F0;
      R3 = 0x40400000;
      F2 = F2 - F3;
      F2 = F2 * F1;                 // p = (2t - 3) t2; h1 = -p
      R3 = 0x3F800000;
      F3 = F2 + F3;                 // h0 = p + 1
      R4 = DM(0, I4);               // buf[s1].value
      R5 = DM(0, I3);               // buf[s2].value
      F3 = F3 * F4;
      F2 = F2 * F5;
      F0 = F3 - F2;                 // h0 v1 + h1 v2
      DM(9, I5) = R0;
      RTS;
#endif

#ifdef CC_CLEAN
// ---- cc_sparse_read at the playhead's tau (word 7): F0; clobbers R0-R6, I4 --
.kf:
      R0 = DM(7, I5);               // tau
      R2 = 0;
      COMP(F0, F2);
      IF LT R0 = PASS R2;
      R2 = 0x3F800000;
      COMP(F0, F2);
      IF GT R0 = PASS R2;
      F1 = F0 * F0;                 // t2
      F2 = F0 + F0;
      R3 = 0x40400000;
      F2 = F2 - F3;
      F2 = F2 * F1;                 // p = (2t - 3) t2; h1 = -p
      R3 = 0x3F800000;
      F3 = F2 + F3;                 // h0 = p + 1
      R6 = 3;
      R4 = DM(0, I5);               // s1
      R4 = LSHIFT R4 BY R6;
      R4 = R4 + R15;
      I4 = R4;
      R4 = DM(0, I4);               // buf[s1].value
      R5 = DM(1, I5);               // s2
      R5 = LSHIFT R5 BY R6;
      R5 = R5 + R15;
      I4 = R5;
      R5 = DM(0, I4);               // buf[s2].value
      F3 = F3 * F4;
      F2 = F2 * F5;
      F0 = F3 - F2;                 // h0 v1 + h1 v2
      RTS;
#endif

#ifdef GEN_WSOLA
.SECTION/PM seg_pmco;
#endif
#ifdef CC_CLEAN
// ---- .clean with the note's constants in registers, for runs where they do not
// change (.fcl_set): R12 = float(src_t0 - origin), R13 = the byte address of
// sample src_start + b_k - 1, R14 = src_start, F15 = float(src_end - src_start
// - 2 - b_k) (b_k: plan B's whole samples, recorder word 234; else 0). With b_k
// 0 the same operations in the same order of evaluation as .clean, so the same
// result; else rec_clean_read's fast path. F1 = index -> F0; clobbers R0-R7, I4. Before the note's second sample
// and near its end it hands over to .clean. .fp_loop has its own copy inline.
.fcl_set:
      R2 = DM(210, I0);             // src_t0
      R3 = DM(3, I0);               // origin
      R2 = R2 - R3;
      F12 = FLOAT R2;
      R14 = DM(218, I0);            // start
      R0 = DM(207, I0);             // end
      R0 = R0 - R14;
      R1 = 2;
      R0 = R0 - R1;
      R1 = DM(234, I0);             // b_k (dt2gen.c's plan B; else 0)
      R0 = R0 - R1;
      F15 = FLOAT R0;               // end - start - 2 - b_k
      R0 = R14 + R1;
      R0 = R0 + R0;
      R1 = DM(205, I0);             // base
      R2 = R1 + R0;
      R1 = 2;
      R13 = R2 - R1;                // base + 2 (start + b_k - 1)
      RTS;
// the per-sample loop's R12-R15, as cc_render_pair's entry sets them
.fcl_end:
      R15 = DM(0, I0);              // ring base
      R1 = 1;
      R0 = DM(1, I0);
      R14 = R0 - R1;                // newest = write_pos - 1
      R0 = DM(2, I0);               // size
      R13 = R0 - R1;                // mask
      R2 = -3;
      R1 = LSHIFT R0 BY R2;
      R12 = R0 - R1;                // safety = size - (size >> 3)
      RTS;
.fcl:
      R6 = PASS R1;                 // the index, for .clean
      F1 = F1 - F12;                // rel = index - (t0 - origin)
      R2 = DM(236, I0);             // b_lo: 1 - b_k (dt2gen.c's plan B), else 1
      COMP(F1, F2);                 // the four samples i - 1 .. i + 2 inside the note:
      IF LT JUMP .fcl_slow;            // b_lo <= rel (k = floor(rel) + b_k >= 1) ...
      COMP(F1, F15);
      IF GE JUMP .fcl_slow;            // ... and rel < end - start - 2
      R0 = FIX F1;                  // k = floor(rel), f = rel - k (as .clean)
      F2 = FLOAT R0;
      COMP(F2, F1);
      IF LE JUMP .fl_c;
      R2 = 1;
      R0 = R0 - R2;
      F2 = FLOAT R0;
.fl_c:
      F7 = F1 - F2;                 // f
      R2 = R0 + R0;
      R2 = R13 + R2;                // the byte address of sample i - 1 (i = start + k)
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = -16;
      R1 = 2;
      R2 = R2 AND R1;               // 0: i - 1 in a word's low half, 2: its high half
      R4 = DM(0, I4);               // (loads leave the flags)
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      IF NE JUMP .od_c;
      R2 = ASHIFT R5 BY R3;         // y3
      R6 = LSHIFT R5 BY R0;
      R6 = ASHIFT R6 BY R3;         // y2
      R5 = ASHIFT R4 BY R3;         // y1
      R4 = LSHIFT R4 BY R0;
      R4 = ASHIFT R4 BY R3;         // y0
      JUMP .fp_c;
.od_c:
      R2 = LSHIFT R6 BY R0;
      R2 = ASHIFT R2 BY R3;         // y3
      R6 = ASHIFT R5 BY R3;         // y2
      R5 = LSHIFT R5 BY R0;
      R5 = ASHIFT R5 BY R3;         // y1
      R4 = ASHIFT R4 BY R3;         // y0
.fp_c:
      R1 = -15;                     // / 32768
      F4 = FLOAT R4 BY R1;
      F5 = FLOAT R5 BY R1;
      F6 = FLOAT R6 BY R1;
      F2 = FLOAT R2 BY R1;
// .clean's operations and order of evaluation, scheduled so that a product is
// rarely used by the very next instruction
      R0 = 0x3F000000;              // 0.5
      F1 = F2 - F4;                 // y3 - y0
      F2 = F0 * F2;                 // 0.5 y3 (y3 not needed after)
      F3 = F5 - F6;                 // y1 - y2
      F1 = F0 * F1;                 // 0.5 (y3 - y0)
      R0 = 0x3FC00000;              // 1.5
      F3 = F0 * F3;                 // 1.5 (y1 - y2)
      R0 = 0x40200000;              // 2.5
      F0 = F0 * F5;                 // 2.5 y1
      F3 = F1 + F3;                 // c3
      F1 = F4 - F0;                 // y0 - 2.5 y1
      R0 = 0x40000000;              // 2
      F0 = F0 * F6;                 // 2 y2
      F1 = F1 + F0;
      F1 = F1 - F2;                 // c2 = y0 - 2.5 y1 + 2 y2 - 0.5 y3
      F2 = F6 - F4;
      R0 = 0x3F000000;
      F2 = F0 * F2;                 // c1 = 0.5 (y2 - y0)
      F0 = F3 * F7;                 // c3 f
      F0 = F0 + F1;                 // + c2
      F0 = F0 * F7;
      F0 = F0 + F2;                 // + c1
      F0 = F0 * F7;
      F0 = F0 + F5;                 // + y1
      RTS;
.fcl_slow:
      R1 = PASS R6;                 // the index
      R0 = DM(235, I0);             // + b_kf: the index from the note's start
      F1 = F1 + F0;
      R0 = DM(233, I0);             // b_llen: 0 unless the note loops (dt2gen.c's plan B)
      R0 = PASS R0;
      IF EQ JUMP .clean;            // (its RTS returns to .fcl's caller)
      R3 = DM(232, I0);             // b_lend
      R4 = 0;
.fs_dn:                             // into [0, b_lend) from the note's start, a loop at a time
      F2 = F1 - F12;
      COMP(F2, F3);
      IF LT JUMP .fs_up;
      F1 = F1 - F0;
      JUMP .fs_dn;
.fs_up:
      COMP(F2, F4);
      IF GE JUMP .clean;
      F1 = F1 + F0;
      F2 = F1 - F12;
      JUMP .fs_up;

// ---- rec_clean_read(r = I0, index = F1) -> F0; clobbers R0-R6, I4 (not R7) --
// recorder words: src 205, src_end 207, src_t0 210, src_start 218, prev_src 219,
// prev_start 220, prev_end 221, prev_t0 222, prev_valid 223, scratch 224-227.
.clean:
      DM(227, I0) = R1;             // index, for the previous note's mapping
      R2 = DM(210, I0);             // src_t0
      R3 = DM(3, I0);               // origin
      R2 = R2 - R3;
      F2 = FLOAT R2;
      F1 = F1 - F2;                 // rel = index - (t0 - origin)
      R4 = DM(205, I0);             // base
      R5 = DM(218, I0);             // start
      R6 = DM(207, I0);             // end
      R2 = 0;
      COMP(F1, F2);
      IF GE JUMP .cl_rel;
      R2 = DM(223, I0);             // prev_valid
      R2 = PASS R2;
      IF EQ JUMP .cl_zero;
      R2 = DM(222, I0);             // prev_t0
      R2 = R2 - R3;
      F2 = FLOAT R2;
      R1 = DM(227, I0);
      F1 = F1 - F2;                 // rel = index - (prev_t0 - origin)
      R4 = DM(219, I0);
      R5 = DM(220, I0);
      R6 = DM(221, I0);
.cl_rel:                            // k = floor(rel), f = rel - k (whatever FIX rounds)
      R0 = FIX F1;
      F2 = FLOAT R0;
      COMP(F2, F1);
      IF LE JUMP .cl_floor;
      R2 = 1;
      R0 = R0 - R2;
      F2 = FLOAT R0;
.cl_floor:
      F1 = F1 - F2;                 // f
      DM(226, I0) = R1;
      R0 = R5 + R0;                 // i = start + k
      // the four samples i-1 .. i+2 all in [start, end): three aligned words hold them
      R2 = 1;
      R2 = R0 - R2;                 // i - 1
      COMP(R2, R5);
      IF LT JUMP .cl_edge;
      R3 = 2;
      R3 = R0 + R3;                 // i + 2
      COMP(R3, R6);
      IF GE JUMP .cl_edge;
      R2 = R0 + R0;                 // (not R2 + R2: digikit's width heuristic)
      R3 = 2;
      R2 = R2 - R3;
      R2 = R4 + R2;                 // the byte address of sample i - 1
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = -16;
      R1 = 2;
      R2 = R2 AND R1;               // 0: i - 1 in a word's low half, 2: its high half
      R4 = DM(0, I4);               // (loads leave the flags)
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      IF NE JUMP .cl_odd;
      R2 = ASHIFT R5 BY R3;         // y3: w1's high half
      R6 = LSHIFT R5 BY R0;
      R6 = ASHIFT R6 BY R3;         // y2: w1's low half
      R5 = ASHIFT R4 BY R3;         // y1: w0's high half
      R4 = LSHIFT R4 BY R0;
      R4 = ASHIFT R4 BY R3;         // y0: w0's low half
      JUMP .cl_float;
.cl_odd:
      R2 = LSHIFT R6 BY R0;
      R2 = ASHIFT R2 BY R3;         // y3: w2's low half
      R6 = ASHIFT R5 BY R3;         // y2: w1's high half
      R5 = LSHIFT R5 BY R0;
      R5 = ASHIFT R5 BY R3;         // y1: w1's low half
      R4 = ASHIFT R4 BY R3;         // y0: w0's high half
.cl_float:
      R1 = -15;                     // / 32768, as .cl_y
      F4 = FLOAT R4 BY R1;
      F5 = FLOAT R5 BY R1;
      F6 = FLOAT R6 BY R1;
      F2 = FLOAT R2 BY R1;
      JUMP .cl_cr;
.cl_edge:                           // near the note's edges: one at a time, 0 outside
      R1 = 1;                       // the four samples around i (.cl_y keeps R0, R4-R6)
      R1 = R0 - R1;
      CALL .cl_y;
      DM(224, I0) = R2;             // y0
      R1 = PASS R0;
      CALL .cl_y;
      DM(225, I0) = R2;             // y1
      R1 = 1;
      R1 = R0 + R1;
      CALL .cl_y;
      DM(227, I0) = R2;             // y2
      R1 = 2;
      R1 = R0 + R1;
      CALL .cl_y;                   // F2 = y3
      R4 = DM(224, I0);             // F4 y0
      R5 = DM(225, I0);             // F5 y1
      R6 = DM(227, I0);             // F6 y2
.cl_cr:
      R0 = 0x3F000000;              // c3 = 0.5 (y3 - y0) + 1.5 (y1 - y2)
      F1 = F2 - F4;
      F1 = F0 * F1;
      F3 = F5 - F6;
      R0 = 0x3FC00000;
      F3 = F0 * F3;
      F1 = F1 + F3;
      DM(227, I0) = R1;             // c3
      R0 = 0x40200000;              // c2 = y0 - 2.5 y1 + 2 y2 - 0.5 y3
      F0 = F0 * F5;
      F1 = F4 - F0;
      R0 = 0x40000000;
      F0 = F0 * F6;
      F1 = F1 + F0;
      R0 = 0x3F000000;
      F0 = F0 * F2;
      F1 = F1 - F0;                 // c2
      F3 = F6 - F4;                 // c1 = 0.5 (y2 - y0)
      R0 = 0x3F000000;
      F3 = F0 * F3;
      R0 = DM(227, I0);             // c3
      R2 = DM(226, I0);             // f
      F0 = F0 * F2;                 // c3 f
      F0 = F0 + F1;                 // + c2
      F0 = F0 * F2;
      F0 = F0 + F3;                 // + c1
      F0 = F0 * F2;
      F0 = F0 + F5;                 // + y1
      RTS;
.cl_zero:
      R0 = 0;
      RTS;

// one sample: R1 = index -> F2 (0 outside [R5, R6)); R4 = base; clobbers R2,
// R3, I4. The aligned word and a shift, as feed.asm and s3_play.asm.
.cl_y:
      R2 = DM(233, I0);             // b_llen: a looped note's points wrap across the seam
      R2 = PASS R2;
      IF EQ JUMP .cl_y_go;
      R2 = R6 - R5;                 // the loop's length (from START to END)
.cl_y_dn:
      COMP(R1, R6);
      IF LT JUMP .cl_y_up;
      R3 = R1 - R2;
      R1 = PASS R3;
      JUMP .cl_y_dn;
.cl_y_up:
      COMP(R1, R5);
      IF GE JUMP .cl_y_go;
      R3 = R1 + R2;
      R1 = PASS R3;
      JUMP .cl_y_up;
.cl_y_go:
      R2 = 0;
      COMP(R1, R5);
      IF LT JUMP .cl_y_ret;
      COMP(R1, R6);
      IF GE JUMP .cl_y_ret;
      R3 = R1 + R1;
      R3 = R3 + R4;                 // the sample's byte address
      R2 = -4;
      R2 = R3 AND R2;
      I4 = R2;
      R2 = 2;
      R2 = R3 AND R2;               // 0: the low half, 2: the high half
      R3 = DM(0, I4);               // its aligned word (a load leaves the flags)
      IF NE JUMP .cl_y_hi;
      R2 = 16;
      R3 = LSHIFT R3 BY R2;
.cl_y_hi:
      R2 = -16;
      R3 = ASHIFT R3 BY R2;
      R2 = -15;
      F2 = FLOAT R3 BY R2;          // / 32768
.cl_y_ret:
      RTS;

#ifndef GEN_WSOLA   /* (plan B: the left voice renders both channels, cc_brun) */
// void cc_tape_replay(const cc_recorder *r, float *out, int n): R4, R8, R12. A
// right voice's replay of its left voice's stereo tape (dt2gen.c gen_pair_replay):
// out[i] = the sum over sample i's slot of weight * .clean(index), at most 4
// entries, on this voice's own samples. The tape is at 0x2de9b0, 9 words a sample:
// the entry count, then (index, weight) pairs.
.GLOBAL cc_tape_replay.;
cc_tape_replay.:
      I7=MODIFY (I7,-0xF)(NW);
      DM(-11, I6) = R12;
      DM(-12, I6) = R13;
      DM(-13, I6) = R14;
      DM(-14, I6) = R15;
      DM(-3, I6) = R8;
      DM(-4, I6) = R9;
      DM(-5, I6) = R10;
      DM(-6, I6) = R11;
      R0 = I0;
      DM(-7, I6) = R0;
      R0 = I1;
      DM(-8, I6) = R0;
      R0 = I3;
      DM(-9, I6) = R0;
      R0 = I5;
      DM(-10, I6) = R0;
      I0 = R4;
      I1 = R8;                      // out, a word a sample
      I3 = 0x2DE9B0;                // the tape slot, 9 words a sample
      R9 = PASS R12;
      IF LE JUMP .tr_done;
      CALL .fcl_set;
.tr_loop:
      R0 = I3;
      I5 = R0;
      R10 = DM(0, I3);              // entries
      R0 = 4;
      COMP(R10, R0);
      IF GT R10 = PASS R0;
      R8 = 0;                       // F8: the sum
      I5=MODIFY (I5,0x1)(NW);       // the first (index, weight)
      R10 = PASS R10;
      IF LE JUMP .tr_store;
.tr_entry:
      R1 = DM(0, I5);               // F1: the index
      R6 = PASS R1;                 // the index, for .clean
      F1 = F1 - F12;                // rel = index - (t0 - origin)
      R2 = DM(236, I0);             // b_lo: 1 - b_k (dt2gen.c's plan B), else 1
      COMP(F1, F2);                 // the four samples i - 1 .. i + 2 inside the note:
      IF LT JUMP .tr_sl;            // b_lo <= rel (k = floor(rel) + b_k >= 1) ...
      COMP(F1, F15);
      IF GE JUMP .tr_sl;            // ... and rel < end - start - 2
      R0 = FIX F1;                  // k = floor(rel), f = rel - k (as .clean)
      F2 = FLOAT R0;
      COMP(F2, F1);
      IF LE JUMP .fl_t;
      R2 = 1;
      R0 = R0 - R2;
      F2 = FLOAT R0;
.fl_t:
      F7 = F1 - F2;                 // f
      R2 = R0 + R0;
      R2 = R13 + R2;                // the byte address of sample i - 1 (i = start + k)
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = -16;
      R1 = 2;
      R2 = R2 AND R1;               // 0: i - 1 in a word's low half, 2: its high half
      R4 = DM(0, I4);               // (loads leave the flags)
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      IF NE JUMP .od_t;
      R2 = ASHIFT R5 BY R3;         // y3
      R6 = LSHIFT R5 BY R0;
      R6 = ASHIFT R6 BY R3;         // y2
      R5 = ASHIFT R4 BY R3;         // y1
      R4 = LSHIFT R4 BY R0;
      R4 = ASHIFT R4 BY R3;         // y0
      JUMP .fp_t;
.od_t:
      R2 = LSHIFT R6 BY R0;
      R2 = ASHIFT R2 BY R3;         // y3
      R6 = ASHIFT R5 BY R3;         // y2
      R5 = LSHIFT R5 BY R0;
      R5 = ASHIFT R5 BY R3;         // y1
      R4 = ASHIFT R4 BY R3;         // y0
.fp_t:
      R1 = -15;                     // / 32768
      F4 = FLOAT R4 BY R1;
      F5 = FLOAT R5 BY R1;
      F6 = FLOAT R6 BY R1;
      F2 = FLOAT R2 BY R1;
// .clean's operations and order of evaluation, scheduled so that a product is
// rarely used by the very next instruction
      R0 = 0x3F000000;              // 0.5
      F1 = F2 - F4;                 // y3 - y0
      F2 = F0 * F2;                 // 0.5 y3 (y3 not needed after)
      F3 = F5 - F6;                 // y1 - y2
      F1 = F0 * F1;                 // 0.5 (y3 - y0)
      R0 = 0x3FC00000;              // 1.5
      F3 = F0 * F3;                 // 1.5 (y1 - y2)
      R0 = 0x40200000;              // 2.5
      F0 = F0 * F5;                 // 2.5 y1
      F3 = F1 + F3;                 // c3
      F1 = F4 - F0;                 // y0 - 2.5 y1
      R0 = 0x40000000;              // 2
      F0 = F0 * F6;                 // 2 y2
      F1 = F1 + F0;
      F1 = F1 - F2;                 // c2 = y0 - 2.5 y1 + 2 y2 - 0.5 y3
      F2 = F6 - F4;
      R0 = 0x3F000000;
      F2 = F0 * F2;                 // c1 = 0.5 (y2 - y0)
      F0 = F3 * F7;                 // c3 f
      F0 = F0 + F1;                 // + c2
      F0 = F0 * F7;
      F0 = F0 + F2;                 // + c1
      F0 = F0 * F7;
      F0 = F0 + F5;                 // + y1
      JUMP .tr_got;
.tr_sl:
      CALL .fcl_slow;
.tr_got:
      R2 = DM(1, I5);               // its weight
      F0 = F0 * F2;
      F8 = F0 + F8;
      I5=MODIFY (I5,0x2)(NW);
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .tr_entry;
.tr_store:
      DM(0, I1) = R8;
      I1=MODIFY (I1,0x1)(NW);
      I3=MODIFY (I3,0x9)(NW);
      R1 = 1;
      R9 = R9 - R1;
      IF NE JUMP .tr_loop;
.tr_done:
      R0 = DM(-7, I6);
      I0 = R0;
      R0 = DM(-8, I6);
      I1 = R0;
      R0 = DM(-9, I6);
      I3 = R0;
      R0 = DM(-10, I6);
      I5 = R0;
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-11, I6);
      R13 = DM(-12, I6);
      R14 = DM(-13, I6);
      R15 = DM(-14, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
#endif

// void cc_bscan(const b_scan *s): R4 = s (dt2gen.c, plan B's splice alignment).
// b_scan words: addr 0 (a byte address: an int16 sample), count 1, step 2 (bytes),
// ref 3, cost 4, points 5 (even), stride 6 (bytes: 32 or 64, so a candidate's
// points share their word half), top 7. For each of count candidates, a step
// apart from addr: the sum over the points of (sample / 32768 - ref[k])^2, into
// cost[c]; or, with top set, only the best two: costs to cost[0..1], candidate
// numbers to top[0..1] (-1: none; an equal later one does not displace). As
// dt2gen.c's C does it on the host.
.GLOBAL cc_bscan.;
cc_bscan.:
      I7=MODIFY (I7,-0x13)(NW);
      DM(-3, I6) = R8;
      DM(-4, I6) = R9;
      DM(-5, I6) = R10;
      DM(-6, I6) = R11;
      R0 = I1;
      DM(-7, I6) = R0;
      R0 = I5;
      DM(-8, I6) = R0;
      DM(-9, I6) = R12;
      DM(-16, I6) = R13;
      DM(-17, I6) = R14;
      DM(-18, I6) = R15;
      I4 = R4;
      R11 = DM(0, I4);              // addr
      R9 = DM(1, I4);               // count
      R10 = DM(2, I4);              // step
      R8 = DM(3, I4);               // ref
      R0 = DM(4, I4);               // cost
      I1 = R0;
      R1 = DM(5, I4);               // points
      R2 = DM(6, I4);               // stride
      R0 = DM(7, I4);               // top
      DM(-11, I6) = R0;
      R12 = R1 * R2 (SSI);          // the points' span in bytes
      R1 = 64;
      COMP(R2, R1);
      R1 = 0;
      IF EQ R1 = PASS R8;           // non-zero (the ref pointer): a 64-byte stride
      DM(-10, I6) = R1;
      R0 = 0x7149F2CA;              // 1e30: the best two so far
      DM(-12, I6) = R0;
      DM(-14, I6) = R0;
      R0 = -1;
      DM(-13, I6) = R0;
      DM(-15, I6) = R0;
      R6 = 0;                       // the candidate's number
      R13 = 16;
      R14 = -16;
      R15 = -15;
      R9 = PASS R9;
      IF LE JUMP .bs_out;
.bs_cand:
      R0 = PASS R11;
      R1 = -4;
      R1 = R0 AND R1;
      I4 = R1;                      // the first point's word
      R5 = R1 + R12;                // past the last
      R1 = 2;
      R1 = R0 AND R1;               // 0: the low halves, 2: the high halves
      R0 = PASS R8;
      I5 = R0;                      // ref
      R3 = 0;                       // F3: the cost
      R2 = DM(-10, I6);
      R2 = PASS R2;
      IF NE JUMP .bs_wide;
      R1 = PASS R1;
      IF NE JUMP .bs_hi;
.bs_lo:                             // two points a pass, 64 bytes apart in all
      R0 = DM(0, I4);
      R1 = DM(8, I4);
      I4=MODIFY (I4,0x10)(NW);
      R0 = LSHIFT R0 BY R13;
      R1 = LSHIFT R1 BY R13;
      R0 = ASHIFT R0 BY R14;
      R1 = ASHIFT R1 BY R14;
      F0 = FLOAT R0 BY R15;         // / 32768
      F1 = FLOAT R1 BY R15;
      R2 = DM(0, I5);
      R4 = DM(1, I5);
      I5=MODIFY (I5,0x2)(NW);
      F0 = F0 - F2;
      F1 = F1 - F4;
      F0 = F0 * F0;
      F1 = F1 * F1;
      F3 = F3 + F0;
      F3 = F3 + F1;
      R0 = I4;
      COMP(R0, R5);
      IF NE JUMP .bs_lo;
      JUMP .bs_got;
.bs_hi:                             // two points a pass, 64 bytes apart in all
      R0 = DM(0, I4);
      R1 = DM(8, I4);
      I4=MODIFY (I4,0x10)(NW);
      R0 = ASHIFT R0 BY R14;
      R1 = ASHIFT R1 BY R14;
      F0 = FLOAT R0 BY R15;         // / 32768
      F1 = FLOAT R1 BY R15;
      R2 = DM(0, I5);
      R4 = DM(1, I5);
      I5=MODIFY (I5,0x2)(NW);
      F0 = F0 - F2;
      F1 = F1 - F4;
      F0 = F0 * F0;
      F1 = F1 * F1;
      F3 = F3 + F0;
      F3 = F3 + F1;
      R0 = I4;
      COMP(R0, R5);
      IF NE JUMP .bs_hi;
      JUMP .bs_got;
.bs_wide:
      R1 = PASS R1;
      IF NE JUMP .bs_whi;
.bs_wlo:                             // two points a pass, 128 bytes apart in all
      R0 = DM(0, I4);
      R1 = DM(16, I4);
      I4=MODIFY (I4,0x20)(NW);
      R0 = LSHIFT R0 BY R13;
      R1 = LSHIFT R1 BY R13;
      R0 = ASHIFT R0 BY R14;
      R1 = ASHIFT R1 BY R14;
      F0 = FLOAT R0 BY R15;         // / 32768
      F1 = FLOAT R1 BY R15;
      R2 = DM(0, I5);
      R4 = DM(1, I5);
      I5=MODIFY (I5,0x2)(NW);
      F0 = F0 - F2;
      F1 = F1 - F4;
      F0 = F0 * F0;
      F1 = F1 * F1;
      F3 = F3 + F0;
      F3 = F3 + F1;
      R0 = I4;
      COMP(R0, R5);
      IF NE JUMP .bs_wlo;
      JUMP .bs_got;
.bs_whi:                             // two points a pass, 128 bytes apart in all
      R0 = DM(0, I4);
      R1 = DM(16, I4);
      I4=MODIFY (I4,0x20)(NW);
      R0 = ASHIFT R0 BY R14;
      R1 = ASHIFT R1 BY R14;
      F0 = FLOAT R0 BY R15;         // / 32768
      F1 = FLOAT R1 BY R15;
      R2 = DM(0, I5);
      R4 = DM(1, I5);
      I5=MODIFY (I5,0x2)(NW);
      F0 = F0 - F2;
      F1 = F1 - F4;
      F0 = F0 * F0;
      F1 = F1 * F1;
      F3 = F3 + F0;
      F3 = F3 + F1;
      R0 = I4;
      COMP(R0, R5);
      IF NE JUMP .bs_whi;
      JUMP .bs_got;
.bs_got:
      R0 = DM(-11, I6);
      R0 = PASS R0;
      IF NE JUMP .bs_top;
      DM(0, I1) = R3;
      I1=MODIFY (I1,0x1)(NW);
      JUMP .bs_next;
.bs_top:                            // keep the best two (strictly better only)
      R0 = DM(-14, I6);
      COMP(F3, F0);
      IF GE JUMP .bs_next;
      R1 = DM(-12, I6);
      COMP(F3, F1);
      IF GE JUMP .bs_second;
      DM(-14, I6) = R1;             // the best becomes the second
      R2 = DM(-13, I6);
      DM(-15, I6) = R2;
      DM(-12, I6) = R3;
      DM(-13, I6) = R6;
      JUMP .bs_next;
.bs_second:
      DM(-14, I6) = R3;
      DM(-15, I6) = R6;
.bs_next:
      R0 = 1;
      R6 = R0 + R6;
      R0 = R11 + R10;
      R11 = PASS R0;
      R1 = 1;
      R9 = R9 - R1;
      IF NE JUMP .bs_cand;
.bs_out:
      R0 = DM(-11, I6);
      R0 = PASS R0;
      IF EQ JUMP .bs_done;
      I4 = R0;
      R1 = DM(-12, I6);
      DM(0, I1) = R1;
      R1 = DM(-14, I6);
      DM(1, I1) = R1;
      R1 = DM(-13, I6);
      DM(0, I4) = R1;
      R1 = DM(-15, I6);
      DM(1, I4) = R1;
.bs_done:
      R0 = DM(-7, I6);
      I1 = R0;
      R0 = DM(-8, I6);
      I5 = R0;
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-9, I6);
      R13 = DM(-16, I6);
      R14 = DM(-17, I6);
      R15 = DM(-18, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

// void cc_bgather(uintptr_t addr, int n, float *dst): R4, R8, R12. dst[k] = the
// int16 sample at byte address addr + 32 k, / 32768 (32 bytes keep the word half).
.GLOBAL cc_bgather.;
cc_bgather.:
      R0 = -4;
      R0 = R4 AND R0;
      I4 = R0;
      R1 = 2;
      R1 = R4 AND R1;               // 0: the low halves, 2: the high halves
      R0 = R12;
      R2 = PASS R8;
      IF LE JUMP .bg_done;
      R3 = 16;
      R5 = -16;
      R6 = -15;
      R7 = I5;                      // (kept for the caller)
      I5 = R0;                      // dst
.bg_loop:
      R0 = DM(0, I4);
      I4=MODIFY (I4,0x8)(NW);
      R1 = PASS R1;
      IF NE JUMP .bg_hi;
      R0 = LSHIFT R0 BY R3;
.bg_hi:
      R0 = ASHIFT R0 BY R5;
      F0 = FLOAT R0 BY R6;
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
      R0 = 1;
      R2 = R2 - R0;
      IF NE JUMP .bg_loop;
      I5 = R7;
.bg_done:
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

#ifdef GEN_WSOLA
// float cc_balign(const cc_recorder *r, float a, float g): R4, R8, R12 -> F0.
// dt2gen.c's b_align (rev from GEN_BPASS, 0x2dee58), the same operations in the
// same order, so the same result: the reference's 16 points (cc_bgather), the
// coarse pass on a gathered grid (every 16th sample unpacked once, the coarse
// reference in R8-R15), its best two, then the refinement (cc_bscan) and the
// distance tie-break. (A SIMD coarse pass was tried: digikit's runner does not
// give the 32-bit DM(k, Ia) forms their SIMD companion, so it could not be
// checked.) At the note's edges (the
// reference partly outside) it returns -1e30 for the C's b_align. Scratch in
// L1 after GEN_ROUT (plan B leaves the tape's area free): the grid 0x2dea30
// (count + 15 words), the costs 0x2deb80, the reference 0x2dec90 (16), the scan
// 0x2decd0 (b_scan's 8 words). Frame: -3..-10 R8-R15, -11..-15 I0-I3, I5,
// -16 a, -17 g, -18 back, -19 fa, -20 b_k, -21 lo, -22 hi, -23 jg (then bj),
// -24 best, -25 best_cost, -26 topi[0], -27 topi[1], -28 count, -29 span,
// -30 the pass, -31 t, -32 the step.
.GLOBAL cc_balign.;
cc_balign.:
      I7=MODIFY (I7,-0x22)(NW);
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
      DM(-15, I6) = R0;
      I0 = R4;
      DM(-16, I6) = R8;             // a
      DM(-17, I6) = R12;            // g
      R0 = DM(0x2DEE58);            // rev
      R13 = 0;                      // back: the stretch compared, after the heads or before
      R0 = PASS R0;
      R1 = 240;
      IF NE R13 = PASS R1;
      DM(-18, I6) = R13;
      R14 = DM(234, I0);            // b_k
      DM(-20, I6) = R14;
      R1 = PASS R8;                 // ia = floor(a), fa = a - ia
      R0 = FIX F1;
      F2 = FLOAT R0;
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F2 = F1 - F2;
      DM(-19, I6) = R2;             // fa
      R0 = R14 + R0;
      R10 = R0 - R13;               // la = ia + b_k - back
      R0 = DM(207, I0);             // span = src_end - src_start - 256
      R1 = DM(218, I0);
      R0 = R0 - R1;
      R1 = 256;
      R11 = R0 - R1;
      DM(-29, I6) = R11;
      R10 = PASS R10;
      IF LT JUMP .ba_c;             // the reference partly outside the note: the C's
      COMP(R10, R11);
      IF GT JUMP .ba_c;
      R0 = DM(218, I0);             // ref: 16 samples 16 apart from la
      R0 = R10 + R0;
      R1 = R0 + R0;
      R2 = DM(205, I0);
      R4 = R2 + R1;
      R8 = 16;
      R12 = 0x2DEC90;
      R2 = I6;
      CJUMP cc_bgather. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .ba_r1 - 1;
.ba_r1:
      R1 = DM(-17, I6);             // jg = floor(g) + b_k - back
      R0 = FIX F1;
      F2 = FLOAT R0;
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      R14 = DM(-20, I6);
      R0 = R14 + R0;
      R13 = DM(-18, I6);
      R12 = R0 - R13;
      DM(-23, I6) = R12;            // jg (bj from here)
      R1 = 512;                     // lo, hi: B_REACH either side, inside the note
      R8 = R12 - R1;
      R9 = R12 + R1;
      R8 = PASS R8;
      IF LT R8 = R8 - R8;
      R11 = DM(-29, I6);
      COMP(R9, R11);
      IF GT R9 = PASS R11;
      COMP(R9, R8);
      IF LT JUMP .ba_g;             // (no candidate: g itself)
      DM(-21, I6) = R8;
      DM(-22, I6) = R9;
      R0 = R9 - R8;                 // the coarse candidates: every 16th offset
      R1 = -4;
      R0 = LSHIFT R0 BY R1;
      R1 = 1;
      R15 = R0 + R1;
      DM(-28, I6) = R15;            // count
      R0 = DM(218, I0);             // the grid: count + 15 samples 16 apart from lo
      R0 = R8 + R0;
      R1 = R0 + R0;
      R2 = DM(205, I0);
      R4 = R2 + R1;
      R1 = 15;
      R8 = R15 + R1;
      R12 = 0x2DEA30;
      R2 = I6;
      CJUMP cc_bgather. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .ba_r2 - 1;
.ba_r2:
      I4 = 0x2DEC90;                // the coarse reference: every other point
      R8 = DM(0, I4);
      R9 = DM(2, I4);
      R10 = DM(4, I4);
      R11 = DM(6, I4);
      R12 = DM(8, I4);
      R13 = DM(10, I4);
      R14 = DM(12, I4);
      R15 = DM(14, I4);
      R0 = DM(-28, I6);             // the grid pointer's end: count words on
      R1 = R0 + R0;
      R0 = R1 + R1;
      R6 = 0x2DEA30;
      R6 = R0 + R6;
      I4 = 0x2DEA30;
      I5 = 0x2DEB80;
.bc_lp:                             // cost[c] = sum over p of (grid[c + 2p] - ref[2p])^2
      R0 = DM(0, I4);
      R1 = DM(2, I4);
      R2 = DM(4, I4);
      R4 = DM(6, I4);
      F0 = F0 - F8;
      F1 = F1 - F9;
      F2 = F2 - F10;
      F4 = F4 - F11;
      F3 = F0 * F0;                 // (cc_bscan's 0 + e0 e0)
      F1 = F1 * F1;
      F2 = F2 * F2;
      F4 = F4 * F4;
      R0 = DM(8, I4);
      F3 = F3 + F1;
      R1 = DM(10, I4);
      F3 = F3 + F2;
      R2 = DM(12, I4);
      F3 = F3 + F4;
      R4 = DM(14, I4);
      F0 = F0 - F12;
      F1 = F1 - F13;
      F2 = F2 - F14;
      F4 = F4 - F15;
      F0 = F0 * F0;
      F1 = F1 * F1;
      F2 = F2 * F2;
      F4 = F4 * F4;
      F3 = F3 + F0;
      F3 = F3 + F1;
      F3 = F3 + F2;
      F3 = F3 + F4;
      DM(0, I5) = R3;
      I4=MODIFY (I4,0x1)(NW);
      I5=MODIFY (I5,0x1)(NW);
      R0 = I4;
      COMP(R0, R6);
      IF NE JUMP .bc_lp;
      R8 = 0x7149F2CA;              // the best two (cc_bscan's top): 1e30, none
      R9 = PASS R8;
      R10 = -1;
      R11 = -1;
      R12 = 0;
      R15 = DM(-28, I6);
      I5 = 0x2DEB80;
.bt_lp:
      R0 = DM(0, I5);
      I5=MODIFY (I5,0x1)(NW);
      COMP(F0, F9);
      IF GE JUMP .bt_nx;
      COMP(F0, F8);
      IF GE JUMP .bt_2;
      R9 = PASS R8;
      R11 = PASS R10;
      R8 = PASS R0;
      R10 = PASS R12;
      JUMP .bt_nx;
.bt_2:
      R9 = PASS R0;
      R11 = PASS R12;
.bt_nx:
      R1 = 1;
      R12 = R1 + R12;
      COMP(R12, R15);
      IF LT JUMP .bt_lp;
      DM(-26, I6) = R10;            // topi
      DM(-27, I6) = R11;
      R0 = DM(-17, I6);             // best = g, best_cost = 1e30 (bj = jg already)
      DM(-24, I6) = R0;
      R0 = 0x7149F2CA;
      DM(-25, I6) = R0;
      I4 = 0x2DECD0;                // the scan: the full reference, its 16 points
      R0 = 0x2DEC90;
      DM(3, I4) = R0;
      R0 = 0x2DEB80;
      DM(4, I4) = R0;
      R0 = 16;
      DM(5, I4) = R0;
      R0 = 32;
      DM(6, I4) = R0;
      R0 = 0;
      DM(7, I4) = R0;
      DM(-30, I6) = R0;             // pass 0
      DM(-31, I6) = R0;             // t 0
// the refinement: pass 0 every 4th offset within 12 of each of the best two,
// pass 1 each offset within 3 of the best so far; ties to the nearest
.br_t:
      R0 = DM(-30, I6);
      R0 = PASS R0;
      IF NE JUMP .br_p1;
      R1 = DM(-31, I6);             // pass 0: centre = lo + topi[t] * 16 (none: skip)
      R2 = DM(-26, I6);
      R1 = PASS R1;
      IF EQ JUMP .br_c0;
      R2 = DM(-27, I6);
.br_c0:
      R2 = PASS R2;
      IF LT JUMP .br_next;
      R0 = 4;
      R2 = LSHIFT R2 BY R0;
      R0 = DM(-21, I6);
      R2 = R0 + R2;                 // centre
      R5 = 4;                       // step
      R6 = 12;                      // reach
      JUMP .br_c;
.br_p1:
      R2 = DM(-23, I6);             // pass 1: centre = bj
      R5 = 1;
      R6 = 3;
.br_c:
      R8 = R2 - R6;                 // j0, j1
      R9 = R2 + R6;
      R10 = DM(-21, I6);            // lo
      R11 = DM(-22, I6);            // hi
.br_w0:
      COMP(R8, R10);
      IF GE JUMP .br_w1;
      R8 = R5 + R8;
      JUMP .br_w0;
.br_w1:
      COMP(R9, R11);
      IF LE JUMP .br_w2;
      R9 = R9 - R5;
      JUMP .br_w1;
.br_w2:
      COMP(R9, R8);
      IF LT JUMP .br_next;
      R0 = R9 - R8;                 // count = ((j1 - j0) >> shift) + 1
      R1 = -2;
      R2 = 4;
      COMP(R5, R2);
      IF NE R1 = R1 - R1;
      R0 = LSHIFT R0 BY R1;
      R1 = 1;
      R12 = R0 + R1;
      I4 = 0x2DECD0;
      R0 = DM(218, I0);             // addr = src + 2 (src_start + j0)
      R0 = R8 + R0;
      R1 = R0 + R0;
      R2 = DM(205, I0);
      R2 = R1 + R2;
      DM(0, I4) = R2;
      DM(1, I4) = R12;
      R0 = R5 + R5;
      DM(2, I4) = R0;               // step, bytes
      DM(-28, I6) = R12;            // (this scan's count)
      DM(-32, I6) = R5;             // (and step: cc_bscan uses R0-R7)
      R4 = 0x2DECD0;
      R2 = I6;
      CJUMP cc_bscan. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .ba_r3 - 1;
.ba_r3:
      R5 = DM(-32, I6);
      R12 = DM(-28, I6);            // the candidates: x = cost + 1e-5 |dist|
      R13 = DM(-18, I6);            // back
      R14 = DM(-20, I6);            // b_k
      R15 = 0;                      // c
      I5 = 0x2DEB80;
.bx_c:
      R0 = R15 * R5 (SSI);
      R0 = R8 + R0;                 // j = j0 + c * step
      R1 = R13 + R0;
      R1 = R1 - R14;
      F1 = FLOAT R1;                // (float)(j + back - b_k)
      R2 = DM(-19, I6);
      F1 = F1 + F2;                 // + fa
      R2 = DM(-17, I6);
      F2 = F1 - F2;                 // - g
      R3 = 0;
      COMP(F2, F3);
      IF LT F2 = -F2;               // dist
      R3 = 0x3727C5AC;              // 1e-5
      F2 = F3 * F2;
      R3 = DM(0, I5);
      I5=MODIFY (I5,0x1)(NW);
      F3 = F3 + F2;                 // x = cost[c] + 1e-5 dist
      R4 = DM(-25, I6);
      COMP(F3, F4);
      IF GE JUMP .bx_n;
      DM(-25, I6) = R3;             // best_cost, best, bj
      DM(-24, I6) = R1;
      DM(-23, I6) = R0;
.bx_n:
      R0 = 1;
      R15 = R0 + R15;
      COMP(R15, R12);
      IF LT JUMP .bx_c;
.br_next:
      R0 = DM(-30, I6);             // the next t, or pass
      R1 = DM(-31, I6);
      R0 = PASS R0;
      IF NE JUMP .ba_done;          // (pass 1 has one t)
      R2 = 1;
      R1 = R2 + R1;
      DM(-31, I6) = R1;
      R2 = 2;
      COMP(R1, R2);
      IF LT JUMP .br_t;
      R0 = 1;
      DM(-30, I6) = R0;
      JUMP .br_t;
.ba_done:
      R0 = DM(-24, I6);             // best
      JUMP .ba_ret;
.ba_g:
      R0 = DM(-17, I6);             // g
      JUMP .ba_ret;
.ba_c:
      R0 = 0xF149F2CA;              // -1e30: the C's b_align
.ba_ret:
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-7, I6);
      R13 = DM(-8, I6);
      R14 = DM(-9, I6);
      R15 = DM(-10, I6);
      R1 = DM(-11, I6);
      I0 = R1;
      R1 = DM(-12, I6);
      I1 = R1;
      R1 = DM(-13, I6);
      I2 = R1;
      R1 = DM(-14, I6);
      I3 = R1;
      R1 = DM(-15, I6);
      I5 = R1;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
#endif

// float cc_clean_read(const cc_recorder *r, float index): R4, R8 -> R0. For the
// C fallback's ph_sample (capicola.c) and plan B's event samples (dt2gen.c
// b_step): .fcl, as rec_clean_read (its fast path for plan B's b_k).
.GLOBAL cc_clean_read.;
cc_clean_read.:
      I7=MODIFY (I7,-0x7)(NW);
      DM(-3, I6) = R12;
      DM(-4, I6) = R13;
      DM(-5, I6) = R14;
      DM(-6, I6) = R15;
      R0 = I0;
      DM(-7, I6) = R0;
      I0 = R4;
      CALL .fcl_set;
      R1 = PASS R8;
      CALL .fcl;
      R12 = DM(-3, I6);
      R13 = DM(-4, I6);
      R14 = DM(-5, I6);
      R15 = DM(-6, I6);
      R1 = DM(-7, I6);
      I0 = R1;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

#ifdef GEN_WSOLA
// void cc_wcopy(float *dst, const float *src, int n): R4, R8, R12 (n > 0)
.GLOBAL cc_wcopy.;
cc_wcopy.:
      I7=MODIFY (I7,-0x3)(NW);
      R0 = I5;
      DM(-3, I6) = R0;
      I5 = R4;
      I4 = R8;
      R1 = 1;
.wc_lp:
      R0 = DM(0, I4);
      I4=MODIFY (I4,0x1)(NW);
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
      R12 = R12 - R1;
      IF GT JUMP .wc_lp;
      R0 = DM(-3, I6);
      I5 = R0;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

// void cc_brun(cc_recorder *r, float *out, int m): R4, R8, R12 (dt2gen.c, plan B):
// m samples between events: actual's clean read (.fcl), or (splicing) temp's and
// actual's crossfaded by smooth_step(splice_phase); with GEN_BPASS's rr (0x2dee50)
// the right channel's too, at the same positions, to its outr (0x2dee54); the ideal head
// on by m steps at once. The same operations in the same order as dt2gen.c's C.
// Registers: F8 actual.index, F9 actual.speed, R10 samples left, R11 rr (0:
// none), R12-R15 .fcl's (R14 the right samples' offset from the left's, bytes),
// I0 the recorder read (I3 r), I1 out, I2 granule[0], I5 the right channel's out.
.GLOBAL cc_brun.;
cc_brun.:
      I7=MODIFY (I7,-0x1F)(NW);
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
      DM(-15, I6) = R0;             // -16 in, -17 w, -18 1 - w, -19 the phase's step,
                                    // -21 .bd's right read, -22/-23 its scratch, -24 the right in,
                                    // -25 r, -26/-27 .bd's right words, -28..-31 M0-M3
      DM(-20, I6) = R12;            // m
      R0 = M0;                      // M0-M3 (the firmware's callers keep M2, M3): kept, and
      DM(-28, I6) = R0;             // meanwhile the SIMD read's constants (gen_bd.py)
      R0 = M1;
      DM(-29, I6) = R0;
      R0 = M2;
      DM(-30, I6) = R0;
      R0 = M3;
      DM(-31, I6) = R0;
      M0 = 16;
      M1 = 0xFFFF0000;
      M2 = -31;
      M3 = 0x3F000000;              // 0.5
      I0 = R4;
      DM(-25, I6) = R4;             // r (the slow path's I0 back)
      R0 = 96;
      R0 = R4 + R0;
      I2 = R0;                      // granule[0]
      I1 = R8;                      // out
      R10 = PASS R12;
      IF LE JUMP .bu_ret;
      R0 = DM(0x2DEE54);
      I5 = R0;                      // the right channel's out
      R11 = DM(0x2DEE50);           // its recorder
      CALL .fcl_set;                // R13, F15 for .bd (R12: 0)
      R14 = 0;
      R11 = PASS R11;
      IF EQ JUMP .bu_go;
      I4 = R11;
      R0 = DM(205, I4);             // the right samples' base
      R1 = DM(205, I0);
      R14 = R0 - R1;
// ---- gen_bd.py: begin loops (generated: edit work/gen_bd.py)
.bu_go:
      R8 = DM(17, I2);              // actual.index
      R9 = DM(19, I2);              // actual.speed
      R1 = 2;
      R1 = R14 AND R1;
      IF NE JUMP .bx_go;            // the right samples across a word's halves: SISD reads
      R0 = DM(57, I2);              // splicing
      R0 = PASS R0;
      IF NE JUMP .bss_set;
.bn_lp:                            // not splicing: actual's read
      R1 = PASS R8;
      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_bn;
      COMP(F1, F15);
      IF GE JUMP .sl_bn;
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
      R11 = PASS R11;
      IF EQ JUMP .mo_bn;
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
      IF NE JUMP .so_bn;           // (decided in SISD: no MODE1 change in a delay slot)
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = R5 AND R3;               // y3
      F2 = FLOAT R2 BY R1;
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .sp_bn (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.so_bn:
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.sp_bn:
      F1 = F2 - F4;                 // y3 - y0
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
      BIT CLR MODE1 0x200000;       // SISD again
      NOP;
      R1 = S0;                      // the right read (PEy's F0)
      R12 = 0;                      // (memory three instructions after the change: MODE1's latency)
      DM(0, I1) = R0;               // both samples out, and the next (.bn_got, .bn_nx)
      DM(0, I5) = R1;
      I1=MODIFY (I1,0x1)(NW);
      I5=MODIFY (I5,0x1)(NW);
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .bn_lp;
      JUMP .bu_end;
.mo_bn:                            // mono: the left channel alone, SISD
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bnm (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bnm (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bnm:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bnm:
      F1 = F2 - F4;                 // y3 - y0
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
      R12 = 0;
      JUMP .bn_got;
.rt_bn:
      R12 = 0;
      JUMP .bn_got;
.sl_bn:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_bn;
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      JUMP .bn_got;
.bn_got:
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .bn_nx;
      R0 = DM(-21, I6);
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.bn_nx:
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .bn_lp;
      JUMP .bu_end;
.bss_set:
      R2 = DM(55, I2);              // adaptive_increment
      R3 = DM(49, I2);              // pitch
      F2 = F2 * F3;
      DM(-19, I6) = R2;
.bss_lp:                            // splicing: temp's and actual's reads, mixed
      R1 = DM(27, I2);              // temp.index
      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_bs1;
      COMP(F1, F15);
      IF GE JUMP .sl_bs1;
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
      R11 = PASS R11;
      IF EQ JUMP .mo_bs1;
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
      IF NE JUMP .so_bs1;           // (decided in SISD: no MODE1 change in a delay slot)
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = R5 AND R3;               // y3
      F2 = FLOAT R2 BY R1;
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .sp_bs1 (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.so_bs1:
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.sp_bs1:
      F1 = F2 - F4;                 // y3 - y0
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
      BIT CLR MODE1 0x200000;       // SISD again
      NOP;
      R1 = S0;                      // the right read (PEy's F0)
      R12 = 0;                      // (memory three instructions after the change: MODE1's latency)
      DM(-21, I6) = R1;
      JUMP .bss_g1;
.mo_bs1:                            // mono: the left channel alone, SISD
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bs1m (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bs1m (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bs1m:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bs1m:
      F1 = F2 - F4;                 // y3 - y0
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
      R12 = 0;
      JUMP .bss_g1;
.rt_bs1:
      R12 = 0;
      JUMP .bss_g1;
.sl_bs1:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_bs1;
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      JUMP .bss_g1;
.bss_g1:
      DM(-16, I6) = R0;             // in
      R0 = DM(-21, I6);
      DM(-24, I6) = R0;             // the right channel's in
      R1 = PASS R8;
      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_bs2;
      COMP(F1, F15);
      IF GE JUMP .sl_bs2;
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
      R11 = PASS R11;
      IF EQ JUMP .mo_bs2;
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
      IF NE JUMP .so_bs2;           // (decided in SISD: no MODE1 change in a delay slot)
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = R5 AND R3;               // y3
      F2 = FLOAT R2 BY R1;
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .sp_bs2 (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.so_bs2:
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.sp_bs2:
      F1 = F2 - F4;                 // y3 - y0
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
      BIT CLR MODE1 0x200000;       // SISD again
      NOP;
      R1 = S0;                      // the right read (PEy's F0)
      R12 = 0;                      // (memory three instructions after the change: MODE1's latency)
      DM(-21, I6) = R1;
      JUMP .bss_g2;
.mo_bs2:                            // mono: the left channel alone, SISD
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bs2m (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bs2m (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bs2m:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bs2m:
      F1 = F2 - F4;                 // y3 - y0
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
      R12 = 0;
      JUMP .bss_g2;
.rt_bs2:
      R12 = 0;
      JUMP .bss_g2;
.sl_bs2:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_bs2;
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      JUMP .bss_g2;
.bss_g2:
      R1 = DM(56, I2);              // w = smooth_step(splice_phase)
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
      IF EQ JUMP .bss_nx;
      R7 = DM(-24, I6);             // the right channel's in
      R0 = DM(-21, I6);             // and o
      R2 = DM(-17, I6);
      R4 = DM(-18, I6);
      F3 = F7 * F2;
      F4 = F0 * F4;
      F0 = F3 + F4;
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.bss_nx:
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
      IF NE JUMP .bss_lp;
      DM(29, I2) = R9;              // temp.speed = actual.speed
      JUMP .bu_end;
.bx_go:
      R0 = DM(57, I2);
      R0 = PASS R0;
      IF NE JUMP .bxs_set;
.bxn_lp:                            // not splicing: actual's read
      R1 = PASS R8;
      CALL .bd;
.bxn_got:
      DM(0, I1) = R0;
      I1=MODIFY (I1,0x1)(NW);
      R11 = PASS R11;
      IF EQ JUMP .bxn_nx;
      R0 = DM(-21, I6);
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.bxn_nx:
      F8 = F8 + F9;                 // actual.index += actual.speed
      R1 = 1;
      R10 = R10 - R1;
      IF NE JUMP .bxn_lp;
      JUMP .bu_end;
.bxs_set:
      R2 = DM(55, I2);              // adaptive_increment
      R3 = DM(49, I2);              // pitch
      F2 = F2 * F3;
      DM(-19, I6) = R2;
.bxs_lp:                            // splicing: temp's and actual's reads, mixed
      R1 = DM(27, I2);              // temp.index
      CALL .bd;
      DM(-16, I6) = R0;             // in
      R0 = DM(-21, I6);
      DM(-24, I6) = R0;             // the right channel's in
      R1 = PASS R8;
      CALL .bd;                  // F0 = o
      R1 = DM(56, I2);              // w = smooth_step(splice_phase)
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
      IF EQ JUMP .bxs_nx;
      R7 = DM(-24, I6);             // the right channel's in
      R0 = DM(-21, I6);             // and o
      R2 = DM(-17, I6);
      R4 = DM(-18, I6);
      F3 = F7 * F2;
      F4 = F0 * F4;
      F0 = F3 + F4;
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
.bxs_nx:
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
      IF NE JUMP .bxs_lp;
      DM(29, I2) = R9;              // temp.speed = actual.speed
      JUMP .bu_end;
// ---- gen_bd.py: end loops (generated: edit work/gen_bd.py)
.bu_end:
      DM(17, I2) = R8;              // actual.index
      R2 = DM(-20, I6);
      F2 = FLOAT R2;                // m
      R0 = DM(7, I2);               // ideal.index += ideal.speed * m
      R1 = DM(9, I2);
      F1 = F1 * F2;
      F0 = F0 + F1;
      DM(7, I2) = R0;
.bu_ret:
      R0 = DM(-28, I6);
      M0 = R0;
      R0 = DM(-29, I6);
      M1 = R0;
      R0 = DM(-30, I6);
      M2 = R0;
      R0 = DM(-31, I6);
      M3 = R0;
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-7, I6);
      R13 = DM(-8, I6);
      R14 = DM(-9, I6);
      R15 = DM(-10, I6);
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
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
// ---- cc_bfast2 / cc_bfast3 (rec, out, n): R4, R8, R12 -> R0. dt2gen.c's plan B
// for an ordinary block of a left voice (machine 2 STRETCH, 3 REPITCH), in place
// of cc_dt2_stretch/_repitch -> gen_run -> gen_wsola: R0 = 1 when served, else 0
// with nothing changed, for the C (dt2entry.asm). Served only when the C would do
// exactly this: a voice gen_run knows (its magic as gen_run last wrote it to
// 0x2dee60), active, CAPI's blend 0 (GEN_BLEND_ZERO: always), no trig (playing, plan B, PHASE as written,
// no declick due), its TUNE's pitch cached (g->ipos/frac), no loop wrap or rebase
// due, and a right channel either absent or mapped as last block. Then gen_wsola's
// stores, one cc_brun when b_count's run is the whole block (its divisions as
// conservative products), else cc_bloop (gen_wsola's loop), REPITCH's level, the declicks' last samples, PHASE (and
// the right record's), the note's end, and diag_account's figures (the C,
// cc_diag_acc, at a frame's first voice). Word offsets: dt2gen.c GEN_AT.
// Frame: -3..-10 R8-R15, -11 I0, -12 I1, -13 I2, -14 I3, -15 I5, -16 t0,
// -17 the budget to store, -18 len, -19 b_llen (float), -20 F4 ideal.speed,
// -21 F5 actual.speed, -22 events (cc_bloop). Registers: R8 v, R9 n, R10 out, R11 machine, R13 rev,
// R14 loop, R15 the right recorder (0: none), R12 the right voice's state;
// I0 r, I1 rec, I2 q (granule[0]), I3 g, I5 the right record.
.GLOBAL cc_bfast2.;
cc_bfast2.:
      R0 = 2;
      JUMP .bf_go;
.GLOBAL cc_bfast3.;
cc_bfast3.:
      R0 = 3;
.bf_go:
      I7=MODIFY (I7,-0x18)(NW);
      DM(-3, I6) = R8;
      DM(-4, I6) = R9;
      DM(-5, I6) = R10;
      DM(-6, I6) = R11;
      DM(-7, I6) = R12;
      DM(-8, I6) = R13;
      DM(-9, I6) = R14;
      DM(-10, I6) = R15;
      R1 = I0;
      DM(-11, I6) = R1;
      R1 = I1;
      DM(-12, I6) = R1;
      R1 = I2;
      DM(-13, I6) = R1;
      R1 = I3;
      DM(-14, I6) = R1;
      R1 = I5;
      DM(-15, I6) = R1;
      R1 = EMUCLK;
      DM(-16, I6) = R1;             // t0
      R11 = PASS R0;                // machine
      R10 = PASS R8;                // out
      R9 = PASS R12;                // n
      I1 = R4;                      // rec
      R0 = 0x2412CC;                // v, as gen_run
      R0 = R4 - R0;
      IF LT JUMP .bf_no;
      R1 = 0x3B00;                  // 32 voice records
      COMP(R0, R1);
      IF GE JUMP .bf_no;
      R2 = 2222;
      R2 = R0 * R2 (SSI);
      R3 = -20;
      R8 = LSHIFT R2 BY R3;
      R2 = 0x1D8;
      R2 = R8 * R2 (SSI);
      COMP(R2, R0);
      IF NE JUMP .bf_no;
      R2 = 1;
      R2 = R8 AND R2;
      IF NE JUMP .bf_no;            // a left voice (record: its right channel too)
      R9 = PASS R9;
      IF LE JUMP .bf_no;
      R0 = 3;                       // the shared generator's: the DSP's machine type (3, 4 GRID, 5 SLICE), as gen_run
      COMP(R11, R0);
      IF NE JUMP .bf_m;
      R2 = 0xDC;
      R2 = R8 * R2 (SSI);
      R3 = 0x250738;                // the parameter record's word 0x13
      R2 = R3 + R2;
      I4 = R2;
      R0 = DM(0, I4);
      R1 = 4;
      COMP(R0, R1);
      IF EQ R11 = PASS R0;
      R1 = 5;
      COMP(R0, R1);
      IF EQ R11 = PASS R0;
.bf_m:
      R2 = 10;
      R2 = LSHIFT R8 BY R2;
      R3 = 0x20080000;
      R2 = R3 + R2;
      I3 = R2;                      // g = VOICE_STATE(v)
      R3 = 72;
      R3 = R2 + R3;
      I0 = R3;                      // r = &g->rec
      R4 = 96;
      R4 = R3 + R4;
      I2 = R4;                      // q = &r->granule[0]
      R2 = 0x1D8;
      R3 = I1;
      R2 = R3 + R2;
      I5 = R2;                      // the right voice's record
// gen_run: an active voice it knows, at blend 0
      R0 = DM(0, I1);
      R0 = PASS R0;
      IF EQ JUMP .bf_no;
      R0 = DM(0x6E, I1);
      R1 = 0xFF;
      R0 = R0 AND R1;
      IF EQ JUMP .bf_no;
      R0 = DM(0, I3);
      R1 = DM(0x2DEE60);
      COMP(R0, R1);
      IF NE JUMP .bf_no;
#if defined(GEN_BLEND_ZERO)   /* (build_gen.sh's default: CAPI is on/off, on = blend 0) */
#elif defined(GEN_BLEND_FIXED)
      JUMP .bf_no;                  // (a fixed blend other than 0: Capicola's keyframes, the C)
#else
      R2 = 0xDC;
      R2 = R8 * R2 (SSI);
      R3 = 0x2506EC;
      R2 = R3 + R2;
      I4 = R2;                      // the parameter record
      R0 = DM(4, I4);               // CAPI's on/off: off, blend 0
      R1 = 0;
      COMP(F0, F1);
      IF EQ JUMP .bf_b0;
      R2 = DM(0x261CA4);            // the receive page's CAPI byte: 0 for blend 0
      R3 = 1;
      R2 = R2 AND R3;
      R3 = 12;
      R2 = LSHIFT R2 BY R3;
      R3 = 0x264220;
      R2 = R3 + R2;
      R3 = -1;
      R3 = LSHIFT R8 BY R3;
      R4 = 0x60;
      R3 = R3 * R4 (SSI);
      R2 = R3 + R2;
      R3 = 0xDC;
      R2 = R3 + R2;
      I4 = R2;
      R2 = -24;
      R0 = DM(0, I4);
      R0 = LSHIFT R0 BY R2;
      R0 = PASS R0;
      IF NE JUMP .bf_no;
#endif
.bf_b0:
// gen_wsola: no trig, no declick due
      R0 = DM(1, I3);               // playing
      R0 = PASS R0;
      IF EQ JUMP .bf_no;
      R0 = DM(17, I3);              // bmode
      R0 = PASS R0;
      IF EQ JUMP .bf_no;
      R0 = DM(0x6C, I1);
      R1 = DM(2, I3);
      COMP(R0, R1);
      IF NE JUMP .bf_no;
      R0 = DM(0x6D, I1);
      R1 = DM(3, I3);
      COMP(R0, R1);
      IF NE JUMP .bf_no;
      R0 = DM(16, I3);              // retrig
      R0 = PASS R0;
      IF NE JUMP .bf_no;
      R0 = DM(0x6E, I1);
      R1 = -24;
      R13 = LSHIFT R0 BY R1;        // rev: byte +0x1bb
      R0 = DM(0x6F, I1);
      R1 = 0xFF;
      R14 = R0 AND R1;              // loop: byte +0x1bc
// the speeds: F6 stretch, F7 pitch
      R0 = 3;
      COMP(R11, R0);
      IF LT JUMP .bf_st;
      IF GT JUMP .bf_sl;
      R0 = DM(0x6B, I1);            // REPITCH: 2 * STEP = hi * 4 + lo / 2^30
      F0 = FLOAT R0;
      R1 = 0x40800000;
      F0 = F0 * F1;
      R1 = DM(0x6A, I1);
      R2 = -8;
      R1 = LSHIFT R1 BY R2;
      F1 = FLOAT R1;
      R2 = 0x34800000;              // 1 / 4194304
      F1 = F1 * F2;
      F0 = F0 + F1;
      R2 = 0;
      COMP(F0, F2);
      IF LT F0 = -F0;
      F6 = PASS F0;
      F7 = PASS F0;
      JUMP .bf_sp;
.bf_sl:
// GRID and SLICE (dt2gen.c gen_run, gen_slice_speed, gen_slice_mode): an empty
// slice to the C; the stretch = w62 * BPM * (1 / (240 * 48000)) * 2^-bars, in
// that order; the pitch the same (slot 2 at 1: REPITCH's way) or TUNE's
      R1 = DM(0x69, I1);            // END - START (whole samples) under 4: the C
      R0 = R1 + R1;
      R1 = DM(0x68, I1);
      R2 = -31;
      R1 = LSHIFT R1 BY R2;
      R0 = R1 + R0;
      R1 = DM(0x67, I1);
      R3 = R1 + R1;
      R1 = DM(0x66, I1);
      R1 = LSHIFT R1 BY R2;
      R3 = R1 + R3;
      R0 = R0 - R3;
      R1 = 4;
      COMP(R0, R1);
      IF LT JUMP .bf_no;
      R2 = DM(0x261CA4);            // this frame's receive page, the track's words
      R3 = 1;
      R2 = R2 AND R3;
      R3 = 12;
      R2 = LSHIFT R2 BY R3;
      R3 = 0x264220;
      R2 = R3 + R2;
      R3 = -1;
      R3 = LSHIFT R8 BY R3;
      R4 = 0x60;
      R3 = R3 * R4 (SSI);
      R2 = R3 + R2;
      R3 = 0xE8;
      R3 = R2 + R3;
      I4 = R3;
      R3 = -24;
      R0 = DM(0, I4);
      R0 = LSHIFT R0 BY R3;         // b: slot 6's value
#ifdef GEN_SLICE_MODE
      R5 = GEN_SLICE_MODE;          // a test image: the way fixed,
      R1 = GEN_SLICE_BARS;          // ... and SLICE's bars (GRID's from its grid)
      R4 = 4;
      COMP(R11, R4);
      IF NE R0 = PASS R1;
#else
      R3 = 0xDC;
      R3 = R2 + R3;
      I4 = R3;
      R3 = -24;
      R5 = DM(0, I4);
      R5 = LSHIFT R5 BY R3;         // the way: slot 2's value
#endif
      R1 = 4;
      COMP(R11, R1);
      R1 = 2;
      IF EQ R0 = R0 - R1;           // GRID: 4 << grid slices, a 16th each
      R1 = 5;                       // (BARS 0..5: 1..32 bars)
      COMP(R0, R1);
      IF GT R0 = PASS R1;
      R1 = 127;
      R0 = R1 - R0;
      R1 = 23;
      R0 = LSHIFT R0 BY R1;         // F0 = 2^-b
      R1 = DM(0x62, I1);
      F1 = FLOAT R1;
      R2 = DM(0x252D50);            // the tempo, BPM
      F6 = F1 * F2;
      R2 = 0x33BA69DC;              // 1 / (240 * 48000)
      F6 = F6 * F2;
      F6 = F6 * F0;
      F7 = PASS F6;
      R1 = 2;
      COMP(R5, R1);
      IF LT JUMP .bf_sp;
      R2 = 0xDC;                    // the STRETCH way: TUNE's pitch as cached
      R2 = R8 * R2 (SSI);
      R3 = 0x2506EC;
      R2 = R3 + R2;
      I4 = R2;
      JUMP .bf_tn;
.bf_st:
      R2 = 0xDC;                    // STRETCH: w72; TUNE's pitch as cached
      R2 = R8 * R2 (SSI);
      R3 = 0x2506EC;
      R2 = R3 + R2;
      I4 = R2;
      R6 = DM(0x72, I1);
.bf_tn:
      R0 = DM(0, I4);               // the TUNE word
      R1 = DM(10, I3);              // g->ipos: the one cached
      COMP(R0, R1);
      IF NE JUMP .bf_no;
      R7 = DM(12, I3);              // g->frac: its pitch
.bf_sp:
      F4 = PASS F6;                 // ideal.speed
      F5 = PASS F7;                 // actual.speed
      R13 = PASS R13;
      IF NE F4 = -F6;
      R13 = PASS R13;
      IF NE F5 = -F7;
      DM(-20, I6) = R4;
      DM(-21, I6) = R5;
// the frame's budget (stored later): B_SEARCHES at a new frame
      R0 = DM(0x2DEF48);            // GEN_FRAME->last_v
      R1 = DM(0x2DEF4C);            // ->budget
      COMP(R8, R0);
      R2 = 1;
      IF LE R1 = PASS R2;
      DM(-17, I6) = R1;
// the mapping: len, b_llen; no loop wrap, no rebase due
      R0 = DM(207, I0);             // src_end
      R1 = DM(218, I0);             // src_start
      R0 = R0 - R1;
      DM(-18, I6) = R0;             // len
      F1 = FLOAT R0;
      R2 = 0;
      R14 = PASS R14;
      IF NE R2 = PASS R1;
      DM(-19, I6) = R2;             // b_llen
      R3 = DM(234, I0);             // b_k
      R1 = DM(17, I2);              // actual.index
      R14 = PASS R14;
      IF EQ JUMP .bf_rb;
      R2 = 1;
      COMP(R0, R2);
      IF LT JUMP .bf_rb;            // (len < 1: no wrap)
      R13 = PASS R13;
      IF NE JUMP .bf_wr;
      R2 = R0 - R3;                 // forward: actual.index < len - b_k
      F2 = FLOAT R2;
      COMP(F1, F2);
      IF GE JUMP .bf_no;
      JUMP .bf_rb;
.bf_wr:
      R2 = 0;                       // reversed: actual.index >= -b_k
      R2 = R2 - R3;
      F2 = FLOAT R2;
      COMP(F1, F2);
      IF LT JUMP .bf_no;
.bf_rb:
      R0 = DM(7, I2);               // ideal.index
      R1 = DM(17, I2);              // actual.index
      R2 = DM(27, I2);              // temp.index
      R3 = DM(57, I2);              // splicing
      R4 = 0x46000000;              // 8192: no rebase while any head is below
      R5 = 0;
      COMP(F0, F4);
      IF LT R5 = PASS R4;
      COMP(F1, F4);
      IF LT R5 = PASS R4;
      R3 = PASS R3;
      IF EQ JUMP .bf_r1;
      COMP(F2, F4);
      IF LT R5 = PASS R4;
.bf_r1:
      R5 = PASS R5;
      IF EQ JUMP .bf_no;
      R4 = 0xC6000000;              // -8192: nor while any is above
      R5 = 0;
      COMP(F0, F4);
      IF GT R5 = PASS R4;
      COMP(F1, F4);
      IF GT R5 = PASS R4;
      R3 = PASS R3;
      IF EQ JUMP .bf_r2;
      COMP(F2, F4);
      IF GT R5 = PASS R4;
.bf_r2:
      R5 = PASS R5;
      IF EQ JUMP .bf_no;
// b_count: no event in the block (room > (n + 3) * the closing rate), or else
// cc_bloop (dt2gen.c, gen_wsola's own loop) renders the block
      R4 = DM(-20, I6);             // F4 ideal.speed
      R5 = DM(-21, I6);             // F5 actual.speed
      R6 = 3;
      R6 = R9 + R6;
      F6 = FLOAT R6;                // n + 3
      R3 = PASS R3;
      IF NE JUMP .bf_cs;
      R2 = DM(-17, I6);             // the budget: none, no splice can start
      R2 = PASS R2;
      IF LE JUMP .bf_ok;
      F2 = F1 - F0;
      F2 = ABS F2;                  // d
      R3 = 0x44200000;              // 640
      F3 = F3 - F2;                 // room
      R2 = 0;
      COMP(F3, F2);
      IF LE JUMP .bf_ev;
      F2 = F5 - F4;
      F2 = ABS F2;                  // dv
      F2 = F6 * F2;
      COMP(F3, F2);
      IF LT JUMP .bf_ev;
      JUMP .bf_ok;
.bf_cs:
      R2 = DM(55, I2);              // splicing: inc = adaptive_increment * pitch
      F2 = F2 * F7;
      R3 = 0x3F800000;
      R1 = DM(56, I2);              // splice_phase
      F3 = F3 - F1;                 // 1 - phase
      F2 = F6 * F2;
      COMP(F3, F2);
      IF LT JUMP .bf_ev;
.bf_ok:
      R2 = 0;                       // one run: cc_brun
      JUMP .bf_k (DB);
      DM(-22, I6) = R2;
      NOP;
.bf_ev:
      R2 = 1;                       // events: cc_bloop
      DM(-22, I6) = R2;
// the right channel: absent, or mapped as last block
.bf_k:
      R15 = 0;
      R0 = DM(0, I5);
      R0 = PASS R0;
      IF EQ JUMP .bf_mono;
      R1 = DM(0x6E, I5);
      R2 = 0xFF;
      R1 = R1 AND R2;
      IF EQ JUMP .bf_mono;
      R1 = DM(0x66, I5);
      R2 = DM(0x66, I1);
      COMP(R1, R2);
      IF NE JUMP .bf_mono;
      R1 = DM(0x67, I5);
      R2 = DM(0x67, I1);
      COMP(R1, R2);
      IF NE JUMP .bf_mono;
      R1 = DM(0x68, I5);
      R2 = DM(0x68, I1);
      COMP(R1, R2);
      IF NE JUMP .bf_mono;
      R1 = DM(0x69, I5);
      R2 = DM(0x69, I1);
      COMP(R1, R2);
      IF NE JUMP .bf_mono;
      R12 = I3;
      R1 = 0x400;
      R12 = R1 + R12;               // gr = VOICE_STATE(v + 1)
      I4 = R12;
      R1 = DM(0x2DEE60);
      R2 = DM(0, I4);
      COMP(R2, R1);
      IF NE JUMP .bf_mono;          // (its first call sets it up)
      R2 = DM(9, I4);               // pair
      R2 = PASS R2;
      IF EQ JUMP .bf_no;
      R2 = DM(16, I4);              // retrig
      R2 = PASS R2;
      IF NE JUMP .bf_no;
      R15 = 72;
      R15 = R12 + R15;              // rr = &gr->rec
      I4 = R15;
      R2 = DM(205, I4);             // rr->src: this record's sample
      COMP(R2, R0);
      IF NE JUMP .bf_no;
      R2 = DM(233, I4);             // rr->b_llen
      R3 = DM(-19, I6);
      COMP(F2, F3);
      IF NE JUMP .bf_no;
      R2 = DM(234, I4);             // rr->b_k
      R3 = DM(234, I0);
      COMP(R2, R3);
      IF NE JUMP .bf_no;
.bf_mono:
// served: gen_run's and gen_wsola's stores
      R0 = -1;
      DM(0x2DEE38) = R0;            // GEN_TAPE_INFO->voice
      R0 = 0;
      DM(0x2DEE34) = R0;            // CC_TAPE_BUF_AT
      DM(217, I0) = R0;             // blend
      R0 = DM(0, I1);
      DM(205, I0) = R0;             // src
      R0 = DM(-20, I6);
      DM(9, I2) = R0;               // ideal.speed
      R0 = DM(-21, I6);
      DM(19, I2) = R0;              // actual.speed
      DM(49, I2) = R7;              // pitch
      R0 = DM(-17, I6);
      DM(0x2DEF4C) = R0;            // GEN_FRAME->budget
      DM(0x2DEF48) = R8;            // ->last_v
      R0 = DM(-18, I6);
      F0 = FLOAT R0;
      DM(232, I0) = R0;             // b_lend
      R0 = DM(-19, I6);
      DM(233, I0) = R0;             // b_llen
      DM(0x2DEE50) = R15;           // GEN_BPASS: the right recorder
      R0 = 0x2DE9B0;
      DM(0x2DEE54) = R0;            // GEN_ROUT
      DM(0x2DEE58) = R13;           // and the direction (cc_bloop's b_step)
      R4 = I0;
      R8 = PASS R10;
      R12 = PASS R9;
      R0 = DM(-22, I6);
      R0 = PASS R0;
      IF NE JUMP .bf_lp;
      R2 = I6;
      CJUMP cc_brun. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .bf_rt - 1;
.bf_rt:
      JUMP .bf_rn;                  // (each call returns right after itself: the runner checks)
.bf_lp:                             // a block with events: gen_wsola's loop
      R2 = I6;
      CJUMP cc_bloop. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .bf_rn - 1;
.bf_rn:                             // (cc_brun keeps R8-R15: R8 is out, R12 n; v and gr again)
      R8 = 0x2412CC;
      R0 = I1;
      R0 = R0 - R8;
      R2 = 2222;
      R2 = R0 * R2 (SSI);
      R3 = -20;
      R8 = LSHIFT R2 BY R3;         // v
      R12 = I3;
      R1 = 0x400;
      R12 = R1 + R12;               // gr again
// the shared generator's level (REPITCH, GRID, SLICE)
      R0 = 3;
      COMP(R11, R0);
      IF LT JUMP .bf_lv;
      R1 = 0x3ECF1AA0;              // 0.4045
      I4 = R10;
      R2 = PASS R9;
      R3 = 1;
.bf_l1:
      R0 = DM(0, I4);
      F0 = F0 * F1;
      DM(0, I4) = R0;
      I4=MODIFY (I4,0x1)(NW);
      R2 = R2 - R3;
      IF GT JUMP .bf_l1;
      R15 = PASS R15;
      IF EQ JUMP .bf_lv;
      I4 = 0x2DE9B0;
      R2 = PASS R9;
.bf_l2:
      R0 = DM(0, I4);
      F0 = F0 * F1;
      DM(0, I4) = R0;
      I4=MODIFY (I4,0x1)(NW);
      R2 = R2 - R3;
      IF GT JUMP .bf_l2;
.bf_lv:
// pos = src_start + b_k + floor(ideal.index)
      R1 = DM(7, I2);
      R0 = FIX F1;
      F2 = FLOAT R0;
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      R1 = DM(218, I0);
      R0 = R1 + R0;
      R1 = DM(234, I0);
      R0 = R1 + R0;
      R1 = DM(4, I3);               // gen_phase_out: not before the note's start
      COMP(R0, R1);
      IF LT R0 = PASS R1;
      R1 = 31;
      R1 = LSHIFT R0 BY R1;
      R2 = 0xA5A5A5;                // PHASE_MARK
      R1 = R2 OR R1;                // phase_lo
      R2 = -1;
      R2 = LSHIFT R0 BY R2;         // phase_hi
// the declicks' last samples (no retrig due), the right channel's ready, PHASE
      R0 = 1;
      R0 = R9 - R0;                 // n - 1
      R4 = R10;
      R5 = R0 + R0;
      R5 = R5 + R5;
      R4 = R5 + R4;
      I4 = R4;
      R4 = DM(0, I4);               // out[n - 1]
      DM(15, I3) = R4;              // g->last_out
      DM(2, I3) = R1;
      DM(3, I3) = R2;
      DM(0x6C, I1) = R1;
      DM(0x6D, I1) = R2;
      R15 = PASS R15;
      IF EQ JUMP .bf_end;
      R4 = 0x2DE9B0;
      R4 = R5 + R4;
      I4 = R4;
      R4 = DM(0, I4);               // GEN_ROUT[n - 1]
      I4 = R12;
      DM(15, I4) = R4;              // gr->last_out
      DM(0x2DEE38) = R8;            // GEN_TAPE_INFO: v, n
      DM(0x2DEE3C) = R9;
      DM(0x6C, I5) = R1;
      DM(0x6D, I5) = R2;
// the note's end (not looping): every head past it, ACTIVE cleared
.bf_end:
      R14 = PASS R14;
      IF NE JUMP .bf_acc;
      R0 = DM(-18, I6);             // len
      R13 = PASS R13;
      IF NE R0 = R0 - R0;           // (reversed: 0)
      R1 = DM(234, I0);
      R0 = R0 - R1;
      F4 = FLOAT R0;                // edge
      R0 = DM(7, I2);
      R1 = DM(17, I2);
      R2 = DM(27, I2);
      R3 = DM(57, I2);
      R5 = 1;                       // over
      R6 = 0;
      R13 = PASS R13;
      IF NE JUMP .bf_er;
      COMP(F0, F4);
      IF LT R5 = PASS R6;
      COMP(F1, F4);
      IF LT R5 = PASS R6;
      R3 = PASS R3;
      IF EQ JUMP .bf_ov;
      COMP(F2, F4);
      IF LT R5 = PASS R6;
      JUMP .bf_ov;
.bf_er:
      COMP(F0, F4);
      IF GE R5 = PASS R6;
      COMP(F1, F4);
      IF GE R5 = PASS R6;
      R3 = PASS R3;
      IF EQ JUMP .bf_ov;
      COMP(F2, F4);
      IF GE R5 = PASS R6;
.bf_ov:
      R5 = PASS R5;
      IF EQ JUMP .bf_acc;
      R0 = DM(0x6E, I1);
      R1 = -256;                    // ~0xff
      R0 = R0 AND R1;
      DM(0x6E, I1) = R0;
      R0 = 0;
      DM(1, I3) = R0;               // g->playing
// diag_account: inline unless the frame starts here (the C then)
.bf_acc:
#ifdef GEN_NO_DIAG
      JUMP .bf_yes;                 // (a release build: no load figures)
#endif
      R0 = DM(0x2DEF58);            // DIAG_AT->magic
      R1 = 0xD1A60004;
      COMP(R0, R1);
      IF NE JUMP .bf_dc;
      R0 = DM(0x2DEF5C);            // ->last_v
      COMP(R8, R0);
      IF LE JUMP .bf_dc;
      DM(0x2DEF5C) = R8;
      R0 = EMUCLK;
      R1 = DM(-16, I6);
      R0 = R0 - R1;                 // this call's cycles
      R1 = DM(0x2DEF64);            // ->frame_cyc
      R1 = R0 + R1;
      DM(0x2DEF64) = R1;
      R1 = DM(0x2DEF78);            // ->call_max
      COMP(R0, R1);
      IF LE JUMP .bf_yes;
      DM(0x2DEF78) = R0;
      JUMP .bf_yes;
.bf_dc:
      R4 = PASS R8;
      R8 = DM(-16, I6);
      R2 = I6;
      CJUMP cc_diag_acc. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .bf_yes - 1;
.bf_yes:
      R0 = 1;
      JUMP .bf_ret;
.bf_no:
      R0 = 0;
.bf_ret:
      R8 = DM(-3, I6);
      R9 = DM(-4, I6);
      R10 = DM(-5, I6);
      R11 = DM(-6, I6);
      R12 = DM(-7, I6);
      R13 = DM(-8, I6);
      R14 = DM(-9, I6);
      R15 = DM(-10, I6);
      R1 = DM(-11, I6);
      I0 = R1;
      R1 = DM(-12, I6);
      I1 = R1;
      R1 = DM(-13, I6);
      I2 = R1;
      R1 = DM(-14, I6);
      I3 = R1;
      R1 = DM(-15, I6);
      I5 = R1;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

// ---- gen_bd.py: begin reads (generated: edit work/gen_bd.py)
// .bs: index F1 -> F0 the left channel's clean read and, with a right recorder
// (R11), the right channel's to DM(-21, I6), the two in SIMD (gen_bd.py); .bd the
// same in SISD, for right samples across a word's halves. .fcl's fast path on both
// channels' samples (k and f found once), else .fcl_slow on each recorder.
// cc_brun's frame (-21..-27) and registers; clobber R0-R7, R12 (0 again for
// .fcl_slow), I3, I4, S0-S7, S12.
.bs:
      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_bs;
      COMP(F1, F15);
      IF GE JUMP .sl_bs;
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
      R11 = PASS R11;
      IF EQ JUMP .mo_bs;
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
      IF NE JUMP .so_bs;           // (decided in SISD: no MODE1 change in a delay slot)
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = R5 AND R3;               // y3
      F2 = FLOAT R2 BY R1;
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .sp_bs (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.so_bs:
      BIT SET MODE1 0x200000;       // SIMD: PEy reads the right channel on S0-S7, S12
      NOP;                          // (MODE1's effect latency)
      R0 = M0;                      // 16, both PEs
      R3 = M1;                      // 0xFFFF0000
      R1 = M2;                      // -31
      R12 = M3;                     // 0.5
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.sp_bs:
      F1 = F2 - F4;                 // y3 - y0
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
      BIT CLR MODE1 0x200000;       // SISD again
      NOP;
      R1 = S0;                      // the right read (PEy's F0)
      R12 = 0;                      // (memory three instructions after the change: MODE1's latency)
      DM(-21, I6) = R1;
      RTS;
.mo_bs:                            // mono: the left channel alone, SISD
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bsm (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bsm (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bsm:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bsm:
      F1 = F2 - F4;                 // y3 - y0
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
      R12 = 0;
      RTS;
.rt_bs:
      R12 = 0;
      RTS;
.sl_bs:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_bs;
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      RTS;
.bd:
      R6 = PASS R1;                 // the index, for .fcl_slow
      R2 = DM(236, I0);             // b_lo
      COMP(F1, F2);
      IF LT JUMP .sl_bd;
      COMP(F1, F15);
      IF GE JUMP .sl_bd;
      R0 = FIX F1;                  // k = floor(index) (FIX rounds: one down where above),
      F2 = FLOAT R0;                // f = index - k (as .fcl)
      R3 = 1;
      COMP(F2, F1);
      IF GT R0 = R0 - R3;
      F2 = FLOAT R0;
      F7 = F1 - F2;                 // f
      R12 = R0 + R0;                // 2k
      R2 = R13 + R12;               // the left sample i - 1's byte address
      R11 = PASS R11;
      IF EQ JUMP .mo_bd;
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
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bdl (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bdl (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bdl:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bdl:
      F1 = F2 - F4;                 // y3 - y0
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
      DM(-22, I6) = R0;             // the left read
      R4 = DM(-27, I6);
      R1 = 2;
      R2 = R4 AND R1;
      R3 = DM(-26, I6);
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bdr (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bdr (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bdr:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bdr:
      F1 = F2 - F4;                 // y3 - y0
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
      DM(-21, I6) = R0;             // the right read
      R0 = DM(-22, I6);
      R12 = 0;
      RTS;
.mo_bd:
      R3 = -4;
      R3 = R2 AND R3;
      I4 = R3;
      R0 = 16;
      R3 = 0xFFFF0000;
      R12 = 0x3F000000;
      R1 = 2;
      R2 = R2 AND R1;
      R1 = -31;
      R4 = DM(0, I4);               // (loads leave the flags)
      IF NE JUMP .od_bdm (DB);
      R5 = DM(1, I4);
      R6 = DM(2, I4);
      R2 = R5 AND R3;               // y3: a word's high half as is, its low half
      F2 = FLOAT R2 BY R1;          // shifted up: x 2^16, so / 2^31 = / 32768
      R6 = LSHIFT R5 BY R0;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = R4 AND R3;
      F5 = FLOAT R5 BY R1;          // y1
      JUMP .fp_bdm (DB);
      R4 = LSHIFT R4 BY R0;
      F4 = FLOAT R4 BY R1;          // y0
.od_bdm:
      R2 = LSHIFT R6 BY R0;
      F2 = FLOAT R2 BY R1;          // y3
      R6 = R5 AND R3;
      F6 = FLOAT R6 BY R1;          // y2
      R5 = LSHIFT R5 BY R0;
      F5 = FLOAT R5 BY R1;          // y1
      R4 = R4 AND R3;
      F4 = FLOAT R4 BY R1;          // y0
.fp_bdm:
      F1 = F2 - F4;                 // y3 - y0
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
      R12 = 0;
      RTS;
.rt_bd:
      R12 = 0;
      RTS;
.sl_bd:
      R12 = 0;                      // (.fcl_slow's F12: plan B's t0 - origin)
      DM(-23, I6) = R6;
      CALL .fcl_slow;               // F0 = the left read
      R11 = PASS R11;
      IF EQ JUMP .rt_bd;
      DM(-22, I6) = R0;
      R6 = DM(-23, I6);
      I0 = R11;
      CALL .fcl_slow;
      R1 = DM(-25, I6);             // r
      I0 = R1;
      DM(-21, I6) = R0;
      R0 = DM(-22, I6);
      RTS;
// ---- gen_bd.py: end reads (generated: edit work/gen_bd.py)
#endif
#endif
#ifndef GEN_WSOLA   /* (dt2entry.asm calls these: only plan B has the fast path) */
.GLOBAL cc_bfast2.;
cc_bfast2.:
.GLOBAL cc_bfast3.;
cc_bfast3.:
      R0 = 0;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
#endif
.cc_render_pair..end:
      .type cc_render_pair.,STT_FUNC;
