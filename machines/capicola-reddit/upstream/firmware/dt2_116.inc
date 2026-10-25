| derived from irpina/digihealth (os153.inc), GPL-2.0-or-later, used here under GPL-3.0 within an AGPL-3.0-or-later project
| (via angellinares/dn2_firmware_explore csrc/usbprobe/dn2_111.inc)
|
| Digitakt II MAIN OS 1.16: the stock routines, sites and data the probe uses.
| Each was found by the signature of its Digitone II 1.11 counterpart; most sit
| 0x1974 below it. build.py guards every one against the stock image, and on
| 1.17 writes build/dt2_fw.inc with each moved through fwver.A().

        | ---- the SysEx router, and its reply path ---------------------------
        .equ ROUTER,      0x4011fcfa    | (msg, len, source): F0 7E aside, then F0 00 20 3C
        .equ ROUTER_HOOK, 0x4011fd26    | lea 0x4021e11a,%a3 -- 6 bytes, before the compare
        .equ ELK_HDR,     0x4021e11a    | F0 00 20 3C, what the hook's lea loads
        .equ SYSEX_SEND,  0x40121a4a    | bool (buf, len, abort*, port); port 2 = USB
        .equ PORT_USB,    2

        | ---- the ColdFire <-> SHARC link, plain on-chip SRAM ----------------
        .equ DSP_REPLY,   0x8000488c    | the SHARC's reply, copied in each frame (2748 B)
