"""Pinned C99 translation of Plaits FM MAIN and analog bass-drum MAIN."""

import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
source = Path(sys.argv[1]).resolve()
lock = json.loads((HERE / "source-lock.json").read_text())
for name, digest in lock["files"].items():
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
        raise ValueError(f"Upstream drift: {name}")
for name, digest in lock["reuse_sha256"].items():
    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
        raise ValueError(f"VA reuse drift: {name}")


def read(name):
    return (source / name).read_text()


def body(text, signature):
    start = text.index("{", text.index(signature)) + 1
    end, depth = start, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start : end - 1]


def common(text):
    text = text.replace("stmlib::", "").replace("std::", "")
    for a, b in [
        ("bool", "int"),
        ("true", "1"),
        ("false", "0"),
        ("size_t", "int"),
        ("uint32_t", "unsigned int"),
    ]:
        text = re.sub(r"\b" + a + r"\b", b, text)
    text = re.sub(r"\bmax\(", "maxf(", text)
    text = re.sub(r"\bmin\(", "minf(", text).replace("fabsf(", "absf(")
    text = re.sub(r"\b([a-zA-Z]\w*_)\b", r"s->\1", text)
    text = text.replace("SemitonesToRatio(", "ratio(")
    text = text.replace("static_cast<unsigned int>(", "(unsigned int)(").replace(
        "static_cast<float>(", "(float)("
    )
    text = re.sub(r"\bfloat\(", "(float)(", text)
    names = re.findall(r"ParameterInterpolator\s+(\w+)\(", text)
    text = re.sub(r"ParameterInterpolator\s+(\w+)\(", r"Interp \1 = interp(", text)
    text = re.sub(r"(\w+)\.Next\(\)", r"next(&\1)", text)
    return text + "\n" + "\n".join(f"commit(&{n});" for n in names)


notice = read("plaits/dsp/engine/fm_engine.cc").split("// ---")[0]
notice = notice.replace("Copyright 2016", "Copyright 2014-2021")
resources = read("plaits/resources.cc")
tables = []
for name in ("lut_sine", "lut_fm_frequency_quantizer", "lut_4x_downsampler_fir"):
    match = re.search(r"const float " + name + r"\[\] = \{.*?\n\};", resources, re.S)
    if not match:
        raise ValueError(f"Missing table: {name}")
    tables.append("static " + match[0])
(HERE / "tables.h").write_text(
    notice + "\n// Original upstream table literals.\n" + "\n".join(tables) + "\n"
)


def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


a0 = f32(55.0 / f32(47872.34))
parts = [
    notice,
    """// Generated from the pinned source by translate.py.
#define PLAITS_MAIN_ONLY 1
#include "../plaits-va/core.c"
#include "core.h"
#include "tables.h"
#define ONE_POLE(out,in,coefficient) out += (coefficient) * ((in) - out);
static const float a0=SOURCE_A0; // Original float32 (440/8)/47872.34.
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
""".replace("SOURCE_A0", repr(a0) + "f"),
]
dsp = read("stmlib/dsp/dsp.h")
for name, sig in [
    ("Interpolate", "const float *table,float index,float size"),
    ("SoftLimit", "float x"),
    ("SoftClip", "float x"),
]:
    parts.append(
        f"static float {name}({sig}) {{"
        + common(body(dsp, "inline float " + name + "("))
        + "}\n"
    )
sine = read("plaits/dsp/oscillator/sine_oscillator.h")
parts.append(
    "static float SinePM(unsigned int phase,float pm) {"
    + common(body(sine, "inline float SinePM("))
    .replace("(unsigned int)(", "uint_from_float(")
    .replace("(float)(phase << kSineLUTBits)", "float_from_uint(phase << kSineLUTBits)")
    + "}\n"
)
parts.append(
    "static float SineNoWrap(float phase) { return Interpolate(lut_sine,phase,512.0f); }\n"
)
parts.append(
    "static void sine_next(SineState *s,float frequency,float amplitude,float *sin,float *cos) {"
    + common(body(sine, "inline void Next(float frequency, float amplitude,"))
    + "}\n"
)
parts.append("""typedef struct {float head_,tail_;float *state_;} Down;
static Down down_init(float *p) { Down s; s.head_=*p; s.tail_=0.0f; s.state_=p; return s; }
static void down_add(Down *s,int i,float sample) {s->head_+=sample*lut_4x_downsampler_fir[3-(i&3)];s->tail_+=sample*lut_4x_downsampler_fir[i&3];}
static float down_read(Down *s) {float v=s->head_;s->head_=s->tail_;s->tail_=0.0f;return v;}
""")
fm = read("plaits/dsp/engine/fm_engine.cc")
parts.append(
    "static void fm_init(FM *s) {" + common(body(fm, "void FMEngine::Init(")) + "}\n"
)
fmr = body(fm, "void FMEngine::Render(")
# Remove only independent AUX work; keep all carrier/modulator equations.
for pattern in [
    r"  Downsampler sub_downsampler\(&sub_fir_\);\n",
    r"      sub_phase_ \+= carrier_increment >> 1;\n",
    r"      float sub = SinePM\(sub_phase_, amount \* carrier \* 0.25f\);\n",
    r"      sub_downsampler.Accumulate\(j, sub\);\n",
    r"    \*aux\+\+ = sub_downsampler.Read\(\);\n",
]:
    fmr, count = re.subn(pattern, "", fmr)
    if count != 1:
        raise ValueError(f"AUX exclusion mismatch: {pattern}")
