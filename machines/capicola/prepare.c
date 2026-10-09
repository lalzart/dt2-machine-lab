/* SPDX-License-Identifier: AGPL-3.0-only
 * Resumable form of capacity.c analyze; see NOTICE for source attribution.
 * Compile alongside capacity.c. No change to preserved analyzer or reader. */
#include "prepare.h"
static float prep_abs(float x) { return x<0.0f ? -x : x; }
static void prep_invalidate(CapPrepare *p) {
    CapBank *b=p->bank;
    b->generation++; if(!b->generation) b->generation=1;
    b->count=0;b->frames=0;b->error=CAP_INPUT_ERROR;
    p->generation=b->generation;
}
static void prep_reset(CapPrepare *p) {
    int i;
    p->index=0;p->count=0;p->wp=0;p->deriv=0.0f;
    p->last_value=0.0f;p->last_whole=0;p->last_fraction=0;
    for(i=0;i<8;i++) p->raw[i]=0.0f;
}
void cap_prepare_init(CapPrepare *p,CapBank *b) {
    p->bank=b;p->input=0;p->token=0;p->generation=b->generation;
    p->frames=0;p->stride=0;p->phase=CAP_PREP_IDLE;p->needed=0;
    prep_reset(p);
}
void cap_prepare_cancel(CapPrepare *p) {
    prep_invalidate(p);p->input=0;p->token=0;p->phase=CAP_PREP_IDLE;
    p->needed=0;prep_reset(p);
}
static int prep_fail(CapPrepare *p) {
    cap_prepare_cancel(p);p->phase=CAP_PREP_FAILED;return p->phase;
}
int cap_prepare_begin(CapPrepare *p,const short *input,int frames,int stride,unsigned token) {
    cap_prepare_cancel(p);
    if(!input || frames<1 || frames>CAP_MAX_INPUT || (stride!=1 && stride!=2) || !token)
        return prep_fail(p);
    p->input=input;p->frames=frames;p->stride=stride;p->token=token;
    p->phase=CAP_PREP_COUNT;return p->phase;
}
int cap_prepare_storage(CapPrepare *p,float *value,int *whole,unsigned *fraction,int capacity) {
    if(p->phase!=CAP_PREP_NEEDS_STORAGE || p->bank->generation!=p->generation
       || capacity<p->needed || cap_bank_bind(p->bank,value,whole,fraction,capacity))
        return prep_fail(p);
    p->generation=p->bank->generation;prep_reset(p);
    p->phase=CAP_PREP_WRITE;return p->phase;
}
static float prep_spline(const float *raw,int wp,float delay) {
    int d=(int)delay;
    float t=delay-d,t2=t*t,t3=t2*t;
    float x0=raw[(wp-d+1)&7],x1=raw[(wp-d)&7];
    float x2=raw[(wp-d-1)&7],x3=raw[(wp-d-2)&7];
    float b0=1.0f+t*(-3.0f+t*(3.0f-t));
    float b1=4.0f+t2*(-6.0f+3.0f*t);
    float b2=1.0f+t*(3.0f+t*(3.0f-3.0f*t));
    return (x0*b0+x1*b1+x2*b2+x3*t3)*(1.0f/6.0f);
}
/* Int16 derivative magnitudes are exact multiples of 2^-16. Reconstruct
 * their ratio with integer long division and IEEE nearest-even rounding.
 * This avoids the target compiler's approximate floating divide. */
static float prep_ratio(float a,float b) {
#ifdef CAP_TARGET
    unsigned numerator=(unsigned)(a*65536.0f);
    unsigned denominator=numerator+(unsigned)(b*65536.0f);
    unsigned q=1, remainder;
    float scale=1.0f;
    int i;
    if(!numerator) return 0.0f;
    while(numerator<denominator) {numerator<<=1;scale*=0.5f;}
    remainder=numerator-denominator;
    for(i=0;i<23;i++) {
        remainder<<=1;q<<=1;
        if(remainder>=denominator) {remainder-=denominator;q++;}
    }
    remainder<<=1;
    if(remainder>denominator || (remainder==denominator && (q&1u))) q++;
    return (float)q*(1.0f/8388608.0f)*scale;
#else
    return a/(a+b);
#endif
}
int cap_prepare_step(CapPrepare *p,unsigned token,int budget) {
    int stop;
    if(token!=p->token || p->generation!=p->bank->generation || budget<1 || budget>CAP_PREP_BUDGET)
        return prep_fail(p);
    if(p->phase!=CAP_PREP_COUNT && p->phase!=CAP_PREP_WRITE) return p->phase;
    stop=p->index+budget;if(stop>p->frames+4) stop=p->frames+4;
    while(p->index<stop) {
        int n=p->index,wp=p->wp,whole=n>0 ? n-1 : 0,keep=0;
        unsigned fraction=0;
        float older=p->deriv,recent,value;
        p->raw[wp]=n<p->frames ? (float)p->input[n*p->stride]*(1.0f/32768.0f) : 0.0f;
        wp=(wp+1)&7;p->wp=wp;
        recent=(p->raw[(wp-1)&7]+4.0f*p->raw[(wp-2)&7]+p->raw[(wp-3)&7])*(1.0f/6.0f);
        p->deriv=(p->raw[(wp-3)&7]-p->raw[(wp-1)&7])*0.5f;value=recent;
        if(n==0 || n==p->frames+3) keep=1;
        else if(((older>0.0f && p->deriv<=0.0f)||(older<0.0f && p->deriv>=0.0f))
                && prep_abs(recent-p->last_value)>0.001f) {
            float alpha=prep_ratio(prep_abs(older),prep_abs(p->deriv));
            int aw=n-2;
            unsigned af=(unsigned)(alpha*16777216.0f+0.5f);
            aw+=(int)(af>>24);af&=16777215u;
            if(p->last_whole+1<aw || (p->last_whole+1==aw && p->last_fraction<af)) {
                whole=aw;fraction=af;value=prep_spline(p->raw,wp,3.0f-alpha);keep=1;
            }
        }
        if(keep) {
            if(p->count>=CAP_CAPACITY) return prep_fail(p);
            if(p->phase==CAP_PREP_WRITE) {
                if(p->count>=p->bank->capacity) return prep_fail(p);
                p->bank->value[p->count]=value;p->bank->whole[p->count]=whole;
                p->bank->fraction[p->count]=fraction;
            }
            p->last_value=value;p->last_whole=whole;p->last_fraction=fraction;p->count++;
        }
        p->index++;
    }
    if(p->index==p->frames+4) {
        if(p->phase==CAP_PREP_COUNT) {p->needed=p->count;p->phase=CAP_PREP_NEEDS_STORAGE;}
        else {
            if(p->count!=p->needed) return prep_fail(p);
            p->bank->count=p->count;p->bank->frames=p->frames;p->bank->error=CAP_OK;
            p->phase=CAP_PREP_READY;p->input=0;
        }
    }
    return p->phase;
}
