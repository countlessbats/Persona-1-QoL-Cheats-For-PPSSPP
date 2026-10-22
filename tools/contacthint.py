"""Contact hints: the Contact action menu shows which mood each action will raise.

How a demon reacts to a contact action comes from a table indexed by the acting character and
the action (DECIDE). Five rows per entry are tested against the demon's trait bits; the first
row that matches gives the chance of raising each of the four moods, and a random roll picks
one. A second roll sometimes repeats the demon's previous mood instead (REPEAT).

This cheat makes contact deterministic and shows the result in advance:
- the roll in DECIDE always picks the mood with the highest chance (first one on a tie);
- the previous-mood repeat is skipped;
- the action menu calls DECIDE for each action of the character on screen and draws the
  resulting mood to the right of the action name, in the colour of that mood's gauge.

usage: contacthint.py cheat OUT.ini | install | uninstall
cheat writes a CWCheat file; install/uninstall patch the running test instance.
"""
import base64, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keystone

DECIDE = 0x088B9D9C     # a0 = action 0-3; returns the mood index (0 Eager, 1 Angry, 2 Scared, 3 Happy)
ROLL_SITE = 0x088B9F80  # jal rand in DECIDE; the mood chances are u16[4] at the caller's sp
RAND = 0x08965100
REPEAT_SITE = 0x088C7EF8  # beq v1,zero,<normal reaction> before the previous-mood repeat checks
REPEAT_ORIG = 0x1060000D
MENU_SITE = 0x088CAB1C  # jal DRAW for each action name in the Contact menu (s0 = action + 1)
DRAW = 0x08822238       # a0 text, a1 x, a2 y, a3/t0/t1 layout, t2 colour (ABGR), t3, stack arg
ACTOR = 0x08D08C28      # s16: battle record index DECIDE reads the acting character from
MENU_ACTOR = 0x08B96938  # record index of the character shown in the menu
FORCED = 0x08B966A0     # u32[4]; a mood whose word is 1 replaces DECIDE's result
GUARD = (0x088CAB1A, 0x8C44)  # high half of lw a0,-0x10(v0) just before the menu site
CAVE = 0x08800A00
COLUMN_X = 0x184

MOODS = (               # index order used by DECIDE; colours match the gauge
    ('Eager', 0xFF40E8F0),
    ('Angry', 0xFF4848FF),
    ('Scared', 0xFFFF9858),
    ('Happy', 0xFF3098FF),
)


def hi(x):
    return (x + 0x8000) >> 16


def lo(x):
    return x - (hi(x) << 16)


def encode(text):
    """Game text: big-endian u16 per character, ended by 0xFF01."""
    out = b''
    for c in text:
        if 'a' <= c <= 'z':
            out += bytes((1, ord(c) - 0x60))
        elif 'A' <= c <= 'Z':
            out += bytes((0, 0xE0 + ord(c) - 0x41))
        else:
            raise ValueError(c)
    return out + b'\xff\x01'


DETRAND_SRC = """
    .set noreorder
    move  $t0, $zero
    move  $t1, $zero
    li    $t2, -1
    move  $v0, $zero
roll:
    addu  $t3, $sp, $t0
    lhu   $t3, 0($t3)
    slt   $t4, $t2, $t3
    beqz  $t4, next
    nop
    move  $t2, $t3
    move  $v0, $t1
next:
    addu  $t1, $t1, $t3
    addiu $t0, $t0, 2
    slti  $t4, $t0, 8
    bnez  $t4, roll
    nop
    jr    $ra
    nop
"""


