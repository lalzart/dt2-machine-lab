/*
 * capicola.h -- a C99 port of Capicola's keyframe time-stretch core.
 *
 * Ported from Capicola (lib/: DeluxeLine.h, SparseLine.h, Analyzer.h,
 * Granule.h, Detector.h, filter.h, KeyframeRecorder.h), GNU AGPL-3.0; this
 * port is distributed under the same licence. The algorithm is Capicola's
 * author's ("Keyframe Time Stretching via Extrema Sampling", DAFx26).
 *
 * Stage 1 of the port: the same arithmetic, operation for operation, so it
 * can be checked sample for sample against the C++ (test/compare.cpp).
 * Differences from the C++, none of which changes an output sample:
 *   - no templates: the keyframe ring is caller-provided memory with a
 *     runtime power-of-two size (it will live in DSP memory);
 *   - no waveshaper (the C++ bypasses it exactly when none is given);
 *   - the Detector keeps its counters but not its write-only event log.
 * Time is double by default; -DCC_F32 (stage 2, for the DSP) makes it float
 * measured from a moving origin, with 32-bit keyframe indices.
 *
 * selcc (the SHARC compiler) rules this code keeps: no struct passed or
 * returned by value across a call (selcc returns a struct wrongly across
 * object files and drops a double member of a struct passed by value), and
 * no type-punning unions (selcc returns 0 for them), and no typedef of a
 * floating type (selcc does integer arithmetic on it). Structs are filled
 * through pointers instead; plain struct assignment is fine.
 */
#ifndef CAPICOLA_H
#define CAPICOLA_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Stage 1 (default): double time and 64-bit keyframe indices, bit-exact with the
   C++. Stage 2 (-DCC_F32): float time relative to a moving origin and 32-bit
   indices, for the DSP; cc_recorder_process shifts the origin as it goes, so the
   times near the play and write heads stay small and keep their fraction.
   cc_time is a macro, not a typedef: selcc does integer arithmetic on a typedef'd
   float or double (work/dtest/probe5.c). */
#ifdef CC_F32
#define cc_time float
typedef int32_t cc_idx;
#define CC_T(x) ((float)(x))
#define cc_fabst fabsf
#else
#define cc_time double
typedef int64_t cc_idx;
#define CC_T(x) ((double)(x))
#define cc_fabst fabs
#endif

/* ---- DeluxeLine<float, 8>: an 8-sample ring with B-spline reads ---------- */
typedef struct { float value, d1, d2, tkeo; } cc_cubic;
typedef struct { float buf[8]; int wp; } cc_dline8;

void     cc_dline8_init(cc_dline8 *l);
void     cc_dline8_write(cc_dline8 *l, float s);
void     cc_dline8_bspline_d1_int(const cc_dline8 *l, int delay, cc_cubic *out);
float    cc_dline8_bspline(const cc_dline8 *l, float delay);
void     cc_dline8_bspline_full(const cc_dline8 *l, float delay, int stride, cc_cubic *out);

/* ---- filters (TPT / zero-delay feedback) --------------------------------- */
typedef struct { float lp, in, s, gain, g; } cc_onepole;
void  cc_onepole_init(cc_onepole *f);
void  cc_onepole_set_cutoff(cc_onepole *f, float fc);
float cc_onepole_tick(cc_onepole *f, float x);

typedef struct { float s1, s2, q, g, r, hp, lp, bp, in, num, den; } cc_svf;
void cc_svf_init(cc_svf *f);
void cc_svf_set_controls(cc_svf *f, float fc, float q);
void cc_svf_tick(cc_svf *f, float x);

/* ---- SparseLine: the keyframe ring --------------------------------------- */
typedef struct cc_keyframe { float value; cc_time time; } cc_keyframe;
typedef struct {
    int32_t s1, s2;         /* ring slots of p1 (later) and p2; slots, not pointers:
                               selcc does not yet resolve a struct through a nested pointer */
    cc_idx index;           /* monotonic index of p1 */
    float duration, inv_duration;
    cc_time end_time;
} cc_window;
typedef struct { cc_idx sparse; cc_time uniform; } cc_pos;   /* also a distance */
typedef struct {
    cc_keyframe *buf;
    cc_idx write_pos;       /* monotonic: keyframes ever written */
    int size;               /* power of two, >= 4 */
    cc_idx origin;          /* the sample count a stored time of 0 stands for */
} cc_sparse;

