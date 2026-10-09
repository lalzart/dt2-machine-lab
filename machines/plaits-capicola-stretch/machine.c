/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 STRETCH backend, sharing one immutable bank among 32 readers.
 * Existing Plaits voice routing and sparse preparation remain unchanged. */
#include "../plaits-integration/machine.c"
#define CAP_TARGET 1
#include "../capicola/stretch.c"
#include "../capicola/prepare.c"
#define CAP_POOL_BASE 0x8422b9c8u
#define CAP_POOL_END 0x9ca2b9c8u
#define CAP_BANK_BASE 0x9ca2bac8u
#define CAP_AUTO_MAGIC 0x43535431u
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
 CapStretch reader;
 unsigned source,epoch,backend,renders,last_destination;
} CapStretchLane;
typedef char stretch_lane_size[sizeof(CapStretchLane)==132 ? 1 : -1];
typedef char stretch_bank_size[sizeof(CapBank)==32 ? 1 : -1];
#define AUTO ((volatile CapAuto *)0x200e4500)
#define HANDOFF ((volatile CapHandoff *)0x200e4000)
#define STATUS ((volatile CapStatus *)0x200e4600)
#define LANES ((CapStretchLane *)0x200e4800)

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
/* LP0 callbacks may interrupt maintenance: publish invalidity BEFORE mutation.
 * Reuse the previously verified small-record callback protocol. */
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
 if(start<s->source+s->frames*2u && start+bytes>s->source) {
  HANDOFF->ready=0;
  s->blocked=!(kind==2 && start==s->source && bytes==s->frames*2u);
  s->epoch=s->epoch+1u;
 }
}
void cap_maintenance(void) {
 volatile CapAuto *s=AUTO;
 volatile CapHandoff *h=HANDOFF;
 CapBank *b=(CapBank *)0x200e4100;
 CapPrepare *p=(CapPrepare *)0x200e4400;
 if(s->magic!=CAP_AUTO_MAGIC) {
  s->source=0;s->frames=0;s->epoch=1;s->seen_epoch=1;s->published_epoch=0;
  s->blocked=0;s->slices=0;s->prepared_frames=0;s->cancellations=0;
  h->ready=0;h->magic=0x43415031u;h->version=1;h->source=0;
  h->pitch=1.0f;h->advance=1.0f;h->gain=1.0f;h->leash=128;
  cap_bank_init(b);cap_prepare_init(p,b);
  for(int i=0;i<32;i++) {
   cap_stretch_init(&LANES[i].reader);
   LANES[i].source=0;LANES[i].epoch=0;LANES[i].backend=0;
   LANES[i].renders=0;LANES[i].last_destination=0;
  }
  s->magic=CAP_AUTO_MAGIC;
 }
 for(unsigned lane=0;lane<32;lane++) {
  if(word(0x255970u+(lane/2u)*2u)!=2) {
   cap_stretch_stop(&LANES[lane].reader);LANES[lane].backend=0;
  }
 }
 unsigned source=0,frames=0,selected=16,reason=9;
 /* Retain a referenced source; otherwise admit the first eligible track. */
 for(unsigned track=0;track<16;track++) {
  unsigned candidate,n,error=stretch_selected(track,&candidate,&n);
  if(!error) {
   if(selected==16) {source=candidate;frames=n;selected=track;reason=0;}
   if(candidate==s->source && n==s->frames) {
    source=candidate;frames=n;selected=track;reason=0;break;
   }
  }
 }
 if(source!=s->source || frames!=s->frames) {
  h->ready=0;cap_prepare_cancel(p);s->cancellations++;
  s->source=source;s->frames=frames;s->blocked=0;
  s->epoch=s->epoch+1u;s->seen_epoch=s->epoch;h->source=source;
  if(source) cap_prepare_begin(p,(const short *)source,(int)frames,1,source);
 } else if(s->seen_epoch!=s->epoch) {
  h->ready=0;cap_prepare_cancel(p);s->cancellations++;
  s->seen_epoch=s->epoch;
  if(source && !s->blocked) cap_prepare_begin(p,(const short *)source,(int)frames,1,source);
 }
 unsigned epoch=s->epoch;
 if(source && !s->blocked) {
  if(p->phase==CAP_PREP_COUNT || p->phase==CAP_PREP_WRITE) {
   int before=p->index;cap_prepare_step(p,source,32);
   s->slices++;s->prepared_frames+=(unsigned)(p->index-before);
  } else if(p->phase==CAP_PREP_NEEDS_STORAGE) {
   unsigned n=(unsigned)p->needed;
   cap_prepare_storage(p,(float *)CAP_BANK_BASE,(int *)(CAP_BANK_BASE+4u*n),
                       (unsigned *)(CAP_BANK_BASE+8u*n),(int)n);
  }
 }
 h->generation=b->generation;s->published_epoch=epoch;
 h->ready=source && !s->blocked && s->epoch==epoch && p->phase==CAP_PREP_READY;
 volatile CapStatus *status=STATUS;
 unsigned seq=status->sequence,total=source ? 2u*(frames+4u) : 0,done=0;
 if(p->phase==CAP_PREP_COUNT) done=(unsigned)p->index;
 else if(p->phase==CAP_PREP_NEEDS_STORAGE) done=frames+4u;
 else if(p->phase==CAP_PREP_WRITE) done=frames+4u+(unsigned)p->index;
 else if(h->ready) done=total;
 if(done>total) done=total;
 status->sequence=seq|1u;status->magic=0x43505331u;status->version=1;
 status->slot=selected<16 ? (unsigned)word(0x2559bcu+selected*0x60u) : 1024u;
 status->state=!source ? 0 : s->blocked ? 4 : p->phase==CAP_PREP_FAILED ? 6 : h->ready ? 5 : 3;
 status->reason=p->phase==CAP_PREP_FAILED ? 8 : reason;
 status->done=done;status->total=total;status->epoch=s->epoch;
 status->source=source;status->frames=frames;status->sequence=(seq+2u)&~1u;
}
static int stretch_published(unsigned source,unsigned frames) {
 const CapBank *b=(const CapBank *)0x200e4100;
 return AUTO->magic==CAP_AUTO_MAGIC && !AUTO->blocked && HANDOFF->ready==1
  && AUTO->epoch==AUTO->published_epoch && AUTO->source==source
  && AUTO->frames==frames && HANDOFF->source==source
  && HANDOFF->generation==b->generation && !b->error && b->frames==(int)frames
  && b->count>=2 && b->count<=b->capacity && b->capacity<=CAP_CAPACITY
  && (unsigned)b->value==CAP_BANK_BASE
  && (unsigned)b->whole==CAP_BANK_BASE+4u*b->capacity
  && (unsigned)b->fraction==CAP_BANK_BASE+8u*b->capacity;
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
  cap_stretch_stop(&s->reader);s->backend=0;return 0;
 }
 unsigned source=*(volatile unsigned *)voice;
 unsigned frames=*(volatile unsigned *)(voice+0x188u);
 unsigned trigger=*(volatile unsigned char *)(0x24f0ccu+lane);
 unsigned selected,n;
 unsigned selection_error=stretch_selected(lane/2u,&selected,&n);
 float pitch=*(volatile float *)(voice+0x1ccu),advance=*(volatile float *)(voice+0x1c8u);
 if(trigger) {
  s->backend=0;cap_stretch_stop(&s->reader);
  int start=stretch_integer_position(voice,0x198u),end=stretch_integer_position(voice,0x1a0u);
  if(!selection_error && selected==source && n==frames && stretch_published(source,frames)
    && *(volatile unsigned *)(voice+0x184u)==48000u
    && cap_stretch_start(&s->reader,(const CapBank *)0x200e4100,start,end,
       *(volatile unsigned char *)(voice+0x1bbu),
       *(volatile unsigned char *)(voice+0x1bcu),pitch,advance,128)==CAP_OK) {
   s->source=source;s->epoch=AUTO->epoch;s->backend=1;
  }
 }
 if(!s->backend) return 0;
 if(selection_error || selected!=s->source || n!=frames
    || source!=s->source || s->epoch!=AUTO->epoch || !stretch_published(source,frames)
    || !*(volatile unsigned char *)(voice+0x1b8u)) cap_stretch_stop(&s->reader);
 else cap_stretch_update(&s->reader,pitch,advance);
 cap_stretch_process(&s->reader,destination,count);
 /* Prototype diagnostic tap at the actual renderer boundary. Native envelopes
  * and effects subsequently reuse/modify destination; retain these 32 words
  * so the runner never mistakes a post-effect buffer for the sparse reader. */
 float *trace=((float *)0x200e6000)+lane*32u;
 for(int i=0;i<count;i++) trace[i]=destination[i];
 s->renders++;s->last_destination=(unsigned)destination;
 return 1;
}
