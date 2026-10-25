// SPDX-License-Identifier: AGPL-3.0-only
// Independent diagnostic: original upstream header code; private fields exposed solely
// for observing splice duration. No source or algorithm edits.
#include <array>
#include <algorithm>
#include <cmath>
#include <vector>
#include <Analyzer.h>
#include <SparseLine.h>
#define private public
#include <Granule.h>
#undef private
extern "C" {
#include "stretch.h"
}
extern "C" int audit(const float *input,int frames,int start,int n,float pitch,float advance,
 float *up,float *port,float *up_event,float *port_event,float *stats) {
 auto sparse=new capicola::SparseLine<131072>(); sparse->Init();
 capicola::Analyzer<131072> analyzer;analyzer.Init(*sparse);
 for(int i=0;i<frames+4;i++) {
  if(i==frames+3)analyzer.ArmFinalFrame();
  analyzer.Analyze(i<frames ? input[i]:0);
 }
 auto grain=new capicola::Granule<131072>();grain->Init(*sparse,start);
 grain->SetPitch(pitch);grain->SetStretch(advance);grain->SetLeash(128);grain->SetFade(960);
 CapBank bank;cap_bank_init(&bank);int keys=cap_measure(input,frames);
 std::vector<float> values(keys);std::vector<int> whole(keys);std::vector<unsigned> fraction(keys);
 if(keys<2 || cap_bank_bind(&bank,values.data(),whole.data(),fraction.data(),keys)
  ||cap_load(&bank,input,frames))return -1;
 CapStretch r;
 if(cap_stretch_start(&r,&bank,0,frames,0,0,pitch,advance,128))return -2;
 r.core.ideal_w=r.core.actual_w=r.core.incoming_w=start;r.core.position=48;
 stats[0]=(float)keys;stats[1]=(float)analyzer.KeyframeCount();
 for(int i=0;i<n;i++) {
  if(i%32==0)grain->BeginBlock(32);
  bool ub=grain->IsSplicing();int pb=r.core.splicing;
  up[i]=grain->Read();port[i]=cap_stretch_tick(&r);
  up_event[i]=!ub && grain->IsSplicing() ? grain->adaptiveDuration:0;
  port_event[i]=!pb && r.core.splicing ? 1.0f/r.core.increment:0;
  if(!ub && grain->IsSplicing() && !grain->IsAdaptive())stats[2]++;
 }
 delete grain;delete sparse;return 0;
}
