/*
 * capicola.c -- C99 port of Capicola's keyframe core (see capicola.h).
 * GNU AGPL-3.0, as Capicola. Each block names the C++ it follows.
 */
#include "capicola.h"
#if defined(CC_SOURCE_ONLY) && !defined(CC_ASM)
#error "CC_SOURCE_ONLY drops the C analyzer and needs sharc/feed.asm (CC_ASM)"
#endif
/* CC_SOURCE_ONLY (with CC_ASM): only what CC_SOURCE uses -- no transient
   detector, no C analyzer (feed.asm), no record/live/playback transport. */
#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static float smooth_step(float p) { return p * p * (3.0f - 2.0f * p); }

/* ======================= DeluxeLine<float, 8> ============================ */

static float dl_get(const cc_dline8 *l, int position) { return l->buf[position & 7]; }

void cc_dline8_init(cc_dline8 *l)
{
    /* unrolled: selcc makes the loop a hardware DO loop, which the device build avoids */
    l->wp = 0;
    l->buf[0] = 0.0f; l->buf[1] = 0.0f; l->buf[2] = 0.0f; l->buf[3] = 0.0f;
    l->buf[4] = 0.0f; l->buf[5] = 0.0f; l->buf[6] = 0.0f; l->buf[7] = 0.0f;
}

#ifndef CC_SOURCE_ONLY
void cc_dline8_write(cc_dline8 *l, float s)
{
    l->buf[l->wp] = s;
    l->wp = (l->wp + 1) & 7;
}

void cc_dline8_bspline_d1_int(const cc_dline8 *l, int delay, cc_cubic *out)
{
    const float x0 = dl_get(l, l->wp - delay + 1);
    const float x1 = dl_get(l, l->wp - delay);
    const float x2 = dl_get(l, l->wp - delay - 1);
    const float inv6 = (float)(1.0 / 6.0);
    const float half = 0.5f;
    out->value = (x0 + 4.0f * x1 + x2) * inv6;
    out->d1    = (x2 - x0) * half;
    out->d2    = 0.0f;
    out->tkeo  = 0.0f;
}

float cc_dline8_bspline(const cc_dline8 *l, float delay)
{
    const int   di = (int)delay;
    const float f  = delay - (float)di;
    const float x0 = dl_get(l, l->wp - di + 1);
    const float x1 = dl_get(l, l->wp - di);
    const float x2 = dl_get(l, l->wp - di - 1);
    const float x3 = dl_get(l, l->wp - di - 2);
    const float t2 = f * f;
    const float t3 = t2 * f;
    const float inv6 = (float)(1.0 / 6.0);
    const float B0 = 1.0f + f * (-3.0f + f * (3.0f - f));
    const float B1 = 4.0f + t2 * (-6.0f + 3.0f * f);
    const float B2 = 1.0f + f * (3.0f + f * (3.0f - 3.0f * f));
    const float B3 = t3;
    return (x0 * B0 + x1 * B1 + x2 * B2 + x3 * B3) * inv6;
}

void cc_dline8_bspline_full(const cc_dline8 *l, float delay, int stride, cc_cubic *out)
{
    const float inv_stride = 1.0f / (float)stride;
    const float ds = delay * (float)stride;
    const int   di = (int)ds;
    const float f  = ds - (float)di;
    const float x0 = dl_get(l, l->wp - di + stride);
    const float x1 = dl_get(l, l->wp - di);
    const float x2 = dl_get(l, l->wp - di - stride);
    const float x3 = dl_get(l, l->wp - di - (2 * stride));
    const float t2 = f * f;
    const float t3 = t2 * f;
    const float inv6 = (float)(1.0 / 6.0);
    const float term1 = 3.0f * f;
    const float term2 = 6.0f * f;
    const float B0 = 1.0f + f * (-3.0f + f * (3.0f - f));
    const float B1 = 4.0f + t2 * (-6.0f + term1);
    const float B2 = 1.0f + f * (3.0f + f * (3.0f - term1));
    const float B3 = t3;
    const float dB0 = -3.0f + f * (6.0f - term1);
    const float dB1 = f * (-12.0f + 9.0f * f);
    const float dB2 = 3.0f + f * (6.0f - 9.0f * f);
    const float dB3 = term1 * f;
    const float d2B0 = 6.0f - term2;
    const float d2B1 = -12.0f + 18.0f * f;
    const float d2B2 = 6.0f - 18.0f * f;
    const float d2B3 = term2;
    const float value = (x0 * B0 + x1 * B1 + x2 * B2 + x3 * B3) * inv6;
    const float d1 = (x0 * dB0 + x1 * dB1 + x2 * dB2 + x3 * dB3) * inv6 * inv_stride;
    const float d2 = (x0 * d2B0 + x1 * d2B1 + x2 * d2B2 + x3 * d2B3) * inv6 * inv_stride * inv_stride;
    out->value = value;
    out->d1 = d1;
    out->d2 = d2;
    out->tkeo = fabsf(d1 * d1 - value * d2);
}

/* ============================ filter.h =================================== */

void cc_onepole_init(cc_onepole *f)
{
    f->lp = f->in = f->s = 0.0f;
    cc_onepole_set_cutoff(f, 1.0f);
}

void cc_onepole_set_cutoff(cc_onepole *f, float fc)
{
    f->g = tanf((float)(M_PI * 0.5f * fc));
    f->gain = f->g / (1.0f + f->g);
}

float cc_onepole_tick(cc_onepole *f, float x)
{
    f->in = x;
    float v = f->gain * (f->in - f->s);
    f->lp = v + f->s;
    f->s  = f->lp + v;
    return f->lp;
}

void cc_svf_init(cc_svf *f)
{
    f->s1 = f->s2 = f->hp = f->lp = f->bp = f->in = 0.0f;
    cc_svf_set_controls(f, 1.0f, 0.0f);
}

void cc_svf_set_controls(cc_svf *f, float fc, float q)
{
    f->g = tanf((float)(M_PI * 0.5f * fc));
    f->q = 0.5f + 4.0f * q;
    f->r = 1.0f / (2.0f * f->q);
    f->num = 2.0f * f->r + f->g;
    f->den = 1.0f + 2.0f * f->r * f->g + f->g * f->g;
}

void cc_svf_tick(cc_svf *f, float x)
{
    f->in = x;
    f->hp = (f->in - f->num * f->s1 - f->s2) / f->den;
    f->bp = f->g * f->hp + f->s1;
    f->lp = f->g * f->bp + f->s2;
    f->s1 = f->g * f->hp + f->bp;
    f->s2 = f->g * f->bp + f->lp;
}

#endif /* !CC_SOURCE_ONLY */

/* ============================ SparseLine ================================= */

static cc_idx sp_oldest(const cc_sparse *s)
{
    return (s->write_pos > (cc_idx)s->size) ? (s->write_pos - s->size) : 0;
}

void cc_sparse_init(cc_sparse *s, cc_keyframe *storage, int size)
{
    /* Only slot 0 is cleared: until a slot is written no reader sees it except
       slot 0 of an empty ring (as sp_reset). The C++ clears the whole ring; the
       outputs are the same (test/compare.cpp). */
    s->buf = storage;
    s->size = size;
    s->write_pos = 0;
    s->origin = 0;
    storage[0].value = 0.0f;
    storage[0].time = CC_T(1.0);
}

#ifndef CC_SOURCE_ONLY
void cc_sparse_clear(cc_sparse *s)
{
    s->write_pos = 0;
    s->origin = 0;
    for (int i = 0; i < s->size; i++) { s->buf[i].value = 0.0f; s->buf[i].time = CC_T(1.0); }
}
#endif

/* As cc_sparse_clear, but only the slots written since: no reader looks past
   [oldest, newest] (sp_slot and the step loops clamp to it) except slot 0 while
   the ring is empty, so the rest need not be cleared again. */
static void sp_reset(cc_sparse *s)
{
    int n = (s->write_pos < (cc_idx)s->size) ? (int)s->write_pos : s->size;
    if (n < 1) n = 1;
    for (int i = 0; i < n; i++) { s->buf[i].value = 0.0f; s->buf[i].time = CC_T(1.0); }
    s->write_pos = 0;
    s->origin = 0;
}

/* The ring slot SparseLine::GetSample(index) returns a pointer to. */
static int32_t sp_slot(const cc_sparse *s, cc_idx index)
{
    cc_idx newest = s->write_pos - 1;
    if (newest < 0) return 0;
    cc_idx oldest = sp_oldest(s);
    if (index < oldest) index = oldest;
    else if (index > newest) index = newest;
    return (int32_t)(index & (s->size - 1));
}

cc_keyframe *cc_sparse_get(cc_sparse *s, cc_idx index) { return &s->buf[sp_slot(s, index)]; }

void cc_sparse_write(cc_sparse *s, const cc_keyframe *kf)
{
    s->buf[s->write_pos & (s->size - 1)] = *kf;
    s->write_pos++;
}

