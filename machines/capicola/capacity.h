/* SPDX-License-Identifier: AGPL-3.0-only
 * Capicola-derived twelve-second experiment. See NOTICE and capacity-contract/.
 */
#ifndef CAPICOLA_CAPACITY_H
#define CAPICOLA_CAPACITY_H
#define CAP_MAX_INPUT 576000
#define CAP_CAPACITY (CAP_MAX_INPUT+4)
#define CAP_OK 0
#define CAP_INPUT_ERROR 1
#define CAP_OVERFLOW 2
#define CAP_CONTROL_ERROR 3

typedef struct {
    float *value;
    int *whole;
    unsigned *fraction;
    int capacity, count, frames, error;
    unsigned generation;
} CapBank;

typedef struct {
    const CapBank *bank;
    unsigned generation;
    int ideal_w, actual_w, incoming_w;
    unsigned ideal_f, actual_f, incoming_f;
    unsigned pitch_q, advance_q;
    float pitch, advance, phase, increment;
    int leash, splicing, position, duration, active;
} CapState;

/* Init once before bind/load. Storage and bank must outlive attached readers.
 * Bind/load are serialized control operations, never concurrent with render.
 * Arrays must be distinct, aligned and sized to capacity. No hidden allocation.
 */
void cap_bank_init(CapBank *b);
int cap_bank_bind(CapBank *b,float *values,int *whole,unsigned *fraction,int capacity);
int cap_measure(const float *input,int frames); /* count or negative error */
int cap_load(CapBank *b,const float *input,int frames);
void cap_init(CapState *s);
void cap_attach(CapState *s,const CapBank *b);
int cap_start(CapState *s,float pitch,float advance,int leash);
void cap_stop(CapState *s);
float cap_tick(CapState *s);
void cap_process(CapState *s,float *out,int frames);
#endif
