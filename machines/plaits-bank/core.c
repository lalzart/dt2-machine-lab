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

// Generated from pinned source; see source-lock.json and translate.py.
#include "../plaits-trio/core.c"
#include "core.h"
#include "tables.h"
static float subsample(Interp *p,float t) { return p->value+p->increment*t; }

static float InterpolateHermite(const float *table,float index,float size) {
  index *= size;
  MAKE_INTEGRAL_FRACTIONAL(index)
  const float xm1 = table[index_integral - 1];
  const float x0 = table[index_integral + 0];
  const float x1 = table[index_integral + 1];
  const float x2 = table[index_integral + 2];
  const float c = (x1 - xm1) * 0.5f;
  const float v = x0 - x1;
  const float w = c + v;
  const float a = w + v + (x2 - x0) * 0.5f;
  const float b_neg = w + a;
  const float f = index_fractional;
  return (((a * f) - b_neg) * f + c) * f + x0;

}

static float InterpolateWrap(const float *table,float index,float size) {
  index -= (float)((int)(index));
  index *= size;
  MAKE_INTEGRAL_FRACTIONAL(index)
  float a = table[index_integral];
  float b = table[index_integral + 1];
  return a + (b - a) * index_fractional;

}

static float Sine(float phase) { return InterpolateWrap(lut_sine,phase,512.0f); }

static void slope_init(Slope *s) {
    s->phase_ = 0.5f;
    s->next_sample_ = 0.0f;
    s->lp_state_ = 1.0f;
    s->hp_state_ = 0.0f;
    s->high_ = 1;

    s->frequency_ = 0.001f;
    s->pw_ = 0.5f;
  
}