/* = cc_sparse_get(s, write_pos - 1): the newest index needs no clamping */
cc_keyframe *cc_sparse_latest(cc_sparse *s)
{
    return &s->buf[(s->write_pos > 0) ? (int32_t)((s->write_pos - 1) & (s->size - 1)) : 0];
}

void cc_sparse_window_at_latest(cc_sparse *s, cc_window *w)
{
    cc_idx idx = s->write_pos - 1;
    w->s1 = sp_slot(s, idx);
    w->s2 = sp_slot(s, idx - 1);
    w->duration = (float)cc_fabst(s->buf[w->s1].time - s->buf[w->s2].time);
    w->inv_duration = (w->duration > 1e-5f) ? (1.0f / w->duration) : 0.0f;
    w->index = idx;
    w->end_time = s->buf[w->s1].time;
}

void cc_sparse_write_position(cc_sparse *s, cc_pos *p)
{
    p->sparse = s->write_pos - 1;
    p->uniform = cc_sparse_latest(s)->time;
}

void cc_sparse_min_read_position(cc_sparse *s, int block_size, cc_pos *p)
{
    cc_time uniform = cc_sparse_latest(s)->time - (cc_time)block_size;
    cc_window w;
    cc_sparse_window_at_latest(s, &w);
    cc_sparse_step_window(s, &w, uniform);
    p->sparse = w.index - 1;
    p->uniform = uniform;
}

/* The window whose later keyframe is index i, as the step loops leave it. */
static void sp_window_at(const cc_sparse *s, cc_window *w, cc_idx i)
{
    const cc_idx mask = s->size - 1;
    w->index = i;
    w->s1 = (int32_t)(i & mask);
    w->s2 = (int32_t)((i - 1) & mask);
    float d = (float)(s->buf[w->s1].time - s->buf[w->s2].time);
    w->duration = d;
    w->inv_duration = (d > 1e-5f) ? (1.0f / d) : 0.0f;
    w->end_time = s->buf[w->s1].time;
}

#define SP_WALK 16   /* longer walks than this jump by binary search */

static cc_time sp_time(const cc_sparse *s, cc_idx i) { return s->buf[i & (s->size - 1)].time; }
static float sp_value(const cc_sparse *s, cc_idx i) { return s->buf[i & (s->size - 1)].value; }

#ifndef SP_SHORT
#define SP_SHORT 48   /* a walk this short goes by indices alone, then one window */
#endif

void cc_sparse_step_window(cc_sparse *s, cc_window *w, cc_time index)
{
    cc_idx newest = s->write_pos - 1;
    cc_idx oldest = sp_oldest(s);
    const cc_idx mask = s->size - 1;
#ifndef CC_NO_SHORTWALK
    /* The usual case (the master window each block, the live edge a block back
       from the newest): the target is a few keyframes away, but the window's
       distance from the newest or oldest sends the code below into a binary
       search over the whole ring. Walking the indices to where the step loops
       stop and making that window once (sp_window_at: the same fields as the
       loops' last step) gives the same window. Longer walks fall through. */
    if (index > w->end_time) {
        cc_idx i = w->index;
        int k = 0;
        while (i < newest && sp_time(s, i) < index && k < SP_SHORT) { i++; k++; }
        if (i >= newest || sp_time(s, i) >= index) {
            if (i != w->index) sp_window_at(s, w, i);
            return;
        }
    } else if (index < s->buf[w->s2].time) {
        cc_idx i = w->index;
        int k = 0;
        while (i > oldest + 1 && index < sp_time(s, i - 1) && k < SP_SHORT) { i--; k++; }
        if (i <= oldest + 1 || index >= sp_time(s, i - 1)) {
            if (i != w->index) sp_window_at(s, w, i);
            return;
        }
    }
#endif
    /* A long walk (a spawn or a trigger far from the window) lands by binary
       search where the step loops below would stop: keyframe times only grow
       between oldest and newest, so the loops stop at the first keyframe at or
       past index (forward) or the last window starting at or before it (back). */
    if (index > w->end_time && newest - w->index > SP_WALK) {
        cc_idx lo = w->index + 1, hi = newest;
        while (lo < hi) {
            cc_idx mid = lo + ((hi - lo) >> 1);
            if (sp_time(s, mid) >= index) hi = mid; else lo = mid + 1;
        }
        sp_window_at(s, w, lo);
    } else if (index < s->buf[w->s2].time && w->index - (oldest + 1) > SP_WALK) {
        cc_idx lo = oldest + 1, hi = w->index - 1;
        while (lo < hi) {
            cc_idx mid = lo + ((hi - lo + 1) >> 1);
            if (sp_time(s, mid - 1) <= index) lo = mid; else hi = mid - 1;
        }
        sp_window_at(s, w, lo);
    }
    while (index > w->end_time && w->index < newest) {
        w->index++;
        w->s2 = w->s1;
        w->s1 = (int32_t)(w->index & mask);
        float d = (float)(s->buf[w->s1].time - s->buf[w->s2].time);
        w->duration = d;
        w->inv_duration = (d > 1e-5f) ? (1.0f / d) : 0.0f;
        w->end_time = s->buf[w->s1].time;
    }
    while (index < s->buf[w->s2].time && w->index > oldest + 1) {
        w->index--;
        w->s1 = w->s2;
        w->s2 = (int32_t)((w->index - 1) & mask);
        float d = (float)(s->buf[w->s1].time - s->buf[w->s2].time);
        w->duration = d;
        w->inv_duration = (d > 1e-5f) ? (1.0f / d) : 0.0f;
        w->end_time = s->buf[w->s1].time;
    }
}

float cc_sparse_read(const cc_sparse *s, const cc_window *w, float t)
{
    if (t < 0.0f) t = 0.0f; else if (t > 1.0f) t = 1.0f;
    float t2 = t * t;
    float h0 = (2.0f * t - 3.0f) * t2 + 1.0f;
    float h1 = (-2.0f * t + 3.0f) * t2;
    return h0 * s->buf[w->s1].value + h1 * s->buf[w->s2].value;
}

/* ============================= Analyzer ================================== */

#ifndef CC_SOURCE_ONLY
static void an_push(cc_analyzer *a, const cc_keyframe *kf)
{
    cc_sparse_write(a->sparse, kf);
    a->sparse_count++;
    a->raw_count++;
}

#endif /* !CC_SOURCE_ONLY */

void cc_analyzer_init(cc_analyzer *a, cc_sparse *s, float fs)
{
    a->sparse = s;
    a->fs = fs;
    cc_dline8_init(&a->raw);
    a->raw_count = 0;
    a->sparse_count = 0;
    a->threshold = 0.001f;
    a->first_analysis = 1;
    a->arm_final = 0;
    memset(&a->most_recent, 0, sizeof a->most_recent);
}

#ifndef CC_SOURCE_ONLY
int cc_analyzer_is_full(const cc_analyzer *a) { return a->sparse_count >= a->sparse->size - 1; }

int cc_analyzer_analyze(cc_analyzer *a, float input)
{
    cc_dline8_write(&a->raw, input);
    const cc_cubic older = a->most_recent;
    cc_dline8_bspline_d1_int(&a->raw, 2, &a->most_recent);

    int crossed = ((older.d1 > 0.0f && a->most_recent.d1 <= 0.0f) ||
                   (older.d1 < 0.0f && a->most_recent.d1 >= 0.0f));

    cc_keyframe *last = cc_sparse_latest(a->sparse);
    cc_keyframe kf;
    kf.value = a->most_recent.value;
    kf.time  = (a->raw_count > 0) ? (cc_time)(a->raw_count - 1 - a->sparse->origin) : CC_T(0.0);

    float value_diff = fabsf(a->most_recent.value - last->value);

    if (a->first_analysis) { an_push(a, &kf); a->first_analysis = 0; return 1; }
    if (a->arm_final)      { an_push(a, &kf); a->arm_final = 0;      return 1; }
    if (crossed && value_diff > a->threshold) {
        float  alpha = fabsf(older.d1) / (fabsf(older.d1) + fabsf(a->most_recent.d1));
        cc_time index = (cc_time)(a->raw_count - 2 - a->sparse->origin) + alpha;
        if (cc_fabst(index - last->time) > CC_T(1.0)) {
            kf.time  = index;
            kf.value = cc_dline8_bspline(&a->raw, 3.0f - alpha);
            an_push(a, &kf);
            return 1;
        }
    }
    a->raw_count++;
    return 0;
}

int cc_analyzer_guard_keyframe(cc_analyzer *a, cc_time max_gap)
{
    if ((cc_time)(a->raw_count - a->sparse->origin) - cc_sparse_latest(a->sparse)->time <= max_gap) return 0;
    cc_keyframe kf;
    kf.value = a->most_recent.value;
    kf.time  = (a->raw_count > 0) ? (cc_time)(a->raw_count - 1 - a->sparse->origin) : CC_T(0.0);
    cc_sparse_write(a->sparse, &kf);
    a->sparse_count++;
    return 1;
}

#endif /* !CC_SOURCE_ONLY */

/* ============================== Granule ================================== */

static void ph_make(cc_playhead *p, const cc_window *w, cc_time pos, float rate)
{
    p->w = *w; p->index = pos; p->tau = 0.0f; p->speed = rate; p->result = 0.0f;
}

#ifdef CC_CLEAN
/* The recorder whose heads are reading (set by src_process for CC_SOURCE, 0
   otherwise): ph_sample has only the keyframe ring. A fixed cell, not a static,
   so a SHARC build can place it (dt2gen.c: DDR). */
#ifndef CC_CTX_AT
static cc_recorder *cc_ctx_mem;
#define CC_CTX_AT (&cc_ctx_mem)
#endif

#ifndef CC_ASM   /* the device build has sharc/render.asm's cc_clean_read */
static float cl_sample(uintptr_t base, int32_t i, int32_t start, int32_t end)
{
    if (i < start) return 0.0f;
    if (i >= end) return 0.0f;
    const uintptr_t a = base + 2u * (uint32_t)i;
    const uint32_t w = *(const uint32_t *)(a & ~(uintptr_t)3);
    const int32_t v = (a & 2u) ? ((int32_t)w >> 16) : ((int32_t)(w << 16) >> 16);
    return (float)v * (1.0f / 32768.0f);
}

/* The source's sample at keyframe time `index` (stream sample t = keyframe time
   t; the note began at stream sample src_t0 = its sample src_start), Catmull-Rom
   between the four around it, silent outside the note. Before this note's
   start, the previous note's mapping (a retrigger's fade-out). sharc/clean.asm
   implements the same as cc_clean_read. */
#ifdef B_READSTAT   /* (host analysis: how many reads, how many at whole-sample positions) */
unsigned long b_reads, b_reads_int;
#endif
float rec_clean_read(const cc_recorder *r, cc_time index)
{
#ifdef B_READSTAT
    b_reads++;
    if (index == (cc_time)(int32_t)index) b_reads_int++;
#endif
    {   /* the four samples inside the note: render.asm's .fcl fast path, the index
           small and b_k whole samples added to the sample number, not the float */
        const cc_time rel = index - (cc_time)(r->src_t0 - r->sparse.origin);
        if (rel >= r->b_lo) {
            if (rel < (cc_time)(r->src_end - r->src_start - 2 - r->b_k)) {
                int32_t k = (int32_t)rel;
                if ((cc_time)k > rel) k--;
                const float f = (float)(rel - (cc_time)k);
                const int32_t i = r->src_start + k + r->b_k;
                const float y0 = cl_sample(r->src, i - 1, r->src_start, r->src_end);
                const float y1 = cl_sample(r->src, i, r->src_start, r->src_end);
                const float y2 = cl_sample(r->src, i + 1, r->src_start, r->src_end);
                const float y3 = cl_sample(r->src, i + 2, r->src_start, r->src_end);
                const float c1 = 0.5f * (y2 - y0);
                const float c2 = y0 - 2.5f * y1 + 2.0f * y2 - 0.5f * y3;
                const float c3 = 0.5f * (y3 - y0) + 1.5f * (y1 - y2);
                return ((c3 * f + c2) * f + c1) * f + y1;
            }
        }
    }
    index += (cc_time)r->b_kf;   /* the rest (.fcl_slow): at the absolute index */
    if (r->b_llen > 0.0f) {   /* a looped note: into the loop (render.asm's .fcl_slow) */
        const cc_time base = (cc_time)(r->src_t0 - r->sparse.origin);
        while (index - base >= (cc_time)r->b_lend) index -= (cc_time)r->b_llen;
        while (index - base < CC_T(0.0)) index += (cc_time)r->b_llen;
    }
    cc_time rel = index - (cc_time)(r->src_t0 - r->sparse.origin);
    uintptr_t base = r->src;
    int32_t start = r->src_start, end = r->src_end;
    if (rel < CC_T(0.0)) {
        if (!r->prev_valid) return 0.0f;
        rel = index - (cc_time)(r->prev_t0 - r->sparse.origin);
        base = r->prev_src;
        start = r->prev_start;
        end = r->prev_end;
    }
    int32_t k = (int32_t)rel;
    if ((cc_time)k > rel) k--;
    const float f = (float)(rel - (cc_time)k);
    const int32_t i = start + k;
    int32_t ix[4];
    for (int d = 0; d < 4; d++) {   /* a looped note's points wrap across the seam (render.asm .cl_y) */
        int32_t j = i - 1 + d;
        if (r->b_llen > 0.0f) {
            const int32_t span = end - start;
            while (j >= end) j -= span;
            while (j < start) j += span;
        }
        ix[d] = j;
    }
    const float y0 = cl_sample(base, ix[0], start, end);
    const float y1 = cl_sample(base, ix[1], start, end);
    const float y2 = cl_sample(base, ix[2], start, end);
    const float y3 = cl_sample(base, ix[3], start, end);
    const float c1 = 0.5f * (y2 - y0);
    const float c2 = y0 - 2.5f * y1 + 2.0f * y2 - 0.5f * y3;
    const float c3 = 0.5f * (y3 - y0) + 1.5f * (y1 - y2);
    return ((c3 * f + c2) * f + c1) * f + y1;
}
#endif
#ifdef CC_ASM
float cc_clean_read(const cc_recorder *r, float index);   /* sharc/clean.asm */
#define CLEAN_READ cc_clean_read
#else
#define CLEAN_READ rec_clean_read
#endif
#endif

#if defined(CC_CLEAN) && defined(CC_TAPE_AT)
/* The stereo pair's tape (sharc/dt2gen.c): while *CC_TAPE_AT points at this
   sample's slot -- word 0 the entry count, then up to four (index, weight) pairs
   -- every clean read adds its index with weight 1 and every mix scales the
   weights, so another channel can replay the sample as the weighted sum of its
   own clean reads at those indices. sharc/render.asm does the same in its loop. */
static uint32_t tape_n(void)
{
    const uint32_t *sl = *CC_TAPE_AT;
    if (!sl) return 0u;
    return sl[0];
}
static void tape_add(float index)
{
    uint32_t *sl = *CC_TAPE_AT;
    if (!sl) return;
    const uint32_t nn = sl[0];
    if (nn >= 4u) return;
    float *e = (float *)(sl + 1u + 2u * nn);
    e[0] = index;
    e[1] = 1.0f;
    sl[0] = nn + 1u;
}
/* entries [k0, k1) times w, [k1, n) times 1 - w */
static void tape_mix(uint32_t k0, uint32_t k1, float w)
{
    uint32_t *sl = *CC_TAPE_AT;
    if (!sl) return;
    const uint32_t nn = sl[0];
    const float u = 1.0f - w;
    uint32_t j;   /* (selcc: no typedef'd variable in a for-init) */
    for (j = k0; j < nn; j++) {
        float *e = (float *)(sl + 2u + 2u * j);
        if (j < k1) e[0] = e[0] * w; else e[0] = e[0] * u;
    }
}
#define TAPE_N()          tape_n()
#define TAPE_ADD(i)       tape_add(i)
#define TAPE_MIX(a, b, w) tape_mix((a), (b), (w))
#else
#define TAPE_N()          0u
#define TAPE_ADD(i)       ((void)0)
#define TAPE_MIX(a, b, w) ((void)0)
#endif

static float ph_sample(const cc_sparse *s, cc_playhead *ph)
{
    ph->tau    = (float)(ph->w.end_time - ph->index) * ph->w.inv_duration;
#ifdef CC_CLEAN
    const cc_recorder *r = *CC_CTX_AT;
    if (r) {
        const float b = r->blend;
        if (b < 1.0f) {
            const float c = CLEAN_READ(r, ph->index);
            float y = c;
            if (b <= 0.0f) TAPE_ADD(ph->index);
            if (b > 0.0f) {
                const float k = cc_sparse_read(s, &ph->w, ph->tau);
                y = c + b * (k - c);
            }
            ph->result = y;
            return y;
        }
    }
#endif
    ph->result = cc_sparse_read(s, &ph->w, ph->tau);
    return ph->result;
}

static void gr_spawn(cc_granule *g, cc_time pos)
{
    cc_window w;
    cc_sparse_window_at_latest(g->sparse, &w);
    cc_sparse_step_window(g->sparse, &w, pos);
    ph_make(&g->ideal, &w, pos, g->stretch);
    ph_make(&g->actual, &w, pos, g->pitch);
    g->splicing = 0;
    g->splice_phase = 0.0f;
}

