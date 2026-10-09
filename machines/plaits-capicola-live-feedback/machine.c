/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 slot-correlated informational status. HANDOFF owns readiness. */
static void cap_feedback(void);
#define CAP_STATUS_PUBLISHED() cap_feedback()
#include "../plaits-capicola-selection/machine.c"

static void cap_feedback(void) {
 /* Keep the wire index independent of the enclosing maintenance state when
  * the pinned compiler inlines this function. Do not initialize aliases in
  * the same declaration; that form emitted an uninitialized stack read. */
 unsigned cap_reply_index=STATUS->state;
 if(cap_reply_index==3u && STATUS->total) {
  unsigned scaled=STATUS->done*4u,total=STATUS->total;
  cap_reply_index=scaled<total ? 3u : scaled<total*2u ? 7u : scaled<total*3u ? 8u : 9u;
 }
 unsigned cap_reply_slot=STATUS->slot;
 unsigned value=STATUS->state && cap_reply_slot<1024u ? 0x8000u|(cap_reply_slot<<4)|cap_reply_index : 0;
 unsigned shift=(*(volatile unsigned *)0x261ca4u)&1u;
 *(volatile unsigned short *)(0x26623au+(shift<<12))=(unsigned short)value;
}
