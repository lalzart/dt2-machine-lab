/*
 * memtest.c -- the one-off L2 memory test image for the DT2 (STRETCH and REPITCH
 * output silence). The boot stream loads (dt2_probe/build_cap.py --memtest):
 *   - a 32 KB pattern at L2 byte 0x20080000: word k = MT_PAT(k);
 *   - memfn.asm's cc_l2fn at L2 byte 0x20090000 (its sw address: MEMFN_L2_SW).
 * Each generator call checks 64 pattern words (rotating) and, every 16th call,
 * runs cc_l2fn and the L1 copy cc_l1fn, checking and timing both. If the
 * firmware uses that L2 region, the pattern changes; if L2 code does not run
 * right, the sums are wrong. Figures in reply word 0 as GEN_DIAG's (item in the
 * top 4 bits, value in the low 28, halves swapped): dt2probe.py capmem.
 * GNU AGPL-3.0, as Capicola.
 */
#include <stdint.h>

uint32_t cc_emuclk(void);              /* dt2entry.asm */
uint32_t cc_l1fn(uint32_t x);          /* memfn.asm */
#ifndef MEMFN_L2_SW
#error "MEMFN_L2_SW: cc_l2fn's address (work/build_memtest.sh)"
#endif
typedef uint32_t (*mt_fn)(uint32_t);

#define MT_BASE  0x20080000u
#define MT_WORDS 8192u
#define MT_PAT(k) (0x5A000000u ^ ((k) * 2654435761u))
#define NITEM    10
#define MT_MAGIC 0x3E3E0002u
typedef struct {
    uint32_t magic, calls, tag, next, checked, bad, first_bad;
    uint32_t l2_ok, l2_wrong, l2_min, l1_min, l1_wrong;
} mt_state;
#define MT ((mt_state *)0x2def00u)

void cc_dt2_stretch(uint32_t *rec, float *out, int n);
void cc_dt2_repitch(uint32_t *rec, float *out, int n);

static void mt_call(float *out, int n)
{
    mt_state *s = MT;
    for (int i = 0; i < n; i++) out[i] = 0.0f;
    if (s->magic != MT_MAGIC) {
        s->calls = 0;
        s->tag = 0;
        s->next = 0;
        s->checked = 0;
        s->bad = 0;
        s->first_bad = 0xffffffffu;
        s->l2_ok = 0;
        s->l2_wrong = 0;
        s->l2_min = 0xffffffffu;
        s->l1_min = 0xffffffffu;
        s->l1_wrong = 0;
        s->magic = MT_MAGIC;
    }
    s->calls++;
    {   /* 64 pattern words */
        const volatile uint32_t *p = (const volatile uint32_t *)MT_BASE;
        uint32_t k = s->next;
        for (int i = 0; i < 64; i++) {
            if (p[k] != MT_PAT(k)) {
                s->bad++;
                if (s->first_bad == 0xffffffffu) s->first_bad = k;
            }
            k++;
            if (k >= MT_WORDS) k = 0;
        }
        s->next = k;
        s->checked += 64u;
    }
    if ((s->calls & 15u) == 0u) {   /* the function in L2, and its L1 copy */
        const uint32_t x = s->calls;
        const uint32_t want = 32u * x + 0x1234u;
        const mt_fn f2 = (mt_fn)MEMFN_L2_SW;
        uint32_t t0 = cc_emuclk();
        const uint32_t y2 = f2(x);
        uint32_t c = cc_emuclk() - t0;
        if (y2 == want) s->l2_ok++; else s->l2_wrong++;
        if (c < s->l2_min) s->l2_min = c;
        t0 = cc_emuclk();
        const uint32_t y1 = cc_l1fn(x);
        c = cc_emuclk() - t0;
        if (y1 != want) s->l1_wrong++;
        if (c < s->l1_min) s->l1_min = c;
    }
    if ((s->calls & 63u) == 0u) {
        uint32_t v = 0;
        s->tag++;
        if (s->tag >= NITEM) s->tag = 0;
        if (s->tag == 0) v = s->checked >> 10;
        if (s->tag == 1) v = s->bad;
        if (s->tag == 2) v = s->first_bad;
        if (s->tag == 3) v = s->l2_ok;
        if (s->tag == 4) v = s->l2_wrong;
        if (s->tag == 5) v = s->l2_min;
        if (s->tag == 6) v = s->l1_min;
        if (s->tag == 7) v = s->l1_wrong;
        if (s->tag == 8) v = s->calls >> 10;
        if (s->tag == 9) v = 0x0ABCDEFu;   /* a known value: the decoder's check */
        const uint32_t w = (s->tag << 28) | (v & 0x0fffffffu);
        const uint32_t sw = (w << 16) | (w >> 16);
        *(volatile uint32_t *)0x266220u = sw;
        *(volatile uint32_t *)0x267220u = sw;
    }
}

void cc_dt2_stretch(uint32_t *rec, float *out, int n) { (void)rec; mt_call(out, n); }
void cc_dt2_repitch(uint32_t *rec, float *out, int n) { (void)rec; mt_call(out, n); }
