/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef CAPICOLA_LIVE_H
#define CAPICOLA_LIVE_H
#include "stretch.h"
#define CAP_LIVE_FADE 64
typedef struct {
    CapStretch current,outgoing;
    int fade_left,start,end,reverse,loop;
    float pitch,advance;
    int pending;
} CapLive;
void cap_live_init(CapLive *s);
void cap_live_stop(CapLive *s);
int cap_live_start(CapLive *s,const CapBank *bank,int start,int end,
                   int reverse,int loop,float pitch,float advance,int leash);
int cap_live_update(CapLive *s,int start,int end,int reverse,int loop,float pitch,float advance);
void cap_live_process(CapLive *s,float *out,int frames);
#endif
