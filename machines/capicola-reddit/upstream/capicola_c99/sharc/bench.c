/*
 * bench.c -- a cost benchmark for the C99 Capicola core on the SHARC+ (selcc).
 * GNU AGPL-3.0, as Capicola.
 *
 * Run in digikit's runner, not on the instrument: cap_bench_init() once, then
 * cap_bench_block() per 32-sample block; the runner counts instructions per call.
 * All state lives in DSP DDR at 0x9e000000 (the region step 4.1 found unowned),
 * as it will in the real generator. Built with -DBENCH_HOST it is the host's
 * reference run of the same code (main() prints each block's output).
 *
 * mode bit 0: 0 = live effect (analyzer + detector + two grains, the heaviest
 *                 path), 1 = playback of a recording (two grains);
 * mode bit 1: 0 = white noise, 1 = the realistic test signal (kick, hat noise,
 *                 a chord; test/render.c's), which the caller has put at SIG as
 *                 SIG_LEN floats (the runner pokes it; the host reads a file).
 * modes 4..7 (build with -DBENCH_SRC, as the device: CC_SOURCE, leash -640, fade
 * 960): the signal as an int16 sample at SIG16 (poked / read like SIG), played
 * by cc_recorder_source with (stretch, pitch) = 4: (0.5, 1), 5: (1.5, 1),
 * 6: (1, 1.26), 7: (0.75, 0.8); a retrigger every 750 blocks. Mode 8: stereo,
 * (1.5, 1), a second engine at BENCH_BASE + 0x6000 on the sample from 1000
 * samples on, called after the first through the stereo link (-DCC_LINK), its
 * block at BENCH_BASE + 0xd00. Modes 9, 10 (-DCC_CLEAN): blend 0 at (1.5, 1)
 * and blend 0.5 at (0.75, 1.26).
 */
#ifdef BENCH_SRC
#include "../capicola.h"
#ifdef BENCH_HOST
static cc_link bench_link_mem;
#define CC_LINK_AT (&bench_link_mem)
#else
#define CC_LINK_AT ((cc_link *)0x9e300000u)
#define CC_CTX_AT  ((cc_recorder **)0x9e300100u)
#endif
#endif
#include "../capicola.c"   /* one translation unit: selcc returns structs wrongly across objects */

#define RING_SIZE    16384
#define BLOCK        32
#define SIG_LEN      48000
#define REC_BLOCKS   375          /* a 0.25 s recording for playback */

#ifdef BENCH_HOST
static unsigned char bench_mem[0x1000 + RING_SIZE * 16 + 0x8000] __attribute__((aligned(16)));
static float sig_mem[SIG_LEN];
#define BENCH_BASE ((uintptr_t)bench_mem)
#define SIG        sig_mem
static int16_t sig16_mem[SIG_LEN + 2];
#define SIG16      ((uintptr_t)sig16_mem)
#else
#define SIG16      0x9e200000u
#define BENCH_BASE 0x9e000000u
#define SIG        ((const float *)0x9e100000u)
#endif

static uint32_t rng_state;
static int sig_pos, use_sig;

static float noise(void)
{
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return (float)(int32_t)rng_state * (1.0f / 2147483648.0f);
}

static void fill(float *in)
{
    for (int i = 0; i < BLOCK; i++) {
        if (use_sig) {
            in[i] = SIG[sig_pos];
            if (++sig_pos == SIG_LEN) sig_pos = 0;
        } else {
            in[i] = noise() * 0.5f;
        }
    }
}

static int blocks_done, src_mode;   /* BENCH_SRC */