void cc_granule_set_pitch(cc_granule *g, float p) { g->pitch = p; g->actual.speed = p; g->temp.speed = p; }
void cc_granule_set_stretch(cc_granule *g, float t) { g->stretch = t; g->ideal.speed = t; }
void cc_granule_set_leash(cc_granule *g, int k) { g->leash = k; }
void cc_granule_set_fade(cc_granule *g, float f)
{
    g->fixed_duration  = (f < 1.0f) ? 1.0f : f;
    g->fixed_increment = 1.0f / g->fixed_duration;
}

void cc_granule_init(cc_granule *g, cc_sparse *s, cc_time start_pos)
{
    g->sparse  = s;
    g->pitch   = 1.0f;
    g->stretch = 1.0f;
    g->leash   = 128;
    cc_granule_set_fade(g, 2400.0f);
    g->adaptive   = 0;
    g->block_size = 0;
    cc_sparse_write_position(s, &g->write_pos);
    g->live_edge  = g->write_pos;
    cc_sparse_window_at_latest(s, &g->master_w);
    gr_spawn(g, start_pos);
}

static void gr_update_master(cc_granule *g)
{
    cc_time m = g->write_pos.uniform - (cc_time)g->fixed_duration;
    if (m > g->live_edge.uniform) m = g->live_edge.uniform;
    const cc_time zero = (cc_time)(-g->sparse->origin);   /* the recording's start */
    if (m < zero) m = zero;
    g->master.uniform = m;
    if (g->master_w.index <= sp_oldest(g->sparse))
        cc_sparse_window_at_latest(g->sparse, &g->master_w);
    cc_sparse_step_window(g->sparse, &g->master_w, m);
    g->master.sparse = g->master_w.index;
}

void cc_granule_begin_block(cc_granule *g, int size)
{
    g->block_size = size;
    cc_sparse_write_position(g->sparse, &g->write_pos);
    cc_sparse_min_read_position(g->sparse, size, &g->live_edge);
    gr_update_master(g);
}

static void gr_reanchor_master(cc_granule *g)
{
    ph_make(&g->temp, &g->master_w, g->master.uniform, g->pitch);
    g->splice_phase = 0.0f;
    g->splicing = 1;
    g->adaptive = 0;
}

static void gr_reanchor_grid(cc_granule *g)
{
    ph_make(&g->temp, &g->ideal.w, g->ideal.index, g->pitch);
    g->splice_phase = 0.0f;
    g->splicing = 1;
    g->adaptive = 0;
}

#ifndef CC_SOURCE_ONLY
void cc_granule_retrigger(cc_granule *g)
{
    ph_make(&g->ideal, &g->master_w, g->master.uniform, g->stretch);
    ph_make(&g->actual, &g->master_w, g->master.uniform, g->pitch);
    g->splicing = 0;
    g->splice_phase = 0.0f;
}

#endif /* !CC_SOURCE_ONLY */

#ifdef CC_ALIGN
#ifndef CC_ALIGN_W
#define CC_ALIGN_W 0.0f
#endif
#ifndef CC_ALIGN_T
#define CC_ALIGN_T 0.0f
#endif
/* Phase-aligned splice start (a port addition): within CC_ALIGN keyframes of the
   grid window `si`, the window whose two keyframe values best match the pair the
   playing head `cur` is reading, scored by squared difference plus a small pull
   toward the grid; the new head starts there at the same fraction of its window,
   so the crossfade joins like with like instead of cancelling. */
/* a float's bits (selcc: a pointer cast; elsewhere memcpy, for strict aliasing) */
#ifdef CC_ASM
#define CC_FBITS(f) (*(const uint32_t *)&(f))
#else
static uint32_t cc_fbits(float f) { uint32_t b; memcpy(&b, &f, 4); return b; }
#define CC_FBITS(f) cc_fbits(f)
#endif
#ifdef CC_LINK
#ifndef CC_LINK_AT
static cc_link cc_link_mem;
#define CC_LINK_AT (&cc_link_mem)
#endif
cc_link *cc_link_ptr(void) { return CC_LINK_AT; }
#endif

static void gr_aligned_start(cc_granule *g, const cc_playhead *cur, cc_idx si, cc_window *w, cc_time *index)
{
    cc_sparse *s = g->sparse;
#ifdef CC_LINK
    cc_link *lk = CC_LINK_AT;
    if (lk->mode == 2) {
        if (lk->k < lk->n) {    /* the other channel's k-th splice: the same offset */
            const float off = lk->off[lk->k];
            lk->k++;
            *w = g->ideal.w;
            *index = g->ideal.index + (cc_time)off;
            cc_sparse_step_window(s, w, *index);
            return;
        }
    }
#endif
    const float a1 = s->buf[cur->w.s1].value, a2 = s->buf[cur->w.s2].value;
    const cc_idx an = (cur->w.index < s->write_pos - 1) ? cur->w.index + 1 : cur->w.index;
    const float a0 = sp_value(s, an);
    const float adur = cur->w.duration;
    const cc_time grid = g->ideal.index;
    const float inv_l = (g->leash < 0) ? 1.0f / (float)(-g->leash) : 1.0f / 960.0f;
    float tau = (float)(cur->w.end_time - cur->index) * cur->w.inv_duration;
    if (tau < 0.0f) tau = 0.0f;
    if (tau > 1.0f) tau = 1.0f;
    cc_idx lo = si - CC_ALIGN, hi = si + CC_ALIGN;
    const cc_idx newest = s->write_pos - 1, oldest = sp_oldest(s) + 1;
    if (lo < oldest) lo = oldest;
    if (hi > newest) hi = newest;
    cc_idx best = si;
    float best_cost = 1e30f;
    cc_idx j;
    for (j = lo; j <= hi; j++) {   /* (selcc cannot declare a typedef'd loop variable here) */
        const float d1 = sp_value(s, j) - a1;
        const float d2 = sp_value(s, j - 1) - a2;
        cc_idx dj = j - si;
        if (dj < 0) dj = -dj;
        const cc_idx jn = (j < newest) ? j + 1 : j;
        const float d0 = sp_value(s, jn) - a0;
        const float dd = (float)(sp_time(s, j) - sp_time(s, j - 1)) - adur;   /* the window's length */
        const float rel = dd / (adur + 1.0f);
        const float tj = (float)(sp_time(s, j) - grid) * inv_l;    /* the distance from the grid, in leashes */
        const float cost = d1 * d1 + d2 * d2 + d0 * d0 + CC_ALIGN_W * rel * rel + CC_ALIGN_T * tj * tj + 1e-4f * (float)dj;
        if (cost < best_cost) { best_cost = cost; best = j; }
    }
    sp_window_at(s, w, best);
    *index = w->end_time - (cc_time)(tau * w->duration);
#ifdef CC_LINK
    if (lk->mode == 1) {
        if (lk->n < CC_LINK_MAX) {
            lk->off[lk->n] = (float)(*index - g->ideal.index);
            lk->n++;
        }
    }
#endif
}
#endif

