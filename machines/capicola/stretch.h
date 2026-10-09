/* SPDX-License-Identifier: AGPL-3.0-only
 * Frozen STRETCH R1 transport. See stretch-contract/ and NOTICE. */
#ifndef CAPICOLA_STRETCH_H
#define CAPICOLA_STRETCH_H
#include "capacity.h"
#define CAP_STRETCH_MAX_OUTPUT 6144000
typedef struct {
    CapState core;
    int start, end, reverse, loop, first_key, key_count;
    int ideal_key, actual_key, incoming_key;
} CapStretch;
void cap_stretch_init(CapStretch *s);
int cap_stretch_start(CapStretch *s,const CapBank *bank,int start,int end,
                      int reverse,int loop,float pitch,float advance,int leash);
int cap_stretch_update(CapStretch *s,float pitch,float advance);
void cap_stretch_stop(CapStretch *s);
float cap_stretch_tick(CapStretch *s);
void cap_stretch_process(CapStretch *s,float *out,int frames);
#endif
