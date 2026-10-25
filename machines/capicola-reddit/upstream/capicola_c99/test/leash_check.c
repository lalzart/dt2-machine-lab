/* leash_check.c -- CC_SOURCE at several leash values and stretch ratios, pitch 1:
   writes lc_<leash>_<stretch*100>.raw (float32, 2 s) for leash_check.py.
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -I.. leash_check.c ../capicola.c -lm -o leash_check */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "capicola.h"

#define RING 2048
#define B 32
#define LEN 48000
static cc_keyframe storage[RING];
static cc_recorder rec;
static int16_t smp[LEN + 2];
static uint32_t rng = 12345;
static float noise(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (rng / 4294967296.0f) * 2 - 1; }

int main(void)
{
    for (int i = 0; i < LEN; i++) {   /* the chord alone, plus faint hats: a steady pitch reference */
        double t = (double)i / 48000, th = fmod(t, 0.125);
        double x = 0.02 * exp(-th * 80) * noise()
                 + 0.2 * (sin(2 * M_PI * 220 * t) + sin(2 * M_PI * 277 * t) + sin(2 * M_PI * 330 * t));
        smp[i] = (int16_t)lrint(x * 32767.0);
    }
    const int leashes[] = {8, 16, 32, 64, 128};
    const float stretches[] = {0.5f, 0.75f, 1.0f, 1.5f, 2.0f};
    for (int a = 0; a < 5; a++) for (int b = 0; b < 5; b++) {
        char fn[64];
        snprintf(fn, sizeof fn, "lc_%d_%d.raw", leashes[a], (int)(stretches[b] * 100));
        FILE *f = fopen(fn, "wb");
        memset(&rec, 0, sizeof rec);
        cc_recorder_init(&rec, storage, RING);
        cc_recorder_set_fade(&rec, 960);
        cc_recorder_set_leash(&rec, leashes[a]);
        cc_recorder_set_stretch(&rec, stretches[b]);
        cc_recorder_set_pitch(&rec, 1.0f);
        cc_recorder_source(&rec, (uintptr_t)smp, 0, LEN, 0);    /* looped: steady */
        float o[B];
        for (int k = 0; k < 2 * 48000 / B; k++) { cc_recorder_process(&rec, NULL, o, B); fwrite(o, sizeof o, 1, f); }
        fclose(f);
    }
    return 0;
}
