/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 experimental automatic preparation. Work runs in the audio task. */
static int cap_auto_valid(void);
#define CAP_LIFETIME_VALID() cap_auto_valid()
#define CAP_BANK_BASE 0x9ca2bac8u
#include "../plaits-capicola-prep/machine.c"

#define CAP_POOL_BASE 0x8422b9c8u
#define CAP_POOL_END 0x9ca2b9c8u
#define CAP_AUTO_MAGIC 0x43415531u
#define CAP_AUTO_BUDGET 32

typedef struct {
 unsigned magic, source, frames, epoch, seen_epoch, published_epoch, blocked;
 unsigned slices, prepared_frames, cancellations;
} CapAuto;
#define AUTO ((volatile CapAuto *)0x200e4500)
#define HANDOFF ((volatile CapHandoff *)0x200e4000)

#ifndef CAP_SELECTION_VALID
#define CAP_SELECTION_VALID() 1
#endif
#ifndef CAP_READ_SOURCE
#define CAP_READ_SOURCE(source,frames,other) \
 source=*(volatile unsigned *)0x2412cc; \
 frames=*(volatile unsigned *)(0x2412cc+0x188); \
 other=*(volatile unsigned *)0x2414a4
#endif

static int cap_auto_valid(void) {
 return AUTO->magic==CAP_AUTO_MAGIC && !AUTO->blocked && CAP_SELECTION_VALID()
    && AUTO->epoch==AUTO->published_epoch
    && *(volatile unsigned *)(0x2412cc+0x188)==AUTO->frames
    && (!*(volatile unsigned *)0x2414a4 || *(volatile unsigned *)0x2414a4==AUTO->source);
}

/* Sample callbacks can interrupt maintenance. Only this small event record and
 * the publication flag are written here; the analyzer and arrays are untouched.
 * kind1: page index; kind2: left-channel offset, byte length.
 * A zero-length slot reset conservatively invalidates any tracked source. */
void cap_event(unsigned kind,unsigned address,unsigned bytes) {
 volatile CapAuto *s=AUTO;
 if(s->magic!=CAP_AUTO_MAGIC || !s->source || !s->frames) return;
 unsigned start;
 if(kind==1) {
  if(address>=0x19200u) return;
  start=CAP_POOL_BASE+(address<<12);bytes=4096;
 } else if(kind==2 && !bytes) {
  HANDOFF->ready=0;s->blocked=1;s->epoch=s->epoch+1u;return;
 } else {
  if(address>0x19000000u || bytes>0x19000000u-address) return;
  start=CAP_POOL_BASE+address;
  if(kind==3) {start+=bytes;bytes=16;}
 }
 if((kind==2 && !bytes) ||
    (start<s->source+s->frames*2u && start+bytes>s->source)) {
  HANDOFF->ready=0;
  s->blocked=!(kind==2 && start==s->source && bytes==s->frames*2u);
  s->epoch=s->epoch+1u;
 }
}

/* Called once after each normal stock audio block, before its time capture. */
void cap_maintenance(void) {
 volatile CapAuto *s=AUTO;
 volatile CapHandoff *h=HANDOFF;
 CapBank *b=(CapBank *)0x200e4100;
 CapPrepare *p=(CapPrepare *)0x200e4400;
 if(s->magic!=CAP_AUTO_MAGIC) {
  s->source=0;s->frames=0;s->epoch=1;s->seen_epoch=1;s->published_epoch=0;
  s->blocked=0;s->slices=0;s->prepared_frames=0;s->cancellations=0;
  h->ready=0;h->magic=0x43415031u;h->version=1;h->source=0;
  h->pitch=1.0f;h->advance=1.0f;h->gain=0.125f;h->leash=128;
  cap_bank_init(b);cap_prepare_init(p,b);
  s->magic=CAP_AUTO_MAGIC;
 }
 unsigned source,frames,other;
 CAP_READ_SOURCE(source,frames,other);
 int valid=word(0x255970)==8 && source>=CAP_POOL_BASE && source<CAP_POOL_END
   && !(source&1u) && frames>0 && frames<=CAP_MAX_INPUT
   && frames<=(CAP_POOL_END-source)/2u && (!other || other==source);
 if(!valid) {source=0;frames=0;}
 if(source!=s->source || frames!=s->frames) {
  h->ready=0;cap_prepare_cancel(p);s->cancellations++;
  s->source=source;s->frames=frames;s->blocked=0;
  s->epoch=s->epoch+1u;s->seen_epoch=s->epoch;
  h->source=source;
  if(source) cap_prepare_begin(p,(const short *)source,(int)frames,1,source);
 } else if(s->seen_epoch!=s->epoch) {
  h->ready=0;cap_prepare_cancel(p);s->cancellations++;
  s->seen_epoch=s->epoch;
  if(source && !s->blocked)
   cap_prepare_begin(p,(const short *)source,(int)frames,1,source);
 }
 if(!source || s->blocked) {h->ready=0;return;}
 unsigned epoch=s->epoch;
 if(p->phase==CAP_PREP_COUNT || p->phase==CAP_PREP_WRITE) {
  int before=p->index;
  cap_prepare_step(p,source,CAP_AUTO_BUDGET);
  s->slices++;s->prepared_frames+=(unsigned)(p->index-before);
 } else if(p->phase==CAP_PREP_NEEDS_STORAGE) {
  unsigned n=(unsigned)p->needed;
  cap_prepare_storage(p,(float *)CAP_BANK_BASE,(int *)(CAP_BANK_BASE+4u*n),
                       (unsigned *)(CAP_BANK_BASE+8u*n),(int)n);
 }
 h->generation=b->generation;
 /* Reader checks this epoch too, covering an interrupt after this comparison
  * but before the ready store. An invalidated step never becomes playable. */
 s->published_epoch=epoch;
 h->ready=p->phase==CAP_PREP_READY && s->epoch==epoch && !s->blocked;
}
