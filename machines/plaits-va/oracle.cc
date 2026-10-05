// Thin host-only C interface to untouched upstream C++ source.
#include "plaits/dsp/engine/virtual_analog_engine.h"
static float scratch[24];
static plaits::VirtualAnalogEngine engine;
extern "C" void oracle_init() {
  stmlib::BufferAllocator allocator(scratch,sizeof(scratch));
  engine.Init(&allocator);
}
extern "C" void oracle_render(const float *p,float *out,float *aux) {
  plaits::EngineParameters q={0,p[0],p[2],p[3],p[1],.8f};
  bool enveloped=false;
  engine.Render(q,out,aux,12,&enveloped);
}