static void slope_render(Slope *s,float frequency,float pw,float *out,int size) { const int shape=3,has_external_fm=0,through_zero_fm=0; const float *external_fm=(const float *)0; const float kMinFrequency=0.000001f;
    
    if (!has_external_fm) {
      if (!through_zero_fm) {
        CONSTRAIN(frequency, kMinFrequency, kMaxFrequency);
      } else {
        CONSTRAIN(frequency, -kMaxFrequency, kMaxFrequency);
      }
      CONSTRAIN(pw, absf(frequency) * 2.0f, 1.0f - 2.0f * absf(frequency))
    }
    
    Interp fm=interp(&s->frequency_, frequency, size);
    Interp pwm=interp(&s->pw_, pw, size);
  
    float next_sample = s->next_sample_;
  
    while (size--) {
      float this_sample = next_sample;
      next_sample = 0.0f;

      float frequency = next(&fm);
      if (has_external_fm) {
        frequency *= (1.0f + *external_fm++);
        if (!through_zero_fm) {
          CONSTRAIN(frequency, kMinFrequency, kMaxFrequency);
        } else {
          CONSTRAIN(frequency, -kMaxFrequency, kMaxFrequency);
        }
      }
      float pw = (shape == 7 ||
                  shape == 2) ? 0.5f : next(&pwm);
      if (has_external_fm) {
        CONSTRAIN(pw, absf(frequency) * 2.0f, 1.0f - 2.0f * absf(frequency))
      }
      s->phase_ += frequency;
      
      if (shape <= 1) {
        if (s->phase_ >= 1.0f) {
          s->phase_ -= 1.0f;
          float t = s->phase_ / frequency;
          this_sample -= ThisBlepSample(t);
          next_sample -= NextBlepSample(t);
        } else if (through_zero_fm && s->phase_ < 0.0f) {
          float t = s->phase_ / frequency;
          s->phase_ += 1.0f;
          this_sample += ThisBlepSample(t);
          next_sample += NextBlepSample(t);
        }
        next_sample += s->phase_;

        if (shape == 1) {
          *out++ = 2.0f * this_sample - 1.0f;
        } else {
          s->lp_state_ += 0.25f * ((s->hp_state_ - this_sample) - s->lp_state_);
          *out++ = 4.0f * s->lp_state_;
          s->hp_state_ = this_sample;
        }
      } else if (shape <= 3) {
        float slope_up = 2.0f;
        float slope_down = 2.0f;
        if (shape == 3) {
          slope_up = 1.0f / (pw);
          slope_down = 1.0f / (1.0f - pw);
        }
        if (s->high_ ^ (s->phase_ < pw)) {
          float t = (s->phase_ - pw) / frequency;
          float discontinuity = (slope_up + slope_down) * frequency;
          if (through_zero_fm && frequency < 0.0f) {
            discontinuity = -discontinuity;
          }
          this_sample -= ThisIntegratedBlepSample(t) * discontinuity;
          next_sample -= NextIntegratedBlepSample(t) * discontinuity;
          s->high_ = s->phase_ < pw;
        }
        if (s->phase_ >= 1.0f) {
          s->phase_ -= 1.0f;
          float t = s->phase_ / frequency;
          float discontinuity = (slope_up + slope_down) * frequency;
          this_sample += ThisIntegratedBlepSample(t) * discontinuity;
          next_sample += NextIntegratedBlepSample(t) * discontinuity;
          s->high_ = 1;
        } else if (through_zero_fm && s->phase_ < 0.0f) {
          float t = s->phase_ / frequency;
          s->phase_ += 1.0f;
          float discontinuity = (slope_up + slope_down) * frequency;
          this_sample -= ThisIntegratedBlepSample(t) * discontinuity;
          next_sample -= NextIntegratedBlepSample(t) * discontinuity;
          s->high_ = 0;
        }
        next_sample += s->high_
          ? s->phase_ * slope_up
          : 1.0f - (s->phase_ - pw) * slope_down;
        *out++ = 2.0f * this_sample - 1.0f;
      } else {
        if (s->high_ ^ (s->phase_ >= pw)) {
          float t = (s->phase_ - pw) / frequency;
          float discontinuity = 1.0f;
          if (through_zero_fm && frequency < 0.0f) {
            discontinuity = -discontinuity;
          }
          this_sample += ThisBlepSample(t) * discontinuity;
          next_sample += NextBlepSample(t) * discontinuity;
          s->high_ = s->phase_ >= pw;
        }
        if (s->phase_ >= 1.0f) {
          s->phase_ -= 1.0f;
          float t = s->phase_ / frequency;
          this_sample -= ThisBlepSample(t);
          next_sample -= NextBlepSample(t);
          s->high_ = 0;
        } else if (through_zero_fm && s->phase_ < 0.0f) {
          float t = s->phase_ / frequency;
          s->phase_ += 1.0f;
          this_sample += ThisBlepSample(t);
          next_sample += NextBlepSample(t);
          s->high_ = 1;
        }
        next_sample += s->phase_ < pw ? 0.0f : 1.0f;
        
        if (shape == 7) {
          const float integrator_coefficient = frequency * 0.0625f;
          this_sample = 128.0f * (this_sample - 0.5f);
          s->lp_state_ += integrator_coefficient * (this_sample - s->lp_state_);
          *out++ = s->lp_state_;
        } else if (shape == 6) {
          const float integrator_coefficient = frequency * 2.0f;
          this_sample = 4.0f * (this_sample - 0.5f);
          s->lp_state_ += integrator_coefficient * (this_sample - s->lp_state_);
          *out++ = s->lp_state_;
        } else if (shape == 5) {
          const float integrator_coefficient = frequency * 2.0f;
          this_sample = 2.0f * this_sample - 1.0f;
          s->lp_state_ += integrator_coefficient * (this_sample - s->lp_state_);
          *out++ = (this_sample - s->lp_state_) * 0.5f;
        } else {
          this_sample = 2.0f * this_sample - 1.0f;
          *out++ = this_sample;
        }
      }
    }
    s->next_sample_ = next_sample;
  
commit(&fm);
commit(&pwm);}

static float Tame(float f0,float harmonics,float order) {
  f0 *= harmonics;
  float max_f = 0.5f / order;
  float max_amount = 1.0f - (f0 - max_f) / (0.5f - max_f);
  CONSTRAIN(max_amount, 0.0f, 1.0f);
  return max_amount * max_amount * max_amount;

}

static const int *ws_table(int index) {
 if(index==0) return lut_ws_inverse_tan;
 if(index==1) return lut_ws_inverse_sin;
 if(index==2) return lut_ws_linear;
 if(index==3) return lut_ws_bump;
 return lut_ws_double_bump;
}

static void ws_init(WS *s) {
  slope_init(&s->slope_);
  s->previous_shape_ = 0.0f;
  s->previous_wavefolder_gain_ = 0.0f;

}

