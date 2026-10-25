| derived from irpina/digihealth (sysinfo.s), GPL-2.0-or-later, used here under GPL-3.0 within an AGPL-3.0-or-later project
| (via angellinares/dn2_firmware_explore csrc/usbprobe/probe.S)
|
| A read-only USB SysEx probe for the Digitakt II (OS 1.16 and 1.17, build.py's DT2_FW): F0 00 20 3C 7D 00 <pack7 body> F7.
|
|   request  <pack7: u16 seq, u8 cmd, args>
|   reply    <pack7: u16 seq, u8 cmd|0x80, u8 status, payload>
|   status   0 ok, 1 refused argument, 2 unknown command
|
|   HELLO 1  -> u16 proto, u32 DSP reply word 0 (the SHARC handler's cycles), the tag
|   PEEK  3  u32 addr, u16 len (1..PEEK_MAX) -> u32 addr, the bytes
|
| The DN2 probe, cut down: no STATS, so no ISR or context-switch hook and no
| second code cave; the only hook is the SysEx router's. The request and reply
| buffers live in a second free run of MAIN OS (BUF, set by the build) instead
| of RAM above the BSS, which on this image ends 1.5 MB below the stack top.
| There is no write command, and none can be added by a request.

#include "dt2_fw.inc"            /* build.py: dt2_116.inc on the chosen OS */

        .equ PROTO,       0x0201           | DT2 probe, protocol 1
        .equ C_HELLO,     1
        .equ C_PEEK,      3
        .equ PEEK_MAX,    256
        .equ NRANGES,     2
        .equ RQ_MAX,      16

        .equ rq,  BUF                   | a request, unpacked (RQ_MAX + 4)
        .equ rp,  BUF + 0x20            | a reply before packing: 4 + 4 + PEEK_MAX
        .equ tx,  BUF + 0x130           | a reply as sent: 6 + 302 + 1
        .equ BUF_END, BUF + 0x268

        .text
        .globl  probe_start
probe_start:

| At ROUTER_HOOK (was: lea ELK_HDR,%a3), once per F0 message other than F0 7E,
| in the MIDI input task. a0 = a1 = the message, F0..F7; d1 = its length;
| d2 = where it came from (2 or 4 USB, the stock MidiRpc test at 0x4011efb8).
| a0, a1, d1, d2 must survive; d0, d3, a2 are reloaded by the router right
| after. The router then drops device 0x7D itself (only 0x00-0x17 route, at
| 0x4011fd4a), so the stock reply path is untouched.
        .globl  probe_rx
probe_rx:
        lea     -16(%sp), %sp
        movem.l %d1-%d2/%a0-%a1, (%sp)
        moveq   #8, %d0
        cmp.l   %d0, %d1
        blt.s   9f                      | header + one byte + F7 at least
        moveq   #PORT_USB, %d0          | USB only
        cmp.l   %d0, %d2
        beq.s   1f
        moveq   #4, %d0
        cmp.l   %d0, %d2
        bne.s   9f
1:      lea     probe_hdr, %a2          | F0 00 20 3C 7D 00
        moveq   #6, %d3
2:      move.b  (%a0)+, %d0
        cmp.b   (%a2)+, %d0
        bne.s   9f
        subq.l  #1, %d3
        bne.s   2b
        move.l  %d1, %d0                | a0 = the body; d0 = its length
        subq.l  #7, %d0
        moveq   #-9, %d3                | the last byte is F7?
        cmp.b   0(%a0,%d0.l), %d3
        bne.s   9f
        bsr.w   diag_rx
9:      movem.l (%sp), %d1-%d2/%a0-%a1
        lea     16(%sp), %sp
        lea     ELK_HDR, %a3            | the instruction this replaced
        rts

| diag_rx(a0 body, d0 its length): unpack, answer, send. A body too short
| to carry seq and cmd is ignored: no reply.
diag_rx:
        lea     -32(%sp), %sp
        movem.l %d2-%d7/%a2-%a3, (%sp)
        lea     rq, %a3                 | the request; seq at +1 puts PEEK's u32 aligned
        lea     1(%a3), %a1
        moveq   #RQ_MAX, %d1
        bsr.w   unpack7
        move.l  %d0, %d5                | request bytes
        moveq   #3, %d1
        cmp.l   %d1, %d5
        blt.w   99f
        lea     rp, %a2
        move.b  1(%a3), (%a2)           | seq, a byte at a time: rq+1 is odd
        move.b  2(%a3), 1(%a2)
        moveq   #0, %d2
        move.b  3(%a3), %d2             | cmd
        move.l  %d2, %d0
        bset    #7, %d0
        move.b  %d0, 2(%a2)
        clr.b   3(%a2)                  | status: ok
        lea     4(%a2), %a1             | the payload
        subq.l  #C_HELLO, %d2
        beq.s   10f
        subq.l  #C_PEEK - C_HELLO, %d2
        beq.s   30f
        moveq   #2, %d0                 | unknown command
        move.b  %d0, 3(%a2)
        bra.w   80f

10:     move.w  #PROTO, %d0             | HELLO: u16 proto, u32 DSP word 0, the tag
        move.w  %d0, (%a1)+
        move.l  DSP_REPLY, (%a1)+
        lea     probe_tag, %a0
11:     move.b  (%a0)+, %d0
        move.b  %d0, (%a1)+
        bne.s   11b
        bra.w   80f

30:     moveq   #9, %d1                 | PEEK: seq, cmd, u32 addr, u16 len
        cmp.l   %d1, %d5
        blt.s   39f
        move.l  4(%a3), %d3             | address
        moveq   #0, %d4
        move.w  8(%a3), %d4             | length
        beq.s   39f
        cmpi.l  #PEEK_MAX, %d4
        bhi.s   39f
        lea     peek_ranges, %a0        | inside one range, its end included
        moveq   #NRANGES, %d2
31:     move.l  %d3, %d1
        sub.l   (%a0), %d1              | the offset into this range
        bcs.s   32f                     | below it
        add.l   %d4, %d1                | where the read ends
        move.l  4(%a0), %d0
        sub.l   (%a0), %d0              | the range's size
        cmp.l   %d0, %d1
        bls.s   33f
32:     addq.l  #8, %a0
        subq.l  #1, %d2
        bne.s   31b
        bra.s   39f
33:     move.l  %d3, (%a1)+
        movea.l %d3, %a0
34:     move.b  (%a0)+, %d0
        move.b  %d0, (%a1)+
        subq.l  #1, %d4
        bne.s   34b
        bra.s   80f
39:     moveq   #1, %d0                 | refused
        move.b  %d0, 3(%a2)

80:     move.l  %a1, %d0                | send: the reply ends at a1
        sub.l   %a2, %d0
        movea.l %a2, %a0
        lea     tx+6, %a1
        bsr.w   pack7
        lea     tx, %a0
        move.l  probe_hdr, %d1          | F0 00 20 3C
        move.l  %d1, (%a0)
        move.w  probe_hdr+4, %d1        | 7D 00
        move.w  %d1, 4(%a0)
        addq.l  #6, %d0
        moveq   #-9, %d1                | F7
        move.b  %d1, 0(%a0,%d0.l)
        addq.l  #1, %d0
        pea     2.w                     | port: USB (PORT_USB)
        clr.l   -(%sp)                  | no abort flag
        move.l  %d0, -(%sp)
        pea     tx
        jsr     SYSEX_SEND
        lea     16(%sp), %sp
99:     movem.l (%sp), %d2-%d7/%a2-%a3
        lea     32(%sp), %sp
        rts

| unpack7(a0 src, d0 len, a1 dst, d1 room) -> d0 bytes out. MidiRpc's
| packing: each group of up to 7 bytes follows a byte whose bit 6-k is byte
| k's bit 7.
unpack7:
        lea     -16(%sp), %sp
        movem.l %d2-%d5, (%sp)
        move.l  %d0, %d2                | bytes left
        moveq   #0, %d3                 | bytes out
1:      tst.l   %d2
        beq.s   9f
        moveq   #0, %d4
        move.b  (%a0)+, %d4             | the group's top bits
        subq.l  #1, %d2
        moveq   #7, %d0
2:      tst.l   %d2
        beq.s   9f
        add.l   %d4, %d4                | this byte's top bit to bit 7
        move.b  (%a0)+, %d5
        subq.l  #1, %d2
        bclr    #7, %d5
        btst    #7, %d4
        beq.s   3f
        bset    #7, %d5
3:      cmp.l   %d1, %d3
        bcc.s   4f                      | no room: drop it
        move.b  %d5, (%a1)+
        addq.l  #1, %d3
4:      subq.l  #1, %d0
        bne.s   2b
        bra.s   1b
9:      move.l  %d3, %d0
        movem.l (%sp), %d2-%d5
        lea     16(%sp), %sp
        rts

| pack7(a0 src, d0 len, a1 dst) -> d0 bytes out.
pack7:
        lea     -16(%sp), %sp
        movem.l %d2-%d4/%a2, (%sp)
        move.l  %a1, %d4                | where the output starts
1:      tst.l   %d0
        beq.s   9f
        movea.l %a1, %a2                | the group's header byte
        addq.l  #1, %a1
        moveq   #0, %d2                 | header
        moveq   #0x40, %d3              | its bit for this byte
2:      move.b  (%a0)+, %d1
        btst    #7, %d1
        beq.s   3f
        or.l    %d3, %d2
3:      bclr    #7, %d1
        move.b  %d1, (%a1)+
        subq.l  #1, %d0
        beq.s   4f
        lsr.l   #1, %d3
        bne.s   2b
4:      move.b  %d2, (%a2)
        bra.s   1b
9:      move.l  %a1, %d0
        sub.l   %d4, %d0
        movem.l (%sp), %d2-%d4/%a2
        lea     16(%sp), %sp
        rts

| ---- constants -------------------------------------------------------------
        .balign 4
peek_ranges:
        .long   0x40000000, 0x48000000  | DDR, 128 MB
        .long   0x80000000, 0x80010000  | the 64 KB on-chip SRAM (the SHARC reply copy is here)
probe_hdr:
        .byte   0xF0, 0x00, 0x20, 0x3C, 0x7D, 0x00
        .balign 4
        .globl  probe_tag
probe_tag:                              | the build's tag, NUL-terminated;
        .skip   TAG_BYTES               | filled in by build.py
        .globl  probe_end
probe_end:
