/* Combined emulator adapter. Original Plaits source remains unchanged. */
#define machine plaits_machine
#include "../plaits-integration/machine.c"
#undef machine
#define CAP_TARGET 1
#include "../capicola/capacity.c"

#ifndef CAP_BANK_BASE
#define CAP_BANK_BASE 0x83000000u
#endif

#ifndef CAP_UPDATE_CONTROLS
#define CAP_UPDATE_CONTROLS() ((void)0)
#endif

#ifndef CAP_LIFETIME_VALID
#define CAP_LIFETIME_VALID() 1
#endif

typedef struct {
 unsigned magic, version, ready, source;
 float pitch, advance, gain;
 int leash;
 unsigned generation;
} CapHandoff;
typedef struct { CapState reader; float gain; unsigned source; } CapLane;

static int cap_valid(const CapHandoff *h,const CapBank *b,unsigned source) {
 if(!CAP_LIFETIME_VALID()) return 0;
 if(h->magic!=0x43415031u || h->version!=1 || h->ready!=1) return 0;
 if(!source || source!=h->source || !h->generation || h->generation!=b->generation) return 0;
 if(b->error || b->frames<1 || b->frames>CAP_MAX_INPUT || b->capacity<2 || b->capacity>CAP_CAPACITY) return 0;
 if(b->count<2 || b->count>b->capacity || b->count>b->frames+4) return 0;
 if((unsigned)b->value!=CAP_BANK_BASE || (unsigned)b->whole!=CAP_BANK_BASE+4u*b->capacity
    || (unsigned)b->fraction!=CAP_BANK_BASE+8u*b->capacity) return 0;
 return h->pitch>=0.5f && h->pitch<=2.0f && h->advance>=0.5f && h->advance<=2.0f
    && h->gain>=0.0f && h->gain<=0.125f && h->leash>=16 && h->leash<=128;
}

int machine(int voice) {
 int lane;
 if(voice==0x2412cc) lane=0;
 else if(voice==0x2414a4) lane=1;
 else return 0;
 CapLane *s=((CapLane *)0x200e4200)+lane;
 /* Also clears Plaits' active flag when entering Capicola or stock. */
 int plaits=plaits_machine(voice);
 if(plaits || word(0x255970)!=8) {cap_stop(&s->reader);return plaits;}
 CAP_UPDATE_CONTROLS();
 const CapHandoff *h=(const CapHandoff *)0x200e4000;
 const CapBank *b=(const CapBank *)0x200e4100;
 unsigned source=*(volatile unsigned *)voice;
 int valid=cap_valid(h,b,source);
 int trigger=(*(volatile int *)0x24f0cc>>(lane*8))&255;
 if(!valid) {cap_init(&s->reader);s->gain=0.0f;s->source=0;}
 else if(trigger) {
  cap_attach(&s->reader,b);
  cap_start(&s->reader,h->pitch,h->advance,h->leash);
  s->gain=h->gain;s->source=source;
 } else if(source!=s->source) cap_stop(&s->reader);
 float *destination=(float *)(voice+4);
 for(int i=0;i<64;i+=2) {
  float value=cap_tick(&s->reader)*s->gain;
  destination[i]=value;destination[i+1]=value;
 }
 return 1;
}
