/* SPDX-License-Identifier: AGPL-3.0-only
 * Standalone test wrapper; all addresses are emulator-only reservations.
 */
#define CAP_TARGET 1
#include "capacity.c"
void kernel(int *job) {
    CapState *s=(CapState *)0x200c1000;
    CapBank *b=(CapBank *)0x200c1100;
    float *controls=(float *)0x200e0100;
    float *out=(float *)0x200e0400;
    if(job[0]==0) {
        job[4]=sizeof(CapState);job[5]=sizeof(CapBank);
        job[6]=(int)((char *)&s->active-(char *)s);
    } else if(job[0]==1) {
        cap_bank_init(b);
        job[4]=cap_bank_bind(b,(float *)0x83000000,
            (int *)(0x83000000+4*job[1]),(unsigned *)(0x83000000+8*job[1]),job[1]);
        if(!job[4]) {
            b->count=job[1];b->frames=job[2];b->error=0;
            b->generation=(unsigned)job[3];
            cap_attach(s,b);
        }
    } else if(job[0]==2) {
        job[4]=cap_start(s,controls[0],controls[1],job[2]);
        job[5]=s->duration;
    } else if(job[0]==3) {
        cap_process(s,out,job[1]);job[4]=s->position;
    } else if(job[0]==4) {
        cap_stop(s);
    } else if(job[0]==6) {
        job[4]=cap_load(b,0,0);
    } else if(job[0]==7) {
        job[4]=exact_duration(job[1],(unsigned)(controls[1]*16777216.0f));
    }
}
