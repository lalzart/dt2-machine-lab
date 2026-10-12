/* SPDX-License-Identifier: AGPL-3.0-only
 * Live-control wrapper; prior reader/analyzer are unchanged. */
#include "live.h"
#include "stretch.c"
void cap_live_init(CapLive *s) {
    cap_stretch_init(&s->current);cap_stretch_init(&s->outgoing);
    s->fade_left=0;s->pending=0;s->start=0;s->end=0;s->reverse=0;s->loop=0;
    s->pitch=1.0f;s->advance=1.0f;
}
void cap_live_stop(CapLive *s) {
    cap_stretch_stop(&s->current);cap_stretch_stop(&s->outgoing);
    s->fade_left=0;s->pending=0;
}
int cap_live_start(CapLive *s,const CapBank *bank,int start,int end,
                   int reverse,int loop,float pitch,float advance,int leash) {
    cap_live_init(s);
    return cap_stretch_start(&s->current,bank,start,end,reverse,loop,pitch,advance,leash);
}
static int live_transition(CapLive *s) {
    CapStretch *old=&s->current;CapState *c=&old->core;
    int local=c->ideal_w,aw;unsigned af;
    if(old->loop) stretch_cycle(local,old->end-old->start,&local);
    stretch_map(old,local,c->ideal_f,&aw,&af);
    if(aw<s->start) {aw=s->start;af=0;}
    if(aw>s->end-1 || (aw==s->end-1 && af)) {aw=s->end-1;af=0;}
    s->outgoing=*old;
    if(cap_stretch_start(old,c->bank,s->start,s->end,s->reverse,s->loop,
                         s->pitch,s->advance,c->leash)!=CAP_OK) {
        cap_live_stop(s);return CAP_CONTROL_ERROR;
    }
    c=&old->core;
    if(s->reverse) {
        local=s->end-1-aw;
        if(af) {local--;af=CAP_Q-af;}
    } else local=aw-s->start;
    c->ideal_w=c->actual_w=c->incoming_w=local;
    c->ideal_f=c->actual_f=c->incoming_f=af;
    c->position=48;
    if(!s->loop) {
        int remaining=stretch_remaining(old,c->advance_q,CAP_STRETCH_MAX_OUTPUT-48);
        if(remaining<1) {cap_live_stop(s);return CAP_CONTROL_ERROR;}
        c->duration=48+remaining;
    }
    s->fade_left=CAP_LIVE_FADE;s->pending=0;return CAP_OK;
}
int cap_live_update(CapLive *s,int start,int end,int reverse,int loop,float pitch,float advance) {
    CapStretch *r=&s->current;
    if(!stretch_valid(r) || start<0 || end<=start || end>r->core.bank->frames
        || (reverse!=0 && reverse!=1) || (loop!=0 && loop!=1) || !stretch_rates(pitch,advance)) {
        cap_live_stop(s);return CAP_CONTROL_ERROR;
    }
    if(!r->core.active && !s->fade_left) {s->pending=0;return CAP_OK;}
    if(cap_stretch_update(r,pitch,advance)!=CAP_OK
        || (s->fade_left && cap_stretch_update(&s->outgoing,pitch,advance)!=CAP_OK)) {
        cap_live_stop(s);return CAP_CONTROL_ERROR;
    }
    s->start=start;s->end=end;s->reverse=reverse;s->loop=loop;
    s->pitch=pitch;s->advance=advance;
    s->pending=start!=r->start || end!=r->end || reverse!=r->reverse || loop!=r->loop;
    if(s->pending && !s->fade_left && r->core.active) return live_transition(s);
    return CAP_OK;
}
void cap_live_process(CapLive *s,float *out,int frames) {
    for(int i=0;i<frames;i++) {
        if(!stretch_valid(&s->current)) cap_live_stop(s);
        if(s->pending && !s->fade_left && s->current.core.active) live_transition(s);
        float y=cap_stretch_tick(&s->current);
        if(s->fade_left) {
            float t=(float)(CAP_LIVE_FADE-s->fade_left)*(1.0f/63.0f);
            float weight=smooth(t),old=cap_stretch_tick(&s->outgoing);
            y=old*(1.0f-weight)+y*weight;
            s->fade_left--;
            if(!s->fade_left) cap_stretch_stop(&s->outgoing);
        }
        out[i]=y;
    }
}
