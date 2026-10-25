/* quality_check.c -- CC_SOURCE STRETCH quality over leash settings and stretch
   ratios, pitch 1: a tonal sample (partials 110, 220, 277.18, 330, 440 Hz) and a
   drum sample (a kick every 0.25 s), each rendered for 3 s to qc_<sig>_<cfg>_<s>.raw.
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -I.. quality_check.c ../capicola.c -lm -o quality_check */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "capicola.h"

#define RING 4096
#define B 32
#define LEN (48000 * 4)
static cc_keyframe storage[RING];
static cc_recorder rec;
static int16_t tonal[LEN + 2], drum[LEN + 2];
static uint32_t rng = 777;
static float noise(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (rng / 4294967296.0f) * 2 - 1; }

int main(int argc, char **argv)
{
    const double P[5] = {110, 220, 277.18, 330, 440};
    for (int i = 0; i < LEN; i++) {
        double t = i / 48000.0, x = 0, tb = fmod(t, 0.25);
        for (int k = 0; k < 5; k++) x += 0.12 * sin(2 * M_PI * P[k] * t + k);
        tonal[i] = (int16_t)lrint(x * 32767);
        double d = 0.7 * exp(-tb * 30) * sin(2 * M_PI * (45 + 150 * exp(-tb * 50)) * tb);   /* kicks only: clean onsets */
        drum[i] = (int16_t)lrint(d * 32767);
    }
    {   FILE *f = fopen("qc_tonal_input.raw", "wb");
        for (int i = 0; i < 3 * 48000; i++) { float v = tonal[i] / 32768.0f; fwrite(&v, 4, 1, f); }
        fclose(f); }
    int cfgs[16] = {8, 32, 128, -480, -960, -1920, -2880}, ncfg = 7;
    if (argc > 1) { ncfg = 0; for (int i = 1; i < argc && ncfg < 16; i++) cfgs[ncfg++] = atoi(argv[i]); }
    const float st[] = {0.5f, 0.8f, 1.25f, 1.6f, 2.0f, 3.0f, 1.0f};
    for (int sg = 0; sg < 2; sg++) for (int c = 0; c < ncfg; c++) for (int k = 0; k < 7; k++) {
        char fn[96];
        snprintf(fn, sizeof fn, "qc_%s_%d_%d.raw", sg ? "drum" : "tonal", cfgs[c], (int)(st[k] * 100));
        FILE *f = fopen(fn, "wb");
        memset(&rec, 0, sizeof rec);
        cc_recorder_init(&rec, storage, RING);
        cc_recorder_set_fade(&rec, 960);
        cc_recorder_set_leash(&rec, cfgs[c]);
        cc_recorder_set_stretch(&rec, st[k]);
        cc_recorder_set_pitch(&rec, getenv("QC_PITCH") ? (float)atof(getenv("QC_PITCH")) : 1.0f);
        cc_recorder_source(&rec, (uintptr_t)(sg ? drum : tonal), 0, LEN, 0);
        if (getenv("QC_BLEND")) cc_recorder_set_blend(&rec, (float)atof(getenv("QC_BLEND")));
        float o[B];
        const int extra = getenv("QC_EXTRA") ? atoi(getenv("QC_EXTRA")) : 0x7fffffff;   /* lookahead budget per block */
        for (int b = 0; b < 3 * 48000 / B; b++) { rec.feed_extra = extra; cc_recorder_process(&rec, NULL, o, B); fwrite(o, sizeof o, 1, f); }
        fclose(f);
    }
    return 0;
}
