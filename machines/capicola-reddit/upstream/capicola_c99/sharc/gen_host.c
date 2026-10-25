/* gen_host.c -- dt2gen.c on the host, replaying a voice record the runner dumped
   (work/selcc_out/gen_rec.txt: 118 voice-record words, then 55 parameter-record
   words, hex) on the same int16 sample (work/selcc_out/gen_sample.i16); prints
   each block's 32 outputs as hex bits.
     cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -DCC_FASTPATH -DGEN_HOST gen_host.c -lm -o gen_host */
#include <stdio.h>
#include <stdlib.h>
#include "dt2gen.c"

static uint32_t vrec[NVOICE * VOICE_STRIDE / 4], prec[NVOICE * PARAM_STRIDE / 4];
static int16_t smp[1 << 20];   /* the left sample at 0x310000, the right one (STEREO) at 0x330000 */
uintptr_t gen_host_voice0 = (uintptr_t)vrec, gen_host_param0 = (uintptr_t)prec;
uintptr_t gen_host_sample(uint32_t w) { return (uintptr_t)smp + (w - (w >= 0x80000000u ? 0x8422B9E8u : 0x310000u)); }
uint32_t gen_host_page_sel, gen_host_page[2][0x400];
float gen_host_bpm = 120.0f;
static long fast_sum;