float cc_granule_read(cc_granule *g)
{
    cc_sparse *s = g->sparse;
    if (g->ideal.index  > g->ideal.w.end_time)  cc_sparse_step_window(s, &g->ideal.w,  g->ideal.index);
    if (g->actual.index > g->actual.w.end_time) cc_sparse_step_window(s, &g->actual.w, g->actual.index);
    if (g->splicing && g->temp.index > g->temp.w.end_time) cc_sparse_step_window(s, &g->temp.w, g->temp.index);

    g->distance.sparse  = g->actual.w.index - g->ideal.w.index;
    g->distance.uniform = g->actual.index   - g->ideal.index;
    g->runway.sparse    = g->live_edge.sparse  - g->actual.w.index;
    g->runway.uniform   = g->live_edge.uniform - g->actual.index;
    g->backlog.sparse   = g->write_pos.sparse  - g->ideal.w.index;
    g->backlog.uniform  = g->write_pos.uniform - g->ideal.index;

    if (!g->splicing || g->adaptive) {
        int front_breach = 0;
        if (g->pitch > 1.0f) {
            cc_time closing = g->splicing
                ? (cc_time)((1.0f - g->splice_phase) * g->adaptive_duration) * (CC_T(1.0) - CC_T(1.0) / (cc_time)g->pitch)
                : (cc_time)g->fixed_duration * (CC_T(1.0) - CC_T(1.0) / (cc_time)g->pitch);
            front_breach = g->runway.uniform <= closing + (cc_time)g->block_size;
        }
        const cc_idx safety = s->size - (s->size >> 3);
        int back_breach = g->backlog.sparse >= safety;
        if (back_breach) {
            gr_reanchor_master(g);
            ph_make(&g->ideal, &g->master_w, g->master.uniform, g->stretch);
        } else if (front_breach) {
            gr_reanchor_grid(g);
        }
    }

    /* leash >= 0: Capicola's, in keyframes. leash < 0 (a port addition, for
       tempo-locked playback): -leash samples between the heads, and the splice
       crossfades over that many samples. Plain ifs: selcc mis-compiles some
       compound conditions (work/dtest/probe6.c). */
    int leash_hit = 0;
    if (g->leash >= 0) {
        cc_idx lead = g->distance.sparse < 0 ? -g->distance.sparse : g->distance.sparse;
        if (lead > g->leash) leash_hit = 1;
    } else {
        cc_time d = g->distance.uniform;
        if (d < CC_T(0.0)) d = -d;
        if (d > (cc_time)(-g->leash)) leash_hit = 1;
    }
    if (!g->splicing && leash_hit) {
        g->temp.index = g->ideal.index;
        g->temp.speed = g->pitch;
        g->temp.w     = g->ideal.w;
#ifdef CC_ALIGN
        gr_aligned_start(g, &g->actual, g->ideal.w.index, &g->temp.w, &g->temp.index);
#endif
        cc_idx si = g->ideal.w.index;
        if (g->leash < 0)
            g->adaptive_duration = (float)(-g->leash);
        else if (g->distance.sparse < 0)
            g->adaptive_duration = (float)(cc_sparse_get(s, si - 1)->time - cc_sparse_get(s, si - g->leash)->time);
        else
            g->adaptive_duration = (float)(cc_sparse_get(s, si + g->leash - 1)->time - cc_sparse_get(s, si - 1)->time);
        float limit = 0.9f * (float)g->runway.uniform;
        if (g->adaptive_duration > limit) g->adaptive_duration = limit;
        if (g->adaptive_duration < 48.0f) g->adaptive_duration = 48.0f;
        g->adaptive_increment = 1.0f / g->adaptive_duration;
        g->splice_phase = 0.0f;
        g->splicing = 1;
        g->adaptive = 1;
    }

    g->ideal.index += g->ideal.speed;

    if (g->splicing && g->splice_phase <= 1.0f) {
        g->temp.speed = g->pitch;
        const uint32_t t0 = TAPE_N();
        float in  = ph_sample(s, &g->temp);
        const uint32_t t1 = TAPE_N();
        float out = ph_sample(s, &g->actual);
        g->temp.index   += g->temp.speed;
        g->actual.index += g->actual.speed;
        const float w = smooth_step(g->splice_phase);
        float mixed = (in * w) + (out * (1.0f - w));
        TAPE_MIX(t0, t1, w);
        g->splice_phase += (g->adaptive ? g->adaptive_increment : g->fixed_increment) * g->pitch;
        return mixed;
    } else if (g->splicing && g->splice_phase > 1.0f) {
        g->actual = g->temp;
        g->splice_phase = 0.0f;
        g->splicing = 0;
    }

    float out = ph_sample(s, &g->actual);
    g->actual.index += g->actual.speed;
    return out;
}

#ifndef CC_SOURCE_ONLY
/* ============================= Detector ================================== */

#define DET_AVG_SEC   0.1f
#define DET_ABS_FLOOR 1e-5f
#define DET_MUTE_AT   100.0f
#define DET_MIN_GAP   0.15f

void cc_detector_init(cc_detector *d, float fs)
{
    d->fs = fs;
    cc_dline8_init(&d->raw);
    cc_dline8_init(&d->env);
    cc_svf_init(&d->svf);
    cc_onepole_init(&d->avg_lp);
    cc_onepole_set_cutoff(&d->avg_lp, 1.0f / ((float)M_PI * DET_AVG_SEC * fs));
    d->cutoff = 0.01f;
    d->resonance = 0.0f;
    cc_svf_set_controls(&d->svf, d->cutoff, d->resonance);
    d->threshold = 1.0f;
    d->kept_count = 0;
    d->total_count = 0;
    d->gap_samps = 0;
    d->min_gap_samps = (int)(DET_MIN_GAP * fs);
    memset(&d->prev_newer, 0, sizeof d->prev_newer);
}

void cc_detector_set_cutoff(cc_detector *d, float fc) { d->cutoff = fc; cc_svf_set_controls(&d->svf, d->cutoff, d->resonance); }
void cc_detector_set_resonance(cc_detector *d, float r) { d->resonance = r; cc_svf_set_controls(&d->svf, d->cutoff, d->resonance); }
void cc_detector_set_threshold(cc_detector *d, float t) { d->threshold = t; }

int cc_detector_analyze(cc_detector *d, float x)
{
    cc_dline8_write(&d->raw, x);
    cc_cubic front;
    cc_dline8_bspline_full(&d->raw, 2.0f, 1, &front);
    cc_svf_tick(&d->svf, front.tkeo);
    const float e = d->svf.lp;
    cc_dline8_write(&d->env, e);
    cc_onepole_tick(&d->avg_lp, e);

    cc_cubic newer;
    cc_dline8_bspline_full(&d->env, 2.0f, 1, &newer);
    const cc_cubic older = d->prev_newer;
    d->prev_newer = newer;

    int fired = 0;
    if (older.d1 < 0.0f && newer.d1 >= 0.0f) {
        const float dd    = older.d1 - newer.d1;
        const float frac  = (dd < -1e-20f) ? (older.d1 / dd) : 0.5f;
        const float lag   = 3.0f - frac;
        cc_cubic peak;
        cc_dline8_bspline_full(&d->env, lag, 1, &peak);
        const float value = peak.value;
        if (value > DET_ABS_FLOOR) {
            const int kept = (d->threshold < DET_MUTE_AT)
                          && (value > d->threshold * d->avg_lp.lp)
                          && (d->gap_samps <= 0);
            d->total_count++;
            if (kept) {
                d->kept_count++;
                d->gap_samps = d->min_gap_samps;
                fired = 1;
            }
        }
    }
    if (d->gap_samps > 0) d->gap_samps--;
    return fired;
}

#endif /* !CC_SOURCE_ONLY */

/* ========================= KeyframeRecorder ============================== */

static void rec_apply_params(cc_recorder *r)
{
    for (int k = 0; k < 2; k++) {
        cc_granule_set_pitch(&r->granule[k], r->cur_pitch);
        cc_granule_set_stretch(&r->granule[k], r->cur_stretch);
        cc_granule_set_leash(&r->granule[k], r->cur_leash);
        cc_granule_set_fade(&r->granule[k], r->cur_fade);
    }
    r->analyzer.threshold = r->cur_threshold;
}

static void rec_reset_reader(cc_recorder *r)
{
    const cc_time zero = (cc_time)(-r->sparse.origin);
    cc_granule_init(&r->granule[0], &r->sparse, zero);
    cc_granule_init(&r->granule[1], &r->sparse, zero);
    r->live_g = 0;
    r->x_gain = 1.0f;
    r->x_step = 0.0f;
    rec_apply_params(r);
}

#ifndef CC_SOURCE_ONLY
static void rec_punch(cc_recorder *r)
{
    r->live_g ^= 1;
    cc_granule_retrigger(&r->granule[r->live_g]);
    r->x_gain = 0.0f;
    r->x_step = 1.0f / ((r->cur_fade < 1.0f) ? 1.0f : r->cur_fade);
}

static float rec_read_pair(cc_recorder *r)
{
    if (r->x_gain >= 1.0f) return cc_granule_read(&r->granule[r->live_g]);
    const float in  = cc_granule_read(&r->granule[r->live_g]);
    const float out = cc_granule_read(&r->granule[r->live_g ^ 1]);
    const float w   = smooth_step(r->x_gain);
    const float y   = in * w + out * (1.0f - w);
    r->x_gain += r->x_step;
    if (r->x_gain > 1.0f) r->x_gain = 1.0f;
    return y;
}

#endif /* !CC_SOURCE_ONLY */

#ifdef CC_CLEAN
/* The fast run (the samples alone, blend 0; leash in samples): the heads move at
   constant speeds, so how many samples can pass before anything gr_fast checks
   for may be due -- a front or back breach, the leash, a splice's end -- is known
   at the block's start. Those first fast_n samples only read and advance (gr_run;
   render.asm's .fr loop); the windows are stepped once after them (gr_catch_up),
   ending where gr_fast's per-sample steps would have. Conservative by two
   samples, so float rounding cannot move an event into the run. */