static void ws_render(WS *s,const Params *p,float *out,int size) {
  const float root = p->note;
  
  const float f0 = NoteToFrequency(root);
  const float pw = p->morph * 0.45f + 0.5f;
  
  // Start from bandlimited slope signal.
  slope_render(&s->slope_,f0, pw, out, size);

  // Try to estimate how rich the spectrum is, and reduce the range of the
  // waveshaping control accordingly.
  const float slope = 3.0f + absf(p->morph - 0.5f) * 5.0f;
  const float shape_amount = absf(p->harmonics - 0.5f) * 2.0f;
  const float shape_amount_attenuation = Tame(f0, slope, 16.0f);
  const float wavefolder_gain = p->timbre;
  const float wavefolder_gain_attenuation = Tame(
      f0,
      slope * (3.0f + shape_amount * shape_amount_attenuation * 5.0f),
      12.0f);
  
  // Apply waveshaper / wavefolder.
  Interp shape_modulation=interp(
      &s->previous_shape_,
      0.5f + (p->harmonics - 0.5f) * shape_amount_attenuation,
      size);
  Interp wf_gain_modulation=interp(
      &s->previous_wavefolder_gain_,
      0.03f + 0.46f * wavefolder_gain * wavefolder_gain_attenuation,
      size);
  for (int i = 0; i < size; ++i) {
    float shape = next(&shape_modulation) * 3.9999f;
    MAKE_INTEGRAL_FRACTIONAL(shape);
    
    const int* shape_1 = ws_table(shape_integral);
    const int* shape_2 = ws_table(shape_integral + 1);
    
    float ws_index = 127.0f * out[i] + 128.0f;
    MAKE_INTEGRAL_FRACTIONAL(ws_index)
    ws_index_integral &= 255;
    
    float x0 = (float)(shape_1[ws_index_integral]) / 32768.0f;
    float x1 = (float)(shape_1[ws_index_integral + 1]) / 32768.0f;
    float x = x0 + (x1 - x0) * ws_index_fractional;

    float y0 = (float)(shape_2[ws_index_integral]) / 32768.0f;
    float y1 = (float)(shape_2[ws_index_integral + 1]) / 32768.0f;
    float y = y0 + (y1 - y0) * ws_index_fractional;
    
    float mix = x + (y - x) * shape_fractional;
    float index = mix * next(&wf_gain_modulation) + 0.5f;
    float fold = InterpolateHermite(
        lut_fold + 1, index, 512.0f);
    out[i] = fold;
  }

commit(&shape_modulation);
commit(&wf_gain_modulation);}

static void harmonic_init(Harmonic *s) {
    s->phase_ = 0.0f;
    s->frequency_ = 0.0f;
    for (int i = 0; i < 12; ++i) {
      s->amplitude_[i] = 0.0f;
    }
  
}

static void harmonic_render(Harmonic *s,int first_harmonic_index,float frequency,const float *amplitudes,float *out,int size) {
    if (frequency >= 0.5f) {
      frequency = 0.5f;
    }
    
    Interp am[12];
    Interp fm=interp(&s->frequency_, frequency, size);
    
    for (int i = 0; i < 12; ++i) {
      float f = frequency * (float)(first_harmonic_index + i);
      if (f >= 0.5f) {
        f = 0.5f;
      }
      am[i]=interp(&s->amplitude_[i], amplitudes[i] * (1.0f - f * 2.0f), size);
    }

    while (size--) {
      s->phase_ += next(&fm);
      if (s->phase_ >= 1.0f) {
        s->phase_ -= 1.0f;
      }
      const float two_x = 2.0f * SineNoWrap(s->phase_);
      float previous, current;
      if (first_harmonic_index == 1) {
        previous = 1.0f;
        current = two_x * 0.5f;
      } else {
        const float k = first_harmonic_index;
        previous = Sine(s->phase_ * (k - 1.0f) + 0.25f);
        current = Sine(s->phase_ * k);
      }
      
      float sum = 0.0f;
      for (int i = 0; i < 12; ++i) {
        sum += next(&am[i]) * current;
        float temp = current;
        current = two_x * current - previous;
        previous = temp;
      }
      if (first_harmonic_index == 1) {
        *out++ = sum;
      } else {
        *out++ += sum;
      }
    }
  
commit(&fm);
for(int i=0;i<12;i++) commit(&am[i]);
}

static const int integer_harmonics[24]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23};

