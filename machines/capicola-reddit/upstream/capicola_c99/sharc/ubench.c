/*
 * ubench.c -- the one-off SHARC+ cost benchmark image for the DT2: the STRETCH and
 * REPITCH generators output silence and, every fourth call, time one of
 * ubench.asm's kernels; the smallest time per kernel (interrupts only ever add)
 * goes out in reply word 0 as GEN_DIAG's figures do (item in the top 4 bits,
 * value in the low 28, halves swapped), read with dt2probe.py capbench.
 * GNU AGPL-3.0, as Capicola. Build: work/build_ubench.sh.
 */
#include <stdint.h>

uint32_t cc_ub_run(int k);   /* ubench.asm */

#define NK     13
#define UB_MAGIC 0x0B0E0C01u
typedef struct { uint32_t magic, calls, tag, runs, next, min[NK]; } ub_state;
#define UB ((ub_state *)0x2def00u)   /* on chip; ubench.asm kernel 2 reads here, kernel 6 keeps 0x2defe8 */

static void ub_out(float *out, int n)
{
    for (int i = 0; i < n; i++) out[i] = 0.0f;
}

static void ub_call(float *out, int n)
{
    ub_state *u = UB;
    ub_out(out, n);
    if (u->magic != UB_MAGIC) {
        u->calls = 0;
        u->tag = 0;
        u->runs = 0;
        u->next = 0;
        for (int i = 0; i < NK; i++) u->min[i] = 0xffffffffu;
        u->magic = UB_MAGIC;
    }
    u->calls++;
    if ((u->calls & 3u) == 0u) {
        const uint32_t k = u->next;   /* no %: selcc would call a division helper */
        u->next = (k + 1u < NK) ? k + 1u : 0u;
        const uint32_t c = cc_ub_run((int)k);
        if (c < u->min[k]) u->min[k] = c;
        u->runs++;
    }
    if ((u->calls & 63u) == 0u) {
        u->tag++;
        if (u->tag > NK) u->tag = 0;
        uint32_t v = u->runs;
        if (u->tag < NK) v = u->min[u->tag];
        const uint32_t w = (u->tag << 28) | (v & 0x0fffffffu);
        const uint32_t sw = (w << 16) | (w >> 16);
        *(volatile uint32_t *)0x266220u = sw;
        *(volatile uint32_t *)0x267220u = sw;
    }
}

void cc_dt2_stretch(uint32_t *rec, float *out, int n) { (void)rec; ub_call(out, n); }
void cc_dt2_repitch(uint32_t *rec, float *out, int n) { (void)rec; ub_call(out, n); }
