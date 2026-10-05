// Isolated emulator kernel ABI. This is not the DTII firmware voice ABI.
#include "core.c"

void kernel(float *job) {
  VA *state=(VA *)0x200e0100;
  float *out=(float *)0x200e0400;
  float *aux=(float *)0x200e0500;
  if(job[4]!=0.0f) va_init(state);
  va_render(state,(const Params *)job,out,aux,12);
}
