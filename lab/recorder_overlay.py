"""Explicit byte-overlay to sector-overlay conversion at the eMMC model edge."""


def sector_overlay(byte_overlay, read, *, sectors=0x760000):
    converted = {}
    for offset, value in byte_overlay.items():
        if type(offset) is not int or not 0 <= offset < sectors * 512:
            raise ValueError("Invalid byte overlay offset")
        if type(value) is not int or not 0 <= value <= 255:
            raise ValueError("Invalid byte overlay value")
        sector = offset // 512
        if sector not in converted:
            converted[sector] = bytearray(read(sector, 512))
            if len(converted[sector]) != 512:
                raise ValueError("Incomplete base sector")
        converted[sector][offset % 512] = value
    return {sector: bytes(data) for sector, data in converted.items()}
