// ubench.asm -- SHARC+ cost microbenchmarks for the DT2 (one-off image, build_cap.py
// --diag with ubench.c in place of dt2gen.c). GNU AGPL-3.0.
//
//   uint32_t cc_ub_run(int k);   R4 = kernel -> R0 = EMUCLK cycles for 64 iterations
//
// Kernels, 8 operations an iteration (the loop itself: R9 = R9 - R1; IF NE JUMP):
//   0 empty loop            1 ALU add                 2 L1 load, block 1 (our data)
//   3 L1 load then use      4 I4 = R then load via I4  5 DDR load, one line
//   6 DDR load, new lines   7 L1 load, block 0         8 compare + untaken jump
//   9 compare + taken jump  10 CALL + RTS              11 empty loop, delayed jump
//   12 float multiply then add (render.asm's forms)
// Uses R0-R7, R12, I4 and R9 (saved at 0x2defec) (R3, R5-R7: dt2entry.asm saves them for the firmware).

.SECTION/PM seg_pmco;

.GLOBAL cc_ub_run.;
cc_ub_run.:
      DM(0x2DEFEC) = R9;            // kept for the caller
      R9 = 64;
      R1 = 1;
      R5 = 3;
      R6 = 5;
      R7 = 0x2DEF00;
      I4 = R7;
      R0 = 0;
      COMP(R4, R0);
      IF EQ JUMP .k0;
      R0 = 1;
      COMP(R4, R0);
      IF EQ JUMP .k1;
      R0 = 2;
      COMP(R4, R0);
      IF EQ JUMP .k2;
      R0 = 3;
      COMP(R4, R0);
      IF EQ JUMP .k3;
      R0 = 4;
      COMP(R4, R0);
      IF EQ JUMP .k4;
      R0 = 5;
      COMP(R4, R0);
      IF EQ JUMP .k5;
      R0 = 6;
      COMP(R4, R0);
      IF EQ JUMP .k6;
      R0 = 7;
      COMP(R4, R0);
      IF EQ JUMP .k7;
      R0 = 8;
      COMP(R4, R0);
      IF EQ JUMP .k8;
      R0 = 9;
      COMP(R4, R0);
      IF EQ JUMP .k9;
      R0 = 10;
      COMP(R4, R0);
      IF EQ JUMP .k10;
      R0 = 11;
      COMP(R4, R0);
      IF EQ JUMP .k11;
      R0 = 12;
      COMP(R4, R0);
      IF EQ JUMP .k12;
      R0 = 0;
      JUMP .ub_ret;
.k0:
      R2 = EMUCLK;
.k0l:
      R9 = R9 - R1;
      IF NE JUMP .k0l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k1:
      R2 = EMUCLK;
.k1l:
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R5 = R5 + R6;
      R9 = R9 - R1;
      IF NE JUMP .k1l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k2:
      R2 = EMUCLK;
.k2l:
      R5 = DM(0, I4);
      R5 = DM(1, I4);
      R5 = DM(2, I4);
      R5 = DM(3, I4);
      R5 = DM(4, I4);
      R5 = DM(5, I4);
      R5 = DM(6, I4);
      R5 = DM(7, I4);
      R9 = R9 - R1;
      IF NE JUMP .k2l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k3:
      R2 = EMUCLK;
.k3l:
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R5 = DM(0, I4);
      R6 = R5 + R6;
      R9 = R9 - R1;
      IF NE JUMP .k3l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k4:
      R2 = EMUCLK;
.k4l:
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      I4 = R7;
      R5 = DM(0, I4);
      R9 = R9 - R1;
      IF NE JUMP .k4l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k5:
      R7 = 0x9E000000;
      I4 = R7;
      R2 = EMUCLK;
.k5l:
      R5 = DM(0, I4);
      R5 = DM(1, I4);
      R5 = DM(2, I4);
      R5 = DM(3, I4);
      R5 = DM(4, I4);
      R5 = DM(5, I4);
      R5 = DM(6, I4);
      R5 = DM(7, I4);
      R9 = R9 - R1;
      IF NE JUMP .k5l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k6:
      R7 = DM(0x2DEFE8);
      R12 = 0x8000;
      R7 = R7 + R12;
      R12 = 0x7FFFF;
      R7 = R7 AND R12;
      DM(0x2DEFE8) = R7;
      R12 = 0x9E000000;
      R7 = R7 + R12;
      I4 = R7;
      R12 = 512;
      R2 = EMUCLK;
.k6l:
      R5 = DM(0, I4);
      R5 = DM(16, I4);
      R5 = DM(32, I4);
      R5 = DM(48, I4);
      R5 = DM(64, I4);
      R5 = DM(80, I4);
      R5 = DM(96, I4);
      R5 = DM(112, I4);
      R7 = R7 + R12;
      I4 = R7;
      R9 = R9 - R1;
      IF NE JUMP .k6l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k7:
      R7 = 0x2412CC;
      I4 = R7;
      R2 = EMUCLK;
.k7l:
      R5 = DM(0, I4);
      R5 = DM(1, I4);
      R5 = DM(2, I4);
      R5 = DM(3, I4);
      R5 = DM(4, I4);
      R5 = DM(5, I4);
      R5 = DM(6, I4);
      R5 = DM(7, I4);
      R9 = R9 - R1;
      IF NE JUMP .k7l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k8:
      R2 = EMUCLK;
.k8l:
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      COMP(R5, R6);
      IF EQ JUMP .ub_ret;
      R9 = R9 - R1;
      IF NE JUMP .k8l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k9:
      R2 = EMUCLK;
.k9l:
      COMP(R5, R6);
      IF NE JUMP .k9t0;
      .k9t0:
      COMP(R5, R6);
      IF NE JUMP .k9t1;
      .k9t1:
      COMP(R5, R6);
      IF NE JUMP .k9t2;
      .k9t2:
      COMP(R5, R6);
      IF NE JUMP .k9t3;
      .k9t3:
      COMP(R5, R6);
      IF NE JUMP .k9t4;
      .k9t4:
      COMP(R5, R6);
      IF NE JUMP .k9t5;
      .k9t5:
      COMP(R5, R6);
      IF NE JUMP .k9t6;
      .k9t6:
      COMP(R5, R6);
      IF NE JUMP .k9t7;
      .k9t7:
      R9 = R9 - R1;
      IF NE JUMP .k9l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k10:
      R2 = EMUCLK;
.k10l:
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      CALL .k10f;
      R9 = R9 - R1;
      IF NE JUMP .k10l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k11:
      R2 = EMUCLK;
.k11l:
      R9 = R9 - R1;
      IF NE JUMP .k11l (DB);
      NOP;
      NOP;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k12:
      R0 = 0x3F800000;
      R3 = 0x3F7FFFFF;
      R5 = 0;
      R2 = EMUCLK;
.k12l:
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      F3 = F0 * F3;
      F0 = F5 + F3;
      R9 = R9 - R1;
      IF NE JUMP .k12l;
      R0 = EMUCLK;
      JUMP .ub_ret;
.k10f:
      RTS;
.ub_ret:
      R0 = R0 - R2;
      R9 = DM(0x2DEFEC);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
.cc_ub_run..end:
      .type cc_ub_run.,STT_FUNC;
