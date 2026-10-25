/* SPDX-License-Identifier: AGPL-3.0-only
 * Matthew Nielsen / Heavylight Industries Capicola Granule playback port.
 * Source: 120b0b843c18bda373d96eb79d49805545f61556 lib/Granule.h.
 * Immutable periodic-medium adapter: see source-contract/ and NOTICE.
 * No fade ceiling, per-head edge gate, source-boundary rescue, or shared voice.
 */
#define cap_stretch_init cap_legacy_init
#define cap_stretch_start cap_legacy_start
#define cap_stretch_update cap_legacy_update
#define cap_stretch_stop cap_legacy_stop
#define cap_stretch_tick cap_legacy_tick
#define cap_stretch_process cap_legacy_process
#include "stretch.c"
#undef cap_stretch_init
#undef cap_stretch_start
#undef cap_stretch_update
#undef cap_stretch_stop
#undef cap_stretch_tick
#undef cap_stretch_process

void cap_stretch_init(CapStretch *s) { cap_legacy_init(s); }
void cap_stretch_stop(CapStretch *s) { cap_legacy_stop(s); }
int cap_stretch_update(CapStretch *s,float pitch,float advance) {
    return cap_legacy_update(s,pitch,advance);
}
/* Exact lower_bound, including the first key. strict selects upper_bound. */
static int source_bound(const CapBank *b,int w,int strict) {
    int lo=0,hi=b->count;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1);
        int before=b->whole[mid]<w || (strict && b->whole[mid]==w
            && b->fraction[mid]==0);
        if(before) lo=mid+1;else hi=mid;
    }
    return lo;
}
int cap_stretch_start(CapStretch *s,const CapBank *b,int start,int end,
                      int reverse,int loop,float pitch,float advance,int leash) {
    int result=cap_legacy_start(s,b,start,end,reverse,loop,pitch,advance,leash);
    if(result) return result;
    /* Keep extrema in the selected PCM domain; traversal zero is synthetic.
     * lower_bound(end-1) excludes that exact reverse traversal-zero key. */
    int first=source_bound(b,start,!reverse);
    int last=source_bound(b,end-1,!reverse);
    s->first_key=first;s->key_count=last-first+1;
    s->ideal_key=s->actual_key=s->incoming_key=1;
    return CAP_OK;
}
static void source_key(const CapStretch *s,int rank,int *w,unsigned *f,int *index) {
    int local,cycle=stretch_cycle(rank,s->key_count,&local);
    if(!local) {*w=cycle*(s->end-s->start);*f=0;*index=-1;return;}
    *index=s->reverse ? s->first_key+s->key_count-1-local
                      : s->first_key+local-1;
    const CapBank *b=s->core.bank;
    if(s->reverse) {
        *w=s->end-1-b->whole[*index];*f=0;
        if(b->fraction[*index]) {(*w)--;*f=CAP_Q-b->fraction[*index];}
    } else {*w=b->whole[*index]-s->start;*f=b->fraction[*index];}
    *w+=cycle*(s->end-s->start);
}
static int source_rank(const CapStretch *s,int w,unsigned f) {
    int local,cycle=stretch_cycle(w,s->end-s->start,&local);
    int lo=1,hi=s->key_count;
    /* A periodic key at traversal zero closes the preceding window. */
    if(local==0 && !f) return cycle*s->key_count;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1),kw,index;unsigned kf;
        source_key(s,mid,&kw,&kf,&index);
        if(less(kw,kf,local,f)) lo=mid+1;else hi=mid;
    }
    return cycle*s->key_count+lo;
}
static float source_origin(const CapStretch *s) {
    const CapState *c=&s->core;
    int w=s->reverse ? s->end-1 : s->start;
    int i=window(c,w,0);
    float duration=span(c,i,i-1);
    float inv=duration>1e-5f ? 1.0f/duration : 0.0f;
    float t=delta(c->bank->whole[i],c->bank->fraction[i],w,0)*inv;
    if(t<0.0f)t=0.0f;else if(t>1.0f)t=1.0f;
    float t2=t*t;
    return ((2.0f*t-3.0f)*t2+1.0f)*c->bank->value[i]
        +((-2.0f*t+3.0f)*t2)*c->bank->value[i-1];
}
static float source_sample(const CapStretch *s,int w,unsigned f,int rank) {
    int aw,bw,ai,bi;unsigned af,bf;
    source_key(s,rank,&aw,&af,&ai);source_key(s,rank-1,&bw,&bf,&bi);
    float duration=delta(aw,af,bw,bf);
    float inv=duration>1e-5f ? 1.0f/duration : 0.0f;
    float t=delta(aw,af,w,f)*inv;
    if(t<0.0f)t=0.0f;else if(t>1.0f)t=1.0f;
    float a=ai<0 ? source_origin(s) : s->core.bank->value[ai];
    float b=bi<0 ? source_origin(s) : s->core.bank->value[bi];
    float t2=t*t;
    return ((2.0f*t-3.0f)*t2+1.0f)*a+((-2.0f*t+3.0f)*t2)*b;
}
static float source_span(const CapStretch *s,int a,int b) {
    int aw,bw,index;unsigned af,bf;
    source_key(s,a,&aw,&af,&index);source_key(s,b,&bw,&bf,&index);
    return delta(aw,af,bw,bf);
}
float cap_stretch_tick(CapStretch *s) {
    CapState *c=&s->core;
    if(!c->active) return 0.0f;
    if(!stretch_valid(s)) {c->active=0;return 0.0f;}
    int grid=source_rank(s,c->ideal_w,c->ideal_f);
    int actual=source_rank(s,c->actual_w,c->actual_f);
    int lead=actual-grid;if(lead<0)lead=-lead;
    if(!c->splicing && lead>c->leash) {
        c->incoming_w=c->ideal_w;c->incoming_f=c->ideal_f;
        float duration=actual<grid ? source_span(s,grid-1,grid-c->leash)
                                 : source_span(s,grid+c->leash-1,grid-1);
        if(duration<48.0f)duration=48.0f;
        c->increment=1.0f/duration;c->phase=0.0f;c->splicing=1;
    }
    advance_time(&c->ideal_w,&c->ideal_f,c->advance_q);
    float y;
    if(c->splicing && c->phase<=1.0f) {
        float incoming=source_sample(s,c->incoming_w,c->incoming_f,
            source_rank(s,c->incoming_w,c->incoming_f));
        float outgoing=source_sample(s,c->actual_w,c->actual_f,actual);
        float weight=smooth(c->phase);
        y=incoming*weight+outgoing*(1.0f-weight);
        advance_time(&c->incoming_w,&c->incoming_f,c->pitch_q);
        advance_time(&c->actual_w,&c->actual_f,c->pitch_q);
        float step=c->increment*c->pitch;
        if(step<0.0000002384185791015625f)step=0.0000002384185791015625f;
        c->phase+=step;
    } else {
        if(c->splicing) {
            c->actual_w=c->incoming_w;c->actual_f=c->incoming_f;
            c->phase=0.0f;c->splicing=0;
            actual=source_rank(s,c->actual_w,c->actual_f);
        }
        y=source_sample(s,c->actual_w,c->actual_f,actual);
        advance_time(&c->actual_w,&c->actual_f,c->pitch_q);
    }
    if(!c->splicing) {c->incoming_w=c->actual_w;c->incoming_f=c->actual_f;}
    if(s->loop && c->ideal_w>=s->end-s->start) {
        int local,cycles=stretch_cycle(c->ideal_w,s->end-s->start,&local);
        int shift=cycles*(s->end-s->start);
        c->ideal_w-=shift;c->actual_w-=shift;c->incoming_w-=shift;
    }
    /* Finite note lifetime belongs to the metric grid, not either pitch head. */
    if(s->loop) c->position=48;
    else if(++c->position>=c->duration)c->active=0;
    return y;
}
void cap_stretch_process(CapStretch *s,float *out,int frames) {
    for(int i=0;i<frames;i++)out[i]=cap_stretch_tick(s);
}