void         cc_sparse_init(cc_sparse *s, cc_keyframe *storage, int size);
void         cc_sparse_clear(cc_sparse *s);
cc_keyframe *cc_sparse_get(cc_sparse *s, cc_idx index);
void         cc_sparse_write(cc_sparse *s, const cc_keyframe *kf);
cc_keyframe *cc_sparse_latest(cc_sparse *s);
void         cc_sparse_window_at_latest(cc_sparse *s, cc_window *w);
void         cc_sparse_write_position(cc_sparse *s, cc_pos *p);
void         cc_sparse_min_read_position(cc_sparse *s, int block_size, cc_pos *p);
void         cc_sparse_step_window(cc_sparse *s, cc_window *w, cc_time index);
float        cc_sparse_read(const cc_sparse *s, const cc_window *w, float t);   /* Catmull-Rom/Hermite */

/* ---- Analyzer: sparsifies a sample stream into keyframes ----------------- */
typedef struct {
    cc_sparse *sparse;
    cc_dline8 raw;
    cc_cubic  most_recent;
    cc_idx    raw_count, sparse_count;
    float     threshold, fs;
    int       first_analysis, arm_final;
} cc_analyzer;

void cc_analyzer_init(cc_analyzer *a, cc_sparse *s, float fs);
int  cc_analyzer_analyze(cc_analyzer *a, float input);
int  cc_analyzer_guard_keyframe(cc_analyzer *a, cc_time max_gap);
int  cc_analyzer_is_full(const cc_analyzer *a);

/* ---- Granule: a grain reader (stretch grid + pitched head) --------------- */
typedef struct {
    cc_window w;
    cc_time index;
    float tau, speed, result;
} cc_playhead;

typedef struct {
    cc_sparse  *sparse;
    cc_playhead ideal, actual, temp;
    cc_pos      write_pos, live_edge, master;
    cc_window   master_w;
    cc_pos      distance, runway, backlog;
    float       pitch, stretch;
    int         leash;
    float       fixed_duration, fixed_increment;
    float       adaptive_duration, adaptive_increment;
    float       splice_phase;
    int         splicing, adaptive;
    int         block_size;
} cc_granule;

void  cc_granule_init(cc_granule *g, cc_sparse *s, cc_time start_pos);
void  cc_granule_set_pitch(cc_granule *g, float p);
void  cc_granule_set_stretch(cc_granule *g, float t);
void  cc_granule_set_leash(cc_granule *g, int k);
void  cc_granule_set_fade(cc_granule *g, float f);
void  cc_granule_begin_block(cc_granule *g, int size);
void  cc_granule_retrigger(cc_granule *g);
float cc_granule_read(cc_granule *g);

/* ---- Detector: TKEO transient finder ------------------------------------- */
typedef struct {
    cc_dline8  raw, env;
    cc_cubic   prev_newer;
    cc_svf     svf;
    cc_onepole avg_lp;
    float      fs, threshold, cutoff, resonance;
    uint32_t   kept_count, total_count;
    int        gap_samps, min_gap_samps;
} cc_detector;

void cc_detector_init(cc_detector *d, float fs);
void cc_detector_set_cutoff(cc_detector *d, float fc);
void cc_detector_set_resonance(cc_detector *d, float r);
void cc_detector_set_threshold(cc_detector *d, float t);
int  cc_detector_analyze(cc_detector *d, float x);

/* ---- KeyframeRecorder: transport + two trading grains -------------------- */
enum { CC_STOPPED, CC_RECORDING, CC_PLAYBACK, CC_LIVE_EFFECT, CC_SOURCE };
enum { CC_REQ_NONE, CC_REQ_ARM, CC_REQ_RECORD, CC_REQ_PLAY, CC_REQ_RESTART_PLAYBACK,
       CC_REQ_CLEAR, CC_REQ_STOP_REC, CC_REQ_STOP_PLAYING, CC_REQ_LIVE_EFFECT,
       CC_REQ_SLICE };

