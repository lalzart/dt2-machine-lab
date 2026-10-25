"""Named OS 1.16 CPU placement constants; other releases require a new profile."""

BASE = 0x40000400
STOCK_SHA = "57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d"
R3_SHA = "6f5a9df5f1bf17c002c7755e1682051aff9e2d990238ec62722c5a459e8e9543"
# Exact zero intervals from the pinned 1.16 deep-reference scan. Deliberately
# exclude Plaits' entire 0x403117c4..0x40312000 allocation and reset-copy data.
# These are candidate locations until the dynamic placement checks pass.
CANDIDATE_GAPS = (
    (0x402E4A24, 0x402E4DA4),
    (0x402E5B5C, 0x402E5EDC),
    (0x402FE45C, 0x402FE5DC),
    (0x402FDE60, 0x402FDF66),
    (0x402FDA60, 0x402FDB5E),
    (0x402FD660, 0x402FD75E),
    (0x40300AE0, 0x40300BDE),
    (0x402FD45C, 0x402FD556),
    (0x402FD85C, 0x402FD956),
    (0x402FDC5C, 0x402FDD56),
    (0x402FE05C, 0x402FE156),
    (0x403010DC, 0x403011D6),
    (0x403014DC, 0x403015D6),
    (0x402FCE64, 0x402FCF5E),
    (0x402FD05C, 0x402FD156),
    (0x402FD264, 0x402FD35E),
    (0x403016E4, 0x403017DE),
    (0x403018DC, 0x403019D6),
)
# Additional candidates from the same exact OS 1.16 caves-small.json scan.
# Optional ownership experiment only; boot/asset-path validation is separate.
OWNERSHIP_GAPS = (
    (0x402FCC5C, 0x402FCD34),
    (0x40301CDC, 0x40301DB4),
    (0x402FCA98, 0x402FCB5C),
    (0x40301B18, 0x40301BDC),
    (0x402FC718, 0x402FC75C),
    (0x403020DC, 0x40302134),
    (0x402FC85C, 0x402FC8A8),
    (0x40301F98, 0x40301FDC),
)
