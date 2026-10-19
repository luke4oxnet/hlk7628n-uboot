#!/usr/bin/env python3
"""Function-by-function match of a rebuilt U-Boot against the original image.

Splits our build into functions using System.map, masks the instruction fields
that depend on link layout (lui/addiu/ori immediates, gp-relative loads/stores,
j/jal targets), then searches the original image for each masked function body.
Same source + same compiler => match; anything that does not match differs.

usage: python3 -I funcdiff.py ORIGINAL.bin OURS_uboot.bin OURS_System.map [TEXT_BASE]
"""
import struct
import sys

GP, T9 = 28, 25
LOADSTORE = (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2a, 0x2b, 0x2e)  # incl. lwl/lwr/swl/swr
LOOSE = False      # also mask every load/store offset (%lo(sym) via GOT-page regs)


def mask(w):
    op = w >> 26
    rs = (w >> 21) & 31
    if op in (2, 3):                              # j / jal: target is layout
        return w & 0xfc000000
    if op in (0x0f, 0x09, 0x0d):                  # lui, addiu, ori: addresses/offsets
        return w & 0xffff0000
    if op in LOADSTORE and (LOOSE or rs in (GP, T9)):
        return w & 0xffff0000                     # lb/lh/lw/lbu/lhu/sb/sh/sw offsets
    return w


def words(buf):
    n = len(buf) // 4
    return list(struct.unpack('<%dI' % n, buf[:n * 4]))


def load_funcs(mapfile, base, size):
    syms = []
    for line in open(mapfile):
        parts = line.split()
        if len(parts) == 3 and parts[1] in 'Tt':
            a = int(parts[0], 16)
            if base <= a < base + size:
                syms.append((a, parts[2]))
    syms.sort()
    funcs = []
    for i, (a, name) in enumerate(syms):
        end = syms[i + 1][0] if i + 1 < len(syms) else None
        if end and end > a:
            funcs.append((name, a - base, end - a))
    return funcs


def main(orig_path, ours_path, mapfile, base=0xBC000000):
    o = open(orig_path, 'rb').read().rstrip(b'\xff')
    n = open(ours_path, 'rb').read()
    om = b''.join(struct.pack('<I', mask(w)) for w in words(o))
    funcs = load_funcs(mapfile, base, len(n))

    matched, differ = [], []
    for name, off, size in funcs:
        body = n[off:off + size]
        mb = b''.join(struct.pack('<I', mask(w)) for w in words(body))
        hits = []
        i = om.find(mb)
        while i >= 0 and len(hits) < 3:
            if i % 4 == 0:
                hits.append(i)
            i = om.find(mb, i + 1)
        (matched if hits else differ).append((name, size, hits))

    tot = sum(s for _, s, _ in matched + differ)
    msz = sum(s for _, s, _ in matched)
    print(f"functions: {len(matched) + len(differ)}  matched: {len(matched)}  "
          f"differ/missing-in-orig: {len(differ)}")
    print(f"code bytes matched: {msz}/{tot} ({100 * msz / tot:.1f}%)")
    print("\n--- functions with NO match in original (largest first) ---")
    for name, size, _ in sorted(differ, key=lambda x: -x[1]):
        print(f"  {size:6d}  {name}")
    amb = [(nm, s, h) for nm, s, h in matched if len(h) > 1]
    if amb:
        print(f"\n({len(amb)} small functions matched at >1 place — ambiguous but present)")


def locate(orig_path, ours_path, mapfile, name, base=0xBC000000):
    """Find where function `name` from our build best aligns in the original."""
    o = open(orig_path, 'rb').read().rstrip(b'\xff')
    n = open(ours_path, 'rb').read()
    fn = {f[0]: f for f in load_funcs(mapfile, base, len(n))}[name]
    ow = [mask(w) for w in words(o)]
    fw = [mask(w) for w in words(n[fn[1]:fn[1] + fn[2]])]
    best = (0, None)
    for start in range(len(ow) - len(fw) + 1):
        if ow[start] != fw[0]:
            continue
        score = sum(1 for k in range(len(fw)) if ow[start + k] == fw[k])
        if score > best[0]:
            best = (score, start)
    score, start = best
    print(f"{name}: ours @ {base + fn[1]:#x} ({len(fw)} insns); best orig @ "
          f"{(base + start * 4) if start is not None else None:#x}  "
          f"{score}/{len(fw)} masked insns equal")
    return base + fn[1], len(fw), (base + start * 4) if start is not None else None


