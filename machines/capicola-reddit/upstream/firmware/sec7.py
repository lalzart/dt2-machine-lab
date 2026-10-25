"""Section 7 of the Digitakt II image (the SHARC's boot stream; the same in OS 1.16
and 1.17): where its code loads, and the one stock change the diag build makes.

Boot-stream byte strings are memory order (little-endian 16-bit parcels), as
dnfw's bootstream.read_span returns them.
"""

SECTION7 = 7
LOAD_ALIAS = 0x28000000                       # L1's boot-stream load address alias
BLOCK1_LAST_STOCK = 0x2D7563                  # last loaded/filled byte of L1 block 1
PAD_TO = 0x2DF000                             # our L1 code's zero padding ends here

# the per-frame handler's reply-word-0 store; the diag build NOPs it so word 0
# carries the generator's counters (dt2probe.py capload reads them)
STORE_SW, STORE_STOCK = 0x1C75C4, bytes.fromhex("7299")   # dm (i4,m5)=r2
NOP16 = bytes.fromhex("0100")


def sw_to_load(sw: int) -> int:
    """an L1 short-word address's place in the boot stream"""
    return LOAD_ALIAS + 2 * sw
