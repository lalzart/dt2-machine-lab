// Copyright 2014-2017 Emilie Gillet.
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

#ifndef DT2_PLAITS_VA_H
#define DT2_PLAITS_VA_H
typedef struct {
 float master_phase_,slave_phase_,next_sample_,previous_pw_; int high_;
 float master_frequency_,slave_frequency_,pw_,waveshape_,phase_modulation_;
} Shape;
typedef struct {
 float phase_,next_sample_,previous_pw_; int high_;
 float frequency_,pw_,waveshape_;
} Saw;
typedef struct {
 Shape primary_,auxiliary_,sync_; Saw variable_saw_;
 float auxiliary_amount_,xmod_amount_,temp_buffer_[24];
} VA;
typedef struct { float note,harmonics,timbre,morph; } Params;
#ifdef __cplusplus
extern "C" {
#endif
void va_init(VA *s);
void va_render(VA *s,const Params *p,float *out,float *aux,int size);
#ifdef __cplusplus
}
#endif
#endif
