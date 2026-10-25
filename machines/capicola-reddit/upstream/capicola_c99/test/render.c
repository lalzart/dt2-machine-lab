/* render.c -- the C port alone, on compare.cpp's scenarios, written as raw floats
   to argv[1]. Built twice (double, -DCC_F32) and compared by f32cmp.py:
     cc -std=c99 -O2 -ffp-contract=off [-DCC_F32] -I.. render.c ../capicola.c -lm -o render */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "capicola.h"

#define RING (1 << 16)
#define B 64
static cc_keyframe storage[RING];
static cc_recorder port;

static uint32_t rng = 12345;
static float noise(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (rng / 4294967296.0f) * 2 - 1; }

static float *test_signal(int n)
{
    float *x = malloc(sizeof(float) * n);
    for (int i = 0; i < n; i++) {
        double t = (double)i / 48000, tb = fmod(t, 0.5), th = fmod(t, 0.125);
        x[i] = (float)(0.5 * exp(-tb * 20) * sin(2 * M_PI * (50 + 200 * exp(-tb * 40)) * tb)
                       + 0.1 * exp(-th * 80) * noise()
                       + 0.1 * (sin(2 * M_PI * 220 * t) + sin(2 * M_PI * 277 * t) + sin(2 * M_PI * 330 * t)));
    }
    return x;
}

int main(int argc, char **argv)
{
    FILE *f = fopen(argv[1], "wb");
    const float pitches[] = {1.0f, 1.5f, 0.75f, 2.0f, 0.5f, 1.25f};
    const float stretches[] = {1.0f, 0.5f, 0.25f, 0.8f, 0.33f};
    float o[B];
    {   /* A: live effect, 8 s, pitch and stretch changing every 0.5 s */
        int n = 48000 * 8;
        float *x = test_signal(n);
        cc_recorder_init(&port, storage, RING);
        cc_recorder_set_fade(&port, 960); cc_recorder_set_leash(&port, 128);
        cc_recorder_set_transient_threshold(&port, 2.0f); cc_recorder_set_tkeo_cutoff(&port, 0.0014f);
        cc_recorder_submit(&port, CC_REQ_LIVE_EFFECT);
        for (int k = 0, blk = 0; k + B <= n; k += B, blk++) {
            if (blk % 375 == 0) {
                cc_recorder_set_pitch(&port, pitches[(blk / 375) % 6]);
                cc_recorder_set_stretch(&port, stretches[(blk / 375) % 5]);
            }
            cc_recorder_process(&port, &x[k], o, B);
            fwrite(o, sizeof o, 1, f);
        }
        free(x);
        if (argc > 2) {
            FILE *k = fopen(argv[2], "w");
            for (long i = 0; i < (long)port.sparse.write_pos && i < RING; i++)
                fprintf(k, "%ld %.9g %.6f\n", i, port.sparse.buf[i].value, (double)port.sparse.buf[i].time + (double)port.sparse.origin);
            fclose(k);
        }
    }
    {   /* B: record 3 s, then play 5 s stretched and pitched, with slices */
        int n = 48000 * 3;
        float *x = test_signal(n);
        float silence[B] = {0};
        cc_recorder_init(&port, storage, RING);
        cc_recorder_submit(&port, CC_REQ_RECORD);
        for (int k = 0; k + B <= n; k += B) cc_recorder_process(&port, &x[k], o, B);
        cc_recorder_submit(&port, CC_REQ_STOP_REC);
        cc_recorder_process(&port, &x[0], o, B);
        cc_recorder_set_stretch(&port, 0.5f); cc_recorder_set_pitch(&port, 1.25f); cc_recorder_set_fade(&port, 960);
        cc_recorder_submit(&port, CC_REQ_PLAY);
        for (int blk = 0; blk < 48000 * 5 / B; blk++) {
            if (blk % 200 == 199) cc_recorder_submit(&port, CC_REQ_SLICE);
            cc_recorder_process(&port, silence, o, B);
            fwrite(o, sizeof o, 1, f);
        }
        free(x);
    }
    fclose(f);
    printf("transients %u, origin %lld\n", port.transient_count, (long long)port.sparse.origin);
    return 0;
}
