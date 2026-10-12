/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16: resolve the selected sample before the stock voice-trigger path. */
static unsigned cap_selected(unsigned *source,unsigned *frames);
static int cap_selection_valid(void);
#define CAP_SELECTION_VALID() cap_selection_valid()
#define CAP_READ_SOURCE(source,frames,other) \
 cap_selected(&(source),&(frames)); other=source
#define cap_maintenance cap_selection_maintenance_inner
#include "../plaits-capicola-controls/machine.c"
#undef cap_maintenance

#ifndef CAP_STATUS_PUBLISHED
#define CAP_STATUS_PUBLISHED()
#endif

#define CAP_SLOT_DM 0x2559bcu
#define CAP_SLOT_TABLE 0x257810u
/* Native status ABI v1: sequence is odd during a write. Status describes the
 * last completed maintenance block; HANDOFF/epoch remain playback authority. */
typedef struct {
 unsigned sequence,magic,version,slot,state,reason,done,total,epoch,source,frames;
} CapStatus;
#define STATUS ((volatile CapStatus *)0x200e4600)
#define CAP_STATUS_MAGIC 0x43505331u
/* State: off0 empty1 unsupported2 preparing3 waiting4 ready5 failed6.
 * Reason: none0 empty1 slot2 stereo3 rate4 long5 short6 bounds7 worker8. */
static unsigned cap_selected(unsigned *source,unsigned *frames) {
 *source=0;*frames=0;
 unsigned slot=(unsigned)word(CAP_SLOT_DM);
 if(slot>=1024u) return 2;
 volatile unsigned *entry=(volatile unsigned *)(CAP_SLOT_TABLE+slot*20u);
 unsigned left=entry[0],right=entry[1],bytes=entry[2],rate=entry[3],stereo=entry[4]&255u;
 if(!bytes) return 1;
 if(left!=right || stereo) return 3;
 if(rate!=48000u) return 4;
 if(bytes>CAP_MAX_INPUT*2u) return 5;
 if(bytes<282u) return 6;
 if((left&1u) || (bytes&1u) || left>=CAP_POOL_END-CAP_POOL_BASE
    || bytes>CAP_POOL_END-CAP_POOL_BASE-left) return 7;
 *source=CAP_POOL_BASE+left;*frames=bytes/2u;
 return 0;
}
static int cap_selection_valid(void) {
 unsigned source,frames;
 return !cap_selected(&source,&frames) && source==AUTO->source && frames==AUTO->frames;
}
void cap_maintenance(void) {
 cap_selection_maintenance_inner();
 cap_panel_controls();
 volatile CapStatus *status=STATUS;
 CapPrepare *p=(CapPrepare *)0x200e4400;
 unsigned source,frames,reason=cap_selected(&source,&frames);
 unsigned state,done=0,total=0;
 if(word(0x255970)!=8) state=0;
 else if(reason) state=reason==1 ? 1 : 2;
 else if(AUTO->blocked) state=4;
 else if(p->phase==CAP_PREP_FAILED) {state=6;reason=8;}
 else {
  state=HANDOFF->ready && AUTO->epoch==AUTO->published_epoch ? 5 : 3;
  total=2u*(frames+4u);
  if(p->phase==CAP_PREP_COUNT) done=(unsigned)p->index;
  else if(p->phase==CAP_PREP_NEEDS_STORAGE) done=frames+4u;
  else if(p->phase==CAP_PREP_WRITE) done=frames+4u+(unsigned)p->index;
  else if(state==5) done=total;
  if(done>total) done=total;
 }
 unsigned seq=status->sequence;
 status->sequence=seq|1u;
 status->magic=CAP_STATUS_MAGIC;status->version=1;
 status->slot=(unsigned)word(CAP_SLOT_DM);status->state=state;status->reason=reason;
 status->done=done;status->total=total;status->epoch=AUTO->epoch;
 status->source=source;status->frames=frames;
 status->sequence=(seq+2u)&~1u;
 CAP_STATUS_PUBLISHED();
}
