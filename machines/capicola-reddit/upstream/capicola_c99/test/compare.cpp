// Sample-for-sample comparison: Capicola's C++ KeyframeRecorder vs the C99 port.
//
//   c++ -std=c++17 -O2 -ffp-contract=off -I../../../capicola/lib -I.. compare.cpp ../capicola.c -o compare
//
// Both sides get the same input, the same block size and the same parameter
// changes at the same block boundaries. Reports, per scenario, the largest
// absolute difference and the first differing sample.
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <vector>
#include "KeyframeRecorder.h"
extern "C" {
#include "capicola.h"
}

static constexpr int kRing = 1 << 16;
static capicola::KeyframeRecorder<kRing> ref;     // static: zero-initialised, as on the module
static cc_keyframe storage[kRing];
static cc_recorder port;

static uint32_t rng = 12345;
static float noise() { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (rng / 4294967296.0f) * 2 - 1; }

static std::vector<float> test_signal(int n)
{
    std::vector<float> x(n);
    for (int i = 0; i < n; i++) {
        double t = (double)i / 48000, tb = fmod(t, 0.5), th = fmod(t, 0.125);
        x[i] = (float)(0.5 * exp(-tb * 20) * sin(2 * M_PI * (50 + 200 * exp(-tb * 40)) * tb)
                       + 0.1 * exp(-th * 80) * noise()
                       + 0.1 * (sin(2 * M_PI * 220 * t) + sin(2 * M_PI * 277 * t) + sin(2 * M_PI * 330 * t)));
    }
    return x;
}

struct Diff { double max = 0; long first = -1; long n = 0; };

static void compare(Diff &d, const float *a, const float *b, int n, long at)
{
    for (int i = 0; i < n; i++) {
        double e = std::fabs((double)a[i] - (double)b[i]);
        if (e > d.max) d.max = e;
        if (e != 0 && d.first < 0) d.first = at + i;
    }
    d.n += n;
}

int main()
{
    const int B = 64;
    const float pitches[] = {1.0f, 1.5f, 0.75f, 2.0f, 0.5f, 1.25f};
    const float stretches[] = {1.0f, 0.5f, 0.25f, 0.8f, 0.33f};

    // ---- A: live effect ---------------------------------------------------
    {
        std::vector<float> x = test_signal(48000 * 8);
        ref.Init(nullptr);
        cc_recorder_init(&port, storage, kRing);
        auto both = [&](auto f_ref, auto f_port) { f_ref(); f_port(); };
        both([&] { ref.SetGrainFade(960); ref.SetGrainLeash(128); ref.SetTransientThreshold(2.0f); ref.SetTkeoCutoff(0.0014f); },
             [&] { cc_recorder_set_fade(&port, 960); cc_recorder_set_leash(&port, 128);
                   cc_recorder_set_transient_threshold(&port, 2.0f); cc_recorder_set_tkeo_cutoff(&port, 0.0014f); });
        ref.SubmitRequest(capicola::Request::LIVE_EFFECT);
        cc_recorder_submit(&port, CC_REQ_LIVE_EFFECT);
        Diff d;
        float oa[B], ob[B];
        for (int k = 0, blk = 0; k + B <= (int)x.size(); k += B, blk++) {
            if (blk % 375 == 0) {   // every 0.5 s
                float p = pitches[(blk / 375) % 6], s = stretches[(blk / 375) % 5];
                ref.SetGrainPitch(p); ref.SetGrainStretch(s);
                cc_recorder_set_pitch(&port, p); cc_recorder_set_stretch(&port, s);
            }
            ref.ProcessBlock(&x[k], oa, B);
            cc_recorder_process(&port, &x[k], ob, B);
            compare(d, oa, ob, B, k);
        }
        printf("A live effect : %ld samples, max |diff| %.3g, first diff at %ld; transients ref %u port %u\n",
               d.n, d.max, d.first, ref.TransientCount(), port.transient_count);
    }

    // ---- B: record, then play back stretched and pitched, with slices ----
    {
        std::vector<float> x = test_signal(48000 * 3);
        ref.Init(nullptr);
        cc_recorder_init(&port, storage, kRing);
        ref.SubmitRequest(capicola::Request::RECORD);
        cc_recorder_submit(&port, CC_REQ_RECORD);
        Diff d;
        float oa[B], ob[B];
        for (int k = 0; k + B <= (int)x.size(); k += B) {
            ref.ProcessBlock(&x[k], oa, B);
            cc_recorder_process(&port, &x[k], ob, B);
            compare(d, oa, ob, B, k);
        }
        ref.SubmitRequest(capicola::Request::STOP_REC);
        cc_recorder_submit(&port, CC_REQ_STOP_REC);
        ref.ProcessBlock(&x[0], oa, B);
        cc_recorder_process(&port, &x[0], ob, B);
        ref.SetGrainStretch(0.5f); ref.SetGrainPitch(1.25f); ref.SetGrainFade(960);
        cc_recorder_set_stretch(&port, 0.5f); cc_recorder_set_pitch(&port, 1.25f); cc_recorder_set_fade(&port, 960);
        ref.SubmitRequest(capicola::Request::PLAY);
        cc_recorder_submit(&port, CC_REQ_PLAY);
        std::vector<float> silence(B, 0.0f);
        for (int blk = 0; blk < 48000 * 5 / B; blk++) {
            if (blk % 200 == 199) { ref.SubmitRequest(capicola::Request::SLICE); cc_recorder_submit(&port, CC_REQ_SLICE); }
            ref.ProcessBlock(silence.data(), oa, B);
            cc_recorder_process(&port, silence.data(), ob, B);
            compare(d, oa, ob, B, (long)blk * B);
        }
        printf("B record+play : %ld samples, max |diff| %.3g, first diff at %ld\n", d.n, d.max, d.first);
    }
    return 0;
}
