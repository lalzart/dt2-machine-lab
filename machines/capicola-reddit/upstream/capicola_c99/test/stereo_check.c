/* stereo_check.c -- two CC_SOURCE channels of a stereo sample called as the DT2
   does (left, then right, each block), with the stereo link (-DCC_LINK) or
   without; writes st_<link>_<stretch*100>.raw (interleaved L R float32, 3 s)
   and st_input.raw. For stereo_check.py.
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -DCC_ALIGN=8 [-DCC_LINK] -I.. stereo_check.c ../capicola.c -lm */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "capicola.h"

#define RING 4096
#define B 32
#define LEN (48000 * 4)
static cc_keyframe sl[RING], sr[RING];
static cc_recorder rl, rr;
static int16_t chl[LEN + 2], chr[LEN + 2];
static uint32_t rng = 99;
static float noise(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (rng / 4294967296.0f) * 2 - 1; }
#ifdef CC_LINK
extern cc_link *cc_link_ptr(void);
#endif

static float PITCH = 1.0f;
static void setup(cc_recorder *r, cc_keyframe *ring, const int16_t *x, float s)
{
    memset(r, 0, sizeof *r);
    cc_recorder_init(r, ring, RING);
    cc_recorder_set_fade(r, 960); cc_recorder_set_leash(r, -640);
    cc_recorder_set_stretch(r, s); cc_recorder_set_pitch(r, PITCH);
    cc_recorder_source(r, (uintptr_t)x, 0, LEN, 0);
}

int main(int argc, char **argv)
{
    if (argc > 1) PITCH = (float)atof(argv[1]);
    for (int i = 0; i < LEN; i++) {
        double t = i / 48000.0, tb = fmod(t, 0.5), th = fmod(t, 0.125);
        double kick = 0.5 * exp(-tb * 20) * sin(2 * M_PI * (50 + 200 * exp(-tb * 40)) * tb);
        double cl = 0.1 * (sin(2 * M_PI * 220 * t) + sin(2 * M_PI * 277 * t) + sin(2 * M_PI * 330 * t));
        double cr = 0.1 * (sin(2 * M_PI * 220 * t + 0.3) + sin(2 * M_PI * 277 * t - 0.4) + sin(2 * M_PI * 330 * t + 0.2));
        double hl = 0.08 * exp(-th * 80) * noise(), hr = 0.08 * exp(-th * 80) * noise();
        chl[i] = (int16_t)lrint((kick + cl + hl) * 32767);
        chr[i] = (int16_t)lrint((kick + cr + hr) * 32767);
        if (getenv("WIDE")) {   /* a wider sample: R 0.7 ms later, its own chord voicing, more of its own noise */
            double tr = (i - 33) / 48000.0, tbr = fmod(tr < 0 ? 0 : tr, 0.5);
            double kr = 0.5 * exp(-tbr * 20) * sin(2 * M_PI * (50 + 200 * exp(-tbr * 40)) * tbr);
            double c2 = 0.1 * (sin(2 * M_PI * 233 * t) + sin(2 * M_PI * 294 * t) + sin(2 * M_PI * 349 * t));
            chr[i] = (int16_t)lrint((kr + c2 + 2.5 * hr) * 32767);
        }
    }
    FILE *f = fopen("st_input.raw", "wb");
    for (int i = 0; i < 3 * 48000; i++) { float v[2] = {chl[i] / 32768.0f, chr[i] / 32768.0f}; fwrite(v, sizeof v, 1, f); }
    fclose(f);
    const float st[] = {0.75f, 1.0f, 1.25f, 1.6f, 2.0f};
    for (int k = 0; k < 5; k++) {
        char fn[64];
#ifdef CC_LINK
        snprintf(fn, sizeof fn, "st_link_%d.raw", (int)(st[k] * 100));
#else
        snprintf(fn, sizeof fn, "st_nolink_%d.raw", (int)(st[k] * 100));
#endif
        f = fopen(fn, "wb");
        setup(&rl, sl, chl, st[k]);
        setup(&rr, sr, chr, st[k]);
        if (getenv("LAG")) rr.rebase_lag = atoi(getenv("LAG"));   /* the DT2 build staggers rebases: right voice 1024 later */
        float ol[B], or_[B];
        long desync = 0, first_desync = -1;
        double maxpos = 0;
        for (int b = 0; b < 3 * 48000 / B; b++) {
#ifdef CC_LINK
            cc_link *lk = cc_link_ptr();
            lk->mode = 1; lk->n = 0; lk->voice = 0;
#endif
            if (getenv("SWEEP")) {   /* TUNE turned: pitch 1 -> 2^(7/12) -> 2^(-5/12) -> 1 over the 3 s, block by block */
                const float t = (float)b * B / 48000.0f, x = (t < 1.0f) ? t * 7.0f : (t < 2.0f) ? 7.0f - 12.0f * (t - 1.0f) : -5.0f + 5.0f * (t - 2.0f);
                const float p = powf(2.0f, x / 12.0f);
                cc_recorder_set_pitch(&rl, p);
                cc_recorder_set_pitch(&rr, p);
            }
            cc_recorder_process(&rl, NULL, ol, B);
#ifdef CC_LINK
            lk->mode = 2; lk->k = 0;
#endif
            cc_recorder_process(&rr, NULL, or_, B);
#ifdef CC_LINK
            lk->mode = 0;
#endif
            for (int i = 0; i < B; i++) { float v[2] = {ol[i], or_[i]}; fwrite(v, sizeof v, 1, f); }
            {   /* the two channels' heads, as positions in the note: in step? */
                const cc_granule *gl = &rl.granule[rl.live_g], *gr = &rr.granule[rr.live_g];
                const double bl = (double)rl.sparse.origin - (double)rl.src_t0, br = (double)rr.sparse.origin - (double)rr.src_t0;
                const double dpos = fmax(fabs((gl->ideal.index + bl) - (gr->ideal.index + br)), fabs((gl->actual.index + bl) - (gr->actual.index + br)));
                if (dpos > maxpos) maxpos = dpos;
                if (gl->splicing != gr->splicing || dpos > 1.0) { desync++; if (first_desync < 0) first_desync = b; }
            }
        }
        fclose(f);
        printf("stretch %.2f pitch %.3f: splice state differs or heads > 1 sample apart in %ld of %d blocks (first at %ld); largest head gap %.4f samples\n", st[k], PITCH, desync, 3 * 48000 / B, first_desync, maxpos);
    }
    return 0;
}
