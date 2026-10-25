# SONG recording indicator — OS1.16

The optional `--recording-led` device profile builds on the working R7 Sketch
profile. It substitutes the stock steady-red value `0x11` for logical SONG LED
5 (UART index 4) only when BUF PHASE is 2, its latched recorder controller is
nonzero, and the native recorder state getter also reports 2 (recording).
Waiting for BAR, processing/publication, completion, refusal, cancellation and
ordinary recorder captures retain stock SONG output. Visibility of Sketch and
the selected track do not control the indicator.

`lab/sketch_led.py` owns this display-only adapter. Its single authenticated hook
is at the stock LED output entry `0x40133d64`, before the native output lock or
queue operation. Every other logical LED and every inactive request follows the
displaced stock entry. The active SONG path calls the same stock entry with a
copied red argument; the caller's original stack/arguments are preserved.
The ordinary compositor subsequently restores its desired output when capture
ends. No additional recorder state, cached LED value, timer, service loop, job,
memory allocation or transport action is introduced.

The wrapper uses vacant space at Sketch +0x7800/+0x7900 inside the existing
reservation. All inherited initialized writes, hooks, backend state layout and
DSP remain exact to R7. Disabled builds reproduce R7 byte for byte. The optional
build flag preserves earlier profiles; it is not another user preference.

The existing controls remain FUNC+SONG for recording/finish while stopped,
and FUNC+RECORD for COPY through the FREEZE backend. This indicator follows
actual BUF recording state, not a particular button press.

The panel map and color encoding reference is the upstream OS1.16 LED sweep
(`devices/digitakt-ii-leds.toml` and finding 19), checked against the stock entry
bytes in this stage. `0x11` is the value used for stock RECORD red. Native panel
UART output establishes the requested value, not the physical LED color or
timing; see the stage report for actual checks and hardware limits.
