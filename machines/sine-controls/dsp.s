// Three trigger-latched controls: TUNE, LEN and LEV; plus TRIG note.
// Exploratory diagnostic DDS. DTII 1.16 only. Runs after the stock voice prologue.
// Entry I4 = voice record; original R4/R8/R12 arguments have been saved.
// Stock epilogue restores callee-saved registers. Data arena is emulator-only.
.section/pm seg_pmco;
.global sine_entry;
sine_entry:
    DM(-5, I6) = R0;
    R2 = I4;
    R1 = 0x2412cc;
    R2 = R2 - R1;
    R1 = 0;
    COMP(R2, R1);
    IF LT JUMP fallback;
    R1 = 15104;
    COMP(R2, R1);
    IF GE JUMP fallback;
    R0 = 0;
    R1 = 472;
find_voice:
    COMP(R2, R1);
    IF LT JUMP found_voice;
    R2 = R2 - R1;
    R0 = R0 + 1;
    JUMP find_voice;
found_voice:
    R1 = 0xfffffffe;
    R1 = R0 AND R1;
    R2 = 0x255970;
    .NOCOMPRESS;
    R1 = R1 + R2;
    .COMPRESS;
    I0 = R1;
    R1 = DM(I0, M5);
    R2 = 0xffff;
    R1 = R1 AND R2;
    R2 = 7;
    COMP(R1, R2);
    IF NE JUMP leave_sine;
    R1 = I4;
    R2 = 4;
    .NOCOMPRESS;
    R1 = R1 + R2;
    .COMPRESS;
    I1 = R1;
    R3 = 64;
    R1 = 2;
    COMP(R0, R1);
    IF GE JUMP zero_buffer;
    // Two lanes, separate phase/age/active words, identical source signal.
    R1 = LSHIFT R0 BY 5;
    R2 = 0x200f0100;
    .NOCOMPRESS;
    R1 = R1 + R2;
    .COMPRESS;
    I0 = R1;
    R2 = 1;
    DM(3, I0) = R2;
    // Per-voice latched trigger B is consumed by stock setup this frame.
    R1 = DM(0x24f0cc);
    R2 = LSHIFT R0 BY 3;
    R2 = -R2;
    R1 = LSHIFT R1 BY R2;
    R2 = 0xff;
    R1 = R1 AND R2;
    R2 = 0;
    COMP(R1, R2);
    IF EQ JUMP resume_voice;
    DM(0, I0) = R2;
    DM(1, I0) = R2;
    R2 = 1;
    DM(2, I0) = R2;
    // Working CPU frame, low halfwords. Track 1 only, matching the pilot scope.
    // Note 60 and TUNE 64.0 give A440. LUT index = note + tune - 55.
    R1 = DM(0x2558de);
    R2 = 0xffff;
    R1 = R1 AND R2;
    R4 = DM(0x2559b6);
    R4 = R4 AND R2;
    .NOCOMPRESS;
    R1 = R1 + R4;
    .COMPRESS;
    R2 = 14080;
    R1 = R1 - R2;
    R2 = 0;
    COMP(R1, R2);
    IF GE JUMP pitch_low_ok;
    R1 = 0;
pitch_low_ok:
    R2 = 32512;
    COMP(R1, R2);
    IF LE JUMP pitch_high_ok;
    R1 = R2;
pitch_high_ok:
    R2 = LSHIFT R1 BY -8;
    R2 = LSHIFT R2 BY 2;
    R4 = 0x200f0800;
    .NOCOMPRESS;
    R2 = R2 + R4;
    .COMPRESS;
    I2 = R2;
    F4 = DM(0, I2);
    F5 = DM(1, I2);
    R2 = 255;
    R1 = R1 AND R2;
    F1 = FLOAT R1;
    R2 = 0x3b800000;
    F1 = F1 * F2;
    F5 = F5 - F4;
    F5 = F5 * F1;
    F5 = F5 + F4;
    R5 = FIX F5;
    DM(4, I0) = R5;
    // Duration = LEN wire value * 25/32 samples; minimum 10 ms, maximum 500 ms.
    R1 = DM(0x2559c4);
    R2 = 0xffff;
    R1 = R1 AND R2;
    F1 = FLOAT R1;
    R2 = 0x3f480000;
    F1 = F1 * F2;
    R1 = FIX F1;
    R2 = 960;
    COMP(R1, R2);
    IF GE JUMP duration_low_ok;
    R1 = R2;
