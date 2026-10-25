// SPDX-License-Identifier: AGPL-3.0-only
// Actual original Analyzer/SparseLine/Granule; immutable sample-host fixture only.
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>
#include <Analyzer.h>
#include <SparseLine.h>
#define private public
#include <Granule.h>
#include <KeyframeRecorder.h>
#undef private
extern "C" {
#include "stretch.h"
#include "live.h"
int cap_live_retrigger(CapLive *,const CapBank *,int,int,int,int,float,float,int);
}

extern "C" int source_pair_audit(const float *input,int frames,int n,float *original,float *port) {
 constexpr int capacity=2097152;
 auto line=new capicola::SparseLine<capacity>();line->Init();
 capicola::Analyzer<capacity> analyzer;analyzer.Init(*line);
 for(int i=0;i<frames+4;i++) {
  if(i==frames+3)analyzer.ArmFinalFrame();
  analyzer.Analyze(i<frames?input[i]:0);
 }
 auto recorder=new capicola::KeyframeRecorder<capacity>();recorder->Init();
 recorder->SetGrainFade(960);recorder->SetGrainStretch(0.425f);
 auto w=line->WindowAt(0);
 float origin=line->Read(w,(float)w.endTime*w.invDuration,capicola::InterpMode::CATMULLROM);
 for(int cycle=0;cycle<32;cycle++) {
  recorder->sparse.Write({origin,(double)cycle*frames});
  for(int k=0;k<analyzer.KeyframeCount();k++) {
   auto key=line->GetSample(k);
   if(key->time>0 && key->time<=frames-1)
    recorder->sparse.Write({key->value,key->time+(double)cycle*frames});
  }
 }
 recorder->ResetReader();
 for(auto &g:recorder->granule)g.Spawn((double)8*frames);
 CapBank bank;cap_bank_init(&bank);int keys=cap_measure(input,frames);
 std::vector<float> values(keys);std::vector<int> whole(keys);std::vector<unsigned> fraction(keys);
 if(cap_bank_bind(&bank,values.data(),whole.data(),fraction.data(),keys)||cap_load(&bank,input,frames))return -1;
 CapLive state;cap_live_start(&state,&bank,0,frames,0,1,1,0.425f,128);
 for(int i=0;i<n;i++) {
  if(i%32==0)for(auto &g:recorder->granule)g.BeginBlock(32);
  if(i==512) {
   recorder->curPitch=2;recorder->Punch();
   recorder->granule[recorder->liveG].Spawn((double)8*frames);
   cap_live_retrigger(&state,&bank,0,frames,0,1,2,0.425f,128);
  }
  original[i]=recorder->ReadPair();cap_live_process(&state,port+i,1);
 }
 delete recorder;delete line;return 0;
}
extern "C" int source_audit(const float *input,int frames,int start,int end,
 int reverse,int loop,float pitch,float advance,int n,float *original,float *port,
 float *events,float *stats) {
 constexpr int capacity=2097152;
 auto analyzed=new capicola::SparseLine<capacity>();analyzed->Init();
 capicola::Analyzer<capacity> analyzer;analyzer.Init(*analyzed);
 for(int i=0;i<frames+4;i++) {
  if(i==frames+3)analyzer.ArmFinalFrame();
  analyzer.Analyze(i<frames?input[i]:0);
 }
 CapBank bank;cap_bank_init(&bank);int count=cap_measure(input,frames);
 std::vector<float> value(count);std::vector<int> whole(count);
 std::vector<unsigned> fraction(count);
 if(cap_bank_bind(&bank,value.data(),whole.data(),fraction.data(),count)
    ||cap_load(&bank,input,frames)) {delete analyzed;return -1;}
 stats[0]=(float)count;stats[1]=(float)analyzer.KeyframeCount();
 for(int i=0;i<count && i<analyzer.KeyframeCount();i++) {
  auto k=analyzed->GetSample(i);
  stats[3]=std::max(stats[3],std::abs(k->value-value[i]));
  stats[4]=std::max(stats[4],(float)std::abs(k->time-(whole[i]+fraction[i]/16777216.0)));
 }
 double origin=reverse?end-1:start;
 auto window=analyzed->WindowAt(origin);
 float initial=analyzed->Read(window,(float)(window.endTime-origin)*window.invDuration,
   capicola::InterpMode::CATMULLROM);
 std::vector<capicola::Keyframe> period;
 period.push_back({initial,0.0});
 for(int i=0;i<analyzer.KeyframeCount();i++) {
  auto k=analyzed->GetSample(i);
  if(k->time<start || k->time>end-1)continue;
  double t=reverse?end-1-k->time:k->time-start;
  if(t>0 && t<end-start)period.push_back({k->value,t});
 }
 std::sort(period.begin(),period.end(),[](auto a,auto b){return a.time<b.time;});
 const int length=end-start;
 const int prefix=512/(int)period.size()+2;
 const int suffix=prefix;
 const int travel=(int)std::ceil(n*std::max(pitch,advance)/length)+2;
 const int cycles=prefix+travel+suffix;
 if((size_t)cycles*period.size()>=capacity*7/8) {delete analyzed;return -2;}
 auto medium=new capicola::SparseLine<capacity>();medium->Init();
 for(int cycle=0;cycle<cycles;cycle++)for(auto k:period)
   medium->Write({k.value,k.time+(double)cycle*length});
 capicola::Granule<capacity> grain;grain.Init(*medium,(double)prefix*length);
 grain.SetPitch(pitch);grain.SetStretch(advance);grain.SetLeash(128);grain.SetFade(960);
 CapStretch state;
 if(cap_stretch_start(&state,&bank,start,end,reverse,loop,pitch,advance,128)) {
  delete medium;delete analyzed;return -3;
 }
 int duration=state.core.duration;
 stats[5]=(float)period.size();stats[6]=(float)duration;
 for(int i=0;i<n;i++) {
  if(i%32==0)grain.BeginBlock(32);
  bool before=grain.IsSplicing();
  original[i]=(loop || i<duration)?grain.Read():0.0f;
  port[i]=cap_stretch_tick(&state);
  if(!before && grain.IsSplicing()) {
   events[i]=grain.IsAdaptive()?grain.adaptiveDuration:-grain.fixedDuration;
   if(!grain.IsAdaptive())stats[2]++;
  }
 }
 delete medium;delete analyzed;return 0;
}
