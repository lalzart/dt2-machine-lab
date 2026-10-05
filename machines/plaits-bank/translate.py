"""Exact-source C99 MAIN translations for waveshaping, additive and grainlets."""

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


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


for name, digest in lock["files"].items():
    if sha(source / name) != digest:
        raise ValueError(f"Upstream drift: {name}")
for name, digest in lock["reuse_sha256"].items():
    if sha(ROOT / name) != digest:
        raise ValueError(f"Reuse drift: {name}")
if sha(ROOT / lock["proposal"]) != lock["proposal_sha256"]:
    raise ValueError("Contract drift")


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
        ("int32_t", "int"),
        ("int16_t", "int"),
    ]:
        text = re.sub(r"\b" + a + r"\b", b, text)
    text = re.sub(r"static_cast<(float|int)>\(", r"(\1)(", text)
    text = re.sub(r"\bmax\(", "maxf(", text)
    text = re.sub(r"\bmin\(", "minf(", text).replace("fabsf(", "absf(")
    text = re.sub(r"\b([a-zA-Z]\w*_)\b", r"s->\1", text)
    text = text.replace("SemitonesToRatio(", "ratio(").replace("parameters.", "p->")
    names = re.findall(r"ParameterInterpolator\s+(\w+)\(", text)
    text = re.sub(r"ParameterInterpolator\s+(\w+)\(", r"Interp \1=interp(", text)
    text = re.sub(r"(\w+)\.Next\(\)", r"next(&\1)", text)
    text = re.sub(r"(\w+)\.subsample\(", r"subsample(&\1,", text)
    return text + "\n" + "\n".join(f"commit(&{n});" for n in names)


notice = read("plaits/dsp/engine/waveshaping_engine.cc").split("// ---")[0]
resources = read("plaits/resources.cc")
tables = []
for name in (
    "lut_fold",
    "lut_ws_inverse_tan",
    "lut_ws_inverse_sin",
    "lut_ws_linear",
    "lut_ws_bump",
    "lut_ws_double_bump",
):
    match = re.search(
        r"const (?:float|int16_t) " + name + r"\[\] = \{.*?\n\};", resources, re.S
    )
    if not match:
        raise ValueError("Missing table: " + name)
    tables.append("static " + match[0].replace("int16_t", "int"))
(HERE / "tables.h").write_text(
    notice
    + "\n// Original float literals; integer table values widened to int32.\n"
    + "\n".join(tables)
    + "\n"
)
parts = [
    notice,
    """// Generated from pinned source; see source-lock.json and translate.py.
#include "../plaits-trio/core.c"
#include "core.h"
#include "tables.h"
static float subsample(Interp *p,float t) { return p->value+p->increment*t; }
""",
]
dsp = read("stmlib/dsp/dsp.h")
for name in ("InterpolateHermite", "InterpolateWrap"):
    parts.append(
        "static float "
        + name
        + "(const float *table,float index,float size) {"
        + common(body(dsp, "inline float " + name + "("))
        + "}\n"
    )
parts.append(
    "static float Sine(float phase) { return InterpolateWrap(lut_sine,phase,512.0f); }\n"
)
osc = read("plaits/dsp/oscillator/oscillator.h")
parts.append(
    "static void slope_init(Slope *s) {" + common(body(osc, "void Init()")) + "}\n"
)
oscr = body(osc[osc.index("template<OscillatorShape shape, bool") :], "void Render(")
for i, name in enumerate(
    (
        "IMPULSE_TRAIN",
        "SAW",
        "TRIANGLE",
        "SLOPE",
        "SQUARE",
        "SQUARE_BRIGHT",
        "SQUARE_DARK",
        "SQUARE_TRIANGLE",
    )
):
    oscr = re.sub(r"\bOSCILLATOR_SHAPE_" + name + r"\b", str(i), oscr)
