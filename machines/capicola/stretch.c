/* SPDX-License-Identifier: AGPL-3.0-only
 * Capicola sparse reader extended for native STRETCH transport. The original
 * analyzer/reader remains byte-for-byte unchanged in capacity.c. */
#include "stretch.h"
#include "capacity.c"

void cap_stretch_init(CapStretch *s) {
    cap_init(&s->core);
    s->start=s->end=s->reverse=s->loop=s->first_key=s->key_count=0;
    s->ideal_key=s->actual_key=s->incoming_key=1;
}
void cap_stretch_stop(CapStretch *s) { cap_stop(&s->core); }
static int stretch_valid(const CapStretch *s) {
    const CapState *c=&s->core;
    return c->bank && c->generation==c->bank->generation && !c->bank->error
        && c->bank->count>=2 && c->bank->frames>=1;
}
static int stretch_rates(float pitch,float advance) {
    return pitch>=0.03125f && pitch<=32.0f
        && advance>=0.0000152587890625f && advance<=64.0f;
}
/* Every base-256 product intermediate fits uint32 at this output bound.
 * The final product is <2^29. Include the current fractional ideal position. */
static int stretch_reaches(const CapState *c,int length,unsigned n,unsigned rate) {
    unsigned f=((rate&CAP_MASK)*n)&CAP_MASK;
    int w=c->ideal_w+product_whole(rate,n)+(int)((c->ideal_f+f)>>24);
    return w>=length;
}
static int stretch_remaining(const CapStretch *s,unsigned rate,int limit) {
    const CapState *c=&s->core;
    int lo=1,hi=limit;
    if(c->ideal_w>=s->end-s->start) return 0;
    if(limit<1 || !stretch_reaches(c,s->end-s->start,(unsigned)hi,rate)) return -1;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1);
        if(stretch_reaches(c,s->end-s->start,(unsigned)mid,rate)) hi=mid;
        else lo=mid+1;
    }
    return lo;
}
int cap_stretch_update(CapStretch *s,float pitch,float advance) {
    CapState *c=&s->core;
    unsigned rate;
    int remaining;
    if(!stretch_valid(s) || !stretch_rates(pitch,advance)) {
        c->active=0;return CAP_CONTROL_ERROR;
    }
    rate=(unsigned)(advance*16777216.0f);
    if(!s->loop && rate!=c->advance_q) {
        remaining=stretch_remaining(s,rate,CAP_STRETCH_MAX_OUTPUT-c->position);
        if(remaining<0) {c->active=0;return CAP_CONTROL_ERROR;}
        c->duration=c->position+remaining;
        if(!remaining) c->active=0;
    }
    c->pitch=pitch;c->advance=advance;
    c->pitch_q=(unsigned)(pitch*16777216.0f);c->advance_q=rate;
    return CAP_OK;
}
int cap_stretch_start(CapStretch *s,const CapBank *bank,int start,int end,
                      int reverse,int loop,float pitch,float advance,int leash) {
    CapState *c;
    int first,last;
    cap_stretch_init(s);c=&s->core;
    if(!bank || bank->error || !bank->value || !bank->whole || !bank->fraction
        || bank->count<2 || bank->count>bank->capacity
        || bank->frames<1 || bank->frames>CAP_MAX_INPUT) return CAP_INPUT_ERROR;
    if(start<0 || end<=start || end>bank->frames
        || (reverse!=0 && reverse!=1) || (loop!=0 && loop!=1)
        || !stretch_rates(pitch,advance) || leash<16 || leash>128)
        return CAP_CONTROL_ERROR;
    c->bank=bank;c->generation=bank->generation;c->leash=leash;
    s->start=start;s->end=end;s->reverse=reverse;s->loop=loop;
    /* Binary search the keys contained in the half-open selected region. */
    first=window(c,start,0);
    if(start==0) first=0;
    last=window(c,end,0);
    s->first_key=first;s->key_count=last-first;
    if(s->key_count<1) s->key_count=0; /* One synthetic rank per silent cycle. */
    c->pitch=pitch;c->advance=advance;
    c->pitch_q=(unsigned)(pitch*16777216.0f);
    c->advance_q=(unsigned)(advance*16777216.0f);
    c->duration=loop ? 0 : stretch_remaining(s,c->advance_q,CAP_STRETCH_MAX_OUTPUT);
    if(!loop && c->duration<1) {c->bank=0;return CAP_CONTROL_ERROR;}
    c->active=1;return CAP_OK;
}
/* Floor division, including a cursor lagging behind the normalized ideal. */
static int stretch_cycle(int w,int length,int *local) {
    if(w>=0 && w<length) {*local=w;return 0;}
    if(w<0 && w>=-length) {*local=w+length;return -1;}
    /* The pinned target compiler does not provide signed divide helpers.
     * Bounded binary division also avoids reciprocal rounding at loop edges. */
    unsigned n=(unsigned)(w<0 ? -w : w),divisor=(unsigned)length;
    unsigned bit=1,quotient=0;
    while(divisor<=(n>>1)) {divisor<<=1;bit<<=1;}
    while(bit) {
        if(n>=divisor) {n-=divisor;quotient|=bit;}
        divisor>>=1;bit>>=1;
    }
    *local=(int)n;
    if(w<0) {
        if(n) {*local=length-(int)n;return -(int)quotient-1;}
        return -(int)quotient;
    }
    return (int)quotient;
}
static void stretch_map(const CapStretch *s,int w,unsigned f,int *aw,unsigned *af) {
    if(s->reverse) {
        *aw=s->end-1-w;
        *af=0;
        if(f) {(*aw)--;*af=CAP_Q-f;}
    } else {*aw=s->start+w;*af=f;}
}
/* Reuse a bracket only after exact Q24 comparisons prove it still contains
 * the requested time. A bounded neighboring step handles ordinary playback;
 * seeks/high rates/wraps fall back to the unchanged binary lower-bound search.
 * These caches never change interpolation or the sparse-rank splice policy. */