fmr = (
    common(fmr)
    .replace("parameters.", "p->")
    .replace("(unsigned int)(", "uint_from_float(")
)
fmr = fmr.replace(
    "Downsampler carrier_downsampler(", "Down carrier_downsampler=down_init("
)
fmr = fmr.replace("carrier_downsampler.Accumulate(", "down_add(&carrier_downsampler,")
fmr = fmr.replace("carrier_downsampler.Read()", "down_read(&carrier_downsampler)")
parts.append(
    "static void fm_render(FM *s,const Params *p,float *out,int size) {"
    + fmr
    + "\n*carrier_downsampler.state_=carrier_downsampler.head_;\n}"
)
# Freeze original double constant folding to a float literal for the C99 target.
a = f32(f32(0.3736) * math.pi * math.pi * math.pi)
parts.append(f"""static void svf_set(Svf *s,float f,float resonance) {{
 const float a={a!r}f; s->g_=f*(3.14159265358979323846f+a*f*f);
 s->r_=1.0f/resonance; s->h_=1.0f/(1.0f+s->r_*s->g_+s->g_*s->g_);
}}
static void svf_init(Svf *s) {{ svf_set(s,0.01f,100.0f);s->state_1_=0.0f;s->state_2_=0.0f; }}
""")
filt = read("stmlib/dsp/filter.h")
svf = body(
    filt[filt.index("class Svf") :],
    "inline void Process(float in, float* out_1, float* out_2)",
)
svf = svf[: svf.index("    if (mode_1")] + "*out_1=bp; *out_2=lp;\n"
parts.append(
    "static void svf_process(Svf *s,float in,float *out_1,float *out_2) {"
    + common(svf)
    + "}\n"
)
analog = read("plaits/dsp/drums/analog_bass_drum.h")
bdi = (
    common(body(analog, "void Init()"))
    .replace("s->resonator_.Init()", "svf_init(&s->resonator_)")
    .replace(
        "s->oscillator_.Init()",
        "s->oscillator_.phase_=0.0f; s->oscillator_.frequency_=0.0f; s->oscillator_.amplitude_=0.0f",
    )
)
parts.append("static void analog_init(AnalogBD *s) {" + bdi + "}\n")
parts.append(
    "static float Diode(float x) {"
    + common(body(analog, "inline float Diode("))
    + "}\n"
)
bdr = common(body(analog, "void Render("))
bdr = bdr.replace("s->oscillator_.Next(", "sine_next(&s->oscillator_,")
bdr = bdr.replace("s->resonator_.set_f_q<FREQUENCY_DIRTY>(", "svf_set(&s->resonator_,")
bdr = re.sub(
    r"s->resonator_\.Process<FILTER_MODE_BAND_PASS,\s*FILTER_MODE_LOW_PASS>\(",
    "svf_process(&s->resonator_,",
    bdr,
)
parts.append(
    "static void analog_render(AnalogBD *s,int sustain,int trigger,float accent,float f0,float tone,float decay,float attack_fm_amount,float self_fm_amount,float *out,int size) {"
    + bdr
    + "}\n"
)
od = read("plaits/dsp/fx/overdrive.h")
parts.append(
    "static void drive_process(Drive *s,float drive,float *in_out,int size) {"
    + common(body(od, "void Process("))
    + "}\n"
)
bd = body(read("plaits/dsp/engine/bass_drum_engine.cc"), "void BassDrumEngine::Render(")
bd = bd[: bd.index("  synthetic_bass_drum_.Render(")]
bd = common(bd).replace("parameters.", "p->")
bd = bd.replace("p->trigger", "trigger").replace("p->accent", "accent")
bd = bd.replace("s->analog_bass_drum_.Render(", "analog_render(&s->analog_,").replace(
    "s->overdrive_.Process(", "drive_process(&s->drive_,"
)
parts.append(
    "static void bd_render(BD *s,const Params *p,int trigger,float accent,float *out,int size) {"
    + bd
    + "}\n"
)
parts.append("""int trio_size(void) { return sizeof(Trio); }
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
""")
(HERE / "core.c").write_text("\n".join(parts))
(HERE / "core.h").write_text(
    notice
    + """
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
"""
)
print("Validated source closure; generated FM/BD MAIN and original tables.")

controls = json.loads((HERE / "controls.json").read_text())
lines = ["// Generated from controls.json; do not edit."]
for name, item in controls.items():
    if isinstance(item, dict) and "dm" in item:
        lines.append(f"#define TRIO_{name.upper()}_DM {item['dm']}")
        if "scale" in item:
            lines.append(
                f"#define TRIO_{name.upper()}_FACTOR (1.0f/{item['scale']}.0f)"
            )
(HERE / "controls.h").write_text("\n".join(lines) + "\n")