parts.append(
    "static void slope_render(Slope *s,float frequency,float pw,float *out,int size) { const int shape=3,has_external_fm=0,through_zero_fm=0; const float *external_fm=(const float *)0; const float kMinFrequency=0.000001f;"
    + common(oscr)
    + "}\n"
)
ws = read("plaits/dsp/engine/waveshaping_engine.cc")
parts.append(
    "static float Tame(float f0,float harmonics,float order) {"
    + common(body(ws, "float Tame("))
    + "}\n"
)
parts.append("""static const int *ws_table(int index) {
 if(index==0) return lut_ws_inverse_tan;
 if(index==1) return lut_ws_inverse_sin;
 if(index==2) return lut_ws_linear;
 if(index==3) return lut_ws_bump;
 return lut_ws_double_bump;
}
""")
wsi = (
    body(ws, "void WaveshapingEngine::Init(")
    .replace("  triangle_.Init();\n", "")
    .replace("  previous_overtone_gain_ = 0.0f;\n", "")
)
parts.append(
    "static void ws_init(WS *s) {"
    + common(wsi).replace("s->slope_.Init()", "slope_init(&s->slope_)")
    + "}\n"
)
wsr = body(ws, "void WaveshapingEngine::Render(")
wsr = wsr.replace(
    "  triangle_.Render<OSCILLATOR_SHAPE_SLOPE>(f0, 0.5f, aux, size);\n", ""
)
start = wsr.index("  const float overtone_gain")
end = wsr.index("  for (", start)
wsr = wsr[:start] + wsr[end:]
start = wsr.index("    float fold_2")
end = wsr.index("    out[i] = fold;", start)
wsr = wsr[:start] + wsr[end:]
wsr = wsr.replace(
    "    aux[i] = sine + (fold_2 - sine) * overtone_gain_modulation.Next();\n", ""
)
wsr = common(wsr).replace(
    "s->slope_.Render<OSCILLATOR_SHAPE_SLOPE>(", "slope_render(&s->slope_,"
)
wsr = re.sub(r"lookup_table_i16_table\[([^]]+)\]", r"ws_table(\1)", wsr)
parts.append(
    "static void ws_render(WS *s,const Params *p,float *out,int size) {" + wsr + "}\n"
)
harm = read("plaits/dsp/oscillator/harmonic_oscillator.h")
hi = common(body(harm, "void Init()")).replace("num_harmonics", "12")
parts.append("static void harmonic_init(Harmonic *s) {" + hi + "}\n")
hr = body(harm, "void Render(").replace("num_harmonics", "12")
hr = hr.replace("stmlib::ParameterInterpolator am[12];", "Interp am[12];")
hr = hr.replace("am[i].Init(", "am[i]=interp(").replace("am[i].Next()", "next(&am[i])")
hr = common(hr) + "\nfor(int i=0;i<12;i++) commit(&am[i]);\n"
parts.append(
    "static void harmonic_render(Harmonic *s,int first_harmonic_index,float frequency,const float *amplitudes,float *out,int size) {"
    + hr
    + "}\n"
)
add = read("plaits/dsp/engine/additive_engine.cc")
parts.append(
    "static const int integer_harmonics[24]={" + ",".join(map(str, range(24))) + "};\n"
)
parts.append(
    "static void amplitudes_update(float centroid,float slope,float bumps,float *amplitudes,const int *harmonic_indices,int num_harmonics) {"
    + common(body(add, "void AdditiveEngine::UpdateAmplitudes("))
    + "}\n"
)
ar = body(add, "void AdditiveEngine::Render(")
ar = ar[: ar.index("  UpdateAmplitudes(", ar.index("harmonic_oscillator_[1].Render"))]
ar = common(ar).replace("UpdateAmplitudes(", "amplitudes_update(")
ar = ar.replace(
    "s->harmonic_oscillator_[0].Render<1>(",
    "harmonic_render(&s->harmonic_oscillator_[0],1,",
).replace(
    "s->harmonic_oscillator_[1].Render<13>(",
    "harmonic_render(&s->harmonic_oscillator_[1],13,",
)
parts.append(
    "static void additive_render(Additive *s,const Params *p,float *out,int size) {"
    + ar
    + "}\n"
)
gl = read("plaits/dsp/oscillator/grainlet_oscillator.h")
for name, sig, params in [
    ("grainlet_carrier", "inline float Carrier(", "float phase,float shape"),
    (
        "grainlet",
        "inline float Grainlet(",
        "float carrier_phase,float formant_phase,float shape,float bleed",
    ),
]:
    b = common(body(gl, sig)).replace("Carrier(", "grainlet_carrier(")
    parts.append("static float " + name + "(" + params + ") {" + b + "}\n")
parts.append(
    "static void grainlet_init(Grainlet *s) {" + common(body(gl, "void Init()")) + "}\n"
)
gr = common(body(gl, "void Render(")).replace("Grainlet(", "grainlet(")
parts.append(
    "static void grainlet_render(Grainlet *s,float carrier_frequency,float formant_frequency,float carrier_shape,float carrier_bleed,float *out,int size) {"
    + gr
    + "}\n"
)


def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


a = f32(f32(0.3736) * math.pi * math.pi * math.pi)
parts.append(f"""static void pole_set(Pole *s,float f) {{
 const float a={a!r}f; s->g_=f*(3.14159265358979323846f+a*f*f);
 s->gi_=1.0f/(1.0f+s->g_);
}}
""")
pole = body(read("stmlib/dsp/filter.h"), "inline float Process(float in)")
pole = pole[: pole.index("    if (mode")] + "return in-lp;\n"
parts.append("static float pole_high(Pole *s,float in) {" + common(pole) + "}\n")
ge = body(read("plaits/dsp/engine/grain_engine.cc"), "void GrainEngine::Render(")
ge = ge[: ge.index("  const float cutoff")]
ge = ge.replace(
    "const float ratio = SemitonesToRatio(", "const float f_ratio = SemitonesToRatio("
).replace("f1 * ratio", "f1 * f_ratio")
ge = common(ge).replace("aux", "s->scratch_")
for i in range(2):
    ge = ge.replace(
        f"s->grainlet_[{i}].Render(", f"grainlet_render(&s->grainlet_[{i}],"
    )
ge = ge.replace(
    "s->dc_blocker_[0].set_f<FREQUENCY_DIRTY>(", "pole_set(&s->dc_blocker_,"
).replace(
    "s->dc_blocker_[0].Process<FILTER_MODE_HIGH_PASS>(", "pole_high(&s->dc_blocker_,"
)
parts.append(
    "static void grain_render(Grain *s,const Params *p,float *out,int size) {"
    + ge
    + "}\n"
)
parts.append("""int bank_size(void) {return sizeof(Bank);}
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
""")
(HERE / "core.c").write_text("\n".join(parts))
(HERE / "core.h").write_text(
    notice
    + """
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
"""
)
controls = json.loads((HERE / "controls.json").read_text())
lines = [
    "// Generated from controls.json; do not edit.",
    f"#define BANK_MAX_MODEL {len(controls['model_names']) - 1}",
]
assert (
    controls["model"]["max_raw"]
    == (len(controls["model_names"]) - 1) * controls["model"]["scale"]
)
for name, item in controls.items():
    if isinstance(item, dict) and "dm" in item:
        lines.append(f"#define BANK_{name.upper()}_DM {item['dm']}")
        if "scale" in item:
            lines.append(
                f"#define BANK_{name.upper()}_FACTOR (1.0f/{item['scale']}.0f)"
            )
(HERE / "controls.h").write_text("\n".join(lines) + "\n")
print("Validated frozen source; generated WS/ADD/GRAIN MAIN, tables and controls.")
