/*
 * rt.c -- the four libc functions the Capicola port calls, for selcc builds.
 */
#include <stddef.h>

float fabsf(float x) { return x < 0.0f ? -x : x; }

/* tanf for the filters' cutoff warping only: x = pi/2 * fc, fc in [0, 1], so
   x in [0, pi/2]. Branch-free: tan(x) = sin(x) / cos(x), each from a Taylor
   polynomial on [0, pi/2] (error well under 1e-6 relative except as cos -> 0,
   where tan is large and the filters only use it as g/(1+g)). Called when a
   cutoff is set, never per sample. */
#ifndef RT_NO_TANF   /* the device build needs none: CC_SOURCE_ONLY has no filters */
float tanf(float x)
{
    const float x2 = x * x;
    const float s = x * (1.0f + x2 * (-1.0f / 6 + x2 * (1.0f / 120 + x2 * (-1.0f / 5040
                  + x2 * (1.0f / 362880 + x2 * (-1.0f / 39916800))))));
    const float c = 1.0f + x2 * (-0.5f + x2 * (1.0f / 24 + x2 * (-1.0f / 720
                  + x2 * (1.0f / 40320 + x2 * (-1.0f / 3628800 + x2 * (1.0f / 479001600))))));
    return s / c;
}
#endif

#ifdef RT_MEMSET_WORDS
/* the device build: every caller (cc_recorder_init, cc_analyzer_init) clears a
   word-aligned struct whose size is a multiple of 4 */
void *memset(void *p, int c, size_t n)
{
    unsigned int w = (unsigned char)c;
    w |= w << 8;
    w |= w << 16;
    unsigned int *q = (unsigned int *)p;
    for (n >>= 2; n; n--) *q++ = w;
    return p;
}
#else
void *memset(void *p, int c, size_t n)
{
    unsigned char *d = (unsigned char *)p;
    if ((((size_t)d | n) & 3u) == 0) {      /* aligned: a word at a time */
        unsigned int w = (unsigned char)c;
        w |= w << 8;
        w |= w << 16;
        unsigned int *q = (unsigned int *)p;
        for (n >>= 2; n; n--) *q++ = w;
        return p;
    }
    while (n--) *d++ = (unsigned char)c;
    return p;
}
#endif
