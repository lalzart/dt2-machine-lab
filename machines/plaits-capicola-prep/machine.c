/* Serialized preparation entry for emulator integration; not a stock scheduler. */
#include "../plaits-capicola/machine.c"
#include "../capicola/prepare.c"
/* cmd: operation, source address, source frames, stride, count/budget.
 * Source and storage belong to the caller; cancel before replacing either.
 * op0 initializes only once; op1 begin, op2 bounded step, op3 bind, op4 cancel.
 * Returns phase, required keys, processed frames in cmd[5..7]. */
void cap_service(unsigned *cmd) {
    CapPrepare *p=(CapPrepare *)0x200e4400;
    CapBank *b=(CapBank *)0x200e4100;
    CapHandoff *h=(CapHandoff *)0x200e4000;
    if(cmd[0]==0) {h->ready=0;cap_bank_init(b);cap_prepare_init(p,b);}
    else if(cmd[0]==1) {
        h->ready=0;
        h->source=cmd[1];
        cap_prepare_begin(p,(const short *)cmd[1],(int)cmd[2],(int)cmd[3],cmd[1]);
    } else if(cmd[0]==2) cap_prepare_step(p,cmd[1],(int)cmd[4]);
    else if(cmd[0]==3) {
        unsigned capacity=cmd[4];
        cap_prepare_storage(p,(float *)CAP_BANK_BASE,(int *)(CAP_BANK_BASE+4*capacity),
                            (unsigned *)(CAP_BANK_BASE+8*capacity),(int)capacity);
    } else cap_prepare_cancel(p);
    h->generation=b->generation;
    h->ready=p->phase==CAP_PREP_READY;
    cmd[5]=p->phase;cmd[6]=p->needed;cmd[7]=p->index;
}
