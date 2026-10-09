/* SPDX-License-Identifier: AGPL-3.0-only
 * Extrema analysis and interpolation adapted from Matthew Nielsen's Capicola,
 * revision 120b0b843c18bda373d96eb79d49805545f61556.
 * Finite transport is a lab adaptation, not the original live Granule policy.
 */
#include "split.h"

static float af(float v) { return v < 0.0f ? -v : v; }
/* Absolute positions never pass through float. Only local differences do. */
#define CAP_Q 16777216u
#define CAP_MASK 16777215u
static int less(int aw, unsigned af, int bw, unsigned bf) {
    return aw<bw || (aw==bw && af<bf);
}
static float delta(int aw, unsigned af, int bw, unsigned bf) {
    return (float)(aw-bw)+(float)((int)af-(int)bf)*(1.0f/16777216.0f);
}
static void advance_time(int *w, unsigned *f, unsigned rate) {
    unsigned sum=*f+(rate&CAP_MASK);
    *w+=(int)(rate>>24)+(int)(sum>>24);
    *f=sum&CAP_MASK;
}
/* 12-bit limbs bound every product below 2^30 for n<=96000. */
static int product_whole(unsigned rate, unsigned n) {
    unsigned lo=(rate&4095u)*n;
    unsigned hi=(rate>>12)*n+(lo>>12);
    return (int)(hi>>12);
}
static int exact_duration(int frames, unsigned rate) {
    int lo=1, hi=frames*2;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1);
        if(product_whole(rate,(unsigned)mid)<frames) lo=mid+1;
        else hi=mid;
    }
    return lo;
}
static float smooth(float p) { return p*p*(3.0f-2.0f*p); }

void cap_init(CapState *s) {
    s->count=0; s->frames=0; s->error=0;
    s->ideal_w=s->actual_w=s->incoming_w=0;
    s->ideal_f=s->actual_f=s->incoming_f=0;
    s->pitch_q=CAP_Q; s->advance_q=CAP_Q;
    s->pitch=1.0f; s->advance=1.0f; s->phase=0.0f; s->increment=0.0f;
    s->leash=128; s->splicing=0; s->position=0; s->duration=0; s->active=0;
}

static float spline(const float *raw, int wp, float delay) {
    int d=(int)delay;
    float t=delay-d, t2=t*t, t3=t2*t;
    float x0=raw[(wp-d+1)&7], x1=raw[(wp-d)&7];
    float x2=raw[(wp-d-1)&7], x3=raw[(wp-d-2)&7];
    float b0=1.0f+t*(-3.0f+t*(3.0f-t));
    float b1=4.0f+t2*(-6.0f+3.0f*t);
    float b2=1.0f+t*(3.0f+t*(3.0f-3.0f*t));
    return (x0*b0+x1*b1+x2*b2+x3*t3)*(1.0f/6.0f);
}

int cap_load(CapState *s, const float *input, int frames) {
    float raw[8], recent=0.0f, deriv=0.0f;
    int n, wp=0;
    cap_init(s);
    if (!input || frames<1 || frames>CAP_MAX_INPUT) {
        s->error=CAP_INPUT_ERROR; return s->error;
    }
    for (n=0;n<frames;n++) {
        if (!(input[n]>=-1.0f && input[n]<=1.0f)) {
            s->error=CAP_INPUT_ERROR; return s->error;
        }
    }
    for (n=0;n<8;n++) raw[n]=0.0f;
    for (n=0;n<frames+4;n++) {
        float older_d=deriv, value;
        int whole; unsigned fraction=0;
        int keep=0;
        raw[wp]=(n<frames ? input[n] : 0.0f); wp=(wp+1)&7;
        recent=(raw[(wp-1)&7]+4.0f*raw[(wp-2)&7]+raw[(wp-3)&7])*(1.0f/6.0f);
        deriv=(raw[(wp-3)&7]-raw[(wp-1)&7])*0.5f;
        value=recent; whole=n>0 ? n-1 : 0;
        if (n==0 || n==frames+3) keep=1;
        else if (((older_d>0.0f && deriv<=0.0f)||(older_d<0.0f && deriv>=0.0f))
                 && af(recent-s->value[s->count-1])>0.001f) {
            float alpha=af(older_d)/(af(older_d)+af(deriv));
            int aw=n-2;
            unsigned af=(unsigned)(alpha*16777216.0f+0.5f);
            aw+=(int)(af>>24); af&=CAP_MASK;
            if (less(s->whole[s->count-1]+1,s->fraction[s->count-1],aw,af)) {
                whole=aw; fraction=af; value=spline(raw,wp,3.0f-alpha); keep=1;
            }
        }
        if (keep) {
            if (s->count>=CAP_CAPACITY) {
                cap_init(s); s->error=CAP_OVERFLOW; return s->error;
            }
            s->value[s->count]=value; s->whole[s->count]=whole;
            s->fraction[s->count]=fraction; s->count++;
        }
    }
    s->frames=frames;
    return CAP_OK;
}

