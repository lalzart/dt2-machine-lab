/* SPDX-License-Identifier: AGPL-3.0-only
 * Capicola-derived finite sample experiment. See NOTICE and contract/.
 */
#ifndef CAPICOLA_FINITE_H
#define CAPICOLA_FINITE_H
#define CAP_CAPACITY 4096
#define CAP_MAX_INPUT 48000
#define CAP_OK 0
#define CAP_INPUT_ERROR 1
#define CAP_OVERFLOW 2
#define CAP_CONTROL_ERROR 3

typedef struct {
    float value[CAP_CAPACITY];
    double time[CAP_CAPACITY];
    int count, frames, error;
    double ideal, actual, incoming;
    float pitch, advance, phase, increment;
    int leash, splicing, position, duration, active;
} CapState;

void cap_init(CapState *s);
int cap_load(CapState *s, const float *input, int frames);
int cap_start(CapState *s, float pitch, float advance, int leash);
void cap_stop(CapState *s);
void cap_process(CapState *s, float *out, int frames);
float cap_tick(CapState *s);
#endif
