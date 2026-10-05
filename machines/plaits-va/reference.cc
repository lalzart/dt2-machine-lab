// Host comparison with the unmodified, pinned upstream VA_VARIANT 2 engine.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include "plaits/dsp/engine/virtual_analog_engine.h"
#include "core.h"

int main(int argc, char **argv) {
  if(argc!=2) return 2;
  FILE *reference=fopen((std::string(argv[1])+"/reference.f32").c_str(),"wb");
  FILE *candidate=fopen((std::string(argv[1])+"/candidate.f32").c_str(),"wb");
  if(!reference || !candidate) return 3;
  float memory[24]; stmlib::BufferAllocator allocator(memory,sizeof(memory));
  plaits::VirtualAnalogEngine original; original.Init(&allocator);
  VA port; va_init(&port);
  const Params timeline[]={{60,.5,.5,.5},{48,.2,.15,.8},{67,.8,.9,.2},{60,.5,.5,.5}};
  double max_error=0, sum=0; float peak=0; bool envelope=false;
  for(int block=0;block<16000;++block) {
    const Params &p=timeline[block/4000];
    plaits::EngineParameters q={0,p.note,p.timbre,p.morph,p.harmonics,.8f};
    float a[12],b[12],c[12],d[12];
    original.Render(q,a,b,12,&envelope); va_render(&port,&p,c,d,12);
    for(int i=0;i<12;++i) {
      float x[]={a[i],b[i]}, y[]={c[i],d[i]};
      fwrite(x,4,2,reference); fwrite(y,4,2,candidate);
      for(int ch=0;ch<2;++ch) {
        if(!std::isfinite(x[ch]) || !std::isfinite(y[ch])) return 4;
        double error=std::abs(double(x[ch])-y[ch]);
        max_error=std::max(max_error,error); sum+=error*error;
        peak=std::max(peak,std::abs(y[ch]));
      }
    }
  }
  fclose(reference); fclose(candidate);
  printf("{\"max_error\":%.12g,\"rms_error\":%.12g,\"peak\":%.9g,\"samples_per_channel\":192000,\"state_bytes\":%zu}\n",max_error,sqrt(sum/384000),peak,sizeof(VA));
  return max_error<=1e-5 && peak<4 ? 0:5;
}
