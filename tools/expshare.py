"""EXP share: every party member in a battle gets the same EXP and Persona EXP.

At battle end the game turns each member's battle score into an adjusted score (record +0xE8)
and sums those into a party total; each member's gain is a flat base plus a share of the
total proportional to their adjusted score, and Persona EXP also uses record +0xEC. Where the
award code reads a member's +0xE8 or +0xEC, these hooks return the average over the members
taking part instead, so every gain comes out equal while the party total stays the same.

usage: expshare.py cheat OUT.ini
"""
import struct, sys
import keystone

REC = 0x08D03D6C        # battle member records, 0x118 bytes each, 5 slots
STRIDE = 0x118
PRESENT = 0x9A          # nonzero when the slot takes part in the EXP award
CAVE = 0x08800400
SITES = (
    (0x088B7C30, 0xE8),  # lw a0,0x4E(s2): adjusted score, character EXP
    (0x088B7F08, 0xE8),  # lw a0,0x4E(s2): adjusted score, Persona EXP
    (0x088B7F18, 0xEC),  # lw a0,0x52(s2): Persona EXP term
)
GUARD = (0x088B7C38, 0x8A30)  # low half of the jal that follows the first site

SRC = f"""
    .set noreorder
avg_e8:
    b     common
    li    $t5, 0xE8
avg_ec:
    li    $t5, 0xEC
common:
    lui   $t0, {REC >> 16:#x}
    ori   $t0, $t0, {REC & 0xFFFF:#x}
    li    $t1, 5
    move  $t2, $zero
    move  $t3, $zero
loop:
    lbu   $t4, {PRESENT:#x}($t0)
    beqz  $t4, next
    addu  $t6, $t0, $t5
    lw    $t4, 0($t6)
    addu  $t2, $t2, $t4
    addiu $t3, $t3, 1
next:
    addiu $t1, $t1, -1
    bnez  $t1, loop
    addiu $t0, $t0, {STRIDE:#x}
    beqz  $t3, done
    move  $a0, $zero
    divu  $zero, $t2, $t3
    mflo  $a0
done:
    jr    $ra
    nop
"""
ENTRY = {0xE8: CAVE, 0xEC: CAVE + 8}  # avg_e8 at +0, avg_ec at +8


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def patches():
    ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 | keystone.KS_MODE_LITTLE_ENDIAN)
    code = bytes(ks.asm(SRC, CAVE)[0])
    assert len(code) <= 0x100
    out = [(CAVE + i, w) for i, (w,) in zip(range(0, len(code), 4), struct.iter_unpack('<I', code))]
    out += [(site, jal(ENTRY[field])) for site, field in SITES]
    return out


def cheat_lines():
    lines = patches()
    head = f'_L 0xE0{len(lines):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}'
    return [head] + [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in lines]


def main():
    if len(sys.argv) < 3 or sys.argv[1] != 'cheat':
        raise SystemExit(__doc__)
    with open(sys.argv[2], 'w', newline='\n') as f:
        f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n_C1 EXP Share\n')
        f.write('\n'.join(cheat_lines()) + '\n')


if __name__ == '__main__':
    main()
