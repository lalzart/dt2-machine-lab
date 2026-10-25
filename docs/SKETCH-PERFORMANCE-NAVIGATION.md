# Sketch performance navigation — R7 / OS1.16

The user reports that the R6 repeat-recording repair works on their device
(no installed-hash readback). The next requested changes are the visible
BAR/NOW preference, bare trig exits, and FUNC+SONG from ordinary track pages.
R6 sources and its package are preserved separately.

Encoder F always displays the remembered BAR/NOW preference, including while
stopped. The former stopped title hard-coded NOW, hiding valid changes to F.
The idle stopped hint explains that stopped capture starts immediately; the
preference is used when the sequencer runs. Active capture still locks the
setting. It remains one volatile value shared across buffers, separate from
NORMAL recorder DEST, with BAR as the boot default.

In the current stopped-recording performance profile, all sixteen bare trig
presses and TRK close only a topmost Sketch view before native input routing.
The original key event continues to stock performance/step handling. Repeats,
releases, a held SONG-owned gesture, and a foreign modal retain ownership.
This supersedes the historical bare-trig-keeps-Sketch behavior for this profile;
the older profile bytes and frozen backend proposal file remain unchanged.

FUNC+SONG continues to use Sketch's remembered BUF, independent of the current
track's sample assignment. This task tests that existing global binding from
native performance pages. The extra keyboard attempt did not establish entry
into the keyboard view and is not coverage. This does not introduce an alternative
recorder, bypass protected dialogs, change FREEZE, or change allocation/storage.

See the stage REPORT.txt, results.json, native screenshots, and package manifest
for actual validation and hardware limits. No hardware transfer is authorized.
