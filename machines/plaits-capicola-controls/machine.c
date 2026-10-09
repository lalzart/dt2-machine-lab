/* SPDX-License-Identifier: AGPL-3.0-only */
static void cap_panel_controls(void);
#define CAP_UPDATE_CONTROLS() cap_panel_controls()
#include "../plaits-capicola-auto/machine.c"

static void cap_panel_controls(void) {
 volatile CapHandoff *h=HANDOFF;
 float semitones=(float)(word(BANK_NOTE_DM)+word(BANK_TUNE_DM))*(1.0f/256.0f)-124.0f;
 CONSTRAIN(semitones,-12.0f,12.0f);
 h->pitch=ratio(semitones);
 unsigned rate=(unsigned)word(BANK_MODEL_DM);
 if(rate>32512u) rate=32512u;
 h->advance=rate<=16384u ? 0.5f+(float)rate*(1.0f/32768.0f)
     : 1.0f+(float)(rate-16384u)*(1.0f/16128.0f);
 float gain=(float)word(BANK_LEVEL_DM)*BANK_LEVEL_FACTOR;
 CONSTRAIN(gain,0.0f,0.125f);
 h->gain=gain;h->leash=128;
}
