/* Restricted private-slot sealing; no PCM free and no general RETIRE_OK. */
#include "protocol.h"
typedef unsigned U;
#define Q ((volatile U *)REQUEST_STATE)
#define G ((volatile U *)GATE_STATE)
#define T ((volatile U *)DSP_STATE)
#define SLOTS_P ((volatile U *)SLOTS)

static U overlaps(U offset,U bytes,U lo,U hi) {
    return bytes && offset<hi && offset+bytes>lo;
}

void seal_emit(U reply) {
    U rev=Q[0],i,slot=0,count=0,lo,left,right,bytes,word;
    volatile U *p,*entry;
    volatile U hi;
    if(!rev || Q[9]!=rev) return;
    if(T[0]!=rev) { T[0]=rev;T[1]=0;T[2]=0;T[5]=0; }
    if(!T[1]) {
        if(G[10]!=rev || G[5]!=rev || G[4]<=G[34] || G[29]) { T[5]=1;return; }
        if(G[15] || G[16] || G[17] || G[19] || G[20] || G[21] ||
           G[22] || G[23] || G[24] || G[25]) { T[5]=2;return; }
        lo=Q[4]-POOL_START;hi=lo+Q[5];
        for(i=PRIVATE_FIRST;i<=PRIVATE_LAST;i++) {
            p=(volatile U *)(SLOTS+i*20u);
            left=p[0];right=p[1];bytes=p[2];
            if(overlaps(left,bytes,lo,hi) || overlaps(right,bytes,lo,hi)) {
                slot=i;count++;
            }
        }
        if(count==1 && G[18]==1) {
            entry=T+64+(slot-PRIVATE_FIRST)*8u;
            entry[0]=Q[1];entry[1]=Q[2];entry[2]=Q[4];entry[3]=Q[5];
            entry[4]=slot;entry[5]=1;
            p=(volatile U *)(SLOTS+slot*20u);
            if(Q[0]!=rev) return;
            for(i=0;i<5;i++) p[i]=0;
            T[3]++;T[6]=slot;
        } else if(count==0 && G[18]==0) {
            /* Retry after lost completion requires an exact native seal record. */
            for(i=0;i<8;i++) {
                entry=T+64+i*8u;
                if(entry[5]==1 && entry[0]==Q[1] && entry[1]==Q[2] &&
                   entry[2]==Q[4] && entry[3]==Q[5]) { count++;slot=entry[4]; }
            }
            if(count!=1) { T[5]=3;return; }
            T[6]=slot;
        } else { T[5]=4;return; }
        if(Q[0]!=rev) return;
        T[2]=0;T[1]=rev;T[7]++;
    }
    if(reply!=0x266220u && reply!=0x267220u &&
       reply!=0x28266220u && reply!=0x28267220u) { T[5]=5;return; }
    i=T[2];
    word=i<16 ? Q[1] : i<32 ? Q[2] : i<48 ? Q[3] : RTOK;
    if(Q[0]!=rev || T[1]!=rev) return;
    *(volatile unsigned char *)(reply+DSP_REPLY_BYTE)=(i<<2)|((word>>((i&15u)*2u))&3u);
    T[2]=(i+1u==FRAGMENTS) ? 0u : i+1u;
    T[4]++;
}
