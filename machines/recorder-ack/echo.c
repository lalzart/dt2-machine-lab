/* Diagnostic receipt only. Never authorizes sample or identity retirement. */
#include "protocol.h"
typedef unsigned U;
#define Q ((volatile U *)REQUEST_STATE)
#define T ((volatile U *)DSP_STATE)

void echo_emit(U reply) {
    U rev=Q[0], epoch=Q[1], generation=Q[2], seq=Q[3];
    U i,word,byte;
    if(!rev || Q[0]!=rev) return;
    if(reply!=0x266220u && reply!=0x267220u &&
       reply!=0x28266220u && reply!=0x28267220u) { T[5]++; return; }
    if(T[0]!=rev) { T[1]=0; T[0]=rev; }
    i=T[1];
    word=i<16 ? epoch : i<32 ? generation : seq;
    byte=(i<<2)|((word>>((i&15u)*2u))&3u);
    if(Q[0]!=rev) return;
    *(volatile unsigned char *)(reply+DSP_REPLY_BYTE)=byte;
    T[1]=(i+1u==FRAGMENTS) ? 0u : i+1u;
    T[2]++; T[3]=reply; T[4]=rev;
}
