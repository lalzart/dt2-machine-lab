/* Isolated diagnostic observer. Every status is advisory: never RETIRE_OK.
 * protocol.h is generated from the frozen machine-lab contract. */
#include "protocol.h"
typedef unsigned U;
#define S ((volatile U *)STATE)
#define Q ((volatile U *)REQUEST)

void observer_latch(void) {
    U epoch=Q[2], id=Q[3], seq=Q[4], offset=Q[5], bytes=Q[6];
    U bad=Q[0]!=TAG || Q[1]!=VERSION || Q[7]!=~seq || Q[15]!=MARKER;
    U i;
    for(i=8;i<15;i++) if(Q[i]) bad=1;
    if(!epoch || !seq || id<FIRST_ID || id>LAST_ID) bad=1;
    if(offset<POOL_START || offset>=POOL_END || !bytes) bad=1;
    if(((offset-POOL_START)&8191u) || (bytes&8191u)) bad=1;
    if(bytes>POOL_END-offset || S[0]==0xffffffffu) bad=1;
    if(epoch<S[1] || (epoch==S[1] && seq<S[3])) bad=1;
    if(bad) { S[7]++; return; }
    if(epoch==S[1] && seq==S[3]) {
        if(id==S[2] && offset==S[4] && bytes==S[5]) S[6]++;
        else S[7]++;
        return;
    }
    S[9]=0;
    S[1]=epoch; S[2]=id; S[3]=seq; S[4]=offset; S[5]=bytes;
    S[0]++;  /* Commit request last. Only the serialized LP0 callback writes it. */
}

static U overlaps(U offset,U bytes,U lo,U hi) {
    return offset<hi && bytes && offset+bytes>lo;
}

void observer_frame(void) {
    U rev=S[0],epoch=S[1],id=S[2],seq=S[3],lo=S[4]-POOL_START;
    /* Force a concrete spill: the pinned compiler otherwise omitted the
     * hi store when inlining the overlap predicate (retained failed control). */
    volatile U hi=lo+S[5];
    U begin=WINDOW+lo,end=WINDOW+hi;
    U active=0,retained=0,roots=0,unknown=0,i;
    if(!rev) return;
    for(i=0;i<32;i++) {
        U base=VOICE_BASE+i*VOICE_STRIDE;
        U pointer=*(volatile U *)base;
        if(pointer>=begin && pointer<end) {
            if(*(volatile unsigned char *)(base+0x1b8u)) active|=1u<<i;
            else retained|=1u<<i;
        }
        /* Explicit cooperative race seam in this isolated build. This is a
         * native request replacement mid-scan, not a modeled hardware ISR. */
        if(i==16 && S[FAULT_WORD]) { S[FAULT_WORD]=0; observer_latch(); }
    }
    for(i=0;i<1025;i++) {
        volatile U *slot=(volatile U *)(SLOTS+i*20u);
        U left=slot[0],right=slot[1],bytes=slot[2];
        if(!bytes) continue;
        if(left>=POOL_END-POOL_START || right>=POOL_END-POOL_START ||
           bytes>POOL_END-POOL_START-left || bytes>POOL_END-POOL_START-right) {
            unknown++; continue;
        }
        if(overlaps(left,bytes,lo,hi) || overlaps(right,bytes,lo,hi)) roots++;
    }
    if(S[0]!=rev) { S[9]=0; S[18]++; return; }
    S[8]++;
    S[10]=epoch; S[11]=id; S[12]=seq;
    S[13]=active; S[14]=retained; S[15]=roots; S[20]=unknown;
    S[16]=active ? 3u : unknown ? 4u : roots ? 2u : 1u;
    S[17]=S[8];
    S[9]=rev; /* Commit observation last; never release an allocation. */
}
