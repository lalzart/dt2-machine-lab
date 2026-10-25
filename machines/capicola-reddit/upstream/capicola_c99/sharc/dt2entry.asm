// dt2entry.asm -- the firmware's calls into dt2gen.c. GNU AGPL-3.0.
//
// cc_dt2_entry: STRETCH's call site (sw 0x1c6af1) -> cc_dt2_stretch.
// cc_dt2_rp_entry: the shared generator's call site (sw 0x1c6b00), taken by every
// other sample machine: REPITCH, GRID and SLICE (the DSP's machine types 3, 4 and
// 5, the voice's parameter record word 0x13) -> cc_dt2_repitch; any other type
// jumps on to the stock generator at 0x1c4ecf with the call's state untouched
// (only R0, R1 and I4 used, all scratch at a call). Both entries also go to the
// stock code when the voice's CAPI switch (slot 2) is off (parameter record word
// 4 = 0).
//
// The dispatch is compiled code that expects R3, R5, R6, R7 kept across the call
// (as well as R9-R11, R13-R15, which selcc keeps itself); selcc treats R3 and
// R5-R7 as scratch. So: save them, call the C, restore. R4/R8/R12 pass through.
.SECTION/PM seg_pmco;

.GLOBAL cc_dt2_entry.;
cc_dt2_entry.:
// CAPI off (the voice's parameter record word 4, the DSP's on/off copy of the
// SRC page's slot 2, is 0): the stock STRETCH, with the call's state untouched
      R0 = 0x2412CC;                // voice records
      R0 = R4 - R0;
      R1 = 2222;
      R0 = R0 * R1 (SSI);
      R1 = -20;
      R0 = LSHIFT R0 BY R1;         // v = offset * 2222 >> 20 (exact for v < 32)
      R2 = PASS R0;                 // (v, for .pf)
      R1 = 0xDC;
      R0 = R0 * R1 (SSI);
      R1 = 0x2506FC;                // parameter records + 0x10
      R0 = R0 + R1;
      I4 = R0;
      R0 = DM(0, I4);
      R0 = PASS R0;
      IF EQ JUMP .st_stock;         // CAPI off: the stock STRETCH (timed)
      CALL .pf;                     // a right voice its left voice rendered: copied
      R0 = PASS R0;
      IF NE JUMP .pf_ret;
      I7=MODIFY (I7,-0x9)(NW);
      DM(-3, I6) = R3;
      DM(-4, I6) = R5;
      DM(-5, I6) = R6;
      DM(-6, I6) = R7;
      DM(-7, I6) = R4;              // (for the C, if the fast path declines)
      DM(-8, I6) = R8;
      DM(-9, I6) = R12;
      R2 = I6;
      CJUMP cc_bfast2. (DB);   // render.asm: plan B's ordinary block in assembly
      DM(I7, M7) = R2;
      DM(I7, M7) = .bf2_r - 1;
.bf2_r:
      R0 = PASS R0;
      IF NE JUMP .ret;
      R4 = DM(-7, I6);
      R8 = DM(-8, I6);
      R12 = DM(-9, I6);
      R2 = I6;
      CJUMP cc_dt2_stretch. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .ret - 1;