static int rec_fast_count(const cc_recorder *r, int n)
{
#ifdef CC_NO_FASTRUN
    (void)r; (void)n;
    return 0;
#else
    if (r->blend > 0.0f) return 0;
    if (r->x_gain < 1.0f) return 0;
    const cc_granule *g = &r->granule[r->live_g];
    if (g->leash >= 0) return 0;
    if (g->splicing) {
        if (!g->adaptive) return 0;
    }
    const cc_sparse *s = g->sparse;
    /* a back breach: windows behind their heads only overstate the backlog */
    if (g->write_pos.sparse - g->ideal.w.index >= (cc_idx)(s->size - (s->size >> 3))) return 0;
    float m = (float)n;
    const float adv = (float)g->actual.speed;
    if (g->pitch > 1.0f) {   /* a front breach: the runway shrinks by adv a sample, the closing does not grow */
        const float k = 1.0f - 1.0f / g->pitch;
        float closing = (float)g->fixed_duration * k;
        if (g->splicing) closing = (1.0f - g->splice_phase) * g->adaptive_duration * k;
        const float slack = (float)(g->live_edge.uniform - g->actual.index) - closing - (float)g->block_size - 1.0f;
        if (slack <= 0.0f) return 0;
        if (adv > 0.0f) {
            const float c = slack / adv - 2.0f;
            if (c < m) m = c;
        }
    }
    if (!g->splicing) {   /* the leash: |actual - ideal| grows by at most |dv| a sample */
        float d = (float)(g->actual.index - g->ideal.index);
        if (d < 0.0f) d = -d;
        float dv = adv - (float)g->ideal.speed;
        if (dv < 0.0f) dv = -dv;
        const float room = (float)(-g->leash) - d;
        if (room <= 0.0f) return 0;
        if (dv > 0.0f) {
            const float c = room / dv - 2.0f;
            if (c < m) m = c;
        }
    } else {   /* the splice's end: the phase grows by inc * pitch a sample */
        const float inc = (g->adaptive ? g->adaptive_increment : g->fixed_increment) * g->pitch;
        if (inc > 0.0f) {
            const float c = (1.0f - g->splice_phase) / inc - 2.0f;
            if (c < m) m = c;
        }
    }
    if (m < 1.0f) return 0;
    return (int)m;
#endif
}

#ifndef CC_ASM   /* (render.asm has its own: .fp_loop, .fs_loop, .fr_catch) */
/* one fast-run sample of granule g: gr_fast's reads and steps without its checks
   or window steps (blend 0: ph_sample is the clean read and its tape entry) */
static float gr_run(cc_granule *g, const cc_recorder *r)
{
    g->ideal.index += g->ideal.speed;
    if (g->splicing) {
        g->temp.speed = g->actual.speed;   /* (the pitch, but for plan B's reverse play) */
        const uint32_t t0 = TAPE_N();
        const float in = CLEAN_READ(r, g->temp.index);
        TAPE_ADD(g->temp.index);
        const uint32_t t1 = TAPE_N();
        const float o = CLEAN_READ(r, g->actual.index);
        TAPE_ADD(g->actual.index);
        g->temp.index   += g->temp.speed;
        g->actual.index += g->actual.speed;
        const float w = smooth_step(g->splice_phase);
        const float y = (in * w) + (o * (1.0f - w));
        TAPE_MIX(t0, t1, w);
        g->splice_phase += (g->adaptive ? g->adaptive_increment : g->fixed_increment) * g->pitch;
        return y;
    }
    const float y = CLEAN_READ(r, g->actual.index);
    TAPE_ADD(g->actual.index);
    g->actual.index += g->actual.speed;
    return y;
}

/* after a fast run: the windows where gr_fast's per-sample steps would have left them */
static void gr_catch_up(cc_granule *g)
{
    cc_sparse *s = g->sparse;
    if (g->ideal.index  > g->ideal.w.end_time)  cc_sparse_step_window(s, &g->ideal.w,  g->ideal.index);
    if (g->actual.index > g->actual.w.end_time) cc_sparse_step_window(s, &g->actual.w, g->actual.index);
    if (g->splicing && g->temp.index > g->temp.w.end_time) cc_sparse_step_window(s, &g->temp.w, g->temp.index);
}
#endif
#endif

/* The playback loop: one sample of the grain pair per output. */
#if defined(CC_ASM)
void cc_render_pair(cc_recorder *r, float *out, int n);   /* sharc/render.asm */
#define rec_render cc_render_pair
#elif defined(CC_FASTPATH)
/* The model sharc/render.asm implements (stage 3): cc_granule_read's common case,
   where the heads only step and read. Whenever anything else may be due this
   sample -- a breach (or a front breach within a sample of the margin), a leash
   splice, a splice ending -- it returns 0 and cc_granule_read handles the sample;
   its window steps are then no-ops, so the result is the same either way. */
static int gr_fast(cc_granule *g, float *y)
{
    cc_sparse *s = g->sparse;
    if (g->ideal.index  > g->ideal.w.end_time)  cc_sparse_step_window(s, &g->ideal.w,  g->ideal.index);
    if (g->actual.index > g->actual.w.end_time) cc_sparse_step_window(s, &g->actual.w, g->actual.index);
    if (g->splicing && g->temp.index > g->temp.w.end_time) cc_sparse_step_window(s, &g->temp.w, g->temp.index);
    if (!g->splicing || g->adaptive) {
        if (g->pitch > 1.0f) {
            float k = 1.0f - 1.0f / g->pitch;
            float closing = (g->splicing ? (1.0f - g->splice_phase) * g->adaptive_duration : g->fixed_duration) * k;
            if (g->live_edge.uniform - g->actual.index <= closing + (float)g->block_size + 1.0f) return 0;
        }
        if (g->write_pos.sparse - g->ideal.w.index >= (cc_idx)(s->size - (s->size >> 3))) return 0;
    }
    if (!g->splicing) {
        if (g->leash >= 0) {
            cc_idx lead = g->actual.w.index - g->ideal.w.index;
            if (lead < 0) lead = -lead;
            if (lead > g->leash) return 0;
        } else {
            cc_time d = g->actual.index - g->ideal.index;
            if (d < CC_T(0.0)) d = -d;
            if (d > (cc_time)(-g->leash)) return 0;
        }
    } else if (g->splice_phase > 1.0f) {
        return 0;
    }
    g->ideal.index += g->ideal.speed;
    if (g->splicing) {
        g->temp.speed = g->pitch;
        const uint32_t t0 = TAPE_N();
        float in  = ph_sample(s, &g->temp);
        const uint32_t t1 = TAPE_N();
        float out = ph_sample(s, &g->actual);
        g->temp.index   += g->temp.speed;
        g->actual.index += g->actual.speed;
        const float w = smooth_step(g->splice_phase);
        *y = (in * w) + (out * (1.0f - w));
        TAPE_MIX(t0, t1, w);
        g->splice_phase += (g->adaptive ? g->adaptive_increment : g->fixed_increment) * g->pitch;
        return 1;
    }
    *y = ph_sample(s, &g->actual);
    g->actual.index += g->actual.speed;
    return 1;
}

static float gr_read(cc_granule *g)
{
    float y;
    if (!gr_fast(g, &y)) y = cc_granule_read(g);
    return y;
}

static void rec_render(cc_recorder *r, float *out, int n)
{
    int i0 = 0;
#ifdef CC_CLEAN
    if (r->fast_n > 0) {
        cc_granule *g = &r->granule[r->live_g];
        for (; i0 < r->fast_n; i0++) {
#ifdef CC_TAPE_AT
            if (*CC_TAPE_BUF_AT) { *CC_TAPE_AT = *CC_TAPE_BUF_AT + 9 * i0; (*CC_TAPE_AT)[0] = 0u; }
#endif
            out[i0] = gr_run(g, r);
        }
        gr_catch_up(g);
    }
#endif
    for (int i = i0; i < n; i++) {
#if defined(CC_CLEAN) && defined(CC_TAPE_AT)
        if (*CC_TAPE_BUF_AT) { *CC_TAPE_AT = *CC_TAPE_BUF_AT + 9 * i; (*CC_TAPE_AT)[0] = 0u; }
#endif
        if (r->x_gain >= 1.0f) { out[i] = gr_read(&r->granule[r->live_g]); continue; }
        const uint32_t t0 = TAPE_N();
        const float in  = gr_read(&r->granule[r->live_g]);
        const uint32_t t1 = TAPE_N();
        const float o   = gr_read(&r->granule[r->live_g ^ 1]);
        const float w   = smooth_step(r->x_gain);
        out[i] = in * w + o * (1.0f - w);
        TAPE_MIX(t0, t1, w);
        r->x_gain += r->x_step;
        if (r->x_gain > 1.0f) r->x_gain = 1.0f;
    }
}
#else
static void rec_render(cc_recorder *r, float *out, int n)
{
    for (int i = 0; i < n; i++) out[i] = rec_read_pair(r);
}
#endif

