#!/usr/bin/env python3
"""Compare a rebuilt U-Boot image against the original vendor image.

usage: python3 -I compare.py ORIGINAL.bin REBUILT.bin
"""
import re
import struct
import sys


def strings(buf, n=4):
    return set(m.decode('latin-1') for m in re.findall(rb'[\x20-\x7e]{%d,}' % n, buf))


def commands(strs):
    # U-Boot help lines look like "name    - description"
    return {m.group(1) for s in strs if (m := re.match(r'^([a-z_][a-z0-9_.]*) +- ', s))}


def find_all(buf, pat):
    out, i = [], 0
    while (j := buf.find(pat, i)) >= 0:
        out.append(j)
        i = j + 1
    return out


def ddr_cfg1(buf):
    """MT7628 start.S loads DDR_CFG1 via `lui t6,HI ; ori t6,t6,LO`."""
    hits = []
    for i in range(0, len(buf) - 8, 4):
        a, b = struct.unpack_from('<II', buf, i)
        if a >> 16 == 0x3c0e and b >> 16 == 0x35ce:   # lui t6 / ori t6,t6
            hits.append((a & 0xffff) << 16 | (b & 0xffff))
    return hits


DDR_SIZES = {0x222A3323: 'DDR2 128M', 0x222e2323: 'DDR2 256M', 0x22322323: 'DDR2 512M',
             0x22362323: 'DDR2 1024M', 0x223a2323: 'DDR2 2048M',
             0x33322434: 'DDR1 512M', 0x33362434: 'DDR1 1024M'}

CHIPS = {'MX25L25635E': 0x2019c220, 'W25Q256FV': 0x40190000, 'W25M512JV': 0x71190000}


def chip_entry(buf, jedec):
    offs = find_all(buf, struct.pack('<I', jedec))
    if not offs:
        return None
    jed, sec, ns = struct.unpack_from('<III', buf, offs[0])
    return (jed, sec, ns, buf[offs[0] + 12])


def link_base(buf):
    his = {}
    for i in range(0, len(buf) - 4, 4):
        (w,) = struct.unpack_from('<I', buf, i)
        if w >> 26 == 0x0f:                             # lui
            hi = w & 0xffff
            if hi in (0xbc00, 0xbfc0):
                his[hi] = his.get(hi, 0) + 1
    return his


def main(orig_path, new_path):
    o, n = open(orig_path, 'rb').read(), open(new_path, 'rb').read()
    so, sn = strings(o), strings(n)
    print(f"size        orig={len(o)}  ours={len(n)}  ({100*len(n)/len(o):.1f}%)")
    for label, f in (('prompt', lambda s: sorted(x for x in s if re.match(r'^(MT|RT)\d{4}[A-Z]? # $', x))),):
        print(f"{label:11} orig={f(so)}  ours={f(sn)}")
    print(f"link base   orig={ {hex(k): v for k, v in link_base(o).items()} }  "
          f"ours={ {hex(k): v for k, v in link_base(n).items()} }")
    do, dn = ddr_cfg1(o), ddr_cfg1(n)
    print(f"DDR_CFG1    orig={[f'{x:#010x} {DDR_SIZES.get(x, "?")}' for x in do]}")
    print(f"            ours={[f'{x:#010x} {DDR_SIZES.get(x, "?")}' for x in dn]}  "
          f"{'MATCH' if do == dn else 'DIFF'}")
    for name, jed in CHIPS.items():
        eo, en = chip_entry(o, jed), chip_entry(n, jed)
        print(f"chip {name:12} {'MATCH' if eo == en else 'DIFF'}  orig={eo} ours={en}")
    co, cn = commands(so), commands(sn)
    print(f"commands    orig-only={sorted(co - cn)}  ours-only={sorted(cn - co)}")
    print(f"strings     common={len(so & sn)}  orig-only={len(so - sn)}  ours-only={len(sn - so)}")


if __name__ == '__main__':
    main(*sys.argv[1:3])
