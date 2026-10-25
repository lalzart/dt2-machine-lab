/*
 * dt2gen.c -- Capicola as the Digitakt II STRETCH, REPITCH, GRID and SLICE generators
 * (OS 1.16 and 1.17: their DSP images are the same), one voice per call. GNU AGPL-3.0, as Capicola. Build: -DCC_F32 -DCC_ASM
 * -DCC_SOURCE_ONLY -DCC_ALIGN=8 -DCC_LINK -DCC_CLEAN, with render.asm, feed.asm and dt2entry.asm (the firmware
 * calls dt2entry's entries, which save what selcc does not and, for the shared
 * generator's call site, send every machine type but REPITCH, GRID and SLICE to
 * the stock code).
 *
 *   void cc_dt2_stretch(uint32_t *rec, float *out, int n)    R4, R8, R12 (n = 32)
 *   void cc_dt2_repitch(uint32_t *rec, float *out, int n)
 *
 * STRETCH: stretch = w72, pitch = 2^(TUNE/12) (full range).
 * All: CAPI, the SRC page's slot after PLAY (firmware/build_cap.py exposes it),
 * switches between the stock machine (off: dt2entry.asm jumps to the stock code)
 * and ours. The DSP keeps only an on/off copy (parameter record word 4), so GRID's
 * and SLICE's three-way value is read from the command frame's receive page,
 * word 0xde + 0x60 * track.
 * REPITCH: stretch = pitch = 2 * STEP (w6a/w6b, Q31 per 96 kHz sample, so per
 * 48 kHz sample twice that): the stock varispeed rate from BARS, LEN and the
 * master tempo, so pitch follows tempo as on the stock machine.
 * GRID and SLICE (the shared generator's call too, cc_dt2_repitch): CAPI is a
 * three-way there (0 off, 1 REPITCH's way, 2 STRETCH's way), the speed the whole
 * sample's at the tempo over SLICE's BARS or GRID's grid (gen_slice_speed).
 *
 * From the voice record (byte address rec; words, traced in digikit's runner):
 *   w0         the channel's samples: byte address, int16, planar
 *   w66/w67    START, w68/w69 END: Q31 sample positions, low word first
 *   w6c/w6d    PHASE: the firmware seeds it on a trig. We write back the play
 *              position (the grid head) with a marker in the low fraction bits,
 *              so a PHASE that is not exactly what we wrote is a new trig
 *   w72        float: source samples per output sample, from BARS, LEN and the
 *              master tempo (the setter at 0x1c4d88 writes it every frame)
 *   byte 0x1b8 ACTIVE
 * From the voice's parameter record (0x2506ec + v * 0xdc): w0 = TUNE / 128
 * (0.5 = centre), used unclamped (the stock STRETCH floors it at -4 semitones).
 *
 * State per voice: its gen_voice (a cc_recorder) in L2 at 0x20080000 + v * 0x400,
 * its 2048-keyframe ring in DSP DDR at 0x9e000000 + v * SLOT + 0x400;
 * initialised on first use (a magic word).
 */
/* the stereo link's record (capicola.h, CC_LINK) after the 32 voice states */
#include "../capicola.h"
/* The stereo tape (capicola.c tape_add/tape_mix, render.asm): a track's left
   voice at CAPI 0 records, per output sample, the indices its clean reads used
   and their final mixing weights (up to four), 9 words a sample; its right voice
   replays them on its own channel instead of running Capicola again. */
#define TAPE_WORDS (9 * 32)
typedef struct { int32_t voice, n; } gen_tape_info;   /* who recorded this frame, how many samples */
#ifdef GEN_HOST
static uint32_t gen_tape_mem[TAPE_WORDS];
static uint32_t *gen_tape_slot, *gen_tape_buf;
static gen_tape_info gen_tape_info_mem = { -1, 0 };
#define GEN_TAPE      gen_tape_mem
#define CC_TAPE_AT    (&gen_tape_slot)
#define CC_TAPE_BUF_AT (&gen_tape_buf)
#define GEN_TAPE_INFO (&gen_tape_info_mem)
#else
/* L1 block 1 after the code (l1l2.ldf ends the code at 0x2de9af): the tape
   0x2de9b0..0x2dee30, then its slot pointer (render.asm writes it per sample for
   the C fallback), the buffer pointer (0: not recording) and the record's info */
#define GEN_TAPE      ((uint32_t *)0x2de9b0u)
#define CC_TAPE_AT    ((uint32_t **)0x2dee30u)
#define CC_TAPE_BUF_AT ((uint32_t **)0x2dee34u)
#define GEN_TAPE_INFO ((gen_tape_info *)0x2dee38u)
#endif
#ifdef GEN_HOST
static cc_link gen_link_mem;
#define CC_LINK_AT (&gen_link_mem)
static cc_recorder *gen_ctx_mem;
#define CC_CTX_AT (&gen_ctx_mem)
#define GEN_FRAME (&gen_frame_mem)
extern uint32_t gen_host_page_sel, gen_host_page[2][0x400];   /* the host test's receive pages */
#define PAGE_SEL   (gen_host_page_sel)
#define PAGE_WORD(sel, off) (gen_host_page[(sel)][(off) >> 2])
extern float gen_host_bpm;
#define GEN_BPM    (gen_host_bpm)
#else
/* On-chip working memory, L1 block 1 after the code (l1_diag.ldf ends the code at
   0x2deeaf; build_cap.py loads our range up to 0x2df000): the stereo link, the
   clean read's context, the lookahead budget and GEN_DIAG's figures. Sizes on the
   SHARC. (The recorders stay in DDR: ubench measured a cached DDR load at 2.2
   cycles and a load from this block, which also holds the code, at 2, so copying
   a recorder here for each call cost more than it saved.) */
#define CC_LINK_AT ((cc_link *)0x2deeb0u)       /* 0x94 bytes */
#define CC_CTX_AT  ((cc_recorder **)0x2def44u)
#define GEN_FRAME  ((gen_frame *)0x2def48u)      /* 0x10 bytes */
/* (DIAG_AT, below: 0x2def58, 0x94 bytes, to 0x2defec) */
/* this frame's receive page: 0x264220 + (DM(0x261ca4) << 12), as the handler
   0x1c778a selects it (digiemu FINDINGS, "Page select") */
#define PAGE_SEL   (*(const volatile uint32_t *)0x261ca4u)
#define PAGE_WORD(sel, off) (*(const volatile uint32_t *)(0x264220u + ((sel) << 12) + (off)))
/* the tempo in BPM, as the firmware keeps it (its STRETCH and REPITCH speeds use it) */
#define GEN_BPM    (*(const volatile float *)0x252d50u)
#endif
#ifdef GEN_DIAG
static void gen_mark(int k);   /* the section since the previous mark, to section k */
#ifdef GEN_SECTIONS   /* the per-section timing (capload items 7-13): about 0.6k cycles a call */
#define CC_MARK(k) gen_mark(k)
#endif
static void gen_fed(uint32_t k);   /* samples analysed this call */
#define CC_FED(k) gen_fed((uint32_t)(k))
#endif
#include "../capicola.c"   /* one translation unit: selcc returns structs wrongly across objects */

#define NVOICE        32
#define VOICE_REC0    0x2412ccu
#define VOICE_STRIDE  0x1d8u
#define PARAM_REC0    0x2506ecu
#define PARAM_STRIDE  0xdcu
#define RING          2048
#define SLOT          0x5000u            /* 20 KB: recorder + ring + header */
#ifdef GEN_HOST
#define RING_OFF      0x800u             /* (64-bit pointers make gen_voice larger here) */
#else
#define RING_OFF      0x400u             /* gen_voice is 0x3fc bytes on the SHARC (gen_voice_fits) */
#endif
/* The state's "initialised" word: a layout version and the struct's size, so a
   slot left in DDR by another build (DRAM keeps it across a reflash) is
   initialised again rather than read with the wrong layout. Bump GEN_LAYOUT
   whenever gen_voice or cc_recorder changes. */
#define GEN_LAYOUT    13u
/* GEN_BUILD (build_gen.sh: a build stamp) makes every new image start from
   fresh state too: the r5 image shared GEN_LAYOUT and sizeof with the CAPI
   images flashed before it, resumed their state, and its right channels were
   noise until a build with a new layout initialised them again. */
#ifndef GEN_BUILD
#define GEN_BUILD     0u
#endif
#define GEN_MAGIC     (0xCA900000u ^ (GEN_LAYOUT << 16) ^ (uint32_t)sizeof(gen_voice) ^ (((uint32_t)(GEN_BUILD) & 0x1fffffu) << 11))
#define PHASE_MARK    0x00a5a5a5u        /* in the fraction bits of the PHASE we write */

#ifdef GEN_HOST
static unsigned char gen_mem[NVOICE * SLOT] __attribute__((aligned(16)));
#define STATE_BASE ((uintptr_t)gen_mem)
#define VOICE_STATE(v) (STATE_BASE + (uintptr_t)(v) * SLOT)
#define RING_AT(v)     (STATE_BASE + (uintptr_t)(v) * SLOT + RING_OFF)
extern uintptr_t gen_host_voice0, gen_host_param0;   /* the host test's records */
#define VOICE_BASE gen_host_voice0
#define PARAM_BASE gen_host_param0
extern uintptr_t gen_host_sample(uint32_t w);         /* a record's sample word -> host address */
#define SAMPLE_ADDR(w) gen_host_sample(w)
#else
#define SAMPLE_ADDR(w) ((uintptr_t)(w))
#define STATE_BASE 0x9e000000u
/* a voice's gen_voice (recorder included) in L2, where a cache miss costs about
   22 cycles against DDR's 52 (the memory probe, 2026-10-04: with a dozen voices
   playing, every call starts with its state out of the cache); its keyframe
   ring stays in DDR (32 x 16 KB does not fit the free L2). L2 0x20080000 +
   32 x 0x400: in the range the memtest image proved the firmware leaves alone. */