static void amplitudes_update(float centroid,float slope,float bumps,float *amplitudes,const int *harmonic_indices,int num_harmonics) {
  const float n = ((float)(num_harmonics) - 1.0f);
  const float margin = (1.0f / slope - 1.0f) / (1.0f + bumps);
  const float center = centroid * (n + margin) - 0.5f * margin;

  float sum = 0.001f;

  for (int i = 0; i < num_harmonics; ++i) {
    float order = absf((float)(i) - center) * slope;
    float gain = 1.0f - order;
    gain += absf(gain);
    gain *= gain;

    float b = 0.25f + order * bumps;
    float bump_factor = 1.0f + Sine(b);

    gain *= bump_factor;
    gain *= gain;
    gain *= gain;
    
    int j = harmonic_indices[i];
    
    // Warning about the following line: this is not a proper LP filter because
    // of the normalization. But in spite of its strange working, this line
    // turns out to be absolutely essential.
    //
    // I have tried both normalizing the LP-ed spectrum, and LP-ing the
    // normalized spectrum, and both of them cause more annoyances than this
    // "incorrect" solution.
    
    ONE_POLE(amplitudes[j], gain, 0.001f);
    sum += amplitudes[j];
  }

  sum = 1.0f / sum;

  for (int i = 0; i < num_harmonics; ++i) {
    amplitudes[harmonic_indices[i]] *= sum;
  }

}

static void additive_render(Additive *s,const Params *p,float *out,int size) {
  const float f0 = NoteToFrequency(p->note);

  const float centroid = p->timbre;
  const float raw_bumps = p->harmonics;
  const float raw_slope = (1.0f - 0.6f * raw_bumps) * p->morph;
  const float slope = 0.01f + 1.99f * raw_slope * raw_slope * raw_slope;
  const float bumps = 16.0f * raw_bumps * raw_bumps;
  amplitudes_update(
      centroid,
      slope,
      bumps,
      &s->amplitudes_[0],
      integer_harmonics,
      24);
  harmonic_render(&s->harmonic_oscillator_[0],1,f0, &s->amplitudes_[0], out, size);
  harmonic_render(&s->harmonic_oscillator_[1],13,f0, &s->amplitudes_[12], out, size);


}

static float grainlet_carrier(float phase,float shape) {
    shape *= 3.0f;
    MAKE_INTEGRAL_FRACTIONAL(shape);
    float t = 1.0f - shape_fractional;
    
    if (shape_integral == 0) {
      phase = phase * (1.0f + t * t * t * 15.0f);
      if (phase >= 1.0f) {
        phase = 1.0f;
      }
      phase += 0.75f;
    } else if (shape_integral == 1) {
      float breakpoint = 0.001f + 0.499f * t * t * t;
      if (phase < breakpoint) {
        phase *= (0.5f / breakpoint);
      } else {
        phase = 0.5f + (phase - breakpoint) * 0.5f / (1.0f - breakpoint);
      }
      phase += 0.75f;
    } else {
      t = 1.0f - t;
      phase = 0.25f + phase * (0.5f + t * t * t * 14.5f);
      if (phase >= 0.75f) phase = 0.75f;
    }
    return (Sine(phase) + 1.0f) * 0.25f;
  
}

static float grainlet(float carrier_phase,float formant_phase,float shape,float bleed) {
    float carrier = grainlet_carrier(carrier_phase, shape);
    float formant = Sine(formant_phase);
    return carrier * (formant + bleed) / (1.0f + bleed);
  
}

static void grainlet_init(Grainlet *s) {
    s->carrier_phase_ = 0.0f;
    s->formant_phase_ = 0.0f;
    s->next_sample_ = 0.0f;
  
    s->carrier_frequency_ = 0.0f;
    s->formant_frequency_ = 0.0f;
    s->carrier_shape_ = 0.0f;
    s->carrier_bleed_ = 0.0f;
  
}

