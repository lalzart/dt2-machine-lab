/* source.c -- CC_SOURCE on the host: the realistic signal (render.c's) as a 16-bit
   sample, played in several scenarios; each scenario's output goes to
   src_<name>.raw (float32) for source_check.py.
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -I.. source.c ../capicola.c -lm -o source */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
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

static int leash = 128;
static void run(const char *name, float stretch, float pitch, int seconds, int retrig_every, int32_t end, int32_t loop)
{
    char fn[64];
    snprintf(fn, sizeof fn, "src_%s.raw", name);
    FILE *f = fopen(fn, "wb");
    memset(&rec, 0, sizeof rec);
    cc_recorder_init(&rec, storage, RING);
    cc_recorder_set_fade(&rec, 960); cc_recorder_set_leash(&rec, leash);
    cc_recorder_set_stretch(&rec, stretch); cc_recorder_set_pitch(&rec, pitch);
    float o[B];
    int blocks = seconds * 48000 / B;
    double worst_jump = 0;
    float prev = 0;
    for (int b = 0; b < blocks; b++) {
        if (b == 0 || (retrig_every && b % retrig_every == 0))
            cc_recorder_source(&rec, (uintptr_t)smp, 0, end, loop);
            if (getenv("QC_BLEND")) cc_recorder_set_blend(&rec, (float)atof(getenv("QC_BLEND")));
        cc_recorder_process(&rec, NULL, o, B);
        for (int i = 0; i < B; i++) {
            if (!isfinite(o[i])) { printf("%s: non-finite at %d\n", name, b * B + i); exit(1); }
            double j = fabs((double)o[i] - prev); if (j > worst_jump) worst_jump = j; prev = o[i];
        }
        fwrite(o, sizeof o, 1, f);
    }
    fclose(f);
    printf("%-10s stretch %.2f pitch %.2f: %d s, largest step between samples %.3f, keyframes %ld, state %d\n",
           name, stretch, pitch, seconds, worst_jump, (long)rec.analyzer.sparse_count, rec.src_state);
}

int main(void)
{
    for (int i = 0; i < LEN; i++) {
        double t = (double)i / 48000, tb = fmod(t, 0.5), th = fmod(t, 0.125);
        double x = 0.5 * exp(-tb * 20) * sin(2 * M_PI * (50 + 200 * exp(-tb * 40)) * tb)
                 + 0.1 * exp(-th * 80) * noise()
                 + 0.1 * (sin(2 * M_PI * 220 * t) + sin(2 * M_PI * 277 * t) + sin(2 * M_PI * 330 * t));
        smp[i] = (int16_t)lrint(x * 32767.0);
    }
    FILE *f = fopen("src_input.raw", "wb");
    for (int i = 0; i < LEN; i++) { float v = smp[i] / 32768.0f; fwrite(&v, 4, 1, f); }
    fclose(f);
    run("unity",   1.0f, 1.0f, 2, 0, LEN, -1);
    run("slow",    0.5f, 1.0f, 3, 0, LEN, -1);
    run("fast",    2.0f, 1.0f, 1, 0, LEN, -1);
    run("pitch",   1.0f, 1.5f, 2, 0, LEN, -1);
    run("pdown",   1.0f, 0.75f, 2, 0, LEN, -1);
    run("retrig",  1.0f, 1.0f, 2, 375, LEN, -1);    /* every 0.25 s */
    run("loop",    1.0f, 1.0f, 2, 0, 24000, 0);     /* the first 0.5 s, looped */
    for (int k = 0; k < 3; k++) {
        static const int L[3] = {32, 16, 8};
        char n1[16], n2[16];
        leash = L[k];
        snprintf(n1, sizeof n1, "slow_l%d", leash); snprintf(n2, sizeof n2, "fast_l%d", leash);
        run(n1, 0.5f, 1.0f, 3, 0, LEN, -1);
        run(n2, 2.0f, 1.0f, 1, 0, LEN, -1);
    }
    return 0;
}