#define VOICE_STATE(v) (0x20080000u + (uintptr_t)(v) * 0x400u)
#define RING_AT(v)     (STATE_BASE + (uintptr_t)(v) * SLOT + RING_OFF)
#define VOICE_BASE VOICE_REC0
#define PARAM_BASE PARAM_REC0
#endif

/* The lookahead budget: per frame (a frame starts when the voice order restarts),
   GEN_FEED_BUDGET samples of analysis beyond what the heads need, shared by all
   voices; after a trig a track catches up over more blocks when others are
   catching up too, instead of every voice doing it in the same frame. A right
   voice gets the allowance its left voice got, so the two keep in step. */
#ifndef GEN_FEED_BUDGET
#define GEN_FEED_BUDGET 160
#endif
typedef struct { uint32_t last_v; int32_t budget, l_allow, l_voice; } gen_frame;

/* A retrigger's declick, in samples. The new note starts at once, as on the
   stock generators (PHASE seeded at START), and the step from the old note's last
   output sample fades out over this many samples (gen_declick), so the old note is
   not rendered at all (Capicola's trig_fade 0). A crossfade that renders it, as
   Capicola's 96 samples did, also replays its raw sample, which the amp envelope
   (after the generator, restarted at the trig) had decayed, at the new note's
   level: a click before the attack on short, plucked sounds. */
#ifndef GEN_RETRIG_FADE
#define GEN_RETRIG_FADE 16
#endif
#ifdef GEN_HOST
static gen_frame gen_frame_mem = { 0xffu, 0, 0, -1 };
#endif

typedef struct {
    uint32_t    magic;
    int32_t     playing;
    uint32_t    phase_lo, phase_hi;      /* what we wrote to PHASE last block */
    int32_t     start;                   /* the note's start sample */
    uint32_t    diag_calls, diag_trigs;  /* GEN_DIAG: voice 0's counters */
    uint32_t    bad_out;                 /* samples zeroed by the output guard */
    /* REPITCH at CAPI 0 (gen_repitch_clean): a plain varispeed read */
    int32_t     fast;                    /* 1 while it plays this way */
    int32_t     pair;                    /* 1 while a right voice replays its left's tape */
    int32_t     ipos, end;               /* the sample under the head; the note's end */
    float       frac;                    /* and the fraction past it */
    uintptr_t   src;                     /* the note's samples */
    uintptr_t   x_src;                   /* a right voice's previous note (gen_pair_replay) */
    float       last_out;                /* the last output sample, for gen_declick */
    int32_t     retrig;                  /* this block starts a note over a playing one */
    int32_t     bmode;                   /* GEN_WSOLA: 1 while this voice plays the analysis-free way */
    cc_recorder rec;
} gen_voice;

/* 2^x for |x| <= 4 or so: an integer power and a degree-5 polynomial on [0, 1). */
static float gen_exp2(float x)
{
    int k = (int)x;
    if ((float)k > x) k--;
    const float f = x - (float)k;
    float p = 1.0f + f * (0.6931472f + f * (0.2402265f + f * (0.0555041f + f * (0.0096181f + f * 0.0013333f))));
    for (; k > 0; k--) p *= 2.0f;
    for (; k < 0; k++) p *= 0.5f;
    return p;
}

static int32_t q31_pos(const uint32_t *rec, int w)   /* a Q31 position's whole samples */
{
    return (int32_t)(rec[w + 1] * 2u + (rec[w] >> 31));
}

static void gen_zero(float *out, int n)
{
    for (int i = 0; i < n; i++) out[i] = 0.0f;
}

/* A retrigger: the step from the old note's last sample fades out over
   GEN_RETRIG_FADE samples; then the last sample for the next block's */
static void gen_declick(gen_voice *g, float *out, int n)
{
    if (g->retrig) {
        const float dw = (g->last_out - out[0]) * (1.0f / (float)(GEN_RETRIG_FADE + 1));
        float w = dw * (float)GEN_RETRIG_FADE;   /* the step's share left: FADE/(FADE+1) .. 1/(FADE+1) */
        int m = GEN_RETRIG_FADE;
        if (m > n) m = n;
        for (int i = 0; i < m; i++) { out[i] += w; w -= dw; }
        g->retrig = 0;
    }
    g->last_out = out[n - 1];
}

static void gen_phase_out(gen_voice *g, uint32_t *rec, int32_t pos)
{
    if (pos < g->start) pos = g->start;
    g->phase_lo = ((uint32_t)pos << 31) | PHASE_MARK;
    g->phase_hi = (uint32_t)pos >> 1;
    rec[0x6c] = g->phase_lo;
    rec[0x6d] = g->phase_hi;
}

#ifndef GEN_WSOLA   /* (plan B plays REPITCH itself: gen_wsola) */
/* n samples of a plain varispeed read of src from *ipos + *frac, stepping by
   rate: the clean read (render.asm's, capicola.c's rec_clean_read on the host)
   with the recorder's source fields pointed at this note, the block's first
   sample as its start so the index stays small */
static void gen_vari(cc_recorder *r, uintptr_t src, int32_t start, int32_t end,
                     int32_t *ipos, float *frac, float rate, float *out, int n)
{
    /* the clean read treats samples below its start as silence, and Catmull-Rom
       needs the one before the head: so its start is a sample before the block's
       first head where that is still in the note (index shifted to match), else
       the note's own start */
    int32_t base = *ipos;
    float shift = 0.0f;
    if (base - 1 >= start) { base -= 1; shift = 1.0f; }
    r->src = src;
    r->src_start = base;
    r->src_end = end;
    r->src_t0 = 0;
    r->sparse.origin = 0;
    r->prev_valid = 0;
    int32_t j = 0;
    float f = *frac;
    for (int i = 0; i < n; i++) {
        out[i] = CLEAN_READ(r, (float)j + f + shift);
        f += rate;
        const int32_t k = (int32_t)f;
        j += k;
        f -= (float)k;
    }
    *ipos += j;
    *frac = f;
}

/* REPITCH at CAPI 0. Capicola's grid and play head both move at the varispeed
   rate there, so it never splices: what it plays is this, a Catmull-Rom read of
   the sample stepping by the rate (and a crossfade on a retrigger), without the
   keyframe analysis or the grains. CAPI above 0 starts Capicola afresh at this
   head; back at 0 this takes over from Capicola's grid head. The recorder is
   only borrowed for its clean read's fields meanwhile. */
static int gen_repitch_clean(gen_voice *g, cc_recorder *r, uint32_t *rec, float *out, int n, uint32_t v)
{
    /* 2 * STEP = hi * 4 + lo / 2^30, as gen_run */
    const float rate = (float)(int32_t)rec[0x6b] * 4.0f + (float)(rec[0x6a] >> 8) * (1.0f / 4194304.0f);
    const uintptr_t src = SAMPLE_ADDR(rec[0]);
    int trig = 0;
    if (!g->playing) trig = 1;
    if (rec[0x6c] != g->phase_lo) trig = 1;
    if (rec[0x6d] != g->phase_hi) trig = 1;
    if (!g->fast) {
        if (!trig) {   /* from Capicola, mid-note: its grid head */
            const cc_granule *gl = &r->granule[r->live_g];
            g->ipos = g->start + (int32_t)((cc_idx)gl->ideal.index + r->sparse.origin - r->src_t0);
            g->frac = 0.0f;
            g->src = src;
            g->end = q31_pos(rec, 0x68);
        }
        g->fast = 1;
    }
    g->bmode = 0;
    if (trig) {
        g->retrig = g->playing;
        g->start = q31_pos(rec, 0x6c);
        g->end = q31_pos(rec, 0x68);
        g->ipos = g->start;
        g->frac = 0.0f;
        g->src = src;
        g->playing = 1;
        g->diag_trigs++;
    }
    CC_MARK(0);
    CC_MARK(2);
    gen_vari(r, g->src, g->start, g->end, &g->ipos, &g->frac, rate, out, n);
    for (int i = 0; i < n; i++) out[i] *= 0.4045f;   /* REPITCH's hand-over level (gen_run) */
    gen_declick(g, out, n);
    CC_MARK(4);
    gen_phase_out(g, rec, g->ipos);
    if (g->ipos >= g->end) {   /* past the note's end: ACTIVE cleared, as gen_wsola */
        const uint32_t w6e = rec[0x6e];
        rec[0x6e] = w6e & ~0xffu;
        g->playing = 0;
    }
    CC_MARK(5);
    return (int)v;
}

#endif

#ifndef GEN_WSOLA   /* (plan B: the left voice renders both channels, gen_pair_copy) */
/* A right voice at CAPI 0 on STRETCH, its left voice having recorded the tape
   this frame: out[i] = sum of weight * this channel's clean read at each index,
   the note mapping (start, end, the trig's stream time, the previous note's) the
   left voice's, the sample addresses this voice's. Its own Capicola is idle
   meanwhile (restarted afresh when the pairing ends). */
