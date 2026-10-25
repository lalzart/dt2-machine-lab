/* pluck_check.c -- CC_SOURCE on a plucky high-pitched loop (decaying notes at
   1.2-3 kHz with harmonics), REPITCH-style (stretch = pitch = rate) at rates
   0.8, 1.0, 1.25; writes pk_input.raw and pk_<rate*100>.raw (float32, 2 s).
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -DCC_ALIGN=8 -I.. pluck_check.c ../capicola.c -lm */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "capicola.h"

#define RING 8192
#define B 32
#define LEN (48000 * 4)
static cc_keyframe ring[RING];
static cc_recorder rec;
static int16_t smp[LEN + 2];

int main(void)
{
    const double notes[8] = {1200, 1500, 1800, 2400, 1350, 2000, 2700, 3000};
    for (int i = 0; i < LEN; i++) {
        double t = i / 48000.0, step = 0.125;
        int k = (int)(t / step);
        double tn = t - k * step, f = notes[k % 8], x = 0;
        for (int h = 1; h <= 6; h++)
            if (f * h < 20000) x += (0.5 / h) * exp(-tn * (25 + 12 * h)) * sin(2 * M_PI * f * h * tn);
        smp[i] = (int16_t)lrint(0.6 * x * 32767);
    }
    FILE *f = fopen("pk_input.raw", "wb");
    for (int i = 0; i < LEN; i++) { float v = smp[i] / 32768.0f; fwrite(&v, 4, 1, f); }
    fclose(f);
    const float rates[3] = {0.8f, 1.0f, 1.25f};
    for (int r = 0; r < 3; r++) {
        char fn[32];
        snprintf(fn, sizeof fn, "pk_%d.raw", (int)(rates[r] * 100));
        f = fopen(fn, "wb");
        memset(&rec, 0, sizeof rec);
        cc_recorder_init(&rec, ring, RING);
        cc_recorder_set_fade(&rec, 960); cc_recorder_set_leash(&rec, -640);
        cc_recorder_set_stretch(&rec, rates[r]); cc_recorder_set_pitch(&rec, rates[r]);
        cc_recorder_source(&rec, (uintptr_t)smp, 0, LEN, 0);
        if (getenv("QC_BLEND")) cc_recorder_set_blend(&rec, (float)atof(getenv("QC_BLEND")));
        float o[B];
        for (int b = 0; b < 2 * 48000 / B; b++) { cc_recorder_process(&rec, NULL, o, B); fwrite(o, sizeof o, 1, f); }
        fclose(f);
    }
    return 0;
}