void cc_recorder_init(cc_recorder *r, cc_keyframe *storage, int size)
{
    memset(r, 0, sizeof *r);
    r->b_lo = 1.0f;   /* (b_k 0: the clean read's fast check from sample 1) */
    cc_sparse_init(&r->sparse, storage, size);
    cc_analyzer_init(&r->analyzer, &r->sparse, 48000.0f);
    cc_granule_init(&r->granule[0], &r->sparse, CC_T(0.0));
    cc_granule_init(&r->granule[1], &r->sparse, CC_T(0.0));
    r->live_g = 0;
    r->x_gain = 1.0f;
    r->x_step = 0.0f;
#ifndef CC_SOURCE_ONLY
    cc_detector_init(&r->detector, 48000.0f);
#endif
    r->transient_count = 0;
    r->cur_pitch = 1.0f;
    r->cur_stretch = 1.0f;
    r->cur_leash = 128;
    r->cur_threshold = 0.001f;
    r->cur_fade = 2400.0f;
    rec_apply_params(r);
    r->state = CC_STOPPED;
    r->request = CC_REQ_NONE;
    r->pending_seed = 0;
    r->fired_this_block = 0;
    r->last_block_size = 0;
    r->trig_gate = 0.0f;
    r->trig_fade = 96.0f;
    r->src_state = 2;
    r->blend = 1.0f;
    r->prev_valid = 0;
    r->feed_extra = 0x7fffffff;
}

#if defined(CC_CLEAN) || !defined(CC_SOURCE_ONLY)   /* the DT2 build without CAPI never sets it */
void cc_recorder_set_blend(cc_recorder *r, float b)
{
    if (b < 0.0f) b = 0.0f;
    if (b > 1.0f) b = 1.0f;
    r->blend = b;
}
#endif

#ifndef CC_SOURCE_ONLY
void cc_recorder_submit(cc_recorder *r, int request) { r->request = request; }
#endif
void cc_recorder_set_pitch(cc_recorder *r, float p) { r->cur_pitch = p; for (int k = 0; k < 2; k++) cc_granule_set_pitch(&r->granule[k], p); }
void cc_recorder_set_stretch(cc_recorder *r, float t) { r->cur_stretch = t; for (int k = 0; k < 2; k++) cc_granule_set_stretch(&r->granule[k], t); }
void cc_recorder_set_leash(cc_recorder *r, int k_) { r->cur_leash = k_; for (int k = 0; k < 2; k++) cc_granule_set_leash(&r->granule[k], k_); }
#ifndef CC_SOURCE_ONLY
void cc_recorder_set_threshold(cc_recorder *r, float v) { r->cur_threshold = v; r->analyzer.threshold = v; }
#endif
void cc_recorder_set_fade(cc_recorder *r, float f) { r->cur_fade = f; for (int k = 0; k < 2; k++) cc_granule_set_fade(&r->granule[k], f); }
#ifndef CC_SOURCE_ONLY
void cc_recorder_set_transient_threshold(cc_recorder *r, float t) { cc_detector_set_threshold(&r->detector, t); }
void cc_recorder_set_tkeo_cutoff(cc_recorder *r, float fc) { cc_detector_set_cutoff(&r->detector, fc); }
void cc_recorder_set_tkeo_resonance(cc_recorder *r, float q) { cc_detector_set_resonance(&r->detector, q); }

static void rec_handle_request(cc_recorder *r)
{
    switch (r->request) {
    case CC_REQ_RECORD:
        sp_reset(&r->sparse);
        cc_analyzer_init(&r->analyzer, &r->sparse, 48000.0f);
        rec_reset_reader(r);
        r->state = CC_RECORDING;
        break;
    case CC_REQ_LIVE_EFFECT:
        sp_reset(&r->sparse);
        cc_analyzer_init(&r->analyzer, &r->sparse, 48000.0f);
        rec_reset_reader(r);
        r->pending_seed = 1;
        r->state = CC_LIVE_EFFECT;
        break;
    case CC_REQ_SLICE:
        if (r->analyzer.sparse_count != 0) r->pending_seed = 1;
        break;
    case CC_REQ_STOP_REC:
        r->analyzer.arm_final = 1;
        rec_reset_reader(r);
        r->state = CC_STOPPED;
        break;
    case CC_REQ_PLAY:
    case CC_REQ_RESTART_PLAYBACK:
        rec_reset_reader(r);
        r->pending_seed = 1;
        r->state = CC_PLAYBACK;
        break;
    case CC_REQ_STOP_PLAYING:
        r->state = CC_STOPPED;
        break;
    case CC_REQ_CLEAR:
        sp_reset(&r->sparse);
        cc_analyzer_init(&r->analyzer, &r->sparse, 48000.0f);
        rec_reset_reader(r);
        r->state = CC_STOPPED;
        break;
    default:
        break;
    }
    r->request = CC_REQ_NONE;
}

#endif /* !CC_SOURCE_ONLY */

#if defined(CC_F32) || defined(CC_REBASE)
/* Stage 2: move the time origin forward by CC_REBASE_STEP samples once the
   furthest head is CC_REBASE_AT past it. Every stored time and every absolute
   position shifts by the same power of two; differences (distance, runway,
   backlog, durations) do not change. The cost is one subtraction per ring slot. */
#ifndef CC_REBASE_AT
#define CC_REBASE_AT   49152.0f
#endif
#define CC_REBASE_STEP 32768

static void gr_shift(cc_granule *g, float d)
{
    g->ideal.index  -= d;  g->ideal.w.end_time  -= d;
    g->actual.index -= d;  g->actual.w.end_time -= d;
    g->temp.index   -= d;  g->temp.w.end_time   -= d;
    g->master_w.end_time -= d;
    g->write_pos.uniform -= d;
    g->live_edge.uniform -= d;
    g->master.uniform    -= d;
}

#ifdef CC_ASM
void cc_shift_times(cc_keyframe *buf, int n, float d);   /* n a multiple of 4 */
#endif
static void rec_rebase(cc_recorder *r)
{
    float hi = (float)(r->analyzer.raw_count - r->sparse.origin);
    for (int k = 0; k < 2; k++) {
        if (r->granule[k].ideal.index  > hi) hi = r->granule[k].ideal.index;
        if (r->granule[k].actual.index > hi) hi = r->granule[k].actual.index;
    }
    int go = 0;
    if (hi >= CC_REBASE_AT + (float)r->rebase_lag) go = 1;
#ifdef CC_LINK
    /* stereo link: the replaying channel rebases exactly when the recording one
       does. Rebased in different blocks, the two hold their times at different
       float magnitudes, splice decisions round apart, and the replayed offsets
       pair up with the wrong splices (test/stereo_check.c, LAG=1024: heads up to
       1300 samples apart) */
    cc_link *lk = CC_LINK_AT;
    if (lk->mode == 2) go = lk->rebased;
    if (lk->mode == 1) lk->rebased = go;
#endif
    if (!go) return;
    const float d = (float)CC_REBASE_STEP;
    cc_keyframe *buf = r->sparse.buf;
#ifdef CC_ASM
    cc_shift_times(buf, r->sparse.size, d);   /* sharc/feed.asm: the same, without the loop's stalls */
#else
    for (int i = 0; i < r->sparse.size; i++) buf[i].time -= d;
#endif
    r->sparse.origin += CC_REBASE_STEP;
    gr_shift(&r->granule[0], d);
    gr_shift(&r->granule[1], d);
}
#endif

/* ---- CC_SOURCE ------------------------------------------------------------ */

#ifdef CC_ASM
void cc_feed(cc_recorder *r);   /* sharc/feed.asm: src_feed's loop */
#endif

#ifndef CC_ASM   /* sharc/feed.asm reads the samples */
static float src_sample(const cc_recorder *r)
{
    /* the aligned word and a shift, not a 16-bit load (s3_play.asm's method) */
    const uintptr_t a = r->src + 2u * (uint32_t)r->src_pos;
    const uint32_t w = *(const uint32_t *)(a & ~(uintptr_t)3);
    const int32_t v = (a & 2u) ? ((int32_t)w >> 16) : ((int32_t)(w << 16) >> 16);
    return (float)v * (1.0f / 32768.0f);
}
#endif

static cc_time src_head_max(const cc_recorder *r)
{
    cc_time hi = r->granule[0].ideal.index;
    for (int k = 0; k < 2; k++) {
        const cc_granule *g = &r->granule[k];
        if (g->ideal.index  > hi) hi = g->ideal.index;
        if (g->actual.index > hi) hi = g->actual.index;
        if (g->splicing && g->temp.index > hi) hi = g->temp.index;
    }
    if (r->src_spawn) {
        const cc_time t0 = (cc_time)(r->src_t0 - r->sparse.origin);
        if (t0 > hi) hi = t0;
    }
    return hi;
}

/* Analyse until the newest keyframe's time reaches `target`, at most `cap`
   samples; returns the samples analysed. */
static int src_feed_run(cc_recorder *r, cc_time target, int cap, float gap)
{
    cc_analyzer *a = &r->analyzer;
    const cc_idx before = a->raw_count;
#ifdef CC_ASM
    (void)a;
    r->feed_target = target;
    r->feed_gap = gap;
    r->feed_cap = cap;
    cc_feed(r);
#else
    for (int k = 0; k < cap; k++) {
        if (a->sparse_count > 0 && cc_sparse_latest(&r->sparse)->time >= target) break;
        float x = 0.0f;
        if (r->src_state == 0) {
            x = src_sample(r);
            if (++r->src_pos >= r->src_end) {
                if (r->src_loop >= 0 && r->src_loop < r->src_end) {
                    r->src_pos = r->src_loop;
                } else {
                    r->src_state = 1;
                    r->src_t_end = a->raw_count + 1;
                }
            }
        }
        cc_analyzer_analyze(a, x);
        cc_analyzer_guard_keyframe(a, (cc_time)gap);
    }
#endif
#ifdef CC_FED
    CC_FED(a->raw_count - before);   /* sharc/dt2gen.c's GEN_DIAG counts the analysed samples */
#endif
    return (int)(a->raw_count - before);
}