#if defined(CC_ASM) && !defined(GEN_HOST) && !defined(GEN_NO_ASM_REPLAY)
void cc_tape_replay(const cc_recorder *r, float *out, int n);   /* render.asm; the tape at GEN_TAPE */
#endif
static int gen_pair_replay(gen_voice *g, cc_recorder *r, uint32_t *rec, float *out, int n, uint32_t v, int machine)
{
    const gen_voice *gl = (const gen_voice *)VOICE_STATE(v - 1u);
    const cc_recorder *rl = &gl->rec;
    const uintptr_t src = SAMPLE_ADDR(rec[0]);
    int trig = 0;
    if (!g->playing) trig = 1;
    if (!g->pair) trig = 1;
    if (rec[0x6c] != g->phase_lo) trig = 1;
    if (rec[0x6d] != g->phase_hi) trig = 1;
    if (trig) {   /* this channel's note */
        g->retrig = g->playing;
        g->x_src = g->pair ? g->src : src;
        g->src = src;
        g->playing = 1;
        g->diag_trigs++;
    }
    g->start = gl->start;   /* the same note */
    g->pair = 1;
    g->bmode = 0;
    r->sparse.origin = rl->sparse.origin;
    r->src_t0 = rl->src_t0;
    r->src_start = rl->src_start;
    r->src_end = rl->src_end;
    r->prev_t0 = rl->prev_t0;
    r->prev_start = rl->prev_start;
    r->prev_end = rl->prev_end;
    r->prev_valid = rl->prev_valid;
    r->src = g->src;
    r->prev_src = g->x_src;
    r->b_lend = rl->b_lend;   /* plan B's loop */
    r->b_llen = rl->b_llen;
    r->b_k = rl->b_k;   /* (and its whole samples) */
    r->b_kf = rl->b_kf;
    r->b_lo = rl->b_lo;
    CC_MARK(0);
    CC_MARK(2);
#if defined(CC_ASM) && !defined(GEN_HOST) && !defined(GEN_NO_ASM_REPLAY)
    cc_tape_replay(r, out, n);   /* render.asm: the loop below, without a C call per read */
#else
    const uint32_t *tp = GEN_TAPE;
    for (int i = 0; i < n; i++) {
        const uint32_t *sl = tp + 9 * i;
        const float *e = (const float *)(sl + 1);
        int m = (int)sl[0];
        if (m > 4) m = 4;
        float y = 0.0f;
        for (int k = 0; k < m; k++) y += e[2 * k + 1] * CLEAN_READ(r, e[2 * k]);
        out[i] = y;
    }
#endif
    if (machine == 3) {
        for (int k = 0; k < n; k++) out[k] *= 0.4045f;   /* REPITCH's hand-over level */
    }
    gen_declick(g, out, n);
    CC_MARK(4);
    /* the play position: the left voice's (the same note, the same heads) */
    const cc_granule *gg = &rl->granule[rl->live_g];
    gen_phase_out(g, rec, gl->start + rl->b_k + (int32_t)((cc_idx)gg->ideal.index + rl->sparse.origin - rl->src_t0));
    GEN_TAPE_INFO->voice = -1;   /* used: a left voice that stops recording (CAPI off) leaves none behind */
    CC_MARK(5);
    return (int)v;
}
#endif

#ifdef GEN_WSOLA
/* the right channel of this frame's stereo pass (gen_wsola), where the tape was
   (0x2de9b0, 32 words); the pass's right recorder (0: none) and where cc_brun's
   run puts its samples at 0x2dee50 (not in the recorder: gen_voice fills its 0x400
   bytes) */
#define GEN_ROUT ((float *)GEN_TAPE)
typedef struct { void *rr; float *outr; int32_t rev; } gen_bpass;
#ifdef GEN_HOST
static gen_bpass gen_bpass_mem;
#define GEN_BPASS (&gen_bpass_mem)
#else
#define GEN_BPASS ((gen_bpass *)0x2dee50u)   /* (render.asm cc_brun, cc_bfast: rr, outr, rev) */
/* VOICE_STATE's slot. selcc does not reject a negative array size: build_gen.sh
   checks this with clang for a 32-bit target (the SHARC's layout) */
#ifndef GEN_VOICE_SLOT
#define GEN_VOICE_SLOT 0x400u
#endif
typedef char gen_voice_fits[(sizeof(gen_voice) <= GEN_VOICE_SLOT) ? 1 : -1];
/* render.asm's cc_bfast (plan B's ordinary blocks in assembly) uses these word
   offsets and addresses; checked here (by clang, build_gen.sh) so they cannot drift */
#define GEN_MAGIC_CELL ((volatile uint32_t *)0x2dee60u)   /* GEN_MAGIC, as gen_run last saw it */
#ifdef GEN_LAYOUT_CHECK   /* (clang only: selcc mishandles offsetof) */
#define GEN_AT(t, f, w) typedef char gen_at_##t##_##f[(offsetof(t, f) == 4u * (w)) ? 1 : -1];
#include <stddef.h>
GEN_AT(gen_voice, magic, 0) GEN_AT(gen_voice, playing, 1) GEN_AT(gen_voice, phase_lo, 2) GEN_AT(gen_voice, phase_hi, 3)
GEN_AT(gen_voice, start, 4) GEN_AT(gen_voice, pair, 9) GEN_AT(gen_voice, ipos, 10) GEN_AT(gen_voice, frac, 12)
GEN_AT(gen_voice, last_out, 15) GEN_AT(gen_voice, retrig, 16) GEN_AT(gen_voice, bmode, 17) GEN_AT(gen_voice, rec, 18)
GEN_AT(cc_recorder, blend, 217) GEN_AT(cc_recorder, src, 205) GEN_AT(cc_recorder, src_start, 218)
GEN_AT(cc_recorder, src_end, 207) GEN_AT(cc_recorder, b_k, 234) GEN_AT(cc_recorder, b_lend, 232)
GEN_AT(cc_recorder, b_llen, 233) GEN_AT(cc_recorder, granule, 24)
GEN_AT(cc_granule, splicing, 57) GEN_AT(cc_granule, splice_phase, 56) GEN_AT(cc_granule, adaptive_increment, 55)
GEN_AT(cc_granule, pitch, 49)
typedef char gen_at_heads[(offsetof(cc_granule, ideal.index) == 28u && offsetof(cc_granule, ideal.speed) == 36u
    && offsetof(cc_granule, actual.index) == 68u && offsetof(cc_granule, actual.speed) == 76u
    && offsetof(cc_granule, temp.index) == 108u) ? 1 : -1];
GEN_AT(gen_frame, last_v, 0) GEN_AT(gen_frame, budget, 1)
#endif
#endif

/* STRETCH at CAPI on without Capicola's analysis (plan B). The heads are
   Capicola's -- the ideal head at the stretch rate, the actual head at the pitch,
   a splice crossfade when they are more than B_LEASH samples apart -- but a
   splice's start is aligned on the source samples themselves (b_align) instead of
   on keyframes, so no keyframe analysis, ring or windows are needed. The heads
   live in the recorder's granule[0] (positions in samples from the note's start
   at r->src_start, less r->b_k, which takes B_REBASE at a time as they pass it,
   and a loop's length as they wrap: small floats, fine resolution), so render.asm's
   fast run (and rec_render's model on the host) plays the samples between events
   unchanged; the windows are given an end time no index reaches, which turns its
   window catch-up into nothing. A left voice renders its right voice's channel
   too, at the same positions (GEN_ROUT; the right voice copies it: gen_pair_copy). */
#ifndef B_LEASH
#define B_LEASH   640.0f     /* samples between the heads before a splice (Capicola's -640) */
#endif
#ifndef B_XFADE
#define B_XFADE   640.0f     /* a splice's crossfade, in input samples */
#endif
#define B_REBASE  4096       /* keep the positions small (under about 2^13: 1/1024 of a sample or finer) */
#define B_REACH   512        /* the splice alignment's search: samples either side of the ideal head */
#define B_POINTS  16         /* its comparison: points, */
#define B_STRIDE  16         /* ... this many samples apart (a 256-sample stretch) */
#define B_CSTEP   16         /* the coarse pass: every B_CSTEP-th offset, */
#ifndef B_CPOINTS
#define B_CPOINTS 8          /* ... on this many points (B_STRIDE * B_POINTS / B_CPOINTS apart) */
#endif
#ifndef B_TOPK
#define B_TOPK    2          /* ... whose best two are refined: every 4th offset, then to the sample */
#endif

/* the note's sample i (from r->src_start), 0 outside the note */
static float b_x(const cc_recorder *r, int32_t i)
{
    const int32_t j = r->src_start + i;
    if (j < r->src_start) return 0.0f;
    if (j >= r->src_end) return 0.0f;
    const uintptr_t a = r->src + 2u * (uint32_t)j;
    const uint32_t w = *(const uint32_t *)(a & ~(uintptr_t)3);
    int32_t v;
    if ((a & 2u) != 0u) v = (int32_t)w >> 16;
    else v = (int32_t)(w << 16) >> 16;
    return (float)v * (1.0f / 32768.0f);
}

static int32_t b_floor(float x)
{
    int32_t k = (int32_t)x;
    if ((float)k > x) k--;
    return k;
}

/* cost[c] = sum over k < points of (x(addr + c * step + stride * k) - ref[k])^2 (step and stride in bytes),
   x the int16 sample at that byte address / 32768, c < count; with top set, only
   the best two candidates instead: their costs to cost[0..1], their numbers to
   top[0..1] (-1: none; a later candidate never displaces an equal one).
   render.asm on the SHARC, the same operations in the same order. */
