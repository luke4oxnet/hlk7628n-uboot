#!/bin/sh
# Build this U-Boot tree inside the 32-bit Debian container (see docker/Dockerfile).
# Normally invoked through docker/build.sh, not by hand.
#
#   /src                  : this repository (read-only)
#   /out                  : output directory
#   /opt/buildroot-gcc342 : Ralink SDK GCC 3.4.2 toolchain
#   /overlay              : optional files copied over the tree before building
#
# Env:
#   VARIANT    rom (default) = flash image, linked at TEXT_BASE from .config (0xBC000000);
#                              runs the CPU-PLL / DDR init itself
#              ram           = RAM-test image, linked at 0x80200000; skips CPU-PLL / DDR init
#                              so an already-running U-Boot can start it with `go`
#   DEFCONFIG  board config to use (default: .config = HLK-7628N)
#   TC_PREFIX  cross-compiler prefix (default: /opt/buildroot-gcc342/bin/mipsel-linux-)
set -eu

VARIANT="${VARIANT:-rom}"
DEFCONFIG="${DEFCONFIG:-.config}"
TC_PREFIX="${TC_PREFIX:-/opt/buildroot-gcc342/bin/mipsel-linux-}"

echo "=============================================="
echo " HLK-7628N U-Boot build  variant=${VARIANT}  config=${DEFCONFIG}"
echo "=============================================="

if [ ! -x "${TC_PREFIX}gcc" ]; then
    echo "toolchain not found at ${TC_PREFIX}gcc" >&2
    exit 1
fi
"${TC_PREFIX}gcc" --version | head -1

# 1. Fresh working copy (keeps the checkout clean; skip VCS and build outputs).
rm -rf /work/src
mkdir -p /work/src
tar -C /src --exclude=./.git --exclude=./out --exclude=./.toolchain -cf - . | tar -C /work/src -xf -
cd /work/src

if [ -d /overlay ]; then
    echo "--- applying overlay from /overlay ---"
    cp -av /overlay/. /work/src/ | sed 's/^/    overlay: /'
fi

# 2. Save the board config now: `make rt2880_config` depends on `unconfig`,
#    which deletes .config.
cp "${DEFCONFIG}" /work/seed.config

# 3. RAM-test variant: same sources, linked to run from SDRAM at 0x80200000.
#    start.S only runs the CPU-PLL/DDR init when TEXT_BASE is a flash address.
if [ "${VARIANT}" = "ram" ]; then
    sed -i -e 's/^# UBOOT_RAM is not set/UBOOT_RAM=y/' \
           -e 's/^UBOOT_ROM=y/# UBOOT_ROM is not set/' \
           -e 's/^TEXT_BASE=.*/TEXT_BASE=0x80200000/' /work/seed.config
fi
grep -E "^(UBOOT_RAM|UBOOT_ROM|TEXT_BASE)=" /work/seed.config | sed 's/^/    config: /'

chmod +x mkconfig *.sh 2>/dev/null || true
chmod +x scripts/* tools/* 2>/dev/null || true

# 4. include/asm and include/asm-mips are two distinct, committed directories;
#    mkconfig (written for a tree where asm is a symlink) would replace asm with
#    a symlink to asm-mips. Leave an existing asm directory alone.
if ! grep -q 'if \[ ! -d asm \]' mkconfig; then
    perl -0pi -e 's/^rm -f asm\nln -s asm-\$2 asm\n/if [ ! -d asm ]; then rm -f asm; ln -s asm-\$2 asm; fi\n/m' mkconfig
fi

# 5. Configure the board, restore .config, and generate autoconf.h
#    (normally emitted by `make menuconfig`, which we bypass).
make CROSS_COMPILE="${TC_PREFIX}" rt2880_config
cp /work/seed.config .config
awk '
  /^#/ {
    if ($0 ~ /is not set/) { print "#undef  " $2 }
    next
  }
  /=/ {
    eq = index($0, "=")
    sym = substr($0, 1, eq-1)
    val = substr($0, eq+1)
    if (val == "y")      print "#define " sym " 1"
    else if (val == "n") print "#undef  " sym
    else                 print "#define " sym " " val
  }
' .config > autoconf.h

# 6. Build.
make CROSS_COMPILE="${TC_PREFIX}" 2>&1

# 7. Collect artifacts.
#    rom: hlk7628n_uboot_flash.bin = uboot.bin padded with 0xFF to 64 KB
#         (the Makefile's hlk_firmware.7628N.uboot) — the image that goes into flash
#    ram: hlk7628n_uboot_ram.bin = raw RAM image for
#             tftpboot 0x80200000 hlk7628n_uboot_ram.bin; go 0x80200000
#         (uboot.img minus its 64-byte mkimage header). Boot-menu option 8 can't
#         start it: it loads to 0x80200000 == ih_load, which bootm treats as XIP
#         and then jumps into the header.
mkdir -p /out
if [ "${VARIANT}" = "ram" ]; then
    dd if=uboot.img of=/out/hlk7628n_uboot_ram.bin bs=64 skip=1 2>/dev/null
    cp uboot.img /out/hlk7628n_uboot_ram.img
    cp u-boot /out/u-boot-ram.elf
    cp System.map /out/System-ram.map
else
    cp hlk_firmware.7628N.uboot /out/hlk7628n_uboot_flash.bin
    cp u-boot /out/u-boot-flash.elf
    cp System.map /out/System-flash.map
fi
(cd /out && sha256sum hlk7628n_uboot_*.bin > SHA256SUMS-${VARIANT}.txt && cat SHA256SUMS-${VARIANT}.txt)
echo "=== build.sh done ==="
