/* SPDX-License-Identifier: AGPL-3.0-only
 * Standalone emulator experiment only; no firmware voice hooks.
 */
#define CAP_TARGET 1
#include "split.c"
void kernel(int *job) {
    CapState *s=(CapState *)0x200c1000;
    float *out=(float *)0x200e0400;
    float *input=(float *)0x200e1000;
    float *controls=(float *)0x200e0100;
    if(job[0]==0) {
        job[4]=sizeof(CapState);
        job[5]=(int)((char *)&s->count-(char *)s);
        job[6]=(int)((char *)&s->active-(char *)s);
    } else if(job[0]==1) {
        job[4]=cap_load(s,input,job[1]);
    } else if(job[0]==2) {
        job[4]=cap_start(s,controls[0],controls[1],job[2]);
    } else if(job[0]==3) {
        cap_process(s,out,job[1]);
        job[4]=s->position;
    } else if(job[0]==4) {
        cap_stop(s);
    }
}