def hint_source(table):
    return f"""
    .set noreorder
    addiu $sp, $sp, -0x40
    sw    $ra, 0x3C($sp)
    sw    $a2, 0x18($sp)
    sw    $a3, 0x1C($sp)
    sw    $t0, 0x20($sp)
    sw    $t1, 0x24($sp)
    sw    $t3, 0x2C($sp)
    lw    $v0, 0x40($sp)
    jal   {DRAW:#x}
    sw    $v0, 0($sp)
    lui   $v1, {hi(ACTOR):#x}
    lh    $v0, {lo(ACTOR)}($v1)
    sw    $v0, 0x30($sp)
    lui   $v0, {hi(MENU_ACTOR):#x}
    lw    $v0, {lo(MENU_ACTOR)}($v0)
    sh    $v0, {lo(ACTOR)}($v1)
    jal   {DECIDE:#x}
    addiu $a0, $s0, -1
    lui   $v1, {hi(ACTOR):#x}
    lw    $t9, 0x30($sp)
    sh    $t9, {lo(ACTOR)}($v1)
    andi  $v0, $v0, 0xFF
    lui   $t9, {hi(FORCED):#x}
    addiu $t9, $t9, {lo(FORCED)}
    move  $t8, $zero
forced:
    lw    $t7, 0($t9)
    xori  $t7, $t7, 1
    movz  $v0, $t8, $t7
    addiu $t8, $t8, 1
    slti  $t7, $t8, 4
    bnez  $t7, forced
    addiu $t9, $t9, 4
    sltiu $t7, $v0, 4
    beqz  $t7, done
    sll   $v0, $v0, 3
    lui   $t9, {hi(table):#x}
    addu  $t9, $t9, $v0
    lw    $a0, {lo(table)}($t9)
    lw    $t2, {lo(table) + 4}($t9)
    li    $a1, {COLUMN_X:#x}
    lw    $a2, 0x18($sp)
    lw    $a3, 0x1C($sp)
    lw    $t0, 0x20($sp)
    lw    $t1, 0x24($sp)
    lw    $t3, 0x2C($sp)
    lw    $v0, 0x40($sp)
    jal   {DRAW:#x}
    sw    $v0, 0($sp)
done:
    lw    $ra, 0x3C($sp)
    jr    $ra
    addiu $sp, $sp, 0x40
"""


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def build():
    """Cave bytes (rolling routine, menu routine, mood table, mood names) and the two entry points."""
    ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 | keystone.KS_MODE_LITTLE_ENDIAN)
    detrand = bytes(ks.asm(DETRAND_SRC, CAVE)[0])
    hint = CAVE + len(detrand)
    size = len(bytes(ks.asm(hint_source(hint), hint)[0]))
    table = hint + size
    strings = table + 8 * len(MOODS)
    data, blobs = b'', b''
    for name, colour in MOODS:
        data += struct.pack('<2I', strings + len(blobs), colour)
        blob = encode(name)
        blobs += blob + b'\0' * (-len(blob) % 4)
    code = bytes(ks.asm(hint_source(table), hint)[0])
    assert len(code) == size
    return detrand + code + data + blobs, CAVE, hint


def patches():
    cave, detrand, hint = build()
    assert len(cave) <= 0x200
    out = [(CAVE + i, w) for i, (w,) in zip(range(0, len(cave), 4), struct.iter_unpack('<I', cave))]
    return out + [(ROLL_SITE, jal(detrand)), (REPEAT_SITE, REPEAT_ORIG & 0xFC1FFFFF),
                  (MENU_SITE, jal(hint))]


def cheat_lines():
    lines = patches()
    head = f'_L 0xE0{len(lines):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}'
    return [head] + [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in lines]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        with open(sys.argv[2], 'w', newline='\n') as f:
            f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n_C1 Contact Hints\n')
            f.write('\n'.join(cheat_lines()) + '\n')
        return
    from ppdbg import Debugger
    d = Debugger(port=int(os.environ.get('PPDBG_PORT', 64301)))
    if cmd == 'install':
        writes = patches()
    elif cmd == 'uninstall':
        writes = [(ROLL_SITE, jal(RAND)), (REPEAT_SITE, REPEAT_ORIG), (MENU_SITE, jal(DRAW))]
    else:
        raise SystemExit(__doc__)
    for a, w in writes:
        d.call('memory.write', address=a, base64=base64.b64encode(struct.pack('<I', w)).decode())


if __name__ == '__main__':
    main()
