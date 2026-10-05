// Copyright 2014-2021 Emilie Gillet.
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

#ifndef DT2_PLAITS_TRIO_H
#define DT2_PLAITS_TRIO_H
#include "../plaits-va/core.h"
#define TRIGGER_RISING_EDGE 1
#define TRIGGER_UNPATCHED 2
typedef struct {unsigned int carrier_phase_,modulator_phase_,sub_phase_;float previous_carrier_frequency_,previous_modulator_frequency_,previous_amount_,previous_feedback_,previous_sample_,sub_fir_,carrier_fir_;} FM;
typedef struct {float g_,r_,h_,state_1_,state_2_;} Svf;
typedef struct {float phase_,frequency_,amplitude_;} SineState;
typedef struct {int pulse_remaining_samples_,fm_pulse_remaining_samples_;float pulse_,pulse_height_,pulse_lp_,fm_pulse_lp_,retrig_pulse_,lp_out_,tone_lp_,sustain_gain_;Svf resonator_;SineState oscillator_;} AnalogBD;
typedef struct {float pre_gain_,post_gain_;} Drive;
typedef struct {AnalogBD analog_;Drive drive_;} BD;
union TrioEngine {unsigned int words[63];VA va;FM fm;BD bd;};
typedef struct {union TrioEngine engine;int model;} Trio;
typedef char trio_size_check[sizeof(Trio)==256 ? 1 : -1];
#ifdef __cplusplus
extern "C" {
#endif
int trio_size(void);
void trio_init(Trio *s,int model);
void trio_render(Trio *s,const Params *p,int trigger,float accent,float *out,int size);
#ifdef __cplusplus
}
#endif
#endif
