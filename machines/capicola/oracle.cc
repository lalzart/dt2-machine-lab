// SPDX-License-Identifier: AGPL-3.0-only
// Original Capicola headers plus the explicit finite-transport policy.
#include <Analyzer.h>
#include <SparseLine.h>
#include <cmath>
#include "core.h"

struct Oracle {
    capicola::SparseLine<CAP_CAPACITY> sparse;
    capicola::Analyzer<CAP_CAPACITY> analyzer;
    int frames=0, error=0, count=0, position=0, duration=0, leash=128;
    bool active=false, splicing=false;
    double ideal=0, actual=0, incoming=0;
    float pitch=1, advance=1, phase=0, increment=0;
    void init() { sparse.Init(); analyzer.Init(sparse); frames=count=error=position=duration=0;active=splicing=false; }
    float sample(double at) {
        if(at<0 || at>=frames) return 0;
        auto w=sparse.WindowAt(at);
        float t=(float)(w.endTime-at)*w.invDuration;
        return sparse.Read(w,t,capicola::InterpMode::CATMULLROM);
    }
    float tick() {
        if(!active) return 0;
        auto grid=sparse.WindowAt(ideal), head=sparse.WindowAt(actual);
        auto lead=std::abs(head.index-grid.index);
        if(!splicing && lead>leash) {
            incoming=ideal;
            float d;
            if(actual<ideal) d=(float)(sparse.GetSample(grid.index-1)->time-sparse.GetSample(grid.index-leash)->time);
            else d=(float)(sparse.GetSample(grid.index+leash-1)->time-sparse.GetSample(grid.index-1)->time);
            if(d>960) d=960; if(d<48) d=48;
            increment=1.0f/d;phase=0;splicing=true;
        }
        ideal+=advance;
        float y;
        if(splicing && phase<=1) {
            float in=sample(incoming),out=sample(actual),w=capicola::SmoothStep(phase);
            y=in*w+out*(1.0f-w);incoming+=pitch;actual+=pitch;phase+=increment*pitch;
        } else {
            if(splicing) { actual=incoming;phase=0;splicing=false; }
            y=sample(actual);actual+=pitch;
        }
        float edge=(float)position/48.0f, remaining=(float)(duration-1-position)/48.0f;
        if(edge>1) edge=1; if(remaining<edge) edge=remaining; if(edge<0) edge=0;
        if(++position>=duration) active=false;
        return y*edge;
    }
};
extern "C" {
void* oracle_new() { auto *o=new Oracle; o->init(); return o; }
void oracle_delete(Oracle *o) { delete o; }
int oracle_load(Oracle *o,const float *in,int frames) {
    o->init();
    if(!in || frames<1 || frames>CAP_MAX_INPUT) return o->error=CAP_INPUT_ERROR;
    for(int i=0;i<frames;i++) if(!(in[i]>=-1 && in[i]<=1)) return o->error=CAP_INPUT_ERROR;
    for(int i=0;i<frames+4;i++) {
        if(i==frames+3) o->analyzer.ArmFinalFrame();
        // Analyze can add at most one frame. Stop before any ring overwrite.
        if(o->analyzer.KeyframeCount()==CAP_CAPACITY) {o->init();return o->error=CAP_OVERFLOW;}
        o->analyzer.Analyze(i<frames ? in[i] : 0);
    }
    o->frames=frames; o->count=(int)o->analyzer.KeyframeCount();return 0;
}
int oracle_start(Oracle *o,float pitch,float advance,int leash) {
    o->active=false;
    if(o->error||o->count<2) return o->error ? o->error:CAP_INPUT_ERROR;
    if(!(pitch>=0.5f&&pitch<=2&&advance>=0.5f&&advance<=2)||leash<16||leash>128) return CAP_CONTROL_ERROR;
    o->pitch=pitch;o->advance=advance;o->leash=leash;
    o->ideal=o->actual=o->incoming=0;o->phase=o->increment=0;o->splicing=false;o->position=0;
    o->duration=(int)std::ceil((double)o->frames/(double)advance);o->active=true;return 0;
}
void oracle_stop(Oracle *o) {o->active=false;}
void oracle_process(Oracle *o,float *out,int frames) {for(int n=0;n<frames;n++)out[n]=o->tick();}
int oracle_count(Oracle *o) {return o->count;}
float oracle_value(Oracle *o,int i) {return o->sparse.GetSample(i)->value;}
double oracle_time(Oracle *o,int i) {return o->sparse.GetSample(i)->time;}
int oracle_position(Oracle *o) {return o->position;}
}