typedef struct { uintptr_t addr; int32_t count, step; const float *ref; float *cost; int32_t points, stride; int32_t *top; } b_scan;
#if defined(CC_ASM) && !defined(GEN_HOST)
void cc_bscan(const b_scan *s);
void cc_bgather(uintptr_t addr, int n, float *dst);   /* n samples 32 bytes apart, / 32768 */
#else
static void cc_bscan(const b_scan *s)
{
    float c0 = 1e30f, c1 = 1e30f;
    int32_t i0 = -1, i1 = -1;
    int32_t c;   /* (selcc: no typedef'd variable in a for-init) */
    for (c = 0; c < s->count; c++) {
        float cost = 0.0f;
        for (int k = 0; k < s->points; k++) {
            const int16_t v = *(const int16_t *)(s->addr + (uintptr_t)(c * s->step + s->stride * k));
            const float e = (float)v * (1.0f / 32768.0f) - s->ref[k];
            cost += e * e;
        }
        if (s->top) {
            if (cost < c1) {
                if (cost < c0) { c1 = c0; i1 = i0; c0 = cost; i0 = c; }
                else { c1 = cost; i1 = c; }
            }
        } else {
            s->cost[c] = cost;
        }
    }
    if (s->top) { s->cost[0] = c0; s->cost[1] = c1; s->top[0] = i0; s->top[1] = i1; }
}
static void cc_bgather(uintptr_t addr, int n, float *dst)
{
    for (int k = 0; k < n; k++) dst[k] = (float)*(const int16_t *)(addr + (uintptr_t)(32 * k)) * (1.0f / 32768.0f);
}
#endif

static float b_align(const cc_recorder *r, float a, float g, int rev)
{
    /* the stretch compared is the one played next: after the heads, or (rev) before them */
    const int32_t back = rev ? B_STRIDE * (B_POINTS - 1) : 0;
    const int32_t ia = b_floor(a);
    const float fa = a - (float)ia;
    const int32_t la = ia + r->b_k - back;   /* (sample numbers from the note's start: + b_k) */
    float ref[B_POINTS];
    const int32_t span = r->src_end - r->src_start - B_STRIDE * B_POINTS;
    if (la >= 0 && la <= span) cc_bgather(r->src + 2u * (uint32_t)(r->src_start + la), B_POINTS, ref);
    else for (int k = 0; k < B_POINTS; k++) ref[k] = b_x(r, la + B_STRIDE * k);   /* (at the note's edges: 0 outside) */
    const int32_t jg = b_floor(g) + r->b_k - back;
    int32_t lo = jg - B_REACH, hi = jg + B_REACH;
    if (lo < 0) lo = 0;
    if (hi > span) hi = span;
    if (hi < lo) return g;
    float cost[2 * B_REACH / B_CSTEP + 2];
    float refc[B_CPOINTS];
    for (int k = 0; k < B_CPOINTS; k++) refc[k] = ref[k * (B_POINTS / B_CPOINTS)];
    int32_t topi[2];
    b_scan s;
    s.ref = refc;
    s.cost = cost;
    s.top = topi;
    s.points = B_CPOINTS;
    s.stride = 2 * B_STRIDE * (B_POINTS / B_CPOINTS);
    s.addr = r->src + 2u * (uint32_t)(r->src_start + lo);
    s.count = (hi - lo) / B_CSTEP + 1;
    s.step = 2 * B_CSTEP;
    cc_bscan(&s);
    CC_MARK(1);   /* (GEN_SECTIONS: the search's reference and coarse pass) */
    int32_t c;   /* (selcc: no typedef'd variable in a for-init) */
    s.top = (int32_t *)0;
    /* every 4th offset within 12 of each, then each offset within 3 of the best,
       on all B_POINTS points; ties to the nearest */
    s.ref = ref;
    s.points = B_POINTS;
    s.stride = 2 * B_STRIDE;
    float best = g, best_cost = 1e30f;
    int32_t bj = jg;
    for (int pass = 0; pass < 2; pass++) {
        const int nt = pass == 0 ? B_TOPK : 1;
        const int32_t step = pass == 0 ? 4 : 1;
        const int32_t shift = pass == 0 ? 2 : 0;   /* (no integer divide in the runtime: step is a power of two) */
        const int32_t reach = pass == 0 ? 12 : 3;
        for (int t = 0; t < nt; t++) {
            int32_t centre = bj;
            if (pass == 0) {
                if (topi[t] < 0) continue;
                centre = lo + topi[t] * B_CSTEP;
            }
            int32_t j0 = centre - reach, j1 = centre + reach;
            while (j0 < lo) j0 += step;
            while (j1 > hi) j1 -= step;
            if (j1 < j0) continue;
            s.addr = r->src + 2u * (uint32_t)(r->src_start + j0);
            s.count = ((j1 - j0) >> shift) + 1;
            s.step = 2 * step;
            cc_bscan(&s);
            for (c = 0; c < s.count; c++) {
                const int32_t j = j0 + c * step;
                float dist = (float)(j + back - r->b_k) + fa - g;
                if (dist < 0.0f) dist = -dist;
                const float x = cost[c] + 1e-5f * dist;
                if (x < best_cost) { best_cost = x; best = (float)(j + back - r->b_k) + fa; bj = j; }
            }
        }
    }
    return best;
}

#if defined(CC_ASM) && !defined(GEN_HOST)
float cc_balign(const cc_recorder *r, float a, float g);   /* render.asm: b_align, rev from GEN_BPASS */
#endif

/* At most B_SEARCHES splice starts (each a b_align search) a frame across all the
   voices: a voice whose heads pass the leash when the frame's are used starts
   its splice in a later block (its heads drift a few samples further apart), so
   splices that fall together do not pile up into one late frame. The count is
   GEN_FRAME's budget word (plan A's lookahead budget, unused here). */
#ifndef B_SEARCHES
#define B_SEARCHES 1
#endif
#ifdef GEN_LAYOUT_CHECK   /* render.asm cc_bfast's constants */
typedef char gen_at_consts[(B_SEARCHES == 1 && B_REBASE == 4096 && (int)B_LEASH == 640 && VOICE_REC0 == 0x2412ccu
    && PARAM_REC0 == 0x2506ecu && VOICE_STRIDE == 0x1d8u && PARAM_STRIDE == 0xdcu && PHASE_MARK == 0x00a5a5a5u) ? 1 : -1];
#endif

/* samples before anything b_step checks for may be due (two to spare), as rec_fast_count */
static int b_count(const cc_granule *q, int n)
{
    float m = (float)n;
    if (!q->splicing) {
        if (GEN_FRAME->budget <= 0) return n;   /* no splice can start in this block */
        float d = q->actual.index - q->ideal.index;
        if (d < 0.0f) d = -d;
        const float room = B_LEASH - d;
        if (room <= 0.0f) return 0;
        float dv = q->actual.speed - q->ideal.speed;
        if (dv < 0.0f) dv = -dv;
        if (dv > 0.0f) {
            const float c = room / dv - 2.0f;
            if (c < m) m = c;
        }
    } else {
        const float inc = q->adaptive_increment * q->pitch;
        if (inc > 0.0f) {
            const float c = (1.0f - q->splice_phase) / inc - 2.0f;
            if (c < m) m = c;
        }
    }
    if (m < 1.0f) return 0;
    return (int)m;
}

/* one sample with the events: a splice's start or end (cc_granule_read's order);
   with GEN_BPASS->rr, the right channel's at the same positions to *yr */
static float b_step(cc_recorder *r, int rev, float *yr)
{
    const cc_recorder *rr = (const cc_recorder *)GEN_BPASS->rr;
    cc_granule *q = &r->granule[0];
    if (!q->splicing) {
        float d = q->actual.index - q->ideal.index;
        if (d < 0.0f) d = -d;
        int go = 0;
        if (d > B_LEASH) { if (GEN_FRAME->budget > 0) go = 1; }
        if (go) {
            GEN_FRAME->budget--;
            CC_MARK(4);
#if defined(CC_ASM) && !defined(GEN_HOST)   /* render.asm's (the same result); the C at the note's edges */
            float t = cc_balign(r, q->actual.index, q->ideal.index);
            if (t < -1.0e29f) t = b_align(r, q->actual.index, q->ideal.index, rev);
            q->temp.index = t;
#else
            q->temp.index = b_align(r, q->actual.index, q->ideal.index, rev);
#endif
            CC_MARK(6);
            q->temp.speed = q->actual.speed;
            q->splice_phase = 0.0f;
            q->splicing = 1;
        }
    }
    q->ideal.index += q->ideal.speed;
    if (q->splicing) {
        if (q->splice_phase <= 1.0f) {
            q->temp.speed = q->actual.speed;
            const float in = CLEAN_READ(r, q->temp.index);
            const float o = CLEAN_READ(r, q->actual.index);
            const float w = smooth_step(q->splice_phase);
            const float w1 = 1.0f - w;
            if (rr) {
                const float inr = CLEAN_READ(rr, q->temp.index);
                const float orr = CLEAN_READ(rr, q->actual.index);
                *yr = (inr * w) + (orr * w1);
            }
            q->temp.index   += q->temp.speed;
            q->actual.index += q->actual.speed;
            const float y = (in * w) + (o * w1);
            q->splice_phase += q->adaptive_increment * q->pitch;
            return y;
        }
        q->actual = q->temp;   /* the splice has ended */
        q->splice_phase = 0.0f;
        q->splicing = 0;
    }
    const float y = CLEAN_READ(r, q->actual.index);
    if (rr) *yr = CLEAN_READ(rr, q->actual.index);
    q->actual.index += q->actual.speed;
    return y;
}

/* m samples between events (b_count): actual's read, or (splicing) temp's and
   actual's crossfaded as b_step does, and with GEN_BPASS->rr the right channel's
   at the same positions to GEN_BPASS->outr; the ideal head on by m steps at once.
   render.asm's cc_brun on the SHARC: the same operations in the same order. */
