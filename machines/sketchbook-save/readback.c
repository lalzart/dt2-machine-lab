/* Original Sketchbook transport. No allocation, audio mutation or file I/O.
 * protocol.h is generated from the local implementation contract. */
#include "protocol.h"
typedef unsigned U;
typedef unsigned char B;
#define S ((volatile U *)DSP_STATE)
#define Q ((volatile U *)LP0_REQUEST)

static U valid_header(U slot, U start, U size, U len, U rate, U stereo) {
    volatile U *p = (volatile U *)(SLOTS + slot * 20u);
    U lo, hi, left, right;
    if (!slot || slot > 1023u || start < 1024u || !size) return 0;
    lo = start - 1024u;
    if (lo >= POOL_BYTES || size > POOL_BYTES - lo) return 0;
    hi = lo + size;
    left = p[0]; right = p[1];
    if (!len || (len & 1u) || rate != 48000u || stereo > 1u) return 0;
    if (p[2] != len || p[3] != rate || *(volatile B *)(SLOTS + slot*20u + 16u) != stereo) return 0;
    if (left < lo || left >= hi || len > hi-left) return 0;
    if (stereo && (right < lo || right >= hi || len > hi-right)) return 0;
    return 1;
}

void readback_latch(void) {
    U i, serial=Q[4], pos=Q[11], count=Q[12], len=Q[8], stereo=Q[10];
    U close=Q[1]==2u;
    U bad=Q[0]!=TAG || (!close && Q[1]!=1u) || Q[13]!=~serial || Q[14] || Q[15]!=MARKER;
    U total;
    if (!Q[2] || !serial || serial <= S[4] || S[0]==0xffffffffu) bad=1;
    if (Q[3]<0x7ffb0001u || Q[3]>0x7ffbffffu) bad=1;
    if (close) { if (count || pos) bad=1; }
    else {
    if (!count || count>CHUNK || len>1920000u || stereo>1u) bad=1;
    total=len;
    if (stereo) total=len*2u;
    if (pos>=total || count>total-pos) bad=1;
    if (!valid_header(Q[5],Q[6],Q[7],len,Q[9],stereo)) bad=1;
    }
    if (bad) { S[20]++; return; }
    for (i=1;i<16;i++) S[i]=Q[i];
    S[16]=0; S[17]=close ? 2u : 0u;
    if (!close) for (i=0;i<5;i++) S[24+i]=*(volatile U *)(SLOTS+Q[5]*20u+i*4u);
    S[0]++; /* Commit only after the complete immutable request/header. */
}

static void put32(volatile B *p, U offset, U value) {
    p[(offset+0u)^1u]=(B)(value>>24);
    p[(offset+1u)^1u]=(B)(value>>16);
    p[(offset+2u)^1u]=(B)(value>>8);
    p[(offset+3u)^1u]=(B)value;
}

void readback_emit(U reply) {
    volatile B *out;
    volatile U *p;
    U rev=S[0], cursor=S[16], count, status=0, i, b, at, word, channel, frame, h;
    U serial=S[4], epoch=S[2], token=S[3], position=S[11];
    if (reply!=0x266220u && reply!=0x267220u && reply!=0x28266220u && reply!=0x28267220u) return;
    out=(volatile B *)(reply+TAIL);
    put32(out,0,0);
    if (!rev) return;
    /* Explicit negative-control latch; zero in every normal initialized build.
     * Suppress data generation while still permitting the CLOSE fence. */
    if (S[31] && S[1]!=2u) return;
    if (S[17]==2u) { status=2u; count=0; }
    else {
    p=(volatile U *)(SLOTS+S[5]*20u);
    for (i=0;i<5;i++) if (p[i]!=S[24+i]) status=1;
    if (!valid_header(S[5],S[6],S[7],S[8],S[9],S[10])) status=1;
    count=S[12]-cursor;
    if (count>PAYLOAD) count=PAYLOAD;
    if (status) count=0;
    }
    put32(out,4,serial); put32(out,8,epoch); put32(out,12,token);
    put32(out,16,position); put32(out,20,cursor); put32(out,24,count); put32(out,28,status);
    for (i=0;i<count;i++) {
        at=position+cursor+i;
        word=at>>1;
        channel=0; frame=word;
        if (S[10]) { channel=word&1u; frame=word>>1; }
        b=*(volatile B *)(WINDOW+S[24+channel]+frame*2u+((at&1u)^1u));
        out[(HEADER+i)^1u]=(B)b;
    }
    h=2166136261u;
    for (i=0;i<32u;i++) {
        b=i<4u ? (MAGIC>>(24u-i*8u))&255u : out[i^1u];
        h=(h^b)*16777619u;
    }
    for (i=0;i<count;i++) h=(h^out[(HEADER+i)^1u])*16777619u;
    put32(out,32,h);
    if (S[0]!=rev) return;
    put32(out,0,MAGIC);
    cursor+=count;
    if (cursor==S[12]) cursor=0;
    S[16]=cursor; S[17]=status; S[19]++;
}
