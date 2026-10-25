/* SPDX-License-Identifier: AGPL-3.0-only
 * OS1.16 native planar mono/stereo sample adapter. See source-contract/.
 */
static unsigned source_select(unsigned track,unsigned channel,unsigned *source,unsigned *frames) {
    *source=0;*frames=0;
    if(word(0x255970u+track*2u)!=2)return 9;
    unsigned slot=(unsigned)word(0x2559bcu+track*0x60u);
    if(slot>=1024u)return 2;
    volatile unsigned *entry=(volatile unsigned *)(0x257810u+slot*20u);
    unsigned left=entry[0],right=entry[1],bytes=entry[2],rate=entry[3],stereo=entry[4]&255u;
    if(!bytes)return 1;
    if(stereo>1u || (stereo ? left==right : left!=right))return 3;
    if(rate!=48000u)return 4;
    if(bytes>CAP_MAX_INPUT*2u)return 5;
    if(bytes<282u)return 6;
    if((left&1u) || (right&1u) || (bytes&1u)
       || left>=CAP_POOL_END-CAP_POOL_BASE || right>=CAP_POOL_END-CAP_POOL_BASE
       || bytes>CAP_POOL_END-CAP_POOL_BASE-left
       || bytes>CAP_POOL_END-CAP_POOL_BASE-right)return 7;
    *source=CAP_POOL_BASE+(channel ? right:left);*frames=bytes/2u;return 0;
}
