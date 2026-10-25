/* SPDX-License-Identifier: AGPL-3.0-only
 * Optional R3 maintenance specialization. Bank/reader layouts and step order
 * are unchanged. Called in the same serialized DSP block context as reference.
 */
static void cap_pin_direct(const CapBank *bank,unsigned generation) {
 unsigned start=(unsigned)&CACHE->entries[0],end=(unsigned)&CACHE->entries[CAP_CACHE_SLOTS];
 unsigned address=(unsigned)bank;
 if(address<start || address>=end || (address-start)%sizeof(CapCacheEntry)) return;
 CapCacheEntry *entry=(CapCacheEntry *)bank; /* CapBank is the first member. */
 if(entry->bank.generation==generation) entry->pinned=1;
}
static void cap_cycle_cached(void) {
 unsigned sources[16],frames[16],errors[16];
 int slots[16];
 cap_cache_cycle(CACHE);
 for(unsigned lane=0;lane<32;lane++) {
  CapStretchLane *r=&LANES[lane];
  if(word(0x255970u+(lane/2u)*2u)!=2) {cap_live_stop(&r->reader);r->backend=0;}
  if(r->backend && r->reader.current.core.active)
   cap_pin_direct(r->reader.current.core.bank,r->reader.current.core.generation);
  if(r->backend && r->reader.fade_left && r->reader.outgoing.core.active)
   cap_pin_direct(r->reader.outgoing.core.bank,r->reader.outgoing.core.generation);
 }
 /* Mark every selected existing bank before an admission can evict one. */
 for(unsigned track=0;track<16;track++) {
  errors[track]=stretch_selected(track,&sources[track],&frames[track]);
  slots[track]=-1;
  if(!errors[track]) {
   slots[track]=cap_cache_find(CACHE,sources[track],(int)frames[track]);
   if(slots[track]>=0) {
    CACHE->entries[slots[track]].referenced=1;
    CACHE->entries[slots[track]].age=CACHE->clock;
   }
  }
 }
 for(unsigned track=0;track<16;track++)
  if(!errors[track] && slots[track]<0)
   cap_cache_select(CACHE,(const short *)sources[track],(int)frames[track],sources[track]);
}
