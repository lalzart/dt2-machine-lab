/* SPDX-License-Identifier: AGPL-3.0-only
 * Extrema analysis and interpolation adapted from Matthew Nielsen's Capicola,
 * revision 120b0b843c18bda373d96eb79d49805545f61556.
 * Finite transport is a lab adaptation, not the original live Granule policy.
 */
#include "capacity.h"

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
/* Base-256 multiplication: every intermediate <2^29 for n<=1152000.
 * Return floor(rate*n/2^24), without 64-bit target arithmetic. */
static int product_whole(unsigned rate,unsigned n) {
    unsigned t=(rate&255u)*n;
    t=((rate>>8)&255u)*n+(t>>8);
    t=((rate>>16)&255u)*n+(t>>8);
    return (int)((rate>>24)*n+(t>>8));
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
    s->bank=0; s->generation=0;
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

static int analyze(CapBank *s, const float *input, int frames, int store) {
    float raw[8], recent=0.0f, deriv=0.0f;
    int n, wp=0;
    float last_value=0.0f; int last_whole=0; unsigned last_fraction=0;
    s->count=0; s->frames=0; s->error=0;
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
                 && af(recent-last_value)>0.001f) {
            float alpha=af(older_d)/(af(older_d)+af(deriv));
            int aw=n-2;
            unsigned af=(unsigned)(alpha*16777216.0f+0.5f);
            aw+=(int)(af>>24); af&=CAP_MASK;
            if (less(last_whole+1,last_fraction,aw,af)) {
                whole=aw; fraction=af; value=spline(raw,wp,3.0f-alpha); keep=1;
            }
        }
        if (keep) {
            if (s->count>=s->capacity) {
                s->count=0; s->frames=0; s->error=CAP_OVERFLOW; return s->error;
            }
            if(store) {
                s->value[s->count]=value; s->whole[s->count]=whole;
                s->fraction[s->count]=fraction;
            }
            last_value=value; last_whole=whole; last_fraction=fraction;
            s->count++;
        }
    }
    s->frames=frames;
    return CAP_OK;
}

void cap_bank_init(CapBank *b) {
    b->value=0; b->whole=0; b->fraction=0; b->capacity=0;
    b->count=0; b->frames=0; b->error=CAP_INPUT_ERROR; b->generation=1;
}
static void invalidate(CapBank *b) {
    b->generation++; if(!b->generation) b->generation=1;
    b->count=0; b->frames=0; b->error=CAP_INPUT_ERROR;
}
int cap_bank_bind(CapBank *b,float *value,int *whole,unsigned *fraction,int capacity) {
    invalidate(b);
    b->value=0; b->whole=0; b->fraction=0; b->capacity=0;
    if(!value || !whole || !fraction || capacity<2 || capacity>CAP_CAPACITY)
        return CAP_INPUT_ERROR;
    b->value=value; b->whole=whole; b->fraction=fraction; b->capacity=capacity;
    return CAP_OK;
}
int cap_measure(const float *input,int frames) {
    CapBank b; int error;
    cap_bank_init(&b); b.capacity=CAP_CAPACITY;
    error=analyze(&b,input,frames,0);
    return error ? -error : b.count;
}
int cap_load(CapBank *b,const float *input,int frames) {
    invalidate(b);
    if(!b->value || !b->whole || !b->fraction || b->capacity<2 || b->capacity>CAP_CAPACITY)
        return CAP_INPUT_ERROR;
    return analyze(b,input,frames,1);
}
void cap_attach(CapState *s,const CapBank *b) { cap_init(s); s->bank=b; }

int cap_start(CapState *s, float pitch, float advance, int leash) {
    s->active=0;
    if (!s->bank || s->bank->error || s->bank->count<2 || s->bank->frames<1)
        return s->bank && s->bank->error ? s->bank->error : CAP_INPUT_ERROR;
    s->generation=s->bank->generation;
    if (!(pitch>=0.5f && pitch<=2.0f && advance>=0.5f && advance<=2.0f)
        || leash<16 || leash>128) return CAP_CONTROL_ERROR;
    s->pitch=pitch; s->advance=advance; s->leash=leash;
    s->ideal_w=s->actual_w=s->incoming_w=0;
    s->ideal_f=s->actual_f=s->incoming_f=0;
    s->phase=0.0f; s->increment=0.0f; s->splicing=0; s->position=0;
    s->pitch_q=(unsigned)(pitch*16777216.0f);
    s->advance_q=(unsigned)(advance*16777216.0f);
    s->duration=exact_duration(s->bank->frames,s->advance_q);
    s->active=1;
    return CAP_OK;
}
void cap_stop(CapState *s) { s->active=0; }

static int window(const CapState *s, int aw, unsigned af) {
    int lo=1, hi=s->bank->count-1;
    while(lo<hi) {
        int mid=lo+((hi-lo)>>1);
        if(less(s->bank->whole[mid],s->bank->fraction[mid],aw,af)) lo=mid+1; else hi=mid;
    }
    return lo;
}
static int clamp_index(const CapState *s, int i) {
    if(i<0) i=0;
    if(i>=s->bank->count) i=s->bank->count-1;
    return i;
}
static float span(const CapState *s, int a, int b) {
    a=clamp_index(s,a); b=clamp_index(s,b);
    return delta(s->bank->whole[a],s->bank->fraction[a],s->bank->whole[b],s->bank->fraction[b]);
}
static float sample(const CapState *s, int aw, unsigned af) {
    int i;
    float duration, inv, t, t2, h0, h1;
    if(aw<0 || aw>=s->bank->frames) return 0.0f;
    i=window(s,aw,af);
    duration=span(s,i,i-1);
    inv=duration>1e-5f ? 1.0f/duration : 0.0f;
    t=delta(s->bank->whole[i],s->bank->fraction[i],aw,af)*inv;
    if(t<0.0f) t=0.0f; else if(t>1.0f) t=1.0f;
    t2=t*t; h0=(2.0f*t-3.0f)*t2+1.0f; h1=(-2.0f*t+3.0f)*t2;
    return h0*s->bank->value[i]+h1*s->bank->value[i-1];
}
float cap_tick(CapState *s) {
    int grid, actual, lead;
    float y, edge, remaining;
    if(!s->active) return 0.0f;
    if(!s->bank || s->generation!=s->bank->generation) { s->active=0; return 0.0f; }
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
int cap_count(const CapState *s) { return s->bank->count; }
float cap_value(const CapState *s,int i) { return s->bank->value[i]; }
#ifndef CAP_TARGET
/* Diagnostics only: never compile host double reconstruction on SHARC. */
double cap_time(const CapState *s,int i) { return (double)s->bank->whole[i]+(double)s->bank->fraction[i]/16777216.0; }
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
