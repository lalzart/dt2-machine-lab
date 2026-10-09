/* SPDX-License-Identifier: AGPL-3.0-only */
#define CAP_TARGET 1
#include "capacity.c"
#include "prepare.c"
void kernel(int *cmd) {
    CapState *s=(CapState *)0x200c1000;
    CapBank *b=(CapBank *)0x200c1100;
    CapPrepare *p=(CapPrepare *)0x200c1800;
    if(cmd[0]==0) {cap_bank_init(b);cap_prepare_init(p,b);cap_init(s);}
    if(cmd[0]==1) cap_prepare_begin(p,(const short *)0x200e8000,cmd[1],cmd[2],(unsigned)cmd[3]);
    if(cmd[0]==2) cap_prepare_step(p,(unsigned)cmd[3],cmd[1]);
    if(cmd[0]==3) cap_prepare_storage(p,(float *)0x83000000,(int *)(0x83000000+4*cmd[1]),(unsigned *)(0x83000000+8*cmd[1]),cmd[1]);
    if(cmd[0]==4) cap_prepare_cancel(p);
    if(cmd[0]==5) {cap_attach(s,b);cap_start(s,1.1f,0.7f,128);}
    if(cmd[0]==6) cap_process(s,(float *)0x200e0400,cmd[1]);
    cmd[4]=p->phase;cmd[5]=p->index;cmd[6]=p->needed;cmd[7]=b->count;
}
