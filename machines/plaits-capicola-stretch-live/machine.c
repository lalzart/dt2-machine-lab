/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 STRETCH backend, sixteen bounded banks and 32 independent readers.
 * Existing Plaits voice routing and sparse preparation remain unchanged. */
#include "../plaits-integration/machine.c"
#define CAP_TARGET 1
#include "../capicola/live.c"
#include "../capicola/prepare.c"
#include "../capicola/cache.c"
#define CAP_POOL_BASE 0x8422b9c8u
#define CAP_POOL_END 0x9ca2b9c8u
#define CAP_BANK_BASE 0x9ca2bac8u
#define CAP_AUTO_MAGIC 0x43535433u
#define CAP_BANK_BYTES 0x6fff00u
#define CACHE ((CapCache *)0x200e7000)
typedef char cache_size[sizeof(CapCache)==1436 ? 1 : -1];
typedef char cache_entry_size[sizeof(CapCacheEntry)==88 ? 1 : -1];
typedef struct {
 unsigned magic,version,ready,source;
 float pitch,advance,gain;
 int leash;
 unsigned generation;
} CapHandoff;
typedef struct {
 unsigned magic,source,frames,epoch,seen_epoch,published_epoch,blocked;
 unsigned slices,prepared_frames,cancellations;
} CapAuto;
typedef struct {
 unsigned sequence,magic,version,slot,state,reason,done,total,epoch,source,frames;
} CapStatus;
typedef struct {
 CapLive reader;
 unsigned source,epoch,backend,renders,last_destination;
} CapStretchLane;
typedef char stretch_lane_size[sizeof(CapStretchLane)==276 ? 1 : -1];
typedef char stretch_bank_size[sizeof(CapBank)==32 ? 1 : -1];
#define AUTO ((volatile CapAuto *)0x200e4500)
#define HANDOFF ((volatile CapHandoff *)0x200e4000)
#define STATUS ((volatile CapStatus *)0x200e4600)
#define LANES ((CapStretchLane *)0x200e8000)
#ifdef CAP_CACHED_MAINTENANCE
#include "../capicola/maintenance.h"
#endif

