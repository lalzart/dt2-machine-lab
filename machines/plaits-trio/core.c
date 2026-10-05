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

// Generated from the pinned source by translate.py.
#define PLAITS_MAIN_ONLY 1
#include "../plaits-va/core.c"
#include "core.h"
#include "tables.h"
#define ONE_POLE(out,in,coefficient) out += (coefficient) * ((in) - out);
static const float a0=0.0011488889576867223f; // Original float32 (440/8)/47872.34.
static const float kSampleRate=48000.0f;
static const int kOversampling=4;
static const int kSineLUTBits=9;
// Explicit unsigned conversions: the pinned compiler emits signed FLOAT/TRUNC.
static unsigned int uint_from_float(float v) {
 if(v>=2147483648.0f) return (unsigned int)(int)(v-2147483648.0f)+2147483648u;
 return (unsigned int)(int)v;
}
static float float_from_uint(unsigned int v) {
 if(v & 2147483648u) return (float)(int)((v>>1)|(v&1u))*2.0f;
 return (float)(int)v;
}

static float Interpolate(const float *table,float index,float size) {
  index *= size;
  MAKE_INTEGRAL_FRACTIONAL(index)
  float a = table[index_integral];
  float b = table[index_integral + 1];
  return a + (b - a) * index_fractional;

}

static float SoftLimit(float x) {
  return x * (27.0f + x * x) / (27.0f + 9.0f * x * x);

}

static float SoftClip(float x) {
  if (x < -3.0f) {
    return -1.0f;
  } else if (x > 3.0f) {
    return 1.0f;
  } else {
    return SoftLimit(x);
  }

}

static float SinePM(unsigned int phase,float pm) {
  const float max_uint32 = 4294967296.0f;
  const int max_index = 32;
  const float offset = (float)(max_index);
  const float scale = max_uint32 / (float)(max_index * 2);

  phase += uint_from_float((pm + offset) * scale) * max_index * 2;
  
  unsigned int integral = phase >> (32 - kSineLUTBits);
  float fractional = float_from_uint(phase << kSineLUTBits) / (float)(max_uint32);
  float a = lut_sine[integral];
  float b = lut_sine[integral + 1];
  return a + (b - a) * fractional;

}

static float SineNoWrap(float phase) { return Interpolate(lut_sine,phase,512.0f); }

static void sine_next(SineState *s,float frequency,float amplitude,float *sin,float *cos) {
    if (frequency >= 0.5f) {
      frequency = 0.5f;
    }
    
    s->phase_ += frequency;
    if (s->phase_ >= 1.0f) {
      s->phase_ -= 1.0f;
    }
    
    *sin = amplitude * SineNoWrap(s->phase_);
    *cos = amplitude * SineNoWrap(s->phase_ + 0.25f);
  
}

typedef struct {float head_,tail_;float *state_;} Down;
static Down down_init(float *p) { Down s; s.head_=*p; s.tail_=0.0f; s.state_=p; return s; }
static void down_add(Down *s,int i,float sample) {s->head_+=sample*lut_4x_downsampler_fir[3-(i&3)];s->tail_+=sample*lut_4x_downsampler_fir[i&3];}
static float down_read(Down *s) {float v=s->head_;s->head_=s->tail_;s->tail_=0.0f;return v;}

static void fm_init(FM *s) {
  s->carrier_phase_ = 0;
  s->modulator_phase_ = 0;
  s->sub_phase_ = 0;

  s->previous_carrier_frequency_ = a0;
  s->previous_modulator_frequency_ = a0;
  s->previous_amount_ = 0.0f;
  s->previous_feedback_ = 0.0f;
  s->previous_sample_ = 0.0f;

}

