/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 informational reply; audio publication remains in the selection ABI. */
static void cap_feedback(void);
#define CAP_STATUS_PUBLISHED() cap_feedback()
#include "../plaits-capicola-selection/machine.c"

static void cap_feedback(void) {
 unsigned state=STATUS->state,percent=0;
 if(state==3u && STATUS->total) {
  /* Maximum product is115200800. Bounded seven-comparison integer floor;
   * no integer-division runtime helper or floating-point rounding. */
  unsigned lo=0,hi=101,scaled=STATUS->done*100u,total=STATUS->total;
  while(lo+1u<hi) {
   unsigned mid=(lo+hi)>>1;
   if(scaled>=mid*total) lo=mid;
   else hi=mid;
  }
  percent=lo;
 } else if(state==5u) percent=100;
 unsigned value=state ? 0xd400u|(state<<7)|percent : 0;
 unsigned shift=(*(volatile unsigned *)0x261ca4u)&1u;
 *(volatile unsigned short *)(0x26623au+(shift<<12))=(unsigned short)value;
}
