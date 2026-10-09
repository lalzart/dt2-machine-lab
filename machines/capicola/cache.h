/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef CAPICOLA_CACHE_H
#define CAPICOLA_CACHE_H
#include "prepare.h"
#define CAP_CACHE_SLOTS 16
#define CAP_CACHE_PRESSURE 7
typedef struct {
    CapBank bank;
    const short *input;
    unsigned token,epoch,seen_epoch,ready_epoch;
    unsigned referenced,pinned,blocked,offset,bytes,age;
    int frames,state,needed;
} CapCacheEntry;
typedef struct {
    unsigned char *arena;
    unsigned arena_bytes,clock,evictions,pressure;
    int working;
    CapPrepare *worker;
    CapCacheEntry entries[CAP_CACHE_SLOTS];
} CapCache;
/* Serialized control operations. No storage movement or hidden allocation.
 * cycle -> pin active readers -> select all tracks -> step once per block.
 * Input and arena must remain alive; invalidate BEFORE rewriting input. */
void cap_cache_init(CapCache *c,CapPrepare *p,void *arena,unsigned bytes);
void cap_cache_cycle(CapCache *c);
void cap_cache_pin(CapCache *c,const CapBank *bank,unsigned generation);
void cap_cache_reference(CapCache *c,unsigned token,int frames);
int cap_cache_select(CapCache *c,const short *input,int frames,unsigned token);
void cap_cache_invalidate(CapCache *c,int index,int blocked);
void cap_cache_step(CapCache *c,int budget);
int cap_cache_find(const CapCache *c,unsigned token,int frames);
int cap_cache_ready(const CapCache *c,int index);
#endif