static void fm_render(FM *s,const Params *p,float *out,int size) {
  
  // 4x oversampling
  const float note = p->note - 24.0f;
  
  const float ratio = Interpolate(
      lut_fm_frequency_quantizer,
      p->harmonics,
      128.0f);
  
  float modulator_note = note + ratio;
  float target_modulator_frequency = NoteToFrequency(modulator_note);
  CONSTRAIN(target_modulator_frequency, 0.0f, 0.5f);

  // Reduce the maximum FM index for high pitched notes, to prevent aliasing.
  float hf_taming = 1.0f - (modulator_note - 72.0f) * 0.025f;
  CONSTRAIN(hf_taming, 0.0f, 1.0f);
  hf_taming *= hf_taming;
  
  Interp carrier_frequency = interp(
      &s->previous_carrier_frequency_, NoteToFrequency(note), size);
  Interp modulator_frequency = interp(
      &s->previous_modulator_frequency_, target_modulator_frequency, size);
  Interp amount_modulation = interp(
      &s->previous_amount_,
      2.0f * p->timbre * p->timbre * hf_taming,
      size);
  Interp feedback_modulation = interp(
      &s->previous_feedback_, 2.0f * p->morph - 1.0f, size);
  
  Down carrier_downsampler=down_init(&s->carrier_fir_);
  
  while (size--) {
    const float max_uint32 = 4294967296.0f;
    const float amount = next(&amount_modulation);
    const float feedback = next(&feedback_modulation);
    float phase_feedback = feedback < 0.0f ? 0.5f * feedback * feedback : 0.0f;
    const unsigned int carrier_increment = uint_from_float(
        max_uint32 * next(&carrier_frequency));
    float _modulator_frequency = next(&modulator_frequency);

    for (int j = 0; j < kOversampling; ++j) {
      s->modulator_phase_ += uint_from_float(max_uint32 * \
           _modulator_frequency * (1.0f + s->previous_sample_ * phase_feedback));
      s->carrier_phase_ += carrier_increment;
      float modulator_fb = feedback > 0.0f ? 0.25f * feedback * feedback : 0.0f;
      float modulator = SinePM(
          s->modulator_phase_, modulator_fb * s->previous_sample_);
      float carrier = SinePM(s->carrier_phase_, amount * modulator);
      ONE_POLE(s->previous_sample_, carrier, 0.05f);
      down_add(&carrier_downsampler,j, carrier);
    }
    
    *out++ = down_read(&carrier_downsampler);
  }

commit(&carrier_frequency);
commit(&modulator_frequency);
commit(&amount_modulation);
commit(&feedback_modulation);
*carrier_downsampler.state_=carrier_downsampler.head_;
}
static void svf_set(Svf *s,float f,float resonance) {
 const float a=11.583945274353027f; s->g_=f*(3.14159265358979323846f+a*f*f);
 s->r_=1.0f/resonance; s->h_=1.0f/(1.0f+s->r_*s->g_+s->g_*s->g_);
}
static void svf_init(Svf *s) { svf_set(s,0.01f,100.0f);s->state_1_=0.0f;s->state_2_=0.0f; }

static void svf_process(Svf *s,float in,float *out_1,float *out_2) {
    float hp, bp, lp;
    hp = (in - s->r_ * s->state_1_ - s->g_ * s->state_1_ - s->state_2_) * s->h_;
    bp = s->g_ * hp + s->state_1_;
    s->state_1_ = s->g_ * hp + bp;
    lp = s->g_ * bp + s->state_2_;
    s->state_2_ = s->g_ * bp + lp;
    
*out_1=bp; *out_2=lp;

}

static void analog_init(AnalogBD *s) {
    s->pulse_remaining_samples_ = 0;
    s->fm_pulse_remaining_samples_ = 0;
    s->pulse_ = 0.0f;
    s->pulse_height_ = 0.0f;
    s->pulse_lp_ = 0.0f;
    s->fm_pulse_lp_ = 0.0f;
    s->retrig_pulse_ = 0.0f;
    s->lp_out_ = 0.0f;
    s->tone_lp_ = 0.0f;
    s->sustain_gain_ = 0.0f;

    svf_init(&s->resonator_);
    s->oscillator_.phase_=0.0f; s->oscillator_.frequency_=0.0f; s->oscillator_.amplitude_=0.0f;
  
}

static float Diode(float x) {
    if (x >= 0.0f) {
      return x;
    } else {
      x *= 2.0f;
      return 0.7f * x / (1.0f + absf(x));
    }
  
}