static void grainlet_render(Grainlet *s,float carrier_frequency,float formant_frequency,float carrier_shape,float carrier_bleed,float *out,int size) {
    if (carrier_frequency >= kMaxFrequency * 0.5f) {
      carrier_frequency = kMaxFrequency * 0.5f;
    }
    if (formant_frequency >= kMaxFrequency) {
      formant_frequency = kMaxFrequency;
    }
    
    Interp carrier_frequency_modulation=interp(
        &s->carrier_frequency_,
        carrier_frequency,
        size);
    Interp formant_frequency_modulation=interp(
        &s->formant_frequency_,
        formant_frequency,
        size);
    Interp carrier_shape_modulation=interp(
        &s->carrier_shape_,
        carrier_shape,
        size);
    Interp carrier_bleed_modulation=interp(
        &s->carrier_bleed_,
        carrier_bleed,
        size);

    float next_sample = s->next_sample_;
    
    while (size--) {
      int reset = 0;
      float reset_time = 0.0f;

      float this_sample = next_sample;
      next_sample = 0.0f;
    
      const float f0 = next(&carrier_frequency_modulation);
      const float f1 = next(&formant_frequency_modulation);
    
      s->carrier_phase_ += f0;
      reset = s->carrier_phase_ >= 1.0f;
      
      if (reset) {
        s->carrier_phase_ -= 1.0f;
        reset_time = s->carrier_phase_ / f0;
        float before = grainlet(
            1.0f,
            s->formant_phase_ + (1.0f - reset_time) * f1,
            subsample(&carrier_shape_modulation,1.0f - reset_time),
            subsample(&carrier_bleed_modulation,1.0f - reset_time));

        float after = grainlet(
            0.0f,
            0.0f,
            subsample(&carrier_shape_modulation,1.0f),
            subsample(&carrier_bleed_modulation,1.0f));

        float discontinuity = after - before;
        this_sample += discontinuity * ThisBlepSample(reset_time);
        next_sample += discontinuity * NextBlepSample(reset_time);
        s->formant_phase_ = reset_time * f1;
      } else {
        s->formant_phase_ += f1;
        if (s->formant_phase_ >= 1.0f) {
          s->formant_phase_ -= 1.0f;
        }
      }
      
      next_sample += grainlet(
          s->carrier_phase_,
          s->formant_phase_,
          next(&carrier_shape_modulation),
          next(&carrier_bleed_modulation));
      *out++ = this_sample;
    }
    
    s->next_sample_ = next_sample;
  
commit(&carrier_frequency_modulation);
commit(&formant_frequency_modulation);
commit(&carrier_shape_modulation);
commit(&carrier_bleed_modulation);}

static void pole_set(Pole *s,float f) {
 const float a=11.583945274353027f; s->g_=f*(3.14159265358979323846f+a*f*f);
 s->gi_=1.0f/(1.0f+s->g_);
}

static float pole_high(Pole *s,float in) {
    float lp;
    lp = (s->g_ * in + s->state_) * s->gi_;
    s->state_ = s->g_ * (in - lp) + lp;

return in-lp;

}

static void grain_render(Grain *s,const Params *p,float *out,int size) {
  const float root = p->note;
  const float f0 = NoteToFrequency(root);
  
  const float f1 = NoteToFrequency(24.0f + 84.0f * p->timbre);
  const float f_ratio = ratio(-24.0f + 48.0f * p->harmonics);
  const float carrier_bleed = p->harmonics < 0.5f
      ? 1.0f - 2.0f * p->harmonics
      : 0.0f;
  const float carrier_bleed_fixed = carrier_bleed * (2.0f - carrier_bleed);
  const float carrier_shape = 0.33f + (p->morph - 0.33f) * \
      maxf(1.0f - f0 * 24.0f, 0.0f);
  
  grainlet_render(&s->grainlet_[0],f0, f1, carrier_shape, carrier_bleed_fixed, out, size);
  grainlet_render(&s->grainlet_[1],f0, f1 * f_ratio, carrier_shape, carrier_bleed_fixed, s->scratch_, size);
  pole_set(&s->dc_blocker_,0.3f * f0);
  for (int i = 0; i < size; ++i) {
    out[i] = pole_high(&s->dc_blocker_,out[i] + s->scratch_[i]);
  }


}

int bank_size(void) {return sizeof(Bank);}
void bank_init(Bank *s,int model) {
 for(int i=0;i<64;i++) s->engine.words[i]=0;
 if(model<0) model=0; if(model>5) model=5; s->model=model;
 if(model<3) trio_init(&s->engine.trio,model);
 else if(model==3) ws_init(&s->engine.ws);
 else if(model==4) {harmonic_init(&s->engine.add.harmonic_oscillator_[0]);harmonic_init(&s->engine.add.harmonic_oscillator_[1]);}
 else {grainlet_init(&s->engine.grain.grainlet_[0]);grainlet_init(&s->engine.grain.grainlet_[1]);pole_set(&s->engine.grain.dc_blocker_,0.01f);}
}
void bank_render(Bank *s,const Params *p,int trigger,float accent,float *out,int size) {
 if(s->model<3) trio_render(&s->engine.trio,p,trigger,accent,out,size);
 else if(s->model==3) ws_render(&s->engine.ws,p,out,size);
 else if(s->model==4) additive_render(&s->engine.add,p,out,size);
 else grain_render(&s->engine.grain,p,out,size);
}
