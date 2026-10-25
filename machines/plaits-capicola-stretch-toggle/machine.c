/* SPDX-License-Identifier: AGPL-3.0-only
 * Optional comparison layer; the R3 engines and storage are unchanged. */
#define cap_stretch_machine cap_toggle_base_machine
#define cap_maintenance cap_toggle_base_maintenance
#include "../plaits-capicola-stretch-live/machine.c"
#undef cap_stretch_machine
#undef cap_maintenance

static int cap_toggle_requested(unsigned track) {
 unsigned raw=word(0x2559bau+track*0x60u);
 return raw>=128u && raw<=256u;
}
int cap_stretch_machine(unsigned voice,float *destination,int count) {
 if(voice>=0x2412ccu && voice<0x2412ccu+32u*0x1d8u
    && !((voice-0x2412ccu)%0x1d8u) && count==32) {
  unsigned lane=(voice-0x2412ccu)/0x1d8u;
  if(word(0x255970u+(lane/2u)*2u)==2
     && *(volatile unsigned char *)(0x24f0ccu+lane)
     && !cap_toggle_requested(lane/2u)) {
   cap_live_stop(&LANES[lane].reader);LANES[lane].backend=0;return 0;
  }
 }
 return cap_toggle_base_machine(voice,destination,count);
}
void cap_maintenance(void) {
 cap_toggle_base_maintenance();
 unsigned track=AUTO->slices&15u,cap=0,stock=0,state=0;
 if(word(0x255970u+track*2u)==2) {
  for(unsigned lane=track*2u;lane<track*2u+2u;lane++) {
   if(*(volatile unsigned char *)(0x2412ccu+lane*0x1d8u+0x1b8u)) {
    if(LANES[lane].backend) cap=1;else stock=1;
   }
  }
  unsigned source,frames,error=stretch_selected(track,&source,&frames);
  state=cap && stock ? 5u : cap ? 3u : stock ? 4u : error ? 6u
       : stretch_published(source,frames)>=0 ? 2u : 1u;
 }
 unsigned shift=(*(volatile unsigned *)0x261ca4u)&1u;
 *(volatile unsigned short *)(0x26623au+(shift<<12))=
  (unsigned short)(0xd000u|(track<<8)|state);
}