static int stretch_window(const CapStretch *s,int w,unsigned f,int *cache) {
    const CapState *c=&s->core;
    int i=*cache,last=c->bank->count-1;
    for(int step=0;step<3;step++) {
        if(i<1 || i>last) break;
        if(i<last && less(c->bank->whole[i],c->bank->fraction[i],w,f)) i++;
        else if(i>1 && !less(c->bank->whole[i-1],c->bank->fraction[i-1],w,f)) i--;
        else {*cache=i;return i;}
    }
    *cache=window(c,w,f);return *cache;
}
static int stretch_rank(const CapStretch *s,int w,unsigned f,int *cache) {
    const CapState *c=&s->core;
    int cycle=0,aw,rank,local=w,n=s->key_count;
    unsigned af;
    if(s->loop) cycle=stretch_cycle(w,s->end-s->start,&local);
    stretch_map(s,local,f,&aw,&af);
    rank=stretch_window(s,aw,af,cache);
    if(!s->loop) return s->reverse ? c->bank->count-1-rank : rank;
    if(!n) return cycle;
    if(s->reverse) {
        int exact=c->bank->whole[rank]==aw && c->bank->fraction[rank]==af;
        rank=s->first_key+n-rank-exact;
    } else rank-=s->first_key;
    if(rank<0) rank=0;else if(rank>n) rank=n;
    return cycle*n+rank;
}
static void stretch_key(const CapStretch *s,int rank,int *w,unsigned *f) {
    const CapState *c=&s->core;
    int n=s->key_count,local,cycle=0,index;
    if(!s->loop) {
        index=s->reverse ? c->bank->count-1-rank : rank;
        index=clamp_index(c,index);
    } else {
        if(!n) {*w=rank*(s->end-s->start);*f=0;return;}
        cycle=stretch_cycle(rank,n,&local);
        index=s->first_key+(s->reverse ? n-1-local : local);
    }
    if(s->reverse) {
        *w=s->end-1-c->bank->whole[index];*f=0;
        if(c->bank->fraction[index]) {(*w)--;*f=CAP_Q-c->bank->fraction[index];}
    } else {*w=c->bank->whole[index]-s->start;*f=c->bank->fraction[index];}
    *w+=cycle*(s->end-s->start);
}
static float stretch_span(const CapStretch *s,int a,int b) {
    int aw,bw;unsigned af,bf;
    stretch_key(s,a,&aw,&af);stretch_key(s,b,&bw,&bf);
    return delta(aw,af,bw,bf);
}
static float stretch_sample(const CapStretch *s,int w,unsigned f,int *cache) {
    int aw,local=w;unsigned af;
    float edge=1.0f,y;
    if(s->loop) stretch_cycle(w,s->end-s->start,&local);
    else if(w<0 || w>=s->end-s->start) return 0.0f;
    stretch_map(s,local,f,&aw,&af);
    if(aw<0 || aw>=s->core.bank->frames) y=0.0f;
    else {
        /* Identical operation order to capacity.c's sparse Hermite sample. */
        int i=stretch_window(s,aw,af,cache);
        float duration=span(&s->core,i,i-1);
        float inv=duration>1e-5f ? 1.0f/duration : 0.0f;
        float t=delta(s->core.bank->whole[i],s->core.bank->fraction[i],aw,af)*inv;
        if(t<0.0f) t=0.0f;else if(t>1.0f) t=1.0f;
        float t2=t*t,h0=(2.0f*t-3.0f)*t2+1.0f,h1=(-2.0f*t+3.0f)*t2;
        y=h0*s->core.bank->value[i]+h1*s->core.bank->value[i-1];
    }
    if(s->loop) {
        float x=(float)local+(float)f*(1.0f/16777216.0f);
        edge=x*(1.0f/48.0f);
        x=(float)(s->end-s->start-1)-x;
        if(x*(1.0f/48.0f)<edge) edge=x*(1.0f/48.0f);
        if(edge>1.0f) edge=1.0f;else if(edge<0.0f) edge=0.0f;
    }
    return y*edge;
}
float cap_stretch_tick(CapStretch *s) {
    CapState *c=&s->core;
    int grid,actual,lead;
    float y,edge;
    if(!c->active) return 0.0f;
    if(!stretch_valid(s)) {c->active=0;return 0.0f;}
    grid=stretch_rank(s,c->ideal_w,c->ideal_f,&s->ideal_key);
    actual=stretch_rank(s,c->actual_w,c->actual_f,&s->actual_key);
    lead=actual-grid;if(lead<0) lead=-lead;
    if(!c->splicing && lead>c->leash) {
        float duration;
        c->incoming_w=c->ideal_w;c->incoming_f=c->ideal_f;
        s->incoming_key=s->ideal_key;
        if(less(c->actual_w,c->actual_f,c->ideal_w,c->ideal_f))
            duration=stretch_span(s,grid-1,grid-c->leash);
        else duration=stretch_span(s,grid+c->leash-1,grid-1);
        if(duration>960.0f) duration=960.0f;
        if(duration<48.0f) duration=48.0f;
        c->increment=1.0f/duration;c->phase=0.0f;c->splicing=1;
    }
    advance_time(&c->ideal_w,&c->ideal_f,c->advance_q);
    if(c->splicing && c->phase<=1.0f) {
        float incoming=stretch_sample(s,c->incoming_w,c->incoming_f,&s->incoming_key);
        float outgoing=stretch_sample(s,c->actual_w,c->actual_f,&s->actual_key);
        float weight=smooth(c->phase);
        y=incoming*weight+outgoing*(1.0f-weight);
        advance_time(&c->incoming_w,&c->incoming_f,c->pitch_q);
        advance_time(&c->actual_w,&c->actual_f,c->pitch_q);
        c->phase+=c->increment*c->pitch;
    } else {
        if(c->splicing) {
            c->actual_w=c->incoming_w;c->actual_f=c->incoming_f;
            s->actual_key=s->incoming_key;
            c->phase=0.0f;c->splicing=0;
        }
        y=stretch_sample(s,c->actual_w,c->actual_f,&s->actual_key);
        advance_time(&c->actual_w,&c->actual_f,c->pitch_q);
    }
    /* An idle incoming cursor has no musical history. Keep it beside actual,
     * rather than subtracting loop periods forever from an unused zero. */
    if(s->loop && !c->splicing) {
        c->incoming_w=c->actual_w;c->incoming_f=c->actual_f;
    }
    if(s->loop && c->ideal_w>=s->end-s->start) {
        int local,cycles=stretch_cycle(c->ideal_w,s->end-s->start,&local);
        int shift=cycles*(s->end-s->start);
        c->ideal_w-=shift;c->actual_w-=shift;c->incoming_w-=shift;
    }
    edge=(float)c->position/48.0f;
    if(edge>1.0f) edge=1.0f;
    if(!s->loop) {
        float remaining=(float)(c->duration-1-c->position)/48.0f;
        if(remaining<edge) edge=remaining;
        if(edge<0.0f) edge=0.0f;
        c->position++;if(c->position>=c->duration) c->active=0;
    } else if(c->position<48) c->position++;
    return y*edge;
}
void cap_stretch_process(CapStretch *s,float *out,int frames) {
    int i;for(i=0;i<frames;i++) out[i]=cap_stretch_tick(s);
}