duration_low_ok:
    R2 = 48000;
    COMP(R1, R2);
    IF LE JUMP duration_high_ok;
    R1 = R2;
duration_high_ok:
    DM(5, I0) = R1;
    // Linear gain = LEV wire value / 32768 * 0.125, clamped at 0.125.
    R1 = DM(0x2559c8);
    R2 = 0xffff;
    R1 = R1 AND R2;
    R2 = 32768;
    COMP(R1, R2);
    IF LE JUMP level_ok;
    R1 = R2;
level_ok:
    F1 = FLOAT R1;
    R2 = 0x36800000;
    F1 = F1 * F2;
    DM(6, I0) = R1;
resume_voice:
    R1 = DM(2, I0);
    R2 = 0;
    COMP(R1, R2);
    IF EQ JUMP zero_buffer;
    R6 = DM(0, I0);
    R8 = DM(1, I0);
sample_loop:
    R2 = DM(5, I0);
    COMP(R8, R2);
    IF GE JUMP finished;
    R1 = LSHIFT R6 BY -24;
    R2 = LSHIFT R1 BY 2;
    R4 = 0x200f0400;
    .NOCOMPRESS;
    R2 = R2 + R4;
    .COMPRESS;
    I2 = R2;
    F0 = DM(I2, M5);
    R1 = R1 + 1;
    R2 = 255;
    R1 = R1 AND R2;
    R1 = LSHIFT R1 BY 2;
    .NOCOMPRESS;
    R1 = R1 + R4;
    .COMPRESS;
    I2 = R1;
    F1 = DM(I2, M5);
    R2 = 0xffffff;
    R2 = R6 AND R2;
    F2 = FLOAT R2;
    R9 = 0x33800000;
    F2 = F2 * F9;
    F7 = F1 - F0;
    F7 = F7 * F2;
    F7 = F7 + F0;
    R9 = 480;
    COMP(R8, R9);
    IF LT JUMP attack;
    R9 = DM(5, I0);
    R10 = 480;
    R9 = R9 - R10;
    COMP(R8, R9);
    IF GE JUMP release;
    R10 = 0x3f800000;
    JUMP envelope_done;
attack:
    F10 = FLOAT R8;
    R9 = 0x3b088889;
    F10 = F10 * F9;
    JUMP envelope_done;
release:
    R9 = DM(5, I0);
    R9 = R9 - R8;
    F10 = FLOAT R9;
    R9 = 0x3b088889;
    F10 = F10 * F9;
envelope_done:
    F7 = F7 * F10;
    R9 = DM(6, I0);
    F7 = F7 * F9;
    DM(I1, M6) = R7;
    R2 = DM(4, I0);
    .NOCOMPRESS;
    R6 = R6 + R2;
    .COMPRESS;
    R8 = R8 + 1;
    R3 = R3 - 1;
    IF NE JUMP sample_loop;
    DM(0, I0) = R6;
    DM(1, I0) = R8;
    JUMP render_done;
finished:
    R2 = 0;
    DM(2, I0) = R2;
zero_buffer:
    R7 = 0;
zero_loop:
    DM(I1, M6) = R7;
    R3 = R3 - 1;
    IF NE JUMP zero_loop;
render_done:
    // Record actual executions separately from signal state (outside both 32-byte lane states).
    R2 = DM(0x200f0180);
    R2 = R2 + 1;
    DM(0x200f0180) = R2;
    JUMP 0x1c524a;
leave_sine:
    R1 = 2;
    COMP(R0, R1);
    IF GE JUMP fallback;
    R1 = LSHIFT R0 BY 5;
    R2 = 0x200f0100;
    .NOCOMPRESS;
    R1 = R1 + R2;
    .COMPRESS;
    I0 = R1;
    R2 = DM(3, I0);
    R1 = 0;
    COMP(R2, R1);
    IF EQ JUMP fallback;
    DM(0, I0) = R1;
    DM(1, I0) = R1;
    DM(2, I0) = R1;
    DM(3, I0) = R1;
    R2 = I4;
    R1 = 4;
    .NOCOMPRESS;
    R2 = R2 + R1;
    .COMPRESS;
    I1 = R2;
    R2 = 0;
    R3 = 64;
leave_clear:
    DM(I1, M6) = R2;
    R3 = R3 - 1;
    IF NE JUMP leave_clear;
fallback:
    R0 = DM(-5, I6);
    // Original six displaced bytes are inserted here by the builder.
    NOP;
    NOP;
    NOP;
    JUMP 0x1c4f18;
