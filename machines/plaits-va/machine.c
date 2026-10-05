// DTII 1.16 experimental wrapper; original Plaits engine lives in core.c.
// Emulator-only memory placement. 12-sample 48k engine FIFO -> 64-sample 96k source.
#include "core.c"
typedef struct {
 VA engine; Params params; float out[12],aux[12];
 int cursor,age,length,active; float gain;
} Lane;
#ifdef PLAITS_SHARE_LANES
#ifndef PLAITS_MAIN_ONLY
#error Lane sharing requires the main-only variant
#endif
// C union access preserves the exact object bits without float comparisons or
// aliasing unrelated int pointers. No padding: all Lane fields are 32-bit.
// Keep an explicit union tag: the pinned compiler misplaces members when the
// union is hidden behind a typedef. The paired target-state test guards this.
union LaneState { Lane lane; unsigned int words[96]; };
typedef char lane_size_check[sizeof(Lane)==384 ? 1 : -1];
typedef struct {
 unsigned int valid,hits,misses;
 union LaneState before,after;
 float output[64];
} RenderCache;
typedef char cache_size_check[sizeof(RenderCache)==1036 ? 1 : -1];
#endif
static int word(int address) { return *(volatile int *)address & 65535; }
int machine(int voice) {
 int lane;
 if(voice==0x2412cc) lane=0;
 else if(voice==0x2414a4) lane=1;
 else return 0;
#ifdef PLAITS_SHARE_LANES
 union LaneState *state=((union LaneState *)0x200e1000)+lane;
 Lane *s=&state->lane;
#else
 Lane *s=((Lane *)0x200e1000)+lane;
#endif
 float *destination=(float *)(voice+4);
 if(word(0x255970)!=7) { s->active=0; return 0; }
 int trigger=(*(volatile int *)0x24f0cc >> (lane*8)) & 255;
 if(trigger) {
   va_init(&s->engine); s->cursor=12; s->age=0; s->active=1;
   s->params.note=(float)(word(0x2558de)+word(0x2559b6))*(1.0f/256.0f)-55.0f;
   CONSTRAIN(s->params.note,0.0f,127.0f);
   // Borrowed B/D/E wire slots. Display labels and actual panel edits unverified.
   s->params.harmonics=(float)word(0x2559b8)*(1.0f/32768.0f);
   s->params.timbre=(float)word(0x2559bc)*(1.0f/32768.0f);
   s->params.morph=(float)word(0x2559be)*(1.0f/32768.0f);
   CONSTRAIN(s->params.harmonics,0.0f,1.0f);
   CONSTRAIN(s->params.timbre,0.0f,1.0f);
   CONSTRAIN(s->params.morph,0.0f,1.0f);
   s->length=(int)((float)word(0x2559c4)*(25.0f/32.0f));
   CONSTRAIN(s->length,960,48000);
   s->gain=(float)word(0x2559c8)*(1.0f/262144.0f);
   CONSTRAIN(s->gain,0.0f,0.125f);
 }
#ifdef PLAITS_SHARE_LANES
 // Every external input has now been latched. The remaining transition is a
 // pure function of Lane. A full-state key makes call order/epochs irrelevant.
 RenderCache *cache=(RenderCache *)0x200e2000;
 // Copying/checking a cached silent transition costs more than filling zeros.
 int cache_active=s->active;
 if(cache_active) {
 int match=cache->valid;
 for(int j=0;match && j<96;j++)
   if(state->words[j]!=cache->before.words[j]) match=0;
 if(match) {
   for(int j=0;j<96;j++) state->words[j]=cache->after.words[j];
   for(int j=0;j<64;j++) destination[j]=cache->output[j];
   cache->hits++;
   return 1;
 }
 cache->misses++;
 for(int j=0;j<96;j++) cache->before.words[j]=state->words[j];
 }
#endif
 for(int i=0;i<64;i+=2) {
   float value=0.0f;
   if(s->active) {
     if(s->age>=s->length) s->active=0;
     else {
       if(s->cursor>=12) { va_render(&s->engine,&s->params,s->out,s->aux,12); s->cursor=0; }
       float envelope=1.0f;
       if(s->age<480) envelope=(float)s->age*(1.0f/480.0f);
       if(s->length-s->age<480) envelope=(float)(s->length-s->age)*(1.0f/480.0f);
       value=s->out[s->cursor]*s->gain*envelope;
       s->cursor++; s->age+=2;
     }
   }
   destination[i]=value; destination[i+1]=value;
 }
#ifdef PLAITS_SHARE_LANES
 if(cache_active) {
 for(int j=0;j<96;j++) cache->after.words[j]=state->words[j];
 for(int j=0;j<64;j++) cache->output[j]=destination[j];
 cache->valid=1;
 }
#endif
 return 1;
}
