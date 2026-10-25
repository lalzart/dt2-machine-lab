/* Diagnostic only. Permission is zero even when observed DSP roots are clear. */
#include "protocol.h"
typedef unsigned U;
#define G ((volatile U *)STATE)
#define S ((volatile U *)REQUEST_STATE)
#define ALIAS (G+64)

static U sync_request(void) {
    U rev=S[0],i;
    if(G[0]!=rev) {
        G[10]=0;
        for(i=0;i<33;i++) ALIAS[i]=0;
        G[6]=0; G[7]=0; G[8]=0; G[9]=0;
        G[34]=G[1];
        G[0]=rev;
    }
    return rev;
}

static U touches(U offset,U bytes,U lo,U hi) {
    return bytes && offset<hi && offset+bytes>lo;
}

void gate_control(void) {
    U rev=sync_request();
    if(G[1]==0xffffffffu) G[29]=1;
    else G[1]++;
    G[2]=rev; G[3]=1;
}

void gate_lookup(U slot) {
    U rev=sync_request(),lo,hi,left,right,bytes;
    volatile U *p;
    if(!rev || slot>=1025) return;
    lo=S[4]-POOL_START; hi=lo+S[5];
    p=(volatile U *)(SLOTS+slot*20u);
    left=p[0];right=p[1];bytes=p[2];
    if(left>=POOL_END-POOL_START || right>=POOL_END-POOL_START ||
       bytes>POOL_END-POOL_START-left || bytes>POOL_END-POOL_START-right) return;
    if(touches(left,bytes,lo,hi) || touches(right,bytes,lo,hi)) {
        ALIAS[slot>>5]|=1u<<(slot&31u);
        if(G[6]==0xffffffffu) G[29]=1; else G[6]++;
        G[7]=G[1]; G[8]=slot; G[9]=rev;
    }
}

static U selected(U base) {
    U track,mask=0,slot;
    for(track=0;track<16;track++) {
        slot=*(volatile unsigned short *)(base+0xe0u+track*0x60u);
        if(slot<1025 && (ALIAS[slot>>5]&(1u<<(slot&31u)))) mask|=1u<<track;
    }
    return mask;
}

void gate_frame(void) {
    U rev=sync_request(),lo,hi,i,left,right,bytes,unknown=0;
    U logical=0,owner=0,frozen=0,preview=0,other=0;
    U param,bank0,bank1,reasons=0;
    if(!rev) return;
    G[10]=0;
    if(G[3] && G[2]==rev && !G[29]) {
        G[4]=G[1]; G[5]=rev;
    }
    G[3]=0;
    lo=S[4]-POOL_START;hi=lo+S[5];
    for(i=0;i<1025;i++) {
        volatile U *p=(volatile U *)(SLOTS+i*20u);
        left=p[0];right=p[1];bytes=p[2];
        if(!bytes) continue;
        if(left>=POOL_END-POOL_START || right>=POOL_END-POOL_START ||
           bytes>POOL_END-POOL_START-left || bytes>POOL_END-POOL_START-right) {
            unknown++;continue;
        }
        if(touches(left,bytes,lo,hi) || touches(right,bytes,lo,hi)) {
            ALIAS[i>>5]|=1u<<(i&31u);
            if(i>=300 && i<=303) logical++;
            else if(i>=304 && i<=311) owner++;
            else if(i>=312 && i<=319) frozen++;
            else if(i==1024) preview++;
            else other++;
        }
    }
    param=selected(PARAM);bank0=selected(COMMAND0);bank1=selected(COMMAND1);
    if(S[13]) reasons|=1u;
    if(S[14]) reasons|=2u;
    if(logical || owner || frozen || preview || other) reasons|=4u;
    if(param || bank0 || bank1) reasons|=8u;
    if(G[5]!=rev || G[4]<=G[34]) reasons|=16u;
    if(unknown) reasons|=32u;
    if(S[9]!=rev || S[0]!=rev) reasons|=64u;
    if(G[29]) reasons|=128u;
    G[11]=S[1];G[12]=S[2];G[13]=S[3];G[14]=reasons;
    G[15]=S[13];G[16]=S[14];G[17]=logical;G[18]=owner;
    G[19]=frozen;G[20]=preview;G[21]=other;
    G[22]=param;G[23]=bank0;G[24]=bank1;G[25]=unknown;
    G[26]=reasons ? 1u : 2u;
    G[27]=0; /* No allocator permission exists in this experiment. */
    G[28]=UNKNOWN_OWNERSHIP;
    G[30]++;
    G[31]=*(volatile unsigned short *)(PARAM+0x22u) |
          *(volatile unsigned short *)(PARAM+0x24u) |
          *(volatile unsigned short *)(PARAM+0x26u) |
          *(volatile unsigned short *)(PARAM+0x28u) |
          *(volatile unsigned short *)(PARAM+0x2au);
    if(S[0]!=rev) { G[10]=0; return; }
    G[10]=rev;
}
