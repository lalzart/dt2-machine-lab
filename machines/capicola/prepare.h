/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef CAPICOLA_PREPARE_H
#define CAPICOLA_PREPARE_H
#include "capacity.h"
#define CAP_PREP_IDLE 0
#define CAP_PREP_COUNT 1
#define CAP_PREP_NEEDS_STORAGE 2
#define CAP_PREP_WRITE 3
#define CAP_PREP_READY 4
#define CAP_PREP_FAILED 5
#define CAP_PREP_BUDGET 256
/* Caller owns immutable input and nonaliasing arrays. Serialize with rendering.
 * Initialize bank/worker once; cancel BEFORE releasing/replacing their storage.
 * Token identifies an input lifetime, not its contents. No allocator is hidden. */
typedef struct {
    CapBank *bank;
    const short *input;
    unsigned token, generation;
    int frames, stride, phase, index, count, needed, wp;
    float raw[8], deriv, last_value;
    int last_whole;
    unsigned last_fraction;
} CapPrepare;
void cap_prepare_init(CapPrepare *p, CapBank *b);
void cap_prepare_cancel(CapPrepare *p);
int cap_prepare_begin(CapPrepare *p,const short *input,int frames,int stride,unsigned token);
int cap_prepare_storage(CapPrepare *p,float *value,int *whole,unsigned *fraction,int capacity);
int cap_prepare_step(CapPrepare *p,unsigned token,int budget);
#endif
