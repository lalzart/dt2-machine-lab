#include "core.c"
void kernel(float *job) {
 Bank *state=(Bank *)0x200e0100;
 if(job[4]!=0.0f) bank_init(state,(int)job[5]);
 bank_render(state,(const Params *)job,(int)job[6],job[7],(float *)0x200e0400,12);
}
