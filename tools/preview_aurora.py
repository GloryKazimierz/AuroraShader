"""Render a CPU mathematical aurora reference, not a Minecraft/GPU screenshot.

Run from this checkout: python -B tools/preview_aurora.py
Requires only Python's standard library and the independent validation reference.
Outputs one deterministic PNG under docs/images on the project drive.
"""
from pathlib import Path
import math
import struct
import zlib
from validate_aurora import aurora_result

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, GAP = 400, 300, 8
TIMES = (0, 50, 100)


def display_color(rgb):
    # Existing M8 default peak shoulder and display encoding, exposure zero.
    peak = max(rgb)
    if peak > .6:
        mapped = .6 + .4 * (1 - math.exp(-(peak-.6)/.4))
        rgb = tuple(c*mapped/peak for c in rgb)
    def encode(c):
        value = c*12.92 if c <= .0031308 else 1.055*c**(1/2.4)-.055
        return int(round(255*min(1,max(0,value))))
    return bytes(encode(c) for c in rgb)


def chunk(name, payload):
    return struct.pack('!I',len(payload)) + name + payload + struct.pack('!I',zlib.crc32(name+payload)&0xffffffff)


def main():
    total_width = len(TIMES)*WIDTH+(len(TIMES)-1)*GAP
    pixels = bytearray()
    for y in range(HEIGHT):
        pixels.append(0)  # PNG row filter: none.
        elevation = math.radians(75 - 70*(y+.5)/HEIGHT)
        for panel, seconds in enumerate(TIMES):
            if panel:
                pixels.extend(bytes((8,8,14))*GAP)
            for x in range(WIDTH):
                azimuth = math.radians(-65+130*(x+.5)/WIDTH)
                direction = (math.cos(elevation)*math.sin(azimuth), math.sin(elevation),
                             -math.cos(elevation)*math.cos(azimuth))
                # A fixed synthetic linear background intentionally isolates the ribbons.
                scene = (.003,.005,.016)
                rgb = aurora_result(direction,scene=scene,seconds=seconds)
                pixels.extend(display_color(rgb))
    assert len(pixels) == HEIGHT*(1+3*total_width)
    metadata = b'Description\0CPU mathematical reference only; not Minecraft, Iris or GPU output. Left: 0s; middle: 50s; right: 100s. No bloom, stars, geometry or fog.'
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR',struct.pack('!2I5B',total_width,HEIGHT,8,2,0,0,0))
    png += chunk(b'tEXt',metadata)
    png += chunk(b'IDAT',zlib.compress(bytes(pixels),9))
    png += chunk(b'IEND',b'')
    output = ROOT/'docs'/'images'/'aurora-math-preview.png'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(png)
    print('CPU mathematical reference only; no Minecraft/Iris/GPU execution.')
    print(output)


if __name__ == '__main__':
    main()