int cap_start(CapState *s, float pitch, float advance, int leash) {
    s->active=0;
    if (s->error || s->count<2 || s->frames<1) return s->error ? s->error : CAP_INPUT_ERROR;
    if (!(pitch>=0.5f && pitch<=2.0f && advance>=0.5f && advance<=2.0f)
        || leash<16 || leash>128) return CAP_CONTROL_ERROR;
    s->pitch=pitch; s->advance=advance; s->leash=leash;
    s->ideal_w=s->actual_w=s->incoming_w=0;
    s->ideal_f=s->actual_f=s->incoming_f=0;
    s->phase=0.0f; s->increment=0.0f; s->splicing=0; s->position=0;
    s->pitch_q=(unsigned)(pitch*16777216.0f);
    s->advance_q=(unsigned)(advance*16777216.0f);
    s->duration=exact_duration(s->frames,s->advance_q);
    s->active=1;
    return CAP_OK;
}
void cap_stop(CapState *s) { s->active=0; }

static int window(const CapState *s, int aw, unsigned af) {
    int lo=1, hi=s->count-1;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1);
        if(less(s->whole[mid],s->fraction[mid],aw,af)) lo=mid+1; else hi=mid;
    }
    return lo;
}
static int clamp_index(const CapState *s, int i) {
    if(i<0) i=0;
    if(i>=s->count) i=s->count-1;
    return i;
}
static float span(const CapState *s, int a, int b) {
    a=clamp_index(s,a); b=clamp_index(s,b);
    return delta(s->whole[a],s->fraction[a],s->whole[b],s->fraction[b]);
}
static float sample(const CapState *s, int aw, unsigned af) {
    int i;
    float duration, inv, t, t2, h0, h1;
    if(aw<0 || aw>=s->frames) return 0.0f;
    i=window(s,aw,af);
    duration=span(s,i,i-1);
    inv=duration>1e-5f ? 1.0f/duration : 0.0f;
    t=delta(s->whole[i],s->fraction[i],aw,af)*inv;
    if(t<0.0f) t=0.0f; else if(t>1.0f) t=1.0f;
    t2=t*t; h0=(2.0f*t-3.0f)*t2+1.0f; h1=(-2.0f*t+3.0f)*t2;
    return h0*s->value[i]+h1*s->value[i-1];
}
float cap_tick(CapState *s) {
    int grid, actual, lead;
    float y, edge, remaining;
    if(!s->active) return 0.0f;
    grid=window(s,s->ideal_w,s->ideal_f); actual=window(s,s->actual_w,s->actual_f);
    lead=actual-grid; if(lead<0) lead=-lead;
    if(!s->splicing && lead>s->leash) {
        float duration;
        s->incoming_w=s->ideal_w; s->incoming_f=s->ideal_f;
        if(less(s->actual_w,s->actual_f,s->ideal_w,s->ideal_f))
            duration=span(s,grid-1,grid-s->leash);
        else duration=span(s,grid+s->leash-1,grid-1);
        if(duration>960.0f) duration=960.0f;
        if(duration<48.0f) duration=48.0f;
        s->increment=1.0f/duration; s->phase=0.0f; s->splicing=1;
    }
    advance_time(&s->ideal_w,&s->ideal_f,s->advance_q);
    if(s->splicing && s->phase<=1.0f) {
        float incoming=sample(s,s->incoming_w,s->incoming_f), outgoing=sample(s,s->actual_w,s->actual_f);
        float w=smooth(s->phase);
        y=incoming*w+outgoing*(1.0f-w);
        advance_time(&s->incoming_w,&s->incoming_f,s->pitch_q); advance_time(&s->actual_w,&s->actual_f,s->pitch_q);
        s->phase+=s->increment*s->pitch;
    } else {
        if(s->splicing) { s->actual_w=s->incoming_w; s->actual_f=s->incoming_f; s->phase=0.0f; s->splicing=0; }
        y=sample(s,s->actual_w,s->actual_f); advance_time(&s->actual_w,&s->actual_f,s->pitch_q);
    }
    edge=(float)s->position/48.0f;
    remaining=(float)(s->duration-1-s->position)/48.0f;
    if(edge>1.0f) edge=1.0f;
    if(remaining<edge) edge=remaining;
    if(edge<0.0f) edge=0.0f;
    s->position++;
    if(s->position>=s->duration) s->active=0;
    return y*edge;
}
void cap_process(CapState *s, float *out, int frames) {
    int n;
    for(n=0;n<frames;n++) out[n]=cap_tick(s);
}
/* Host/target state sizing for tests; not a serialized ABI. */
int cap_state_size(void) { return sizeof(CapState); }
int cap_count(const CapState *s) { return s->count; }
float cap_value(const CapState *s,int i) { return s->value[i]; }
#ifndef CAP_TARGET
/* Diagnostics only: never compile host double reconstruction on SHARC. */
double cap_time(const CapState *s,int i) { return (double)s->whole[i]+(double)s->fraction[i]/16777216.0; }
#endif
int cap_duration(const CapState *s) { return s->duration; }
int cap_ideal_whole(const CapState *s) { return s->ideal_w; }
unsigned cap_ideal_fraction(const CapState *s) { return s->ideal_f; }
int cap_position(const CapState *s) { return s->position; }

/* Diagnostic mask: exclude both entry and exit of crossfades in pitch tests. */
void cap_process_trace(CapState *s, float *out, int *splice, int frames) {
    int n;
    for(n=0;n<frames;n++) {
        int before=s->splicing;
        out[n]=cap_tick(s);
        splice[n]=before || s->splicing;
    }
}
