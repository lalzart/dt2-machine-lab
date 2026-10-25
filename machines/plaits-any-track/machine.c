// Track-indexed wrapper; engine math and MIT source notices remain in the included core.
// Dedicated macro controls; existing six-model cores and lane layout.
#include "../plaits-bank/core.c"
#include "../plaits-controls/controls.h"
typedef struct {
 Bank engine; Params params; float out[12];
 int cursor,age,length,active; float gain; int pending_trigger; float accent;
} BankLane;
typedef char lane_size_check[sizeof(BankLane)==352 ? 1 : -1];
static int word(int address) {return *(volatile int *)address & 65535;}
int machine(int voice) {
 unsigned v=(unsigned)voice;
 if(v<0x2412ccu || v>=0x2412ccu+32u*0x1d8u || (v-0x2412ccu)%0x1d8u) return 0;
 int lane=(v-0x2412ccu)/0x1d8u;
 int track=lane/2;
 int controls=track*0x60;
 BankLane *s=((BankLane *)0x200e1000)+lane;
 float *destination=(float *)(voice+4);
 if(word(0x255970+track*2)!=7) {s->active=0;return 0;}
 int trigger=*(volatile unsigned char *)(0x24f0cc+lane);
 if(trigger) {
  int model=(word(BANK_MODEL_DM+controls)+128)/256;
  CONSTRAIN(model,0,BANK_MAX_MODEL); bank_init(&s->engine,model);
  s->params.note=(float)(word(BANK_NOTE_DM+track*2)+word(BANK_TUNE_DM+controls))*(1.0f/256.0f)-55.0f;
  CONSTRAIN(s->params.note,0.0f,127.0f);
  s->length=((word(BANK_LENGTH_DM+controls)>>8)+1)*9600;
  CONSTRAIN(s->length,9600,1228800);
  s->gain=(float)word(BANK_LEVEL_DM+controls)*BANK_LEVEL_FACTOR;
  CONSTRAIN(s->gain,0.0f,0.125f);
  s->accent=0.8f;s->cursor=12;s->age=0;s->active=1;s->pending_trigger=1;
 }
 // Continuous macros update at each voice call, without reinitializing state.
  s->params.harmonics=(float)word(BANK_HARMONICS_DM+controls)*BANK_HARMONICS_FACTOR;
  s->params.timbre=(float)word(BANK_TIMBRE_DM+controls)*BANK_TIMBRE_FACTOR;
  s->params.morph=(float)word(BANK_MORPH_DM+controls)*BANK_MORPH_FACTOR;
  CONSTRAIN(s->params.harmonics,0.0f,1.0f);
  CONSTRAIN(s->params.timbre,0.0f,1.0f);
  CONSTRAIN(s->params.morph,0.0f,1.0f);
 for(int i=0;i<64;i+=2) {
  float value=0.0f;
  if(s->active) {
   if(s->age>=s->length) s->active=0;
   else {
    if(s->cursor>=12) {
     bank_render(&s->engine,&s->params,s->pending_trigger,s->accent,s->out,12);
     s->pending_trigger=0;s->cursor=0;
    }
    float envelope=1.0f;
    if(s->engine.model!=2 && s->age<480) envelope=(float)s->age*(1.0f/480.0f);
    if(s->length-s->age<480) envelope=(float)(s->length-s->age)*(1.0f/480.0f);
    value=s->out[s->cursor]*s->gain*envelope;s->cursor++;s->age+=2;
   }
  }
  destination[i]=value;destination[i+1]=value;
 }
 return 1;
}
