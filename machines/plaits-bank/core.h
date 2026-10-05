// Copyright 2016 Emilie Gillet.
//
// Author: Emilie Gillet (emilie.o.gillet@gmail.com)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// 
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// 
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
// 
// See http://creativecommons.org/licenses/MIT/ for more information.
//

#ifndef DT2_PLAITS_BANK_H
#define DT2_PLAITS_BANK_H
#include "../plaits-trio/core.h"
typedef struct {float phase_,next_sample_,lp_state_,hp_state_;int high_;float frequency_,pw_;} Slope;
typedef struct {Slope slope_;float previous_shape_,previous_wavefolder_gain_;} WS;
typedef struct {float phase_,frequency_,amplitude_[12];} Harmonic;
typedef struct {Harmonic harmonic_oscillator_[2];float amplitudes_[24];} Additive;
typedef struct {float carrier_phase_,formant_phase_,next_sample_,carrier_frequency_,formant_frequency_,carrier_shape_,carrier_bleed_;} Grainlet;
typedef struct {float g_,gi_,state_;} Pole;
typedef struct {Grainlet grainlet_[2];Pole dc_blocker_;float scratch_[12];} Grain;
union BankEngine {unsigned int words[64];Trio trio;WS ws;Additive add;Grain grain;};
typedef struct {union BankEngine engine;int model;} Bank;
typedef char bank_size_check[sizeof(Bank)==260 ? 1 : -1];
#ifdef __cplusplus
extern "C" {
#endif
int bank_size(void);
void bank_init(Bank *s,int model);
void bank_render(Bank *s,const Params *p,int trigger,float accent,float *out,int size);
#ifdef __cplusplus
}
#endif
#endif