def load_dis(path):
    import re
    d = {}
    for line in open(path):
        m = re.match(r'\s*([0-9a-f]{8}):\t([0-9a-f]{8}) \t(.*)', line)
        if m:
            d[int(m.group(1), 16)] = m.group(3).strip()
    return d


def show_diff(orig_path, ours_path, mapfile, orig_dis, ours_dis, name):
    """Print only the instructions of `name` that differ from the original."""
    ours_at, n, orig_at = locate(orig_path, ours_path, mapfile, name)
    if orig_at is None:
        return
    o = open(orig_path, 'rb').read()
    u = open(ours_path, 'rb').read()
    od, ud = load_dis(orig_dis), load_dis(ours_dis)
    for k in range(n):
        oa, ua = orig_at + 4 * k, ours_at + 4 * k
        ow = struct.unpack_from('<I', o, oa - 0xBC000000)[0]
        uw = struct.unpack_from('<I', u, ua - 0xBC000000)[0]
        if ow != uw:
            tag = 'layout' if mask(ow) == mask(uw) else 'CODE  '
            print(f"  {tag} +{4*k:#05x}  orig {oa:#x}: {od.get(oa,''):<36} ours {ua:#x}: {ud.get(ua,'')}")


def seq_diff(orig_path, ours_path, mapfile, orig_dis, ours_dis, name, orig_len=None):
    """Align `name` against the original with difflib and print the edit blocks."""
    import difflib
    ours_at, n, orig_at = locate(orig_path, ours_path, mapfile, name)
    if orig_at is None:
        return
    o = open(orig_path, 'rb').read()
    u = open(ours_path, 'rb').read()
    m = orig_len // 4 if orig_len else n + 256
    ow = [mask(w) for w in words(o[orig_at - 0xBC000000:orig_at - 0xBC000000 + 4 * m])]
    uw = [mask(w) for w in words(u[ours_at - 0xBC000000:ours_at - 0xBC000000 + 4 * n])]
    od, ud = load_dis(orig_dis), load_dis(ours_dis)
    sm = difflib.SequenceMatcher(None, ow, uw, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        print(f"--- {tag}: orig[{i1}:{i2}] ({i2-i1} insns) vs ours[{j1}:{j2}] ({j2-j1} insns)")
        for k in range(i1, min(i2, i1 + 12)):
            a = orig_at + 4 * k
            print(f"    - orig {a:#x}: {od.get(a, '')}")
        for k in range(j1, min(j2, j1 + 12)):
            a = ours_at + 4 * k
            print(f"    + ours {a:#x}: {ud.get(a, '')}")


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--seqdiff':
        # --seqdiff ORIG OURS MAP ORIG.dis OURS.dis NAME [ORIG_LEN_BYTES]
        LOOSE = True
        seq_diff(a[1], a[2], a[3], a[4], a[5], a[6], int(a[7], 0) if len(a) > 7 else None)
        sys.exit(0)
    if a and a[0] == '--loose':
        LOOSE = True
        a = a[1:]
    if a and a[0] == '--locate':
        for nm in a[4:]:
            locate(a[1], a[2], a[3], nm)
        sys.exit(0)
    if a and a[0] == '--diff':
        # --diff ORIG OURS MAP ORIG.dis OURS.dis NAME...
        for nm in a[6:]:
            show_diff(a[1], a[2], a[3], a[4], a[5], nm)
        sys.exit(0)
    main(a[0], a[1], a[2], int(a[3], 16) if len(a) > 3 else 0xBC000000)
