/* Prey Eyes lives in the 8 KB below the game module (0x08802000-0x08804000), past the other
 * mods' code. The cheat writes .text every refresh; .bss is never written by the cheat, so the
 * knowledge in it lasts until the game is closed (RAM starts zeroed). */
ENTRY(pe_reticle)
SECTIONS
{
  .text 0x08802000 : { *(.text .text.*) *(.rodata .rodata.* .srodata .srodata.*) }
  ASSERT(. <= 0x08803A00, "code too large")
  .bss 0x08803A00 (NOLOAD) : { *(.sbss .sbss.* .bss .bss.* COMMON) }
  ASSERT(. <= 0x08804000, "bss too large")
  .data : { *(.data .data.* .sdata .sdata.*) }
  ASSERT(SIZEOF(.data) == 0, "initialized .data is not supported; use const or bss")
  /DISCARD/ : { *(.MIPS.* .reginfo .pdr .comment .note* .gnu* .eh_frame* .debug* .mdebug*) }
}