int main(int argc, char **argv)
{
    int blocks = atoi(argv[1]);
    FILE *f = fopen(argv[2], "r");
    for (int i = 0; i < 0x1d8 / 4; i++) if (fscanf(f, "%x", &vrec[i]) != 1) return 1;
    for (int i = 0; i < 0xdc / 4; i++) if (fscanf(f, "%x", &prec[i]) != 1) return 1;
    const int stereo = getenv("STEREO") != NULL;   /* voice 1 = the right channel, from lines 3-4 */
    {
        static uint32_t vr1[0x1d8 / 4], pr1[0xdc / 4];
        int ok = 1;
        for (int i = 0; i < 0x1d8 / 4; i++) if (fscanf(f, "%x", &vr1[i]) != 1) ok = 0;
        for (int i = 0; i < 0xdc / 4; i++) if (fscanf(f, "%x", &pr1[i]) != 1) ok = 0;
        if (stereo) {
            if (!ok) return 1;
            memcpy(&vrec[0x1d8 / 4], vr1, sizeof vr1);
            memcpy(&prec[0xdc / 4], pr1, sizeof pr1);
        }
        /* line 5 (optional): the firmware's tempo float (0x252d50) and the track's
           receive page words 0xdc and 0xe8 (slots 2 and 6 in their high halves) */
        uint32_t bpm, w2, w6;
        if (ok && fscanf(f, "%x %x %x", &bpm, &w2, &w6) == 3) {
            memcpy(&gen_host_bpm, &bpm, 4);
            for (int p = 0; p < 2; p++) {
                gen_host_page[p][0xdc >> 2] = w2;
                gen_host_page[p][0xe8 >> 2] = w6;
            }
        }
    }
    fclose(f);
    f = fopen(argv[3], "rb");
    size_t ns = fread(smp, 2, sizeof smp / 2, f);
    fclose(f);
    (void)ns;
    if (getenv("CAPI")) {   /* as dt2trace_gen.py pokes it: slot 2 of the voice's track, both pages */
        /* the replayed record is voice 0 here, whatever track the runner used */
        for (int p = 0; p < 2; p++) gen_host_page[p][0xdc >> 2] = (uint32_t)(atoi(getenv("CAPI")) << 8) << 16;
    }
    if (getenv("HTUNE")) {   /* TUNE in semitones on both voices' parameter records (word 0 = TUNE / 128, 0.5 = centre) */
        const float t = (64.0f + (float)atof(getenv("HTUNE"))) / 128.0f;
        memcpy(&prec[0], &t, 4);
        memcpy(&prec[0xdc / 4], &t, 4);
    }
    if (getenv("HEND")) {   /* the note's END (voice record words 0x68/0x69, Q31), both voices */
        const uint32_t e = (uint32_t)atoi(getenv("HEND"));
        for (int v2 = 0; v2 < 2; v2++) { vrec[v2 * (0x1d8 / 4) + 0x68] = (e & 1u) << 31; vrec[v2 * (0x1d8 / 4) + 0x69] = e >> 1; }
    }
    if (getenv("HPLAY")) {   /* 0 forward, 1 reverse, 2 forward loop, 3 reverse loop: the flags, PHASE seeded as the firmware */
        const int pm = atoi(getenv("HPLAY"));
        const int rv = (pm & 1) != 0, lp = (pm & 2) != 0;
        for (int v2 = 0; v2 < 2; v2++) {
            uint32_t *w = vrec + v2 * (0x1d8 / 4);
            w[0x6e] = (w[0x6e] & 0x00ffffffu) | ((uint32_t)rv << 24);
            w[0x6f] = (w[0x6f] & ~0xffu) | (uint32_t)lp;
            const uint32_t st = w[0x67] * 2u + (w[0x66] >> 31), en = w[0x69] * 2u + (w[0x68] >> 31);
            const uint32_t seed = rv ? en - 1u : st;
            w[0x6c] = (seed & 1u) << 31;
            w[0x6d] = seed >> 1;
        }
    }
    if (getenv("HSTRETCH")) {   /* the stretch ratio, voice record word 0x72 */
        const float t = (float)atof(getenv("HSTRETCH"));
        memcpy(&vrec[0x72], &t, 4);
        memcpy(&vrec[0x1d8 / 4 + 0x72], &t, 4);
    }
    float out[32];
    const char *rt = getenv("RETRIG");
    for (int b = 0; b < blocks; b++) {
        if (rt) {   /* the same trigs as dt2trace_gen.py: PHASE re-seeded at START */
            char key[16]; snprintf(key, sizeof key, ",%d,", b);
            char all[256]; snprintf(all, sizeof all, ",%s,", rt);
            if (strstr(all, key)) {
                vrec[0x6c] = vrec[0x66]; vrec[0x6d] = vrec[0x67];
                vrec[0x1d8 / 4 + 0x6c] = vrec[0x1d8 / 4 + 0x66]; vrec[0x1d8 / 4 + 0x6d] = vrec[0x1d8 / 4 + 0x67];
            }
        }
        for (int v = 0; v < (stereo ? 2 : 1); v++) {
            uint32_t *vr = vrec + v * (0x1d8 / 4);
            if (rt && v == 1) { /* the same trig on the right voice */ }
            const uint32_t mt = prec[v * (0xdc / 4) + 0x13];   /* the DSP's machine type: 3-5 the shared generator's */
            if (mt >= 3 && mt <= 5) cc_dt2_repitch(vr, out, 32); else cc_dt2_stretch(vr, out, 32);
            if (getenv("TAPEDUMP") && v == 0 && b == atoi(getenv("TAPEDUMP"))) {
                for (int i = 0; i < 9 * 32; i++) fprintf(stderr, "%u ", gen_tape_mem[i]);
                fprintf(stderr, "\n");
            }
            if (getenv("POS") && v == 0) {   /* the analyser's source position against the play head */
                const cc_recorder *r_ = &((gen_voice *)gen_mem)->rec;
                fprintf(stderr, "block %d src_pos %d head %.1f stretch %.3f pitch %.3f blend %.3f\n", b, (int)r_->src_pos,
                        (double)r_->granule[r_->live_g].ideal.index + (double)r_->sparse.origin - (double)r_->src_t0, r_->cur_stretch, r_->cur_pitch, r_->blend);
            }
            if (getenv("FASTSTAT") && v == 0) fast_sum += ((gen_voice *)gen_mem)->rec.fast_n;
            for (int i = 0; i < 32; i++) { uint32_t u; memcpy(&u, &out[i], 4); printf("%08x ", u); }
            printf("\n");
        }
    }
    if (getenv("FASTSTAT")) fprintf(stderr, "fast run: %.1f%% of voice 0's samples\n", 100.0 * (double)fast_sum / (32.0 * blocks));
#ifdef B_READSTAT
    { extern unsigned long b_reads, b_reads_int;
      fprintf(stderr, "reads %lu (%.2f per channel sample), at whole samples %.1f%%\n", b_reads,
              (double)b_reads / (32.0 * blocks * (stereo ? 2 : 1)), 100.0 * (double)b_reads_int / (double)(b_reads ? b_reads : 1)); }
#endif
    return 0;
}
