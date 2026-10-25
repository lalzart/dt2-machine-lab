# Track scope gap register

Hardware flash, physical timing/load, listening, external synchronization and
maximum simultaneous 16-track capacity are deferred. One keyboard arp follows
the selected track; pattern mode/rate settings remain shared rather than sixteen
independent arpeggiators. Flex retains its one shared recorder. No memory monitor
is included. Native emulator checks and package/reset gates cannot establish
flash safety or coupled physical cold boot.

The inherited snapshot has different stock filter state per track. Cross-track
bit-exact synthesis comparisons tap the raw machine output before those filters;
T1 full-frame parity and same-track mixed/solo comparisons are separate gates.
All exploratory failures remain in unique ignored runs, including the initially
incorrect cross-track post-filter comparator. No PCM tolerance is relaxed.

The ready CPU snapshot contains a copied stock seven-entry machine menu. It
cannot validate the already-existing extended Plaits menu. Preserve failed menu
probes as fixture limitations; the unlock is checked through the actual native
permission routine on all tracks. Native non-T1 arp panel/recording checks use
this fixture without changing its stock menu objects. Physical menu selection
remains part of the deferred device trial.