static void analog_render(AnalogBD *s,int sustain,int trigger,float accent,float f0,float tone,float decay,float attack_fm_amount,float self_fm_amount,float *out,int size) {
    const int kTriggerPulseDuration = 1.0e-3f * kSampleRate;
    const int kFMPulseDuration = 6.0e-3f * kSampleRate;
    const float kPulseDecayTime = 0.2e-3f * kSampleRate;
    const float kPulseFilterTime = 0.1e-3f * kSampleRate;
    const float kRetrigPulseDuration = 0.05f * kSampleRate;
    
    const float scale = 0.001f / f0;
    const float q = 1500.0f * ratio(decay * 80.0f);
    const float tone_f = minf(
        4.0f * f0 * ratio(tone * 108.0f),
        1.0f);
    const float exciter_leak = 0.08f * (tone + 0.25f);
      

    if (trigger) {
      s->pulse_remaining_samples_ = kTriggerPulseDuration;
      s->fm_pulse_remaining_samples_ = kFMPulseDuration;
      s->pulse_height_ = 3.0f + 7.0f * accent;
      s->lp_out_ = 0.0f;
    }
    
    Interp sustain_gain = interp(
        &s->sustain_gain_,
        accent * decay,
        size);
    
    while (size--) {
      // Q39 / Q40
      float pulse = 0.0f;
      if (s->pulse_remaining_samples_) {
        --s->pulse_remaining_samples_;
        pulse = s->pulse_remaining_samples_ ? s->pulse_height_ : s->pulse_height_ - 1.0f;
        s->pulse_ = pulse;
      } else {
        s->pulse_ *= 1.0f - 1.0f / kPulseDecayTime;
        pulse = s->pulse_;
      }
      if (sustain) {
        pulse = 0.0f;
      }
      
      // C40 / R163 / R162 / D83
      ONE_POLE(s->pulse_lp_, pulse, 1.0f / kPulseFilterTime);
      pulse = Diode((pulse - s->pulse_lp_) + pulse * 0.044f);

      // Q41 / Q42
      float fm_pulse = 0.0f;
      if (s->fm_pulse_remaining_samples_) {
        --s->fm_pulse_remaining_samples_;
        fm_pulse = 1.0f;
        // C39 / C52
        s->retrig_pulse_ = s->fm_pulse_remaining_samples_ ? 0.0f : -0.8f;
      } else {
        // C39 / R161
        s->retrig_pulse_ *= 1.0f - 1.0f / kRetrigPulseDuration;
      }
      if (sustain) {
        fm_pulse = 0.0f;
      }
      ONE_POLE(s->fm_pulse_lp_, fm_pulse, 1.0f / kPulseFilterTime);

      // Q43 and R170 leakage
      float punch = 0.7f + Diode(10.0f * s->lp_out_ - 1.0f);

      // Q43 / R165
      float attack_fm = s->fm_pulse_lp_ * 1.7f * attack_fm_amount;
      float self_fm = punch * 0.08f * self_fm_amount;
      float f = f0 * (1.0f + attack_fm + self_fm);
      CONSTRAIN(f, 0.0f, 0.4f);

      float resonator_out;
      if (sustain) {
        sine_next(&s->oscillator_,f, next(&sustain_gain), &resonator_out, &s->lp_out_);
      } else {
        svf_set(&s->resonator_,f, 1.0f + q * f);
        svf_process(&s->resonator_,
            (pulse - s->retrig_pulse_ * 0.2f) * scale,
            &resonator_out,
            &s->lp_out_);
      }
      
      ONE_POLE(s->tone_lp_, pulse * exciter_leak + resonator_out, tone_f);
      
      *out++ = s->tone_lp_;
    }
  
commit(&sustain_gain);}

static void drive_process(Drive *s,float drive,float *in_out,int size) {
    const float drive_2 = drive * drive;
    const float pre_gain_a = drive * 0.5f;
    const float pre_gain_b = drive_2 * drive_2 * drive * 24.0f;
    const float pre_gain = pre_gain_a + (pre_gain_b - pre_gain_a) * drive_2;
    const float drive_squashed = drive * (2.0f - drive);
    const float post_gain = 1.0f / SoftClip(
          0.33f + drive_squashed * (pre_gain - 0.33f));
    
    Interp pre_gain_modulation = interp(
        &s->pre_gain_,
        pre_gain,
        size);
    
    Interp post_gain_modulation = interp(
        &s->post_gain_,
        post_gain,
        size);
    
    while (size--) {
      float pre = next(&pre_gain_modulation) * *in_out;
      *in_out++ = SoftClip(pre) * next(&post_gain_modulation);
    }
  
commit(&pre_gain_modulation);
commit(&post_gain_modulation);}

static void bd_render(BD *s,const Params *p,int trigger,float accent,float *out,int size) {
  const float f0 = NoteToFrequency(p->note);
  
  const float attack_fm_amount = minf(p->harmonics * 4.0f, 1.0f);
  const float self_fm_amount = maxf(minf(p->harmonics * 4.0f - 1.0f, 1.0f), 0.0f);
  const float drive = maxf(p->harmonics * 2.0f - 1.0f, 0.0f) * \
      maxf(1.0f - 16.0f * f0, 0.0f);
  
  const int sustain = trigger & TRIGGER_UNPATCHED;
  
  analog_render(&s->analog_,
      sustain,
      trigger & TRIGGER_RISING_EDGE,
      accent,
      f0,
      p->timbre,
      p->morph,
      attack_fm_amount,
      self_fm_amount,
      out,
      size);

  drive_process(&s->drive_,
      0.5f + 0.5f * drive,
      out,
      size);


}

int trio_size(void) { return sizeof(Trio); }
void trio_init(Trio *s,int model) {
 for(int i=0;i<63;i++) s->engine.words[i]=0;
 if(model<0) model=0; if(model>2) model=2; s->model=model;
 if(model==0) va_init(&s->engine.va);
 else if(model==1) fm_init(&s->engine.fm);
 else {analog_init(&s->engine.bd.analog_);s->engine.bd.drive_.pre_gain_=0.0f;s->engine.bd.drive_.post_gain_=0.0f;}
}
void trio_render(Trio *s,const Params *p,int trigger,float accent,float *out,int size) {
 if(s->model==0) va_render(&s->engine.va,p,out,(float *)0,size);
 else if(s->model==1) fm_render(&s->engine.fm,p,out,size);
 else bd_render(&s->engine.bd,p,trigger,accent,out,size);
}