#if defined(CC_ASM) && !defined(GEN_HOST)
void cc_brun(cc_recorder *r, float *out, int m);
#else
static void cc_brun(cc_recorder *r, float *out, int m)
{
    cc_granule *q = &r->granule[0];
    const cc_recorder *rr = (const cc_recorder *)GEN_BPASS->rr;
    float *outr = GEN_BPASS->outr;
    float ai = q->actual.index;
    const float as = q->actual.speed;
    if (!q->splicing) {
        for (int i = 0; i < m; i++) {
            out[i] = CLEAN_READ(r, ai);
            if (rr) outr[i] = CLEAN_READ(rr, ai);
            ai += as;
        }
    } else {
        float ti = q->temp.index, p = q->splice_phase;
        const float inc = q->adaptive_increment * q->pitch;
        for (int i = 0; i < m; i++) {
            const float in = CLEAN_READ(r, ti);
            const float o = CLEAN_READ(r, ai);
            const float w = smooth_step(p);
            const float w1 = 1.0f - w;
            out[i] = (in * w) + (o * w1);
            if (rr) {
                const float inr = CLEAN_READ(rr, ti);
                const float orr = CLEAN_READ(rr, ai);
                outr[i] = (inr * w) + (orr * w1);
            }
            ti += as;
            ai += as;
            p += inc;
        }
        q->temp.index = ti;
        q->temp.speed = as;
        q->splice_phase = p;
    }
    q->actual.index = ai;
    q->ideal.index += q->ideal.speed * (float)m;
}
#endif

/* the heads' whole samples: b_k = k (b_kf, b_lo with it) */
static void b_shift(cc_recorder *r, int32_t k)
{
    r->b_k = k;
    r->b_kf = (float)k;
    r->b_lo = (float)(1 - k);
}

/* a fresh note (or this way of playing taken up) at sample start; heads at a */
static void b_begin(gen_voice *g, cc_recorder *r, uintptr_t src, int32_t start, int32_t end, float a)
{
    cc_granule *q = &r->granule[0];
    r->src = src;
    r->src_start = start;
    r->src_end = end;
    r->src_t0 = 0;
    r->sparse.origin = 0;
    r->prev_valid = 0;
    r->live_g = 0;
    r->x_gain = 1.0f;
    r->x_step = 0.0f;
    b_shift(r, b_floor(a));   /* the heads at a's fraction, b_k its whole samples */
    a -= r->b_kf;
    q->ideal.index = a;
    q->actual.index = a;
    q->temp.index = a;
    q->splicing = 0;
    q->splice_phase = 0.0f;
    q->adaptive = 1;
    q->adaptive_increment = 1.0f / B_XFADE;
    q->ideal.w.end_time = 3.0e38f;   /* no window catch-up (render.asm .fr_catch, gr_catch_up) */
    q->actual.w.end_time = 3.0e38f;
    q->temp.w.end_time = 3.0e38f;
    g->start = start;
    g->bmode = 1;
}

/* the block's samples: the runs between events by cc_brun, the events (a splice's
   start or end) by b_step; GEN_BPASS->rr the right channel's recorder, ->rev the
   direction. gen_wsola's, and render.asm cc_bfast's for a block with events. */
void cc_bloop(cc_recorder *r, float *out, int n)
{
    cc_granule *q = &r->granule[0];
    const int rev = GEN_BPASS->rev;
    int i = 0;
    while (i < n) {
        int m = b_count(q, n - i);
        if (m > 0) {
            GEN_BPASS->outr = GEN_ROUT + i;
            cc_brun(r, out + i, m);
            i += m;
        } else {
            float yr = 0.0f;
            out[i] = b_step(r, rev, &yr);
            GEN_ROUT[i] = yr;
            i++;
        }
    }
}

/* The slice machines, GRID (DSP type 4) and SLICE (5), at CAPI on: the whole
   sample (w62 frames) lasts the slice machine's bars at the tempo, as the stock
   STRETCH and REPITCH fit their START..END to BARS (w72 = frames * BPM / (240 *
   48000 * 2^BARS), the firmware's tempo float at 0x252d50). SLICE's bars are its
   slot 6 (BARS: 0..5 for 1 to 32 bars); GRID's slot 6 is its grid (0..4 for
   4..64 slices), taken as a 16th a slice. Slot 2 picks the way: 1 REPITCH's
   (pitch moves with the tempo), 2 STRETCH's (TUNE's pitch). GEN_SLICE_MODE (a test
   image without the slots on the screen) fixes the way, and SLICE's bars at
   2^GEN_SLICE_BARS. */
#if defined(GEN_SLICE_MODE) && !defined(GEN_SLICE_BARS)
#define GEN_SLICE_BARS 0
#endif

/* the value byte of the SRC page halfword at off + 2 on voice v's track (off a
   word's offset: 0xdc for slot 2, 0xe8 for slot 6) */
static uint32_t gen_page_hi(uint32_t v, uint32_t off)
{
    const uint32_t sel = PAGE_SEL & 1u;
    const uint32_t w = PAGE_WORD(sel, off + 0x60u * (v >> 1));
    return w >> 24;
}

static int gen_slice_mode(uint32_t v)
{
#ifdef GEN_SLICE_MODE
    (void)v;
    return GEN_SLICE_MODE;
#else
    return (int)gen_page_hi(v, 0xdcu);
#endif
}

static float gen_slice_speed(const uint32_t *rec, uint32_t v, int machine)
{
    int32_t b = (int32_t)gen_page_hi(v, 0xe8u);   /* log2 of the bars (render.asm .bf_sl: the same steps) */
#ifdef GEN_SLICE_MODE
    if (machine != 4) b = GEN_SLICE_BARS;
#endif
    if (machine == 4) b = b - 2;   /* 4 << grid slices, a 16th each */
    if (b > 5) b = 5;   /* (BARS 0..5: 1..32 bars, build_cap.py BARS_MAX) */
    float s = (float)(int32_t)rec[0x62] * GEN_BPM;
    s = s * 8.68055565e-08f;   /* 1 / (240 * 48000) */
    for (; b > 0; b--) s = s * 0.5f;
    for (; b < 0; b++) s = s * 2.0f;
    return s;
}

/* machine 2 STRETCH: the ideal head at w72's stretch, the actual at the TUNE's
   pitch; machine 3 REPITCH: both at the stock varispeed rate (2 * STEP), so they
   never part and it plays as a varispeed read, at the stock level (0.4045);
   machines 4 and 5 (above) at the slice speed, with TUNE's pitch the STRETCH way,
   at the shared generator's level as REPITCH.
   PLAY: the voice record's reverse (byte +0x1bb) and loop (+0x1bc) flags, the
   loop from START to END (these machines' loop start is START): reversed, the
   heads start at END - 1 (where the firmware seeds PHASE) and run down; looped,
   they move on by a loop when the actual head passes the end (a read past it
   wraps meanwhile: .fcl_slow, rec_clean_read). */
