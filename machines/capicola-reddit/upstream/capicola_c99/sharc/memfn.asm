// memfn.asm -- the memory test's timed function (memtest.c). Assembled twice:
// with -DMEMFN_L2 as cc_l2fn (linked into L2 by memtest_l2.ldf) and plain as
// cc_l1fn (L1, with memtest.c). R4 = x -> R0 = 32 x + 0x1234: 32 dependent adds,
// so a wrong fetch shows as a wrong sum. GNU AGPL-3.0.
.SECTION/PM seg_pmco;
#ifdef MEMFN_L2
.GLOBAL cc_l2fn.;
cc_l2fn.:
#else
.GLOBAL cc_l1fn.;
cc_l1fn.:
#endif
      R0 = 0x1234;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      R0 = R4 + R0;
      I12 = DM(M7, I6);
      NOP;
      JUMP (M14, I12) (DB);
      NOP;
      RFRAME;
#ifdef MEMFN_L2
.cc_l2fn..end:
      .type cc_l2fn.,STT_FUNC;
#else
.cc_l1fn..end:
      .type cc_l1fn.,STT_FUNC;
#endif
