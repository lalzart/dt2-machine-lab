# Capacity gap register

- Firmware allocator, bank ownership, placement and bandwidth are unverified. Emulator external arena is not a device allocation.
- Worst-case distinct sample storage is 6912048 bytes plus temporary float input up to 2304000 bytes. Multiple distinct banks need a total pool budget before firmware integration.
- Target analyzer mismatch remains outside this capacity slice; reader tests use host-analyzed banks. Count and load must use the same arithmetic/backend with unchanged input.
- Original sparse finite transport can end audibly before its output counter stops; matching the reference does not establish ideal end-of-sample or stretch quality.
- Stereo, loops, reverse, stock STRETCH listening and physical timing remain deferred. No hardware or firmware packaging in this slice.