static int gen_wsola(gen_voice *g, cc_recorder *r, uint32_t *rec, float *out, int n, uint32_t v, int record, int machine)
{
    cc_granule *q = &r->granule[0];
    const uintptr_t src = SAMPLE_ADDR(rec[0]);
    const int rev = (int)((rec[0x6e] >> 24) & 0xffu);   /* byte +0x1bb */
    const int loop = (int)(rec[0x6f] & 0xffu);          /* byte +0x1bc */
    int trig = 0;
    if (!g->playing) trig = 1;
    if (!g->bmode) trig = 1;
    if (rec[0x6c] != g->phase_lo) trig = 1;
    if (rec[0x6d] != g->phase_hi) trig = 1;
    if (trig) {
        int fresh = 1;
        if ((v & 1u) != 0u) {
            if (g->pair) {   /* a right voice whose pairing ends: on from its left voice's heads */
                const gen_voice *gl = (const gen_voice *)VOICE_STATE(v - 1u);
                if (gl->bmode) {
                    const cc_granule *ql = &gl->rec.granule[0];
                    b_begin(g, r, src, gl->rec.src_start, gl->rec.src_end, 0.0f);
                    b_shift(r, gl->rec.b_k);
                    q->ideal = ql->ideal;
                    q->actual = ql->actual;
                    q->temp = ql->temp;
                    q->splicing = ql->splicing;
                    q->splice_phase = ql->splice_phase;
                    fresh = 0;
                }
            }
        }
        if (fresh) {   /* from the note's START, at PHASE (START, or END - 1 reversed) */
            g->retrig = g->playing;
            const int32_t start = q31_pos(rec, 0x66);
            b_begin(g, r, src, start, q31_pos(rec, 0x68), (float)(q31_pos(rec, 0x6c) - start));
        }
        g->playing = 1;
        g->pair = 0;
        g->fast = 0;
        g->diag_trigs++;
    }
    r->src = src;
    float stretch, pitch;
    int tuned = 1;   /* the pitch from TUNE */
    if (machine == 3) {   /* 2 * STEP = hi * 4 + lo / 2^30, its sign the direction (rev) */
        float rate = (float)(int32_t)rec[0x6b] * 4.0f + (float)(rec[0x6a] >> 8) * (1.0f / 4194304.0f);
        if (rate < 0.0f) rate = -rate;
        stretch = rate;
        pitch = rate;
        tuned = 0;
    } else if (machine == 2) {
        stretch = *(const float *)&rec[0x72];
        pitch = stretch;
    } else {
        stretch = gen_slice_speed(rec, v, machine);
        pitch = stretch;
        if (gen_slice_mode(v) < 2) tuned = 0;
    }
    if (tuned) {
        const uint32_t tune_w = *(const uint32_t *)(PARAM_BASE + v * PARAM_STRIDE);
        if ((uint32_t)g->ipos != tune_w) {   /* (plan B: ipos/frac cache the TUNE word and its pitch) */
            g->ipos = (int32_t)tune_w;   /* (before the call: selcc kept tune_w in R1 across
                                            gen_exp2 and stored the pitch here instead) */
            const float tune = *(const float *)(PARAM_BASE + v * PARAM_STRIDE);
            g->frac = gen_exp2((tune * 128.0f - 64.0f) * (1.0f / 12.0f));
        }
        pitch = g->frac;
    }
    CC_MARK(0);
    q->ideal.speed = rev ? -stretch : stretch;
    q->actual.speed = rev ? -pitch : pitch;
    q->pitch = pitch;
    cc_recorder_set_blend(r, 0.0f);
    {   /* a new frame (the voice order restarts): its splice starts */
        gen_frame *fr = GEN_FRAME;
        if (v <= fr->last_v) fr->budget = B_SEARCHES;
        fr->last_v = v;
    }
    const int32_t k0 = r->b_k;   /* (b_k before this block's loop wrap and rebase) */
    const int32_t len = r->src_end - r->src_start;
    r->b_lend = (float)len;
    r->b_llen = loop ? (float)len : 0.0f;
    if (loop) {   /* past the loop's end (or, reversed, its start): every head on by a loop (in b_k) */
        if (len >= 1) {
            if (!rev) {
                while (q->actual.index >= (float)(len - r->b_k)) b_shift(r, r->b_k - len);
            } else {
                while (q->actual.index < (float)(-r->b_k)) b_shift(r, r->b_k + len);
            }
        }
    }
    {   /* rebase: the positions by B_REBASE towards 0 (into b_k) once all three are
           past twice that, so a float's resolution stays fine either way */
        float lo = q->ideal.index, hi = q->ideal.index;
        if (q->actual.index < lo) lo = q->actual.index;
        if (q->actual.index > hi) hi = q->actual.index;
        if (q->splicing) {
            if (q->temp.index < lo) lo = q->temp.index;
            if (q->temp.index > hi) hi = q->temp.index;
        }
        float k = 0.0f;
        if (lo >= (float)(2 * B_REBASE)) k = (float)B_REBASE;
        if (hi <= (float)(-2 * B_REBASE)) k = -(float)B_REBASE;
        if (k != 0.0f) {
            q->ideal.index -= k;
            q->actual.index -= k;
            q->temp.index -= k;
            b_shift(r, r->b_k + (int32_t)k);
        }
    }
    /* the stereo pass: a left voice whose right voice plays the same note (its
       record active, the same START and END) renders that channel too, the
       right voice's samples on this note's mapping */
    gen_voice *gr = (gen_voice *)0;
    cc_recorder *rr = (cc_recorder *)0;
    uint32_t *rec_r = rec + VOICE_STRIDE / 4u;
    if (record) {
        int ok = 1;
        if (rec_r[0] == 0u) ok = 0;
        if ((rec_r[0x6e] & 0xffu) == 0u) ok = 0;
        if (rec_r[0x66] != rec[0x66]) ok = 0;   /* START and END, Q31 */
        if (rec_r[0x67] != rec[0x67]) ok = 0;
        if (rec_r[0x68] != rec[0x68]) ok = 0;
        if (rec_r[0x69] != rec[0x69]) ok = 0;
        if (ok) {
            gr = (gen_voice *)VOICE_STATE(v + 1u);
            if (gr->magic != GEN_MAGIC) gr = (gen_voice *)0;   /* (its first call sets it up) */
        }
        if (gr) {
            rr = &gr->rec;
            int same = 1;   /* the right channel's mapping as last block's: not written again */
            if (trig) same = 0;
            if (!gr->pair) same = 0;
            if (r->b_k != k0) same = 0;
            if (rr->src != SAMPLE_ADDR(rec_r[0])) same = 0;
            if (rr->b_llen != r->b_llen) same = 0;
            if (rr->b_k != r->b_k) same = 0;
            if (!same) {
            rr->src = SAMPLE_ADDR(rec_r[0]);
            rr->src_start = r->src_start;
            rr->src_end = r->src_end;
            rr->src_t0 = r->src_t0;
            rr->sparse.origin = r->sparse.origin;
            rr->prev_valid = 0;
            rr->b_lend = r->b_lend;
            rr->b_llen = r->b_llen;
            rr->b_k = r->b_k;
            rr->b_kf = r->b_kf;
            rr->b_lo = r->b_lo;
            }
            if (trig) gr->retrig = gr->playing;
        }
    }
    GEN_BPASS->rr = rr;
    CC_MARK(0);   /* (GEN_SECTIONS: 0 gen_run, the parameters, the mapping and the stereo
                     setup; 4 the render loop; a splice search's reference and coarse
                     pass 1, its refinement 6 (2 the worst search, 3 their count); 5 after) */
    GEN_BPASS->rev = rev;
    cc_bloop(r, out, n);
    CC_MARK(4);
    if (machine >= 3) {
        for (int k = 0; k < n; k++) out[k] *= 0.4045f;   /* the shared generator's hand-over level (gen_run) */
    }
    const int32_t pos = r->src_start + r->b_k + b_floor(q->ideal.index);
    if (rr) {
        if (machine >= 3) {
            float *o2 = GEN_ROUT;
            for (int k = 0; k < n; k++) o2[k] *= 0.4045f;
        }
        gen_declick(gr, GEN_ROUT, n);
        /* the right voice as gen_pair_copy leaves it, so dt2entry.asm's copy
           (.pf) can stand for its call: its flags once a pairing starts, its PHASE
           each block (its phase_lo/hi are not needed while it is paired: a right
           voice whose pairing ends starts again from these heads anyway) */
        if (!gr->pair) {
            gr->playing = 1;
            gr->pair = 1;
            gr->bmode = 0;
            gr->fast = 0;
            gr->start = g->start;
        }
        GEN_TAPE_INFO->voice = (int32_t)v;   /* the right voice's channel is ready */
        GEN_TAPE_INFO->n = n;
    }
    gen_declick(g, out, n);
    gen_phase_out(g, rec, pos);
    if (rr) {
        rec_r[0x6c] = g->phase_lo;   /* the same play position */
        rec_r[0x6d] = g->phase_hi;
    }
    if (!loop) {   /* the note is over once every head is past its end (start, reversed):
           ACTIVE cleared, as the stock generators do, so the voice idles until its
           next trig -- else a muted track's last note plays silence on, through
           the clean read's slowest path, for ever */
        const float edge = (float)((rev ? 0 : len) - r->b_k);
        int over = 1;
        if (!rev) {
            if (q->ideal.index < edge) over = 0;
            if (q->actual.index < edge) over = 0;
            if (q->splicing) { if (q->temp.index < edge) over = 0; }
        } else {
            if (q->ideal.index >= edge) over = 0;
            if (q->actual.index >= edge) over = 0;
            if (q->splicing) { if (q->temp.index >= edge) over = 0; }
        }
        if (over) {
            const uint32_t w6e = rec[0x6e];   /* byte +0x1b8, ACTIVE */
            rec[0x6e] = w6e & ~0xffu;
            g->playing = 0;
        }
    }
    CC_MARK(5);
    return (int)v;
}
#endif

#ifdef GEN_WSOLA
#if defined(CC_ASM) && !defined(GEN_HOST)
void cc_wcopy(float *dst, const float *src, int n);   /* render.asm */
#else
static void cc_wcopy(float *dst, const float *src, int n)
{
    for (int i = 0; i < n; i++) dst[i] = src[i];
}
#endif
/* A right voice whose left voice rendered its channel this frame (gen_wsola's
   stereo pass): that copied out; its own heads idle meanwhile (taken up from the
   left voice's when the pairing ends). On the SHARC dt2entry.asm (.pf) does this
   before the C (the left voice has set the rest); this is its fallback and the
   host's. */
static int gen_pair_copy(gen_voice *g, uint32_t *rec, float *out, int n, uint32_t v)
{
    const gen_voice *gl = (const gen_voice *)VOICE_STATE(v - 1u);
    if (n > 0) cc_wcopy(out, GEN_ROUT, n);
    int trig = 0;
    if (!g->playing) trig = 1;
    if (!g->pair) trig = 1;
    if (rec[0x6c] != g->phase_lo) trig = 1;
    if (rec[0x6d] != g->phase_hi) trig = 1;
    if (trig) g->diag_trigs++;
    g->playing = 1;
    g->pair = 1;
    g->bmode = 0;
    g->fast = 0;
    g->start = gl->start;
    gen_phase_out(g, rec, gl->start + gl->rec.b_k + b_floor(gl->rec.granule[0].ideal.index));
    GEN_TAPE_INFO->voice = -1;
    return (int)v;
}
#endif