static unsigned stretch_selected(unsigned track,unsigned *source,unsigned *frames) {
 *source=0;*frames=0;
 if(word(0x255970u+track*2u)!=2) return 9;
 unsigned slot=(unsigned)word(0x2559bcu+track*0x60u);
 if(slot>=1024u) return 2;
 volatile unsigned *entry=(volatile unsigned *)(0x257810u+slot*20u);
 unsigned left=entry[0],right=entry[1],bytes=entry[2],rate=entry[3],stereo=entry[4]&255u;
 if(!bytes) return 1;
 if(left!=right || stereo) return 3;
 if(rate!=48000u) return 4;
 if(bytes>CAP_MAX_INPUT*2u) return 5;
 if(bytes<282u) return 6;
 if((left&1u) || (bytes&1u) || left>=CAP_POOL_END-CAP_POOL_BASE
    || bytes>CAP_POOL_END-CAP_POOL_BASE-left) return 7;
 *source=CAP_POOL_BASE+left;*frames=bytes/2u;return 0;
}
/* Invalidate publication before any LP0 PCM mutation. */
void cap_event(unsigned kind,unsigned address,unsigned bytes) {
 if(AUTO->magic!=CAP_AUTO_MAGIC) return;
 unsigned start=0;
 int global=kind==2 && !bytes;
 if(!global) {
  if(kind==1) {
   if(address>=0x19200u) return;
   start=CAP_POOL_BASE+(address<<12);bytes=4096;
  } else {
   if(address>0x19000000u || bytes>0x19000000u-address) return;
   start=CAP_POOL_BASE+address;
   if(kind==3) {start+=bytes;bytes=16;}
  }
 }
 for(int i=0;i<CAP_CACHE_SLOTS;i++) {
  CapCacheEntry *e=&CACHE->entries[i];
  if(e->token && (global || (start<e->token+(unsigned)e->frames*2u && start+bytes>e->token)))
   cap_cache_invalidate(CACHE,i,global || !(kind==2 && start==e->token && bytes==(unsigned)e->frames*2u));
 }
}
void cap_maintenance(void) {
 volatile CapAuto *s=AUTO;
 if(s->magic!=CAP_AUTO_MAGIC) {
  s->source=0;s->frames=0;s->epoch=1;s->seen_epoch=1;s->published_epoch=0;
  s->blocked=0;s->slices=0;s->prepared_frames=0;s->cancellations=0;
  HANDOFF->ready=0;HANDOFF->magic=0x43415031u;HANDOFF->version=2;HANDOFF->source=0;
  HANDOFF->pitch=1.0f;HANDOFF->advance=1.0f;HANDOFF->gain=1.0f;HANDOFF->leash=128;
  cap_cache_init(CACHE,(CapPrepare *)0x200e4400,(void *)CAP_BANK_BASE,CAP_BANK_BYTES);
  for(int i=0;i<32;i++) {
   cap_live_init(&LANES[i].reader);
   LANES[i].source=0;LANES[i].epoch=0;LANES[i].backend=0;
   LANES[i].renders=0;LANES[i].last_destination=0;
  }
  s->magic=CAP_AUTO_MAGIC;
 }
#ifdef CAP_CACHED_MAINTENANCE
 cap_cycle_cached();
#else
 cap_cache_cycle(CACHE);
 for(unsigned lane=0;lane<32;lane++) {
  CapStretchLane *r=&LANES[lane];
  if(word(0x255970u+(lane/2u)*2u)!=2) {cap_live_stop(&r->reader);r->backend=0;}
  if(r->backend && r->reader.current.core.active)
   cap_cache_pin(CACHE,r->reader.current.core.bank,r->reader.current.core.generation);
  if(r->backend && r->reader.fade_left && r->reader.outgoing.core.active)
   cap_cache_pin(CACHE,r->reader.outgoing.core.bank,r->reader.outgoing.core.generation);
 }
 /* Mark all existing selected banks before admitting any replacement. */
 for(unsigned track=0;track<16;track++) {
  unsigned source,frames;
  if(!stretch_selected(track,&source,&frames)) cap_cache_reference(CACHE,source,(int)frames);
 }
 for(unsigned track=0;track<16;track++) {
  unsigned source,frames;
  if(!stretch_selected(track,&source,&frames))
   cap_cache_select(CACHE,(const short *)source,(int)frames,source);
 }
#endif
 cap_cache_step(CACHE,32);
 unsigned ready=0,used=0;
 for(int i=0;i<CAP_CACHE_SLOTS;i++) {
  if(cap_cache_ready(CACHE,i)) ready++;
  used+=CACHE->entries[i].bytes;
 }
 /* R2 diagnostic ABI: ready count, allocated bytes, eviction/pressure counts. */
 HANDOFF->ready=ready;HANDOFF->source=used;HANDOFF->generation=CACHE->clock;
 s->source=ready;s->frames=used;s->slices++;s->cancellations=CACHE->evictions;
 STATUS->magic=0x43505332u;STATUS->version=2;STATUS->state=ready;
 STATUS->reason=CACHE->pressure;STATUS->done=used;STATUS->total=CAP_BANK_BYTES;
}
static int stretch_published(unsigned source,unsigned frames) {
 if(AUTO->magic!=CAP_AUTO_MAGIC) return -1;
 int index=cap_cache_find(CACHE,source,(int)frames);
 return cap_cache_ready(CACHE,index) ? index : -1;
}
static int stretch_integer_position(unsigned voice,unsigned offset) {
 unsigned low=*(volatile unsigned *)(voice+offset),high=*(volatile unsigned *)(voice+offset+4u);
 if(high>CAP_MAX_INPUT/2u || (low&0x7fffffffu)) return -1;
 return (int)((high<<1)|(low>>31));
}
int cap_stretch_machine(unsigned voice,float *destination,int count) {
 if(voice<0x2412ccu || voice>=0x2412ccu+32u*0x1d8u
    || (voice-0x2412ccu)%0x1d8u || count!=32) return 0;
 unsigned lane=(voice-0x2412ccu)/0x1d8u;
 if((unsigned)destination!=*(volatile unsigned *)(0x24ef2cu+lane*4u)
    || (unsigned)destination<0x80000000u || (unsigned)destination>0xa0000000u-128u
    || ((unsigned)destination&3u)) return 0;
 CapStretchLane *s=&LANES[lane];
 if(word(0x255970u+(lane/2u)*2u)!=2) {
  cap_live_stop(&s->reader);s->backend=0;return 0;
 }
 unsigned source=*(volatile unsigned *)voice;
 unsigned frames=*(volatile unsigned *)(voice+0x188u);
 unsigned trigger=*(volatile unsigned char *)(0x24f0ccu+lane);
 unsigned selected,n;
 unsigned selection_error=stretch_selected(lane/2u,&selected,&n);
 float pitch=*(volatile float *)(voice+0x1ccu),advance=*(volatile float *)(voice+0x1c8u);
 if(trigger) {
  s->backend=0;cap_live_stop(&s->reader);
  int start=stretch_integer_position(voice,0x198u),end=stretch_integer_position(voice,0x1a0u);
  int bank=stretch_published(source,frames);
  if(!selection_error && selected==source && n==frames && bank>=0
    && *(volatile unsigned *)(voice+0x184u)==48000u
    && cap_live_start(&s->reader,&CACHE->entries[bank].bank,start,end,
       *(volatile unsigned char *)(voice+0x1bbu),
       *(volatile unsigned char *)(voice+0x1bcu),pitch,advance,128)==CAP_OK) {
   s->source=source;s->epoch=CACHE->entries[bank].epoch;s->backend=1;
  }
 }
 if(!s->backend) return 0;
 int bank=stretch_published(source,frames);
 if(selection_error || selected!=s->source || n!=frames
    || source!=s->source || bank<0 || s->epoch!=CACHE->entries[bank].epoch
    || s->reader.current.core.bank!=&CACHE->entries[bank].bank
    || !*(volatile unsigned char *)(voice+0x1b8u)) cap_live_stop(&s->reader);
 else cap_live_update(&s->reader,stretch_integer_position(voice,0x198u),
    stretch_integer_position(voice,0x1a0u),*(volatile unsigned char *)(voice+0x1bbu),
    *(volatile unsigned char *)(voice+0x1bcu),pitch,advance);
 cap_live_process(&s->reader,destination,count);
 /* The stock renderer owns +0x1b8 and clears it at finite completion.
  * Retain this lifecycle contract after replacing that renderer. Keep the
  * custom backend latched until trigger: never resume stock mid-note. */
 if(!s->reader.current.core.active && !s->reader.fade_left)
  *(volatile unsigned char *)(voice+0x1b8u)=0;
 /* Prototype diagnostic tap at the actual renderer boundary. Native envelopes
  * and effects subsequently reuse/modify destination; retain these 32 words
  * so the runner never mistakes a post-effect buffer for the sparse reader. */
#ifndef CAP_DISABLE_TRACE
 float *trace=((float *)0x200eb000)+lane*32u;
 for(int i=0;i<count;i++) trace[i]=destination[i];
#endif
 s->renders++;s->last_destination=(unsigned)destination;
 return 1;
}
