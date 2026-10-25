/* SPDX-License-Identifier: AGPL-3.0-only
 * Capicola KeyframeRecorder-style two-grain handoffs for native sample controls.
 * Module default fixed fade is 960 output samples, independent of adaptive fade.
 */
#include "live.h"
#include "source-playback.c"
#define CAP_SOURCE_HANDOFF 960
void cap_live_init(CapLive *s) {
    cap_stretch_init(&s->current);cap_stretch_init(&s->outgoing);
    s->fade_left=0;s->pending=0;s->start=s->end=s->reverse=s->loop=0;
    s->pitch=s->advance=1.0f;
}
void cap_live_stop(CapLive *s) {
    cap_stretch_stop(&s->current);cap_stretch_stop(&s->outgoing);
    s->fade_left=s->pending=0;
}
int cap_live_start(CapLive *s,const CapBank *bank,int start,int end,
                   int reverse,int loop,float pitch,float advance,int leash) {
    cap_live_init(s);
    return cap_stretch_start(&s->current,bank,start,end,reverse,loop,pitch,advance,leash);
}
int cap_live_retrigger(CapLive *s,const CapBank *bank,int start,int end,
                   int reverse,int loop,float pitch,float advance,int leash) {
    CapStretch old=s->current;
    int alive=old.core.active && stretch_valid(&old);
    int result=cap_live_start(s,bank,start,end,reverse,loop,pitch,advance,leash);
    if(!result && alive) {
        s->outgoing=old;s->outgoing.loop=1;s->fade_left=CAP_SOURCE_HANDOFF;
    }
    return result;
}
static int source_transition(CapLive *s) {
    CapStretch *r=&s->current;
    int local=r->core.ideal_w,aw;unsigned af;
    stretch_cycle(local,r->end-r->start,&local);
    stretch_map(r,local,r->core.ideal_f,&aw,&af);
    if(aw<s->start) {aw=s->start;af=0;}
    if(aw>s->end-1 || (aw==s->end-1 && af)) {aw=s->end-1;af=0;}
    s->outgoing=*r;s->outgoing.loop=1;
    if(cap_stretch_start(r,r->core.bank,s->start,s->end,s->reverse,s->loop,
        s->pitch,s->advance,r->core.leash)!=CAP_OK) {
        cap_live_stop(s);return CAP_CONTROL_ERROR;
    }
    if(s->reverse) {local=s->end-1-aw;if(af){local--;af=CAP_Q-af;}}
    else local=aw-s->start;
    r->core.ideal_w=r->core.actual_w=r->core.incoming_w=local;
    r->core.ideal_f=r->core.actual_f=r->core.incoming_f=af;
    if(!s->loop) {
        int remaining=stretch_remaining(r,r->core.advance_q,CAP_STRETCH_MAX_OUTPUT);
        if(remaining<1){cap_live_stop(s);return CAP_CONTROL_ERROR;}
        r->core.duration=remaining;
    }
    s->fade_left=CAP_SOURCE_HANDOFF;s->pending=0;return CAP_OK;
}
int cap_live_update(CapLive *s,int start,int end,int reverse,int loop,float pitch,float advance) {
    CapStretch *r=&s->current;
    if(!stretch_valid(r) || start<0 || end<=start || end>r->core.bank->frames
       || (reverse!=0 && reverse!=1) || (loop!=0 && loop!=1)
       || !stretch_rates(pitch,advance)) {cap_live_stop(s);return CAP_CONTROL_ERROR;}
    if(!r->core.active && !s->fade_left) {s->pending=0;return CAP_OK;}
    s->start=start;s->end=end;s->reverse=reverse;s->loop=loop;
    s->pitch=pitch;s->advance=advance;
    s->pending=start!=r->start || end!=r->end || reverse!=r->reverse || loop!=r->loop;
    /* Copy before updating rates: the retiring grain keeps its old controls. */
    if(s->pending && !s->fade_left && r->core.active)return source_transition(s);
    if(cap_stretch_update(r,pitch,advance)!=CAP_OK) {
        cap_live_stop(s);return CAP_CONTROL_ERROR;
    }
    return CAP_OK;
}
void cap_live_process(CapLive *s,float *out,int frames) {
    for(int i=0;i<frames;i++) {
        if(!stretch_valid(&s->current))cap_live_stop(s);
        if(s->pending && !s->fade_left && s->current.core.active)source_transition(s);
        float y=cap_stretch_tick(&s->current);
        if(s->fade_left) {
            float t=(float)(CAP_SOURCE_HANDOFF-s->fade_left)*(1.0f/960.0f);
            float weight=smooth(t),old=cap_stretch_tick(&s->outgoing);
            y=old*(1.0f-weight)+y*weight;
            if(!--s->fade_left)cap_stretch_stop(&s->outgoing);
        }
        out[i]=y;
    }
}