/* returns the voice, or -1 for a record that is not one */
static int gen_run(uint32_t *rec, float *out, int n, int machine)
{
    /* the voice index without a search loop: selcc makes a constant-count loop a
       hardware DO loop and leaves it by a jump, which leaks loop and PC stack
       entries (work/doscan.py). 2222 / 2^20 ~ 1 / 472, exact for v < 32. */
    const uint32_t off = (uint32_t)((uintptr_t)rec - VOICE_BASE);
    const uint32_t v = (off * 2222u) >> 20;
    /* two ifs, not `a || b`: selcc reused the register holding off for v in the
       second operand (work/dtest/probe6.c), so every voice but 0 was refused */
    if (off >= NVOICE * VOICE_STRIDE) { gen_zero(out, n); return -1; }
    if (v * VOICE_STRIDE != off) { gen_zero(out, n); return -1; }
    gen_voice *g = (gen_voice *)VOICE_STATE(v);
    const uint32_t active = rec[0x6e] & 0xffu;      /* byte +0x1b8 */
    if ((v & 1u) == 0u) GEN_TAPE_INFO->voice = -1;   /* until this left voice records one */
    *CC_TAPE_BUF_AT = (uint32_t *)0;
    if (rec[0] == 0u || active == 0u) {
        g->playing = 0;
        g->last_out = 0.0f;
        gen_zero(out, n);
        return (int)v;
    }
    if (machine == 3) {   /* the shared generator's call: 3 REPITCH, 4 GRID, 5 SLICE (dt2entry.asm sends no other) */
        const uint32_t t = *(const uint32_t *)(PARAM_BASE + v * PARAM_STRIDE + 0x4cu);
        if (t == 4u) machine = 4;
        if (t == 5u) machine = 5;
    }
    if (machine >= 4) {   /* an empty slice (a sample without slices: END 0): silence, as stock */
        if (q31_pos(rec, 0x68) - q31_pos(rec, 0x66) < 4) {
            g->playing = 0;
            g->last_out = 0.0f;
            gen_zero(out, n);
            return (int)v;
        }
    }
    cc_recorder *r = &g->rec;
    float *o = out;
    CC_MARK(-1);   /* (GEN_DIAG: the sections start here) */
    if (g->magic != GEN_MAGIC) {
        cc_recorder_init(r, (cc_keyframe *)RING_AT(v), RING);
        cc_recorder_set_fade(r, 960.0f);
        r->trig_fade = 0.0f;   /* a retrigger switches at once; gen_declick smooths the step */
        cc_recorder_set_leash(r, -640);   /* 640 samples (13 ms): tight timing; CC_ALIGN keeps splices clean */
        g->playing = 0;
        g->phase_lo = g->phase_hi = 0xffffffffu;
        g->diag_calls = 0;
        g->diag_trigs = 0;
        g->bad_out = 0;
        g->fast = 0;
        g->pair = 0;
        g->last_out = 0.0f;
        g->retrig = 0;
        g->bmode = 0;
        g->ipos = -1;   /* (plan B's TUNE cache: no TUNE word is all ones) */
        g->magic = GEN_MAGIC;
    }
#if defined(GEN_WSOLA) && !defined(GEN_HOST)
    *GEN_MAGIC_CELL = GEN_MAGIC;   /* for render.asm's cc_bfast, which cannot know it */
#endif
    float blend = 1.0f;   /* CAPI / 127: 0 the samples, 1 the keyframes */
#ifdef CC_CLEAN   /* otherwise the blend stays 1: keyframes only, as before CAPI */
#ifdef GEN_BLEND_FIXED   /* no CAPI knob (its ColdFire patch is not in the image): a fixed blend */
    blend = GEN_BLEND_FIXED;
#else
    {
        const uint32_t sel = PAGE_SEL & 1u;
        const uint32_t pw = PAGE_WORD(sel, 0xdcu + 0x60u * (v >> 1));
        uint32_t capi = (pw >> 16) >> 8;
        const float on = *(const float *)(PARAM_BASE + v * PARAM_STRIDE + 0x10u);
        if (on == 0.0f) capi = 0;
        if (capi > 127u) capi = 127u;
        blend = (float)capi * (1.0f / 127.0f);
    }
#endif
    cc_recorder_set_blend(r, blend);
#endif
#ifdef GEN_WSOLA
    if (blend == 0.0f) {   /* plan B: STRETCH and REPITCH; a right voice copies the channel its left rendered */
        if ((v & 1u) != 0u) {
            if (GEN_TAPE_INFO->voice == (int32_t)v - 1) {
#ifndef GEN_NO_PAIR
                if (GEN_TAPE_INFO->n == n) return gen_pair_copy(g, rec, out, n, v);
#endif
            }
        }
        return gen_wsola(g, r, rec, out, n, v, (v & 1u) == 0u, machine);
    }
#endif
#if !(defined(GEN_WSOLA) && defined(GEN_BLEND_ZERO))   /* (plan B at blend 0 returned above: Capicola's way, never run) */
    if (machine == 3) {
#if !defined(GEN_NO_REPITCH_FAST) && !defined(GEN_WSOLA)
        if (blend == 0.0f) return gen_repitch_clean(g, r, rec, out, n, v);
#endif
        if (g->fast) {   /* back to Capicola: a fresh start at the varispeed's head */
            g->fast = 0;
            r->state = CC_STOPPED;
            cc_recorder_source(r, g->src, g->ipos, g->end, -1);
            g->start = g->ipos;
        }
    }
    if (machine == 2) {
        if (g->fast) {   /* was REPITCH's varispeed: Capicola's state is stale, so a fresh note */
            g->fast = 0;
            g->playing = 0;
            r->state = CC_STOPPED;
        }
        if ((v & 1u) != 0u) {
            if (blend == 0.0f) {
                if (GEN_TAPE_INFO->voice == (int32_t)v - 1) {
#if !defined(GEN_NO_PAIR) && !defined(GEN_WSOLA)   /* (plan B returned above) */
                    if (GEN_TAPE_INFO->n == n) return gen_pair_replay(g, r, rec, out, n, v, machine);
#endif
                }
            }
            int pair_end = g->pair;
#ifdef GEN_WSOLA
            if (blend == 0.0f) pair_end = 0;   /* (gen_wsola takes over from the left voice's heads) */
#endif
            if (pair_end) {   /* the pairing ends: Capicola afresh at the left voice's head */
                const gen_voice *gl = (const gen_voice *)VOICE_STATE(v - 1u);
                const cc_granule *gg = &gl->rec.granule[gl->rec.live_g];
                const int32_t pos = gl->start + gl->rec.b_k + (int32_t)((cc_idx)gg->ideal.index + gl->rec.sparse.origin - gl->rec.src_t0);
                g->pair = 0;
                r->state = CC_STOPPED;
                cc_recorder_source(r, SAMPLE_ADDR(rec[0]), pos, q31_pos(rec, 0x68), -1);
                g->start = pos;
                g->playing = 1;
            }
        } else if (blend == 0.0f) {
            *CC_TAPE_BUF_AT = GEN_TAPE;   /* the left voice records */
        }
        if (g->bmode) {   /* back from the analysis-free way: a fresh note */
            g->bmode = 0;
            g->playing = 0;
            r->state = CC_STOPPED;
        }
        const float stretch = *(const float *)&rec[0x72];
        const float tune = *(const float *)(PARAM_BASE + v * PARAM_STRIDE);
        cc_recorder_set_stretch(r, stretch);
        cc_recorder_set_pitch(r, gen_exp2((tune * 128.0f - 64.0f) * (1.0f / 12.0f)));
    } else {
        /* 2 * STEP = hi * 4 + lo / 2^30 */
        const float rate = (float)(int32_t)rec[0x6b] * 4.0f + (float)(rec[0x6a] >> 8) * (1.0f / 4194304.0f);
        cc_recorder_set_stretch(r, rate);
        cc_recorder_set_pitch(r, rate);
    }
    int trig_now = 0;
    if (!g->playing || rec[0x6c] != g->phase_lo || rec[0x6d] != g->phase_hi) {
        /* a trig: PHASE was seeded at the start position */
        const int32_t start = q31_pos(rec, 0x6c);
        const int32_t end = q31_pos(rec, 0x68);
        cc_recorder_source(r, SAMPLE_ADDR(rec[0]), start, end, -1);
        g->retrig = g->playing;
        g->start = start;
        g->playing = 1;
        g->diag_trigs++;
        trig_now = 1;
    }
    /* stereo link: a track's left voice (even) records its splices' alignment,
       its right voice (odd), called right after in the same frame, replays them,
       so both channels splice at the same points of the sample */
    cc_link *lk = CC_LINK_AT;
    if ((v & 1u) == 0u) {
        lk->mode = 1;
        lk->n = 0;
        lk->voice = (int32_t)v;
    } else {
        lk->mode = 0;
        if (lk->voice == (int32_t)v - 1) {
            if (lk->n >= 0) {
                if (lk->n <= CC_LINK_MAX) lk->mode = 2;
            }
        }
        lk->k = 0;
    }
    gen_frame *fr = GEN_FRAME;
    if (v <= fr->last_v) fr->budget = GEN_FEED_BUDGET;
    fr->last_v = v;
    int32_t extra = fr->budget;
    if ((v & 1u) != 0u) {
        if (fr->l_voice == (int32_t)v - 1) extra = fr->l_allow;
    }
    if (extra < 0) extra = 0;
    /* a trig's block analyses only what the new note's heads need: its lookahead
       grows from the next block on, when tracks that trig together no longer
       all pay in the same frame (the right voice gets its left's 0) */
    if (trig_now) extra = 0;
    r->feed_extra = extra;
    r->rebase_lag = (int32_t)(((v >> 1) & 7u) * 1024u);   /* tracks rebase in different frames (a track's right voice follows its left: CC_LINK) */
    CC_MARK(0);
    cc_recorder_process(r, (const float *)0, o, n);
    if (*CC_TAPE_BUF_AT) {
        GEN_TAPE_INFO->voice = (int32_t)v;
        GEN_TAPE_INFO->n = n;
        *CC_TAPE_BUF_AT = (uint32_t *)0;
    }
    fr->budget -= r->feed_extra_used;
    if ((v & 1u) == 0u) {
        fr->l_allow = extra;
        fr->l_voice = (int32_t)v;
    } else {
        fr->l_voice = -1;
    }
    if ((v & 1u) != 0u) lk->voice = -1;    /* used once */
    {   /* output guard: a non-finite or wild sample would poison the shared mix
           and effects (a NaN stays a NaN through the delay and reverb). The sum
           of squares is NaN, infinite or >= 64 whenever a sample is bad, so the
           sample-by-sample check runs only then (a loud block costs it too) */
        float e = 0.0f;
        for (int i = 0; i < n; i++) e += o[i] * o[i];
        int check = 1;
        if (e < 64.0f) check = 0;
        if (check) for (int i = 0; i < n; i++) {
            const float y = o[i];
            const uint32_t b = CC_FBITS(y);
            int bad = 0;
            if (((b >> 23) & 0xffu) == 0xffu) bad = 1;
            if (y > 8.0f) bad = 1;
            if (y < -8.0f) bad = 1;
            if (bad) { o[i] = 0.0f; g->bad_out++; }
        }
    }
    lk->mode = 0;
    if (machine == 3) {
        /* the stock shared generator hands REPITCH over at 0.4045 of the sample's
           scale (measured with a DC sample: tempo-, pitch-, frequency- and LEV-
           independent), STRETCH at 1.0; the firmware's mix expects that */
        for (int i = 0; i < n; i++) o[i] *= 0.4045f;
    }
    gen_declick(g, o, n);
    /* the play position: the live grain's grid head, from the note's start */
    const cc_granule *gl = &r->granule[r->live_g];
    gen_phase_out(g, rec, g->start + (int32_t)((cc_idx)gl->ideal.index + r->sparse.origin - r->src_t0));
#endif
    CC_MARK(5);
    return (int)v;
}

