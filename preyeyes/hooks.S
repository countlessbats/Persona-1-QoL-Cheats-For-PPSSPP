# Entry points the game's code is patched to call. Each gives the C code (o32) a fresh frame with
# its own argument area and keeps the registers the game still needs.
    .set noreorder
    .set noat
    .set hardfloat
    .set oddspreg
    .text

# Replaces jal 0x0880851C at 0x0886B1D4, the first sprite of each target reticle. The reticle
# routine's frame holds the overlay cell (+0xCC). f12-f17 and a0-t3 carry the sprite's arguments
# and must survive.
    .globl reticle_shim
reticle_shim:
    addiu $sp, $sp, -0x50
    sw    $ra, 0x10($sp)
    sw    $a0, 0x14($sp)
    sw    $a1, 0x18($sp)
    sw    $a2, 0x1C($sp)
    sw    $a3, 0x38($sp)
    sw    $t0, 0x3C($sp)
    sw    $t1, 0x40($sp)
    sw    $t2, 0x44($sp)
    sw    $t3, 0x48($sp)
    swc1  $f12, 0x20($sp)
    swc1  $f13, 0x24($sp)
    swc1  $f14, 0x28($sp)
    swc1  $f15, 0x2C($sp)
    swc1  $f16, 0x30($sp)
    swc1  $f17, 0x34($sp)
    lw    $a0, 0x50+0xCC($sp)
    jal   pe_reticle
    nop
    lwc1  $f12, 0x20($sp)
    lwc1  $f13, 0x24($sp)
    lwc1  $f14, 0x28($sp)
    lwc1  $f15, 0x2C($sp)
    lwc1  $f16, 0x30($sp)
    lwc1  $f17, 0x34($sp)
    lw    $a0, 0x14($sp)
    lw    $a1, 0x18($sp)
    lw    $a2, 0x1C($sp)
    lw    $a3, 0x38($sp)
    lw    $t0, 0x3C($sp)
    lw    $t1, 0x40($sp)
    lw    $t2, 0x44($sp)
    lw    $t3, 0x48($sp)
    lw    $ra, 0x10($sp)
    j     0x0880851C
    addiu $sp, $sp, 0x50

# Replaces jal 0x08822D44 (skill help text) at 0x0887D900 in the battle skill list.
    .globl hover_shim
hover_shim:
    addiu $sp, $sp, -0x18
    sw    $ra, 0x10($sp)
    jal   pe_hover
    nop
    lw    $ra, 0x10($sp)
    jr    $ra
    addiu $sp, $sp, 0x18

# Replaces jal 0x08822D30 (affinity text) at 0x0882CF30 on Analyze's details page; v0 holds the
# demon's table entry.
    .globl details_shim
details_shim:
    addiu $sp, $sp, -0x18
    sw    $ra, 0x10($sp)
    jal   pe_details
    move  $a1, $v0
    lw    $ra, 0x10($sp)
    jr    $ra
    addiu $sp, $sp, 0x18

# Entry hooks: the routine's first instruction becomes "j shim" and its second a nop (it would
# otherwise run in the jump's delay slot); the shim runs both before continuing at the third.

# Damage multiplier lookup 0x0888B3D8 (addiu sp,sp,-0x20; sw ra,0x18(sp)): a1 = attack type,
# a2 = affinity row.
    .globl learn_shim
learn_shim:
    addiu $sp, $sp, -0x20
    sw    $ra, 0x10($sp)
    sw    $a0, 0x14($sp)
    sw    $a1, 0x18($sp)
    sw    $a2, 0x1C($sp)
    move  $a0, $a1
    jal   pe_learn
    move  $a1, $a2
    lw    $ra, 0x10($sp)
    lw    $a0, 0x14($sp)
    lw    $a1, 0x18($sp)
    lw    $a2, 0x1C($sp)
    j     0x0888B3E0
    sw    $ra, 0x18($sp)

# Battle rewards 0x088B7084 (addiu sp,sp,-0xB0; addiu a0,zero,0x738).
    .globl award_shim
award_shim:
    addiu $sp, $sp, -0x20
    sw    $ra, 0x10($sp)
    sw    $a1, 0x18($sp)
    sw    $a2, 0x1C($sp)
    jal   pe_award
    sw    $a3, 0x0C($sp)
    lw    $ra, 0x10($sp)
    lw    $a1, 0x18($sp)
    lw    $a2, 0x1C($sp)
    lw    $a3, 0x0C($sp)
    addiu $sp, $sp, 0x20 - 0xB0
    j     0x088B708C
    addiu $a0, $zero, 0x738

# Replaces each jal to the sceUtilitySavedataShutdownStart stub (0x08981444): shut the utility down,
# then look at how the save or load went.
    .globl shutdown_shim
shutdown_shim:
    addiu $sp, $sp, -0x18
    sw    $ra, 0x10($sp)
    jal   0x08981444
    nop
    jal   pe_utility_done
    sw    $v0, 0x14($sp)
    lw    $ra, 0x10($sp)
    lw    $v0, 0x14($sp)
    jr    $ra
    addiu $sp, $sp, 0x18

# draw_text(text, x, y, abgr): the game's text routine 0x08822238 with its line height, layer
# and end code; its ninth argument (character limit) is read from the caller's sp+0.
    .globl draw_text
draw_text:
    addiu $sp, $sp, -0x28
    sw    $ra, 0x24($sp)
    move  $t2, $a3
    li    $a3, 0x0A
    li    $t0, 0x0E
    li    $t1, 5
    li    $t3, -0xFF
    li    $v0, 0x80
    jal   0x08822238
    sw    $v0, 0($sp)
    lw    $ra, 0x24($sp)
    jr    $ra
    addiu $sp, $sp, 0x28
