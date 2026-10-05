// Host-only C interface to the complete, untouched upstream engines.
#include <new>
#include <cstring>
#include "plaits/dsp/engine/virtual_analog_engine.h"
#include "plaits/dsp/engine/fm_engine.h"
#include "plaits/dsp/engine/bass_drum_engine.h"
static float scratch[24];
static plaits::VirtualAnalogEngine va;
static plaits::FMEngine fm;
static plaits::BassDrumEngine bd;
static plaits::Engine *current;
extern "C" void oracle_init(int model) {
  // Recreate a zero-initialized voice, including FIR state not reset by Init.
  if(model==0) { std::memset((void *)&va,0,sizeof(va)); new (&va) plaits::VirtualAnalogEngine(); current=&va; }
  else if(model==1) { std::memset((void *)&fm,0,sizeof(fm)); new (&fm) plaits::FMEngine(); current=&fm; }
  else { std::memset((void *)&bd,0,sizeof(bd)); new (&bd) plaits::BassDrumEngine(); current=&bd; }
  stmlib::BufferAllocator allocator(scratch,sizeof(scratch));
  current->Init(&allocator);
}
extern "C" void oracle_render(const float *p,int trigger,float accent,float *out) {
  plaits::EngineParameters q={trigger,p[0],p[2],p[3],p[1],accent};
  float aux[12]; bool enveloped=false;
  current->Render(q,out,aux,12,&enveloped);
}