#ifdef GEN_DIAG
/* Load diagnostic: EMUCLK around every call. A frame starts when the voice
   order restarts. Every 1024 frames the window's figures are published; reply
   word 0 (both reply pages) cycles through them, item in the top 4 bits and the
   value in the low 28, halves swapped as the ColdFire's copy reads them
   (dt2probe.py capload decodes it). */
uint32_t cc_emuclk(void);                 /* dt2entry.asm */
#define DIAG_N      15   /* 0-5 load and guards, 7-13 section sums (CC_MARK 0-6), 14 playing calls */
#define DIAG_MAGIC  0xD1A60004u
typedef struct {
    uint32_t magic, last_v, frame_t0, frame_cyc, frames, tag;
    uint32_t win_max, win_sum, call_max, per_max, late;
    uint32_t pub[DIAG_N + 1];
    uint32_t sec[7], mark_t, n_play;
    uint32_t srch;   /* GEN_SECTIONS: this search's reference and coarse pass, so far */
} gen_diag;
#ifdef GEN_HOST
static gen_diag gen_diag_mem;
#define DIAG_AT (&gen_diag_mem)
extern uint32_t gen_host_reply[2];
#define REPLY0(p) (gen_host_reply[(p)])
#else
#define DIAG_AT ((gen_diag *)0x2def58u)   /* 0x94 bytes, to 0x2defec */
#define REPLY0(p) (*(volatile uint32_t *)(0x266220u + 0x1000u * (p)))
#endif

static void gen_fed(uint32_t k)
{
    gen_diag *d = DIAG_AT;
    if (d->magic == DIAG_MAGIC) {   /* (pub[15] is never published: the accumulator) */
        /* not `d->pub[15] += k`: selcc added pub's address instead of k */
        const uint32_t s = d->pub[15];
        d->pub[15] = s + k;
    }
}

/* k = -1 starts the sections; k = 4 (after render) also counts a playing call */
static void gen_mark(int k)
{
    gen_diag *d = DIAG_AT;
    const uint32_t t = cc_emuclk();
    if (k >= 0) {
        if (d->magic == DIAG_MAGIC) {
            const uint32_t dt = t - d->mark_t;
            d->sec[k] += dt;
            if (k == 5) d->n_play++;   /* (once a call: 4 may come more than once) */
            if (k == 1) d->srch = dt;   /* a search's first part (b_align) */
            if (k == 6) {   /* its end: the worst whole search to section 2, the count to 3 */
                const uint32_t whole = d->srch + dt;
                if (whole > d->sec[2]) d->sec[2] = whole;
                const uint32_t c3 = d->sec[3];
                d->sec[3] = c3 + 1u;
                d->srch = 0;
            }
        }
    }
    d->mark_t = t;
}

/* the stock generators' figures (dt2entry.asm times them when CAPI is off, and
   for the shared generator's other machines): L1 words after the tape's info */
#define STOCK_S    ((volatile uint32_t *)0x2dee40u)   /* stock STRETCH cycles, this window */
#define STOCK_SH   ((volatile uint32_t *)0x2dee44u)   /* the shared generator's (REPITCH, the others) */
#define STOCK_F    ((volatile uint32_t *)0x2dee48u)   /* stock cycles in this frame */
#define ALL_MAX    ((volatile uint32_t *)0x2dee4cu)   /* the worst frame, ours and stock together */

/* a frame starts when the voice order restarts: close the previous one, and
   publish every 1024 frames */
static void diag_frame(gen_diag *d, uint32_t uv, uint32_t t0)
{
    if (d->magic != DIAG_MAGIC) {
        for (int i = 0; i <= DIAG_N; i++) d->pub[i] = 0;
        for (int i = 0; i < 7; i++) d->sec[i] = 0;
        d->n_play = 0;
        d->magic = DIAG_MAGIC;
        d->last_v = 0xffu;
        d->frame_t0 = t0;
        d->frame_cyc = 0;
        d->frames = 0;
        d->tag = 0;
        d->win_max = 0;
        d->win_sum = 0;
        d->call_max = 0;
        d->per_max = 0;
        d->late = 0;
        *STOCK_S = 0u;
        *STOCK_SH = 0u;
        *STOCK_F = 0u;
        *ALL_MAX = 0u;
    }
    if (uv <= d->last_v) {   /* a new frame: close the previous one */
        const uint32_t per = t0 - d->frame_t0;
        d->frame_t0 = t0;
        if (d->frame_cyc > d->win_max) d->win_max = d->frame_cyc;
        d->win_sum += d->frame_cyc;   /* < 2^32 over 1024 frames of < 4M cycles */
        {
            const uint32_t all = d->frame_cyc + *STOCK_F;
            if (all > *ALL_MAX) *ALL_MAX = all;
            *STOCK_F = 0u;
        }
        if (per > d->per_max) d->per_max = per;
        if (per > 700000u) d->late++;
        if (per > 676667u) {   /* more than 1.5% late: enough to click (capload item 5, a running total) */
            const uint32_t s5 = d->pub[5];   /* (not `d->pub[5]++`: selcc, see gen_fed) */
            d->pub[5] = s5 + 1u;
        }
        d->frame_cyc = 0;
        d->frames++;
        if ((d->frames & 1023u) == 0u) {
            d->pub[0] = d->win_max;
            d->pub[1] = d->win_sum >> 10;
            d->pub[2] = d->call_max;
            d->pub[3] = d->per_max;
            d->pub[4] = d->late;
#ifdef GEN_SECTIONS
            for (int i = 0; i < 7; i++) { d->pub[7 + i] = d->sec[i]; d->sec[i] = 0; }
            d->pub[14] = d->n_play;
            d->pub[6] = d->pub[15];   /* samples analysed in the window */
#else
            /* the stock generators: mean cycles a frame, and the worst frame of all */
            d->pub[6] = *STOCK_S >> 10;
            d->pub[7] = *STOCK_SH >> 10;
            d->pub[8] = *ALL_MAX;
            d->pub[14] = 0;
#endif
            *STOCK_S = 0u;
            *STOCK_SH = 0u;
            *ALL_MAX = 0u;
            d->pub[15] = 0;
            d->n_play = 0;
            d->win_max = 0;
            d->win_sum = 0;
            d->call_max = 0;
            d->per_max = 0;
        }
        if ((d->frames & 31u) == 0u) {
            d->tag++;
            if (d->tag >= DIAG_N) d->tag = 0;
            const uint32_t w = (d->tag << 28) | (d->pub[d->tag] & 0x0fffffffu);
            const uint32_t sw = (w << 16) | (w >> 16);
            REPLY0(0) = sw;
            REPLY0(1) = sw;
        }
    }
    d->last_v = uv;
}

static void diag_account(int v, uint32_t t0)
{
    const uint32_t c = cc_emuclk() - t0;
    gen_diag *d = DIAG_AT;
    diag_frame(d, (uint32_t)v, t0);
    d->frame_cyc += c;
    if (c > d->call_max) d->call_max = c;
}

/* dt2entry.asm, after a stock generator's call: its voice record, cycles, and
   kind (0 STRETCH, 1 the shared generator) */
void cc_diag_stock(uint32_t *rec, uint32_t c, int kind)
{
    const uint32_t off = (uint32_t)((uintptr_t)rec - VOICE_BASE);
    const uint32_t v = (off * 2222u) >> 20;
    if (off >= NVOICE * VOICE_STRIDE) return;
    gen_diag *d = DIAG_AT;
    diag_frame(d, v, cc_emuclk() - c);
    const uint32_t f = *STOCK_F;
    *STOCK_F = f + c;
    if (kind) {
        const uint32_t s = *STOCK_SH;
        *STOCK_SH = s + c;
    } else {
        const uint32_t s = *STOCK_S;
        *STOCK_S = s + c;
    }
}

/* render.asm cc_bfast: a call it served, at a frame's first voice */
void cc_diag_acc(int v, uint32_t t0) { diag_account(v, t0); }

void cc_dt2_stretch(uint32_t *rec, float *out, int n)
{
    const uint32_t t0 = cc_emuclk();
    const int v = gen_run(rec, out, n, 2);
    if (v >= 0) diag_account(v, t0);
}
void cc_dt2_repitch(uint32_t *rec, float *out, int n)
{
    const uint32_t t0 = cc_emuclk();
    const int v = gen_run(rec, out, n, 3);
    if (v >= 0) diag_account(v, t0);
}
#else
void cc_diag_stock(uint32_t *rec, uint32_t c, int kind) { (void)rec; (void)c; (void)kind; }
void cc_diag_acc(int v, uint32_t t0) { (void)v; (void)t0; }
void cc_dt2_stretch(uint32_t *rec, float *out, int n) { (void)gen_run(rec, out, n, 2); }
void cc_dt2_repitch(uint32_t *rec, float *out, int n) { (void)gen_run(rec, out, n, 3); }
#endif
