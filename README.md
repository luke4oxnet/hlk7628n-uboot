# U-Boot for the Hi-Link HLK-7628N (MediaTek MT7628)

Ralink/MediaTek SDK **U-Boot 1.1.3** for the HLK-7628N module, reconstructed so
that it rebuilds the vendor's bootloader image **byte for byte**
(`sha256 2558d4e2…df86f5e350`, built May 23 2020).

Lineage: Hi-Link HLK-7628N SDK U-Boot →
[benegon/uboot-hlk7628an](https://github.com/benegon/uboot-hlk7628an) (2023 dump,
commit `1f17101`) → this repository, which reverts benegon's later additions back
to the vendor's 2020 snapshot. See [doc/HLK7628N-RECONSTRUCTION.md](doc/HLK7628N-RECONSTRUCTION.md)
for how each change was derived from the vendor binary.

> **Flashing a bootloader can brick the board.** Have a serial console attached,
> and test the RAM image first (below).

## Board configuration

| | |
|---|---|
| SoC | MT7628AN, MIPS 24KEc, CPU clock from CPLL |
| RAM | DDR2, 1024 Mbit component (128 MB), 16-bit (`DDR_CFG1 = 0x22362323`) |
| Flash | SPI NOR, 31 supported chips incl. 32 MB parts (W25Q256FV, W25M512JV, MX25L25635E) with automatic 4-byte addressing; 3-byte default mode |
| Console | UART 115200 8N1 (the default env still says `baudrate=57600`, as in the vendor image) |
| Defaults | `ipaddr=10.10.10.123`, `serverip=10.10.10.3`, `bootdelay=10` |
| Flash layout | U-Boot `0x00000–0x2FFFF` (192 KB), env `0x30000`, factory `0x40000`, kernel `0x50000` |
| Config | `.config` (`HLK_7628N`, `TEXT_BASE=0xBC000000`) |

## Building

Requires Docker. The build uses the Ralink SDK toolchain the tree expects for
MT7628 — `buildroot-gcc342` (GCC 3.4.2, i386 Linux binaries), fetched from
[sukillall/buildroot-gcc342](https://github.com/sukillall/buildroot-gcc342) at a
pinned commit — inside a 32-bit Debian container.

```sh
docker/build.sh            # both variants
docker/build.sh rom        # flash image only
docker/build.sh ram        # RAM-test image only
PIN_DATE=1 VERIFY=1 docker/build.sh rom   # reproduce + verify the vendor image
```

| Variant | Output | Purpose |
|---|---|---|
| `rom` | `out/rom/hlk7628n_uboot_flash.bin` | Flash image, linked at `0xBC000000`, padded to 192 KB |
| `ram` | `out/ram/hlk7628n_uboot_ram.bin` | RAM-test image, linked at `0x80200000` |

Each output directory also has `SHA256SUMS-<variant>.txt`, the ELF, `System.map`
and `build.log`.

`PIN_DATE=1` sets `__DATE__`/`__TIME__` to the vendor build time (or to
`BUILD_DATE`/`BUILD_TIME`), so the flash image is reproducible.

### CI

GitHub Actions (`.github/workflows/build.yml`) builds both variants on every push
and uploads them as the artifacts **hlk7628n-uboot-flash** and
**hlk7628n-uboot-ram-test**. A third job rebuilds the flash image with the vendor
timestamp and checks it against `docker/vendor-flash.sha256`. That check only holds
while the sources match the vendor image; drop it or update the hash once you
make intentional changes.

## Testing from RAM (no flash write)

The RAM variant skips the CPU-PLL/DDR init in `start.S`, so the U-Boot already on
the board can load and start it. Nothing is written to flash; a power cycle
returns to the installed bootloader.

1. Put `hlk7628n_uboot_ram.bin` on your TFTP server.
2. At the board's boot menu choose **4** (command line), then:

   ```
   MT7628 # setenv ipaddr <board-ip>
   MT7628 # setenv serverip <tftp-server-ip>
   MT7628 # setenv autostart no
   MT7628 # tftpboot 0x80200000 hlk7628n_uboot_ram.bin
   MT7628 # go 0x80200000
   ```

3. The new U-Boot prints its banner and boot menu. Check the build date, the
   flash probe line (`info id : …`), `Total memory` and that the console is
   readable at 115200.

Don't use boot-menu option **8** for this: it loads to `0x80200000`, which equals
the image's load address, so `bootm` treats it as execute-in-place and jumps into
the 64-byte image header.

## Flashing

Only after the RAM test works. Either:

- boot-menu option **9** ("Load Boot Loader code then write to Flash via TFTP")
  and enter `hlk7628n_uboot_flash.bin` as the file name, or
- the web failsafe U-Boot page (192 KB limit).

## Repository layout

| Path | |
|---|---|
| `docker/` | `build.sh` (host entry point), `container-build.sh`, `Dockerfile`, `datewrap/` (timestamp-pinning gcc wrapper), `vendor-flash.sha256` |
| `contrib/compare.py` | summary comparison of two images (prompt, DDR config, flash table, commands, strings) |
| `contrib/funcdiff.py` | function-by-function match of a build against another image using `System.map` |
| `doc/HLK7628N-RECONSTRUCTION.md` | evidence for each change versus benegon's tree |

The original U-Boot README is in `README`.

## License

GPL-2.0, as U-Boot (see `COPYING`).
