/* SPDX-License-Identifier: AGPL-3.0-only
 * Bounded cache around the preserved analyzer; see stretch-multi-contract/. */
#include "cache.h"
static unsigned cache_epoch(unsigned epoch) { epoch++;return epoch ? epoch : 1; }
static void cache_retire(CapCache *c,int index) {
    CapCacheEntry *e=&c->entries[index];
    if(c->working==index) {cap_prepare_cancel(c->worker);c->working=-1;}
    else e->bank.generation=cache_epoch(e->bank.generation);
    e->bank.count=0;e->bank.frames=0;e->bank.error=CAP_INPUT_ERROR;
    e->ready_epoch=0;e->bytes=0;e->offset=0;e->needed=0;
}
void cap_cache_init(CapCache *c,CapPrepare *p,void *arena,unsigned bytes) {
    c->arena=(unsigned char *)arena;c->arena_bytes=bytes&~3u;
    c->clock=0;c->evictions=0;c->pressure=0;c->working=-1;c->worker=p;
    for(int i=0;i<CAP_CACHE_SLOTS;i++) {
        CapCacheEntry *e=&c->entries[i];cap_bank_init(&e->bank);
        e->input=0;e->token=0;e->epoch=1;e->seen_epoch=0;e->ready_epoch=0;
        e->referenced=0;e->pinned=0;e->blocked=0;e->offset=0;e->bytes=0;
        e->age=0;e->frames=0;e->state=CAP_PREP_IDLE;e->needed=0;
    }
    cap_prepare_init(p,&c->entries[0].bank);
}
void cap_cache_cycle(CapCache *c) {
    c->clock++;
    for(int i=0;i<CAP_CACHE_SLOTS;i++) {c->entries[i].referenced=0;c->entries[i].pinned=0;}
}
void cap_cache_pin(CapCache *c,const CapBank *bank,unsigned generation) {
    for(int i=0;i<CAP_CACHE_SLOTS;i++) {
        CapCacheEntry *e=&c->entries[i];
        if(&e->bank==bank && e->bank.generation==generation) e->pinned=1;
    }
}
int cap_cache_find(const CapCache *c,unsigned token,int frames) {
    for(int i=0;i<CAP_CACHE_SLOTS;i++)
        if(c->entries[i].token==token && c->entries[i].frames==frames) return i;
    return -1;
}
void cap_cache_reference(CapCache *c,unsigned token,int frames) {
    int index=cap_cache_find(c,token,frames);
    if(index>=0) {c->entries[index].referenced=1;c->entries[index].age=c->clock;}
}
int cap_cache_select(CapCache *c,const short *input,int frames,unsigned token) {
    if(!input || !token || frames<141 || frames>CAP_MAX_INPUT) return -1;
    int index=cap_cache_find(c,token,frames);
    if(index<0) {
        unsigned oldest=0;
        for(int i=0;i<CAP_CACHE_SLOTS;i++) {
            CapCacheEntry *e=&c->entries[i];
            if(!e->token) {index=i;break;}
            unsigned age=c->clock-e->age;
            if(!e->referenced && !e->pinned && (index<0 || age>oldest)) {index=i;oldest=age;}
        }
        if(index<0) return -1;
        CapCacheEntry *e=&c->entries[index];
        if(e->token) c->evictions++;
        cache_retire(c,index);
        e->input=input;e->frames=frames;e->token=token;e->epoch=cache_epoch(e->epoch);
        e->seen_epoch=0;e->blocked=0;e->state=CAP_PREP_IDLE;
    }
    CapCacheEntry *e=&c->entries[index];e->referenced=1;e->age=c->clock;
    return index;
}
void cap_cache_invalidate(CapCache *c,int index,int blocked) {
    if(index<0 || index>=CAP_CACHE_SLOTS || !c->entries[index].token) return;
    CapCacheEntry *e=&c->entries[index];
    e->ready_epoch=0;e->epoch=cache_epoch(e->epoch);e->blocked=blocked!=0;
    e->needed=0;e->state=CAP_PREP_IDLE;
}
/* At most sixteen nonoverlapping extents: first fit needs no free-list heap. */
static int cache_space(const CapCache *c,unsigned bytes,unsigned *offset) {
    unsigned at=0;
    if(!bytes || bytes>c->arena_bytes) return 0;
    for(int pass=0;pass<=CAP_CACHE_SLOTS;pass++) {
        unsigned next=at;
        if(at>c->arena_bytes-bytes) return 0;
        for(int i=0;i<CAP_CACHE_SLOTS;i++) {
            const CapCacheEntry *e=&c->entries[i];
            if(e->bytes && at<e->offset+e->bytes && at+bytes>e->offset)
                if(e->offset+e->bytes>next) next=e->offset+e->bytes;
        }
        if(next==at) {*offset=at;return 1;}
        at=next;
    }
    return 0;
}
static int cache_reclaim(CapCache *c,unsigned bytes,unsigned *offset) {
    if(!bytes || bytes>c->arena_bytes) return 0;
    for(int pass=0;pass<CAP_CACHE_SLOTS;pass++) {
        if(cache_space(c,bytes,offset)) return 1;
        int oldest=-1;unsigned age=0;
        for(int i=0;i<CAP_CACHE_SLOTS;i++) {
            CapCacheEntry *e=&c->entries[i];unsigned elapsed=c->clock-e->age;
            if(e->bytes && !e->referenced && !e->pinned && (oldest<0 || elapsed>age))
                {oldest=i;age=elapsed;}
        }
        if(oldest<0) return 0;
        cache_retire(c,oldest);c->entries[oldest].token=0;
        c->entries[oldest].input=0;c->entries[oldest].frames=0;
        c->entries[oldest].state=CAP_PREP_IDLE;c->evictions++;
    }
    return cache_space(c,bytes,offset);
}
int cap_cache_ready(const CapCache *c,int index) {
    if(index<0 || index>=CAP_CACHE_SLOTS) return 0;
    const CapCacheEntry *e=&c->entries[index];const CapBank *b=&e->bank;
    return e->token && !e->blocked && e->ready_epoch==e->epoch
        && e->state==CAP_PREP_READY && !b->error && b->frames==e->frames
        && b->count>=2 && b->count<=b->capacity && b->capacity<=CAP_CAPACITY
        && e->bytes==(unsigned)b->capacity*12u && e->offset<=c->arena_bytes
        && e->bytes<=c->arena_bytes-e->offset
        && (unsigned char *)b->value==c->arena+e->offset
        && (unsigned char *)b->whole==c->arena+e->offset+4u*b->capacity
        && (unsigned char *)b->fraction==c->arena+e->offset+8u*b->capacity;
}
void cap_cache_step(CapCache *c,int budget) {
    if(budget<1 || budget>CAP_PREP_BUDGET) return;
    CapPrepare *p=c->worker;
    if(c->working>=0) {
        CapCacheEntry *e=&c->entries[c->working];
        if(e->blocked || e->epoch!=e->seen_epoch || (!e->referenced && !e->pinned)) {
            cache_retire(c,c->working);e->state=CAP_PREP_IDLE;
        }
    }
    if(c->working<0) {
        for(int i=0;i<CAP_CACHE_SLOTS;i++) {
            CapCacheEntry *e=&c->entries[i];unsigned unused;
            if(!e->token || !e->referenced || e->blocked || cap_cache_ready(c,i)
                || e->state==CAP_PREP_FAILED) continue;
            if(e->state==CAP_CACHE_PRESSURE && !cache_reclaim(c,(unsigned)e->needed*12u,&unused)) continue;
            int needed=e->needed;
            cache_retire(c,i);cap_prepare_init(p,&e->bank);
            cap_prepare_begin(p,e->input,e->frames,1,e->token);
            e->seen_epoch=e->epoch;c->working=i;
            if(needed>0) {p->needed=needed;p->phase=CAP_PREP_NEEDS_STORAGE;}
            break;
        }
    }
    if(c->working<0) return;
    int index=c->working;CapCacheEntry *e=&c->entries[index];unsigned epoch=e->epoch;
    if(p->phase==CAP_PREP_COUNT || p->phase==CAP_PREP_WRITE) cap_prepare_step(p,e->token,budget);
    else if(p->phase==CAP_PREP_NEEDS_STORAGE) {
        unsigned offset,n=(unsigned)p->needed;
        if(cache_reclaim(c,n*12u,&offset)) {
            e->offset=offset;e->bytes=n*12u;
            cap_prepare_storage(p,(float *)(c->arena+offset),(int *)(c->arena+offset+4u*n),
                                (unsigned *)(c->arena+offset+8u*n),(int)n);
        } else {
            e->needed=p->needed;e->state=CAP_CACHE_PRESSURE;c->pressure++;c->working=-1;return;
        }
    }
    e->state=p->phase;
    if(e->epoch!=epoch || e->blocked) return;
    if(p->phase==CAP_PREP_READY) {e->ready_epoch=epoch;e->needed=0;c->working=-1;}
    else if(p->phase==CAP_PREP_FAILED) {e->bytes=0;c->working=-1;}
}