int cap_bench_init(int mode)
{
#ifdef BENCH_SRC
    {
        static const float S[4] = {0.5f, 1.5f, 1.0f, 0.75f}, P[4] = {1.0f, 1.0f, 1.26f, 0.8f};
        cc_recorder *r = (cc_recorder *)BENCH_BASE;
        cc_keyframe *ring = (cc_keyframe *)(BENCH_BASE + 0x1000u);
        src_mode = mode;
        blocks_done = 0;
        cc_recorder_init(r, ring, 2048);
        cc_recorder_set_fade(r, 960.0f);
        cc_recorder_set_leash(r, -640);
        cc_recorder_set_stretch(r, mode == 8 ? 1.5f : mode == 9 ? 1.5f : mode == 10 ? 0.75f : S[(mode - 4) & 3]);
        cc_recorder_set_pitch(r, mode == 8 ? 1.0f : mode == 9 ? 1.0f : mode == 10 ? 1.26f : P[(mode - 4) & 3]);
#ifdef CC_CLEAN
        if (mode == 9) cc_recorder_set_blend(r, 0.0f);
        if (mode == 10) cc_recorder_set_blend(r, 0.5f);
#endif
        if (mode == 8) {
            cc_recorder *r2 = (cc_recorder *)(BENCH_BASE + 0x6000u);
            cc_recorder_init(r2, (cc_keyframe *)(BENCH_BASE + 0x7000u), 2048);
            cc_recorder_set_fade(r2, 960.0f);
            cc_recorder_set_leash(r2, -640);
            cc_recorder_set_stretch(r2, 1.5f);
            cc_recorder_set_pitch(r2, 1.0f);
        }
        return (int)r->state;
    }
#else
    cc_recorder *r = (cc_recorder *)BENCH_BASE;
    cc_keyframe *ring = (cc_keyframe *)(BENCH_BASE + 0x1000u);
    float *in = (float *)(BENCH_BASE + 0x800u);
    float *out = (float *)(BENCH_BASE + 0xc00u);
    rng_state = 12345;
    sig_pos = 0;
    use_sig = (mode & 2) != 0;
    cc_recorder_init(r, ring, RING_SIZE);
    cc_recorder_set_fade(r, 960.0f);
    cc_recorder_set_leash(r, 128);
    cc_recorder_set_transient_threshold(r, 2.0f);
    cc_recorder_set_tkeo_cutoff(r, 0.0014f);
    cc_recorder_set_pitch(r, 1.25f);
    cc_recorder_set_stretch(r, 0.5f);
    if (mode & 1) {
        cc_recorder_submit(r, CC_REQ_RECORD);
        for (int b = 0; b < (use_sig ? REC_BLOCKS : 64); b++) {
            fill(in);
            cc_recorder_process(r, in, out, BLOCK);
        }
        cc_recorder_submit(r, CC_REQ_STOP_REC);
        cc_recorder_process(r, in, out, BLOCK);
        cc_recorder_submit(r, CC_REQ_PLAY);
    } else {
        cc_recorder_submit(r, CC_REQ_LIVE_EFFECT);
    }
    return (int)r->state;
#endif
}

/* One 32-sample block (output at BENCH_BASE + 0xc00); returns the keyframe count. */
int cap_bench_block(void)
{
    cc_recorder *r = (cc_recorder *)BENCH_BASE;
    float *in = (float *)(BENCH_BASE + 0x800u);
    float *out = (float *)(BENCH_BASE + 0xc00u);
#ifdef BENCH_SRC
    (void)in;
    if (src_mode == 8) {
        cc_recorder *r2 = (cc_recorder *)(BENCH_BASE + 0x6000u);
        if (blocks_done % 750 == 0) {
            cc_recorder_source(r, SIG16, 0, SIG_LEN, -1);
            cc_recorder_source(r2, SIG16 + 2000u, 0, SIG_LEN - 1000, -1);
        }
        blocks_done++;
#ifdef CC_LINK
        cc_link *lk = CC_LINK_AT;
        lk->mode = 1; lk->n = 0; lk->voice = 0;
#endif
        cc_recorder_process(r, (const float *)0, out, BLOCK);
#ifdef CC_LINK
        lk->mode = 2; lk->k = 0;
#endif
        cc_recorder_process(r2, (const float *)0, (float *)(BENCH_BASE + 0xd00u), BLOCK);
#ifdef CC_LINK
        lk->mode = 0;
#endif
        return (int)r2->analyzer.sparse_count;
    }
    if (blocks_done % 750 == 0) cc_recorder_source(r, SIG16, 0, SIG_LEN, -1);
    blocks_done++;
    cc_recorder_process(r, (const float *)0, out, BLOCK);
    return (int)r->analyzer.sparse_count;
#else
    fill(in);
    cc_recorder_process(r, in, out, BLOCK);
    return (int)r->analyzer.sparse_count;
#endif
}

#ifdef BENCH_HOST
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
/* bench_host MODE BLOCKS [SIGFILE]: one line per block, "keyframes out0..out31" as hex bits */
int main(int argc, char **argv)
{
    int mode = atoi(argv[1]), blocks = atoi(argv[2]);
    if (argc > 3) { FILE *f = fopen(argv[3], "rb"); if (!f || fread(sig_mem, 4, SIG_LEN, f) != SIG_LEN) return 1; fclose(f); }
    for (int i = 0; i < SIG_LEN; i++) {   /* as dt2trace_bench.py pokes it */
        float v = sig_mem[i] * 32767.0f;
        sig16_mem[i] = (int16_t)(v >= 32767.0f ? 32767 : v <= -32768.0f ? -32768 : (int)lrintf(v));
    }
    cap_bench_init(mode);
    const uint32_t *o = (const uint32_t *)(BENCH_BASE + 0xc00u);
    for (int b = 0; b < blocks; b++) {
        int k = cap_bench_block();
        printf("%d", k);
        for (int i = 0; i < BLOCK; i++) printf(" %08x", o[i]);
        if (mode == 8) for (int i = 0; i < BLOCK; i++) printf(" %08x", o[64 + i]);
        printf("\n");
    }
    return 0;
}
#endif
