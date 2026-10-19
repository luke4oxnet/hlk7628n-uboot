#!/bin/sh
# Build the HLK-7628N U-Boot in Docker.
#
#   docker/build.sh [rom|ram|all]        (default: all)
#
#   rom -> out/rom/hlk7628n_uboot_flash.bin   image for SPI flash (64 KB aligned)
#   ram -> out/ram/hlk7628n_uboot_ram.bin     RAM-test image; from a running U-Boot:
#                                               tftpboot 0x80200000 hlk7628n_uboot_ram.bin
#                                               go 0x80200000
# Env:
#   PIN_DATE=1   pin __DATE__/__TIME__ to the vendor build time (May 23 2020 14:42:28),
#                or to BUILD_DATE / BUILD_TIME if set, for reproducible output
#   VERIFY=1     with PIN_DATE=1: fail unless the rom image matches docker/vendor-flash.sha256
#   OUT=dir      output root (default: out)
set -eu

cd "$(dirname "$0")/.."
ROOT=$(pwd)
VARIANTS=${1:-all}
[ "$VARIANTS" = all ] && VARIANTS="rom ram"

IMAGE=hlk7628n-uboot-build
GCC342_REPO=https://github.com/sukillall/buildroot-gcc342.git
GCC342_SHA=d287db6cc69b269870298835b3f3020b96c7d22c
TC_DIR="$ROOT/.toolchain/buildroot-gcc342"

# 1. Ralink SDK toolchain (GCC 3.4.2, i386 Linux binaries), pinned.
if [ ! -x "$TC_DIR/bin/mipsel-linux-gcc" ]; then
    echo "--- fetching buildroot-gcc342 @ ${GCC342_SHA} ---"
    rm -rf "$TC_DIR"
    mkdir -p "$TC_DIR"
    git -C "$TC_DIR" init -q
    git -C "$TC_DIR" fetch -q --depth 1 "$GCC342_REPO" "$GCC342_SHA"
    git -C "$TC_DIR" checkout -q FETCH_HEAD
fi

# 2. Build container.
echo "--- docker image ${IMAGE} ---"
docker build -q --platform linux/386 -t "$IMAGE" docker/ >/dev/null

if [ "${PIN_DATE:-0}" = "1" ]; then
    TC=/opt/datewrap/mipsel-linux-
else
    TC=/opt/buildroot-gcc342/bin/mipsel-linux-
fi

# 3. Build each variant.
for v in $VARIANTS; do
    out="$ROOT/${OUT:-out}/$v"
    rm -rf "$out"
    mkdir -p "$out"
    echo "--- building variant: $v ---"
    if ! docker run --rm --platform linux/386 \
            -e VARIANT="$v" -e TC_PREFIX="$TC" \
            -e BUILD_DATE="${BUILD_DATE:-May 23 2020}" -e BUILD_TIME="${BUILD_TIME:-14:42:28}" \
            -v "$ROOT:/src:ro" \
            -v "$TC_DIR:/opt/buildroot-gcc342:ro" \
            -v "$ROOT/docker/datewrap:/opt/datewrap:ro" \
            -v "$out:/out" \
            "$IMAGE" > "$out/build.log" 2>&1; then
        tail -40 "$out/build.log"
        echo "build failed: $v (full log: $out/build.log)" >&2
        exit 1
    fi
    cat "$out/SHA256SUMS-$v.txt"

    if [ "$v" = rom ] && [ "${PIN_DATE:-0}" = "1" ]; then
        expect=$(cut -d' ' -f1 docker/vendor-flash.sha256)
        got=$(cut -d' ' -f1 "$out/SHA256SUMS-rom.txt")
        if [ "$got" = "$expect" ]; then
            echo "OK: flash image is byte-identical to the vendor image"
        else
            echo "flash image differs from the vendor image ($expect)"
            [ "${VERIFY:-0}" = "1" ] && exit 1
        fi
    fi
done
