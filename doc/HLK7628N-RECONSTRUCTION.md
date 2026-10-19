# Reconstructing the vendor HLK-7628N U-Boot

Target: the vendor bootloader image shipped on an HLK-7628N board.

| | |
|---|---|
| Size | 196,608 bytes (3 × 64 KB, `0xFF`-padded); 180,244 bytes of content |
| SHA-256 | `2558d4e27c0d45261739e1eb221046ddef47446c0d40a676856440df86f5e350` |
| Banner | `U-Boot 1.1.3 (May 23 2020 - 14:42:28)`, prompt `MT7628 # ` |

Result: this repository, built with `PIN_DATE=1 docker/build.sh rom`, produces an
image with the same SHA-256.

## Identifying the platform

- Prompt `MT7628 # `, `RESET MT7628 PHY`, HLK-7628N ASCII banner; no MT7621 /
  1004K code. SPI controller accessed at `0xb0000b00` (MT7628).
- Link base `0xBC000000`: every absolute `lui` in the image uses `0xbc00`.
- The flash-driver strings (`flash_always_3byte`, `flash_to_4byte`,
  `raspi_4byte_mode`, …) occur together in only one public repository:
  benegon/uboot-hlk7628an, which also ships the HLK-7628N `.config`.

## Configuration read from the binary

| Setting | Evidence (vendor image addresses, base `0xBC000000`) |
|---|---|
| DDR2, 1024 Mbit, 16-bit | `0xbc0009dc`: `lui t6,0x2236; ori t6,t6,0x2323` → `DDR_CFG1 = 0x22362323`, the start.S value for `ON_BOARD_DDR2` + `ON_BOARD_1024M_DRAM_COMPONENT` |
| CPU clock from CPLL | `0xbc0006b4`: `DYN_CFG0 = 0xa01` and clock select `ori …,0xc` (BPLL would be `0xe`, XTAL `0xd`) |
| `USE_3BYTE` | `raspi_4byte_mode` (`0xbc00cf04`) has no unconditional `if (!enable) return 0` after the SR3 check |
| Toolchain GCC 3.4.2 | calls are `jalr t9` (1,842×, no `bal` relaxation); `__func__` strings kept for dead code (`raspi_read_rg`, `raspi_write_rg`) and constant-foldable checks kept (`HCCA not aligned!!`) — GCC 4.x drops all of these |

benegon's committed `.config` matches all of these.

## Function-by-function comparison

With the same compiler, identical source compiles to identical instructions
except for link-layout fields (`lui`/`addiu`/`ori` immediates, gp- and
GOT-relative load/store offsets, `j`/`jal` targets). `contrib/funcdiff.py`
masks those fields, takes each function from `System.map` and searches the
vendor image for it.

| Stage | Functions matched | Code bytes |
|---|---|---|
| benegon @ `1f17101`, GCC 3.4.2 | 429 / 459 | 89.6 % |
| + SPI driver | 434 / 459 | 92.0 % |
| + wps.c, board.c additions removed | 436 / 441 | 95.4 % |
| + httpd / net | 440 / 441 | 97.0 % |
| + board_init_r boot flow | 441 / 441 | 100 % |

The remaining 16 differing words were the build timestamp (15) and the UART
divisor (1).

## Changes versus benegon, and why

### `drivers/spi_rt6855A_flash.c`
- **chip table:** the vendor `chip_prob` loop is bounded `sltiu …,31`; benegon's
  is `32`. The extra entry is `QH256XIQ`, which the vendor image doesn't contain.
- **`ralink_spi_command`:** the vendor image has `read len: %d`, `"%x "` and
  `write offs 0x%x, len 0x%x`, i.e. the older `spi read` / `spi write`
  implementation; benegon replaced `spi write` with a 64 KB
  read-modify-erase-write.
- **`do_mem_cp` / `do_flerase`:** no `cp.env` / `erase env` in the vendor image.
- **`burn_env` / `burn_uboot`:** not registered in the vendor image.

Everything else in the driver already matched, including the W25Q256FV/W25M512JV
entries (`addr4b = 1`) and the Winbond extended-address-register clear
(`id == 0xEF → write 0xC5`) in `raspi_4byte_mode`.

### `lib_mips/board.c`
- **Boot flow:** in the vendor image, the menu-'3' path loads `t9 = do_bootm`
  and branches to the last call site of `board_init_r`, which is followed by
  the epilogue. GCC only cross-jumps like that when nothing follows
  `do_bootm` on that path — the classic `if (BootType == '3') { … do_bootm(); }
  else { …menu… }`. benegon removed the `else` and set `BootType = '5'`
  (web failsafe) after a failed boot.
- **Removed:** `bgn_init_gpio()` call, env-upload branch of `tftp_config`,
  `burn_env`, `burn_uboot`, `invalidate_linux`, the `MTRIQ:C,D` banner line.

### `peripheral/wps.c`
Only `init_wps()` / `readwps()` exist in the vendor image; the GPIO helpers, the
bit-banged I2C driver and `gpioset` / `i2ccmd` are later additions.

### `httpd/httpd.c`, `net/net.c`
- The `name="firmware4b"` form check (an empty FIXME branch) is not in the
  vendor `httpd_findandstore_firstchunk`.
- The vendor `NetLoopHttpd` calls `setenv("ipaddr", …)` unconditionally.

### `include/configs/rt2880.h`
`CONFIG_BOOTDELAY` 10 (vendor default environment has `bootdelay=10`).

### `board/rt2880/serial.c`
The vendor `serial_setbrg` loads divisor `22`: 40 MHz / 16 / 115200 = 21.7,
rounded. benegon computes `40 MHz / 16 / CONFIG_BAUDRATE` = 43 (57600). The
console therefore runs at 115200 while the default env still reads
`baudrate=57600`.

## Unchanged

DDR / CPU-PLL init (`start.S`, `0xbc000000–0xbc000fa0`): identical apart from
link-layout words. Flash probe, read/write/erase and 4-byte addressing:
identical. USB is OHCI (`RALINK_OHCI`) with USB storage and FAT, as in the
vendor image.