.ret:
      R3 = DM(-3, I6);
      R5 = DM(-4, I6);
      R6 = DM(-5, I6);
      R7 = DM(-6, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
// the stock generator at 0x1c5576, timed: its cycles to cc_diag_stock (dt2gen.c,
// capload's stock figures); R3, R5-R7 kept for the firmware, as cc_dt2_entry does
.st_stock:
#ifdef GEN_NO_DIAG
      JUMP 0x1C5576;              // (a release build: the stock generator untimed, the call's state untouched)
#endif
      I7=MODIFY (I7,-0x8)(NW);
      DM(-3, I6) = R3;
      DM(-4, I6) = R5;
      DM(-5, I6) = R6;
      DM(-6, I6) = R7;
      DM(-7, I6) = R4;              // the voice record
      R0 = EMUCLK;
      DM(-8, I6) = R0;
      R2 = I6;
      CJUMP 0x1C5576 (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .st_stock_ret - 1;
.st_stock_ret:
      R0 = EMUCLK;
      R1 = DM(-8, I6);
      R8 = R0 - R1;                 // its cycles
      R4 = DM(-7, I6);
      R12 = 0;
      R2 = I6;
      CJUMP cc_diag_stock. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .st_stock_dret - 1;
.st_stock_dret:
      R3 = DM(-3, I6);
      R5 = DM(-4, I6);
      R6 = DM(-5, I6);
      R7 = DM(-6, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
.cc_dt2_entry..end:
      .type cc_dt2_entry.,STT_FUNC;

.GLOBAL cc_dt2_rp_entry.;
cc_dt2_rp_entry.:
      R0 = 0x2412CC;                // voice records
      R0 = R4 - R0;                 // offset
      R1 = 2222;
      R0 = R0 * R1 (SSI);
      R1 = -20;
      R0 = LSHIFT R0 BY R1;         // v = offset * 2222 >> 20 (exact for v < 32)
      R2 = PASS R0;                 // (v, for .pf)
      R1 = 0xDC;
      R0 = R0 * R1 (SSI);
      R1 = 0x250738;                // parameter records + 0x4c
      R0 = R0 + R1;
      I4 = R0;
      R0 = DM(0, I4);               // machine type (the DSP's: 3 REPITCH, 4 GRID, 5 SLICE)
      R1 = 3;
      COMP(R0, R1);
      IF LT JUMP .sh_stock;          // SAMPLE, WERP: the stock generator
      R1 = 5;
      COMP(R0, R1);
      IF GT JUMP .sh_stock;
#ifdef GEN_SLICE_MODE
      R1 = 4;                       // a test image (dt2gen.c GEN_SLICE_MODE): GRID and SLICE always ours
      COMP(R0, R1);
      IF GE JUMP .rp_on;
#endif
      R0 = I4;
      R1 = 0x3C;
      R0 = R0 - R1;                 // word 4 of the same record (+0x10)
      I4 = R0;
      R0 = DM(0, I4);
      R0 = PASS R0;
      IF EQ JUMP .sh_stock;          // CAPI off: the stock machine
.rp_on:
      CALL .pf;                     // a right voice its left voice rendered: copied
      R0 = PASS R0;
      IF NE JUMP .pf_ret;
      I7=MODIFY (I7,-0x9)(NW);
      DM(-3, I6) = R3;
      DM(-4, I6) = R5;
      DM(-5, I6) = R6;
      DM(-6, I6) = R7;
      DM(-7, I6) = R4;              // (for the C, if the fast path declines)
      DM(-8, I6) = R8;
      DM(-9, I6) = R12;
      R2 = I6;
      CJUMP cc_bfast3. (DB);   // render.asm: plan B's ordinary block in assembly
      DM(I7, M7) = R2;
      DM(I7, M7) = .bf3_r - 1;
.bf3_r:
      R0 = PASS R0;
      IF NE JUMP .rp_ret;
      R4 = DM(-7, I6);
      R8 = DM(-8, I6);
      R12 = DM(-9, I6);
      R2 = I6;
      CJUMP cc_dt2_repitch. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .rp_ret - 1;
.rp_ret:
      R3 = DM(-3, I6);
      R5 = DM(-4, I6);
      R6 = DM(-5, I6);
      R7 = DM(-6, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
// the stock generator at 0x1c4ecf, timed: its cycles to cc_diag_stock (dt2gen.c,
// capload's stock figures); R3, R5-R7 kept for the firmware, as cc_dt2_entry does
.sh_stock:
#ifdef GEN_NO_DIAG
      JUMP 0x1C4ECF;              // (a release build: the stock generator untimed, the call's state untouched)
#endif
      I7=MODIFY (I7,-0x8)(NW);
      DM(-3, I6) = R3;
      DM(-4, I6) = R5;
      DM(-5, I6) = R6;
      DM(-6, I6) = R7;
      DM(-7, I6) = R4;              // the voice record
      R0 = EMUCLK;
      DM(-8, I6) = R0;
      R2 = I6;
      CJUMP 0x1C4ECF (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .sh_stock_ret - 1;
.sh_stock_ret:
      R0 = EMUCLK;
      R1 = DM(-8, I6);
      R8 = R0 - R1;                 // its cycles
      R4 = DM(-7, I6);
      R12 = 1;
      R2 = I6;
      CJUMP cc_diag_stock. (DB);
      DM(I7, M7) = R2;
      DM(I7, M7) = .sh_stock_dret - 1;
.sh_stock_dret:
      R3 = DM(-3, I6);
      R5 = DM(-4, I6);
      R6 = DM(-5, I6);
      R7 = DM(-6, I6);
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
.cc_dt2_rp_entry..end:
      .type cc_dt2_rp_entry.,STT_FUNC;

// .pf: a right voice (v = R2 odd) whose left voice rendered its channel this
// frame (dt2gen.c gen_wsola's stereo pass: GEN_TAPE_INFO at 0x2dee38 = {v - 1,
// n}): its n = R12 samples copied from GEN_ROUT (0x2de9b0) to out (R8), the info
// marked used (-1); the left voice has set this voice's state and PHASE. R0 = 1
// when done so; else R0 = 0 and R4, R8, R12 as they were (for the C). Uses R0,
// R1, R4, I4; I5 kept.
.pf:
      R1 = 1;
      R1 = R2 AND R1;
      IF EQ JUMP .pf_no;            // a left voice
      R0 = DM(0x2DEE38);            // the voice that rendered this frame's right channel
      R1 = 1;
      R1 = R2 - R1;
      COMP(R0, R1);
      IF NE JUMP .pf_no;
      R0 = DM(0x2DEE3C);            // and its n
      COMP(R0, R12);
      IF NE JUMP .pf_no;
      R12 = PASS R12;
      IF LE JUMP .pf_no;
      R0 = -1;
      DM(0x2DEE38) = R0;
      R4 = I5;
      I5 = R8;
      I4 = 0x2DE9B0;
      R1 = 1;
.pf_cp:
      R0 = DM(0, I4);
      I4=MODIFY (I4,0x1)(NW);
      DM(0, I5) = R0;
      I5=MODIFY (I5,0x1)(NW);
      R12 = R12 - R1;
      IF GT JUMP .pf_cp;
      I5 = R4;
      R0 = 1;
      RTS;
.pf_no:
      R0 = 0;
      RTS;
// the return of an entry that .pf served
.pf_ret:
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;

// cc_emuclk: the core's cycle counter (GEN_DIAG's load figures)
.GLOBAL cc_emuclk.;
cc_emuclk.:
      R0 = EMUCLK;
      I12 = DM(M7, I6);
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
.cc_emuclk..end:
      .type cc_emuclk.,STT_FUNC;