typedef struct {
    cc_sparse   sparse;
    cc_analyzer analyzer;
    cc_granule  granule[2];
    int         live_g;
    float       x_gain, x_step;
    cc_detector detector;
    uint32_t    transient_count;
    int         state, request;
    float       cur_pitch, cur_stretch, cur_threshold, cur_fade;
    int         cur_leash;
    int         pending_seed, fired_this_block, last_block_size;
    float       trig_gate;
    /* CC_SOURCE (port addition, not in the C++): a 16-bit sample in memory,
       analysed just ahead of the heads. Fields after this point only; the
       assembly render loop relies on the offsets above. */
    uintptr_t   src;                 /* byte address of sample 0 (int16, little-endian) */
    int32_t     src_pos, src_end, src_loop;   /* next sample to analyse; end; loop start or -1 */
    int         src_state;           /* 0 analysing, 1 past the end (silence), 2 idle */
    cc_idx      src_t0;              /* analysed-sample count where this note began */
    cc_idx      src_t_end;           /* ... and where its sample ended */
    int         src_spawn;           /* a grain to start at src_t0 */
    float       trig_fade;           /* retrigger crossfade, samples */
    float       feed_target, feed_gap;   /* src_feed's block bounds (for sharc/feed.asm) */
    int         feed_cap;
    /* clean read (CC_CLEAN, port addition): the heads read the source's own
       samples (Catmull-Rom) as well as, or instead of, Capicola's keyframes:
       blend 0 = the samples, 1 = the keyframes (the default), in between a mix */
    float       blend;
    int32_t     src_start;                      /* this note's first sample */
    uintptr_t   prev_src;                       /* the note before it, for its fade-out */
    int32_t     prev_start, prev_end;
    cc_idx      prev_t0;
    int         prev_valid;
    float       clean_y[4];                     /* scratch for sharc/clean.asm */
    /* lookahead budget (port addition): src_feed always analyses what this
       block's heads need; the lookahead beyond that (for aligned splices) at
       most feed_extra samples, and reports how many it took in feed_extra_used.
       Default: unlimited. Four words keep the size a multiple of 16 bytes. */
    int32_t     feed_extra, feed_extra_used, rebase_lag;   /* rebase_lag: CC_F32's rebase this many samples later (default 0) */
    int32_t     fast_n;      /* CC_CLEAN: this block's first fast_n samples need no event check (rec_fast_count) */
    /* sample loop (sharc/dt2gen.c's plan B): a clean read at or past b_lend (from
       the note's start) or before it wraps by b_llen; 0 = no loop */
    float       b_lend, b_llen;
    /* plan B's positions are small floats plus b_k whole samples (b_kf the same,
       as a float; b_lo = 1 - b_k, the clean read's fast check): a read at index is
       the note's sample index + b_k. 0, 0, 1 elsewhere */
    int32_t     b_k;
    float       b_kf, b_lo;
} cc_recorder;

void cc_recorder_init(cc_recorder *r, cc_keyframe *storage, int size);
void cc_recorder_submit(cc_recorder *r, int request);
void cc_recorder_set_pitch(cc_recorder *r, float p);
void cc_recorder_set_stretch(cc_recorder *r, float t);
void cc_recorder_set_leash(cc_recorder *r, int k);
void cc_recorder_set_threshold(cc_recorder *r, float v);
void cc_recorder_set_fade(cc_recorder *r, float f);
void cc_recorder_set_transient_threshold(cc_recorder *r, float t);
void cc_recorder_set_tkeo_cutoff(cc_recorder *r, float fc);
void cc_recorder_set_tkeo_resonance(cc_recorder *r, float q);
/* Stereo link (port addition, -DCC_LINK): a channel recording (mode 1) keeps,
   in order, each aligned splice's offset from the grid; the other channel of
   the same sample, replaying (mode 2) right after, starts its k-th splice at the
   k-th offset, so both channels splice at the same points. The record lives at
   CC_LINK_AT (default: static memory). */
#define CC_LINK_MAX 32
typedef struct { int32_t mode, n, k, voice; float off[CC_LINK_MAX]; int32_t rebased; } cc_link;   /* rebased: the recording channel rebased this block */

void cc_recorder_process(cc_recorder *r, const float *in, float *out, int n);
/* Start a note from a 16-bit sample at byte address data: play from sample start
   to end (exclusive), looping back to loop_start if it is >= 0. The first note
   resets the engine; later ones continue its clock and crossfade over
   trig_fade samples (0: switch at once, without rendering the old note). cc_recorder_process then ignores `in`. */
void cc_recorder_source(cc_recorder *r, uintptr_t data, int32_t start, int32_t end, int32_t loop_start);
void cc_recorder_set_blend(cc_recorder *r, float b);   /* CC_CLEAN: 0 samples .. 1 keyframes */

#ifdef __cplusplus
}
#endif
#endif /* CAPICOLA_H */
