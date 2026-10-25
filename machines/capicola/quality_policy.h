/* SPDX-License-Identifier: AGPL-3.0-only
 * Optional finite-file quality policy, derived from Capicola's adaptive spans.
 * Included by the guarded source overlay after the preserved transport helpers.
 * See quality-contract/ and NOTICE. No extra reader state or allocation.
 */
static float quality_runway(const CapStretch *s,int w,unsigned f) {
    return (float)(s->end-s->start-1-w)-(float)f*(1.0f/16777216.0f);
}
static int quality_front_slow(const CapStretch *s) {
    const CapState *c=&s->core;
    return !s->loop && less(c->ideal_w,c->ideal_f,c->actual_w,c->actual_f)
        && quality_runway(s,c->ideal_w,c->ideal_f)>=48.0f
        && quality_runway(s,c->actual_w,c->actual_f)<=960.0f+32.0f*c->pitch;
}
/* Fast integer rejection avoids a function call on ordinary interior reads.
 * Maximum supported pitch32 gives runway960+32*32=1984. Two extra samples
 * conservatively cover fractional and binary32 rounding at the boundary.
 * The argument is always a side-effect-free reader pointer. */
#define quality_front(s) (!(s)->loop && (s)->core.actual_w>=(s)->end-(s)->start-1986 \
    && quality_front_slow(s))

static float quality_duration(const CapStretch *s,float duration) {
    const CapState *c=&s->core;
    if(s->loop) {
        float limit=(float)(s->end-s->start);
        if(duration>limit) duration=limit;
    } else {
        float runway=quality_runway(s,c->actual_w,c->actual_f);
        float incoming=quality_runway(s,c->ideal_w,c->ideal_f);
        if(quality_front(s)) duration=960.0f;
        if(incoming<runway) runway=incoming;
        if(duration>0.9f*runway) duration=0.9f*runway;
    }
    return duration<48.0f ? 48.0f : duration;
}
/* Pure arguments: avoid a call/spill sequence for this per-sample clamp.
 * The minimum exceeds binary32 ULP through phase1. */
#define QUALITY_MIN_STEP 0.0000002384185791015625f
#define quality_phase_step(increment,pitch) \
    (((increment)*(pitch)<QUALITY_MIN_STEP) ? QUALITY_MIN_STEP : (increment)*(pitch))
