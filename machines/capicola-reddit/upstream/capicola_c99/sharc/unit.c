/*
 * unit.c -- differential unit drivers for the C99 Capicola port: the same
 * functions run natively (the host) and in digikit's SHARC runner (selcc), each
 * writing its results as 32-bit words to RES; the two word lists must match.
 * GNU AGPL-3.0, as Capicola.
 */
#include "../capicola.c"   /* one translation unit: selcc returns structs wrongly across objects */

#ifdef UNIT_HOST
static uint32_t res_mem[256];
static cc_keyframe ring_mem[64];
#define RES  res_mem
#define RING ring_mem
#else
#define RES  ((uint32_t *)0x9e100000u)
#define RING ((cc_keyframe *)0x9e200000u)
#endif

static void put_f(int i, float v) { ((float *)RES)[i] = v; }   /* no union: selcc returns 0 for type-punning unions */

static float sig(int n)   /* a deterministic test signal: two ramps, no libm */
{
    float a = (float)((n * 7) % 23) / 23.0f - 0.5f;
    float b = (float)((n * 3) % 11) / 11.0f - 0.5f;
    return 0.7f * a + 0.3f * b;
}

/* 1: the 8-sample line's reads after ten writes. */
int unit_dline(void)
{
    cc_dline8 l;
    cc_dline8_init(&l);
    for (int n = 0; n < 10; n++) cc_dline8_write(&l, sig(n));
    cc_cubic a;
    cc_dline8_bspline_d1_int(&l, 2, &a);
    put_f(0, a.value); put_f(1, a.d1);
    put_f(2, cc_dline8_bspline(&l, 2.5f));
    cc_cubic c;
    cc_dline8_bspline_full(&l, 2.3f, 1, &c);
    put_f(3, c.value); put_f(4, c.d1); put_f(5, c.d2); put_f(6, c.tkeo);
    return 7;
}

/* 2: the analyzer over 64 samples: keyframe count, then each keyframe's value
   and time (as float). */
int unit_analyzer(void)
{
    cc_sparse s;
    cc_analyzer a;
    cc_sparse_init(&s, RING, 64);
    cc_analyzer_init(&a, &s, 48000.0f);
    for (int n = 0; n < 64; n++) cc_analyzer_analyze(&a, sig(n));
    int k = (int)a.sparse_count;
    RES[0] = (uint32_t)k;
    for (int i = 0; i < k && i < 60; i++) {
        put_f(1 + 2 * i, RING[i].value);
        put_f(2 + 2 * i, (float)RING[i].time);
    }
    return 1 + 2 * (k < 60 ? k : 60);
}

#ifdef UNIT_HOST
#include <stdio.h>
int main(void)
{
    int n = unit_dline();
    printf("dline:");
    for (int i = 0; i < n; i++) printf(" %08x", RES[i]);
    printf("\n");
    n = unit_analyzer();
    printf("analyzer:");
    for (int i = 0; i < n; i++) printf(" %08x", RES[i]);
    printf("\n");
    return 0;
}
#endif
