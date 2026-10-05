// Six-model prepared DTII 1.16 source adapter; independent track-1 lanes.
#include "core.c"
#include "controls.h"
typedef struct {
 Bank engine; Params params; float out[12];
 int cursor,age,length,active; float gain; int pending_trigger; float accent;
} BankLane;
typedef char lane_size_check[sizeof(BankLane)==352 ? 1 : -1];
static int word(int address) {return *(volatile int *)address & 65535;}
int machine(int voice) {
 int lane;
 if(voice==0x2412cc) lane=0;
 else if(voice==0x2414a4) lane=1;
 else return 0;
 BankLane *s=((BankLane *)0x200e1000)+lane;
 float *destination=(float *)(voice+4);
 if(word(0x255970)!=7) {s->active=0;return 0;}
 int trigger=(*(volatile int *)0x24f0cc>>(lane*8))&255;
 if(trigger) {
  int model=(word(BANK_MODEL_DM)+128)/256;
  CONSTRAIN(model,0,BANK_MAX_MODEL); bank_init(&s->engine,model);
  s->params.note=(float)(word(BANK_NOTE_DM)+word(BANK_TUNE_DM))*(1.0f/256.0f)-55.0f;
  CONSTRAIN(s->params.note,0.0f,127.0f);
  s->params.harmonics=(float)word(BANK_HARMONICS_DM)*BANK_HARMONICS_FACTOR;
  s->params.timbre=(float)word(BANK_TIMBRE_DM)*BANK_TIMBRE_FACTOR;
  s->params.morph=(float)word(BANK_MORPH_DM)*BANK_MORPH_FACTOR;
  CONSTRAIN(s->params.harmonics,0.0f,1.0f);
  CONSTRAIN(s->params.timbre,0.0f,1.0f);
  CONSTRAIN(s->params.morph,0.0f,1.0f);
  s->length=(int)((float)word(BANK_LENGTH_DM)*(25.0f/32.0f));
  CONSTRAIN(s->length,960,48000);
  s->gain=(float)word(BANK_LEVEL_DM)*BANK_LEVEL_FACTOR;
  CONSTRAIN(s->gain,0.0f,0.125f);
  s->accent=0.8f;s->cursor=12;s->age=0;s->active=1;s->pending_trigger=1;
 }
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