/* Analyse until the newest keyframe is far enough past the furthest head for
   this block's reads (and, for pitch > 1, for the front-breach margin), at most
   rate*n + 2n samples a block, so the lookahead builds up over a few blocks
   rather than in one. Silence after the end; the guard keyframe per sample. */
static void src_feed(cc_recorder *r, int n)
{
    float rate = r->cur_stretch;
    if (r->cur_pitch > rate) rate = r->cur_pitch;
    if (rate < 1.0f) rate = 1.0f;
    const float close = (r->cur_pitch > 1.0f) ? r->cur_fade * (1.0f - 1.0f / r->cur_pitch) : 0.0f;
    /* and one splice's length more: a splice crossfades over at most 0.9 of the
       runway to the newest keyframe, which live input cannot extend but a sample
       in memory can */
    const float splice = (r->cur_leash < 0) ? (float)(-r->cur_leash) : r->cur_fade;
    const cc_time hmax = src_head_max(r);
    const cc_time need = hmax + (cc_time)(rate * (float)n + close + 2.0f * (float)n + 4.0f);
    const cc_time target = hmax + (cc_time)(rate * (float)n + close + 2.0f * (float)n + 4.0f + 1.15f * splice);
    const int cap = (int)(rate * (float)n) + 2 * n + 8;
    float gap = 0.5f * r->cur_fade;
    const float gcap = r->cur_fade - 2.0f * (float)n;
    if (gap > gcap) gap = gcap;
    if (gap < 1.0f) gap = 1.0f;
    r->feed_extra_used = 0;
    if (r->feed_extra >= cap) {   /* unlimited: one run, as before the budget */
        (void)need;
        src_feed_run(r, target, cap, gap);
        return;
    }
    /* what the heads need first; then, free, up to the heads' own advance this
       block (rate * n), which keeps a built-up lookahead from shrinking; then
       the lookahead's growth, within the budget */
    int used = src_feed_run(r, need, cap, gap);
    const int keep = (int)(rate * (float)n) - used;
    if (keep > 0) used += src_feed_run(r, target, keep, gap);
    int more = cap - used;
    if (more > r->feed_extra) more = r->feed_extra;
    if (more > 0) r->feed_extra_used = src_feed_run(r, target, more, gap);
}

void cc_recorder_source(cc_recorder *r, uintptr_t data, int32_t start, int32_t end, int32_t loop_start)
{
    r->b_k = 0;   /* (positions from the note's start, as Capicola's) */
    r->b_kf = 0.0f;
    r->b_lo = 1.0f;
    r->b_llen = 0.0f;
    if (r->state != CC_SOURCE) {
        sp_reset(&r->sparse);
        cc_analyzer_init(&r->analyzer, &r->sparse, 48000.0f);
        rec_reset_reader(r);
        r->state = CC_SOURCE;
        r->src_spawn = 0;
    } else {
        r->src_spawn = 1;            /* the new grain starts at src_t0 once it is analysed */
        r->prev_src = r->src;        /* the old note's mapping, for its fade-out */
        r->prev_start = r->src_start;
        r->prev_end = r->src_end;
        r->prev_t0 = r->src_t0;
        r->prev_valid = 1;
    }
    r->request = CC_REQ_NONE;
    r->src = data;
    r->src_pos = start;
    r->src_start = start;
    r->src_end = (end > start) ? end : start + 1;
    r->src_loop = loop_start;
    r->src_state = 0;
    r->src_t0 = r->analyzer.raw_count;
}

#ifndef CC_MARK
#define CC_MARK(k) ((void)0)   /* sharc/dt2gen.c's GEN_DIAG times the sections between marks */
#endif
static void src_process(cc_recorder *r, float *out, int n)
{
    if (r->src_state == 2) {
        for (int i = 0; i < n; i++) out[i] = 0.0f;
        return;
    }
    CC_MARK(1);
    src_feed(r, n);
    CC_MARK(2);
    if (r->src_spawn) {
        /* a retrigger: the other grain starts the new note, the old one fades */
        r->live_g ^= 1;
        cc_granule *g = &r->granule[r->live_g];
        gr_spawn(g, (cc_time)(r->src_t0 - r->sparse.origin));
        if (r->trig_fade > 0.0f) {
            r->x_gain = 0.0f;
            r->x_step = 1.0f / ((r->trig_fade < 1.0f) ? 1.0f : r->trig_fade);
        } else {   /* 0: switch at once, the old note is not rendered (the caller declicks) */
            r->x_gain = 1.0f;
            r->x_step = 0.0f;
        }
        r->src_spawn = 0;
    }
    /* the other grain only while it is heard (a retrigger's crossfade): its heads
       are made afresh at a spawn, and its master window lands where it would
       have by steps (cc_sparse_step_window's binary search) */
    cc_granule_begin_block(&r->granule[r->live_g], n);
    if (r->x_gain < 1.0f) cc_granule_begin_block(&r->granule[r->live_g ^ 1], n);
    CC_MARK(6);
#ifdef CC_CLEAN
    r->fast_n = rec_fast_count(r, n);
    CC_MARK(3);
    *CC_CTX_AT = r;
#endif
    rec_render(r, out, n);
#if defined(CC_CLEAN) && defined(CC_TAPE_AT)
    *CC_TAPE_AT = (uint32_t *)0;
#endif
    CC_MARK(4);
#ifdef CC_CLEAN
    *CC_CTX_AT = (cc_recorder *)0;
#endif
    if (r->src_state == 1 && r->x_gain >= 1.0f) {
        const cc_granule *g = &r->granule[r->live_g];
        cc_time lo = g->ideal.index;
        if (g->actual.index < lo) lo = g->actual.index;
        if (lo > (cc_time)(r->src_t_end - r->sparse.origin) + (cc_time)r->cur_fade) r->src_state = 2;
    }
}

void cc_recorder_process(cc_recorder *r, const float *in, float *out, int n)
{
    r->last_block_size  = n;
    r->fired_this_block = 0;
#ifndef CC_SOURCE_ONLY
    if (r->request != CC_REQ_NONE) rec_handle_request(r);
#endif
#if defined(CC_F32) || defined(CC_REBASE)
    rec_rebase(r);
#endif

#ifdef CC_SOURCE_ONLY
    (void)in;
    if (r->state == CC_SOURCE) src_process(r, out, n);
    else for (int i = 0; i < n; i++) out[i] = 0.0f;
#else
    switch (r->state) {
    case CC_STOPPED:
        for (int i = 0; i < n; i++) out[i] = in[i];
        break;
    case CC_RECORDING:
        for (int i = 0; i < n; i++) {
            if (cc_analyzer_is_full(&r->analyzer)) { cc_recorder_submit(r, CC_REQ_STOP_REC); out[i] = in[i]; continue; }
            cc_analyzer_analyze(&r->analyzer, in[i]);
            out[i] = in[i];
        }
        break;
    case CC_PLAYBACK:
        cc_granule_begin_block(&r->granule[0], n);
        cc_granule_begin_block(&r->granule[1], n);
        if (r->pending_seed) { rec_punch(r); r->pending_seed = 0; }
        rec_render(r, out, n);
        break;
    case CC_LIVE_EFFECT: {
        int fire = 0;
        for (int i = 0; i < n; i++) {
            cc_analyzer_analyze(&r->analyzer, in[i]);
            if (cc_detector_analyze(&r->detector, in[i])) fire = 1;
        }
        if (r->trig_gate > 0.0f) r->trig_gate -= (float)n;
        if (fire && r->trig_gate <= 0.0f) {
            r->transient_count++;
            r->pending_seed = 1;
            r->fired_this_block = 1;
            r->trig_gate = r->cur_fade;
        }
        cc_granule_begin_block(&r->granule[0], n);
        cc_granule_begin_block(&r->granule[1], n);
        if (r->pending_seed) { rec_punch(r); r->pending_seed = 0; }
        rec_render(r, out, n);
        float gap = 0.5f * r->cur_fade;
        const float cap = r->cur_fade - 2.0f * (float)n;
        if (gap > cap) gap = cap;
        if (gap < 1.0f) gap = 1.0f;
        cc_analyzer_guard_keyframe(&r->analyzer, (cc_time)gap);
        break;
    }
    case CC_SOURCE:
        src_process(r, out, n);
        break;
    }
#endif
}
