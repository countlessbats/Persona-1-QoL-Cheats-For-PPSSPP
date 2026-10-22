"""Rank share: Persona rank points earned by one party member are split among the whole party.

Casting a skill gives the caster's Persona 1-3 rank points (fewer when the Persona's level is
above a value the battle code keeps at LEVEL). This hook computes that gain, divides it by the number of party
members in the battle and adds the share to every member's equipped Persona, carrying
fractions over to later casts. Points are added one at a time through the game's own routine,
so rank-ups, stat growth and new skills work as normal. The game shows the caster's rank-up
message itself; other members' rank-ups are queued and fed one at a time into the mailbox the
battle display polls for that message.

usage: rankshare.py cheat OUT.ini | install | uninstall
cheat writes a CWCheat file; install/uninstall patch the running test instance.
"""
import base64, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keystone

REC = 0x08D03D6C        # battle member records, 0x118 bytes each, 5 slots
REC_STRIDE = 0x118
PRESENT = 0x9A          # nonzero when the slot is in the party
PERSONA = 0x08D04D18    # battle copies of the equipped Personas, parallel to REC
PERSONA_STRIDE = 0x6C
USE = 0x0888C58C        # a0 = Persona copy; adds the rank points for one cast
USE_ADD1 = 0x0888C640   # inside USE: add one point, then the rank-up check
LEARN = 0x0886BC80      # a0 = Persona copy; rebuilds the skill list for its rank
LEVEL = 0x08D05C84      # level the game compares with the Persona's level
SITE = 0x0889CD58       # jal USE in the skill action
GUARD = (0x0889CD86, 0x9047)  # high half of lbu a3,6(v0) a few lines after the site
FRAC = 0x08800580       # rank points carried per slot, in 1/N units
CAVE = 0x08800600
MAILBOX = 0x08D066FC    # rank-up message: -0x9F4 member, -0x9F0 Persona (shown when nonzero),
                        # -0x9EC rank, -0x9E8 learned skill; the display clears it when done
POLL_SITE = 0x08890D30  # addu s0,v0,v1 / lw a0,-0x9F0(s0) before the display's check
QUEUE = 0x08800540      # count, then up to 8 entries of 4 bytes: member, Persona, rank, skill
QUEUE_MAX = 8
POLL_CAVE = 0x08800880
SHOW = 0x088910EC       # display: show the rank-up message in the mailbox (s0 = MAILBOX)
SHOWN = 0x08891188      # display: lw a1,8(sp) / lbu v0,0xC5(a1) after the message is cleared


def hi(x):
    return (x + 0x8000) >> 16


def lo(x):
    return x - (hi(x) << 16)


SRC = f"""
    .set noreorder
add1:
    addiu $sp, $sp, -0x10
    sw    $s0, 0($sp)
    sw    $ra, 4($sp)
    j     {USE_ADD1:#x}
    move  $s0, $a0
share:
    addiu $sp, $sp, -0x30
    sw    $ra, 0x1C($sp)
    sw    $s0, 0($sp)
    sw    $s1, 4($sp)
    sw    $s2, 8($sp)
    sw    $s3, 0xC($sp)
    sw    $s4, 0x10($sp)
    sw    $s5, 0x14($sp)
    sw    $s6, 0x18($sp)
    move  $s5, $a0
    lbu   $t0, 0x64($a0)
    bnez  $t0, done
    move  $s4, $zero
    lui   $t1, {hi(LEVEL):#x}
    lw    $t1, {lo(LEVEL)}($t1)
    lbu   $t2, 0x4B($a0)
    addiu $t3, $t1, 3
    slt   $t3, $t3, $t2
    beqz  $t3, counted
    li    $s3, 3
    sll   $t1, $t1, 1
    lui   $t4, 0x5555
    ori   $t4, $t4, 0x5556
    mult  $t1, $t4
    sra   $t1, $t1, 31
    mfhi  $t4
    subu  $t4, $t4, $t1
    slt   $t4, $t4, $t2
    li    $s3, 2
    li    $t5, 1
    movn  $s3, $t5, $t4
counted:
    lui   $t0, {hi(REC):#x}
    addiu $t0, $t0, {lo(REC)}
    li    $t1, 5
    move  $s2, $zero
count:
    lbu   $t2, {PRESENT:#x}($t0)
    sltu  $t2, $zero, $t2
    addu  $s2, $s2, $t2
    addiu $t1, $t1, -1
    bnez  $t1, count
    addiu $t0, $t0, {REC_STRIDE:#x}
    beqz  $s2, done
    lui   $s0, {hi(REC):#x}
    addiu $s0, $s0, {lo(REC)}
    lui   $s1, {hi(PERSONA):#x}
    addiu $s1, $s1, {lo(PERSONA)}
    lui   $s6, {hi(FRAC):#x}
    addiu $s6, $s6, {lo(FRAC)}
slot:
    lbu   $t0, {PRESENT:#x}($s0)
    beqz  $t0, next
    lbu   $t0, 0x64($s1)
    bnez  $t0, next
    lw    $t1, 0($s6)
    sltiu $t2, $t1, 16
    movz  $t1, $zero, $t2
    addu  $t1, $t1, $s3
    sw    $t1, 0($s6)
point:
    lw    $t1, 0($s6)
    sltu  $t2, $t1, $s2
    bnez  $t2, next
    subu  $t1, $t1, $s2
    sw    $t1, 0($s6)
    jal   add1
    move  $a0, $s1
    bne   $s1, $s5, other
    nop
    b     point
    or    $s4, $s4, $v0
other:
    beqz  $v0, point
    lw    $t0, 0x54($s1)
    sw    $t0, 0x20($sp)
    lw    $t0, 0x58($s1)
    sw    $t0, 0x24($sp)
    jal   {LEARN:#x}
    move  $a0, $s1
    move  $t0, $zero
    move  $t3, $zero
compare:
    addu  $t1, $sp, $t0
    lbu   $t1, 0x20($t1)
    addu  $t2, $s1, $t0
    lbu   $t2, 0x54($t2)
    bne   $t1, $t2, learned
    addiu $t0, $t0, 1
    slti  $t4, $t0, 7
    bnez  $t4, compare
    nop
    b     push
    nop
learned:
    move  $t3, $t2
push:
    lui   $t0, {hi(QUEUE):#x}
    lw    $t1, {lo(QUEUE)}($t0)
    sltiu $t2, $t1, {QUEUE_MAX}
    beqz  $t2, point
    sll   $t2, $t1, 2
    addu  $t2, $t2, $t0
    lbu   $t4, {PRESENT:#x}($s0)
    sb    $t4, {lo(QUEUE) + 4}($t2)
    lbu   $t4, 0x1E($s1)
    sb    $t4, {lo(QUEUE) + 5}($t2)
    lbu   $t4, 0x53($s1)
    sb    $t4, {lo(QUEUE) + 6}($t2)
    sb    $t3, {lo(QUEUE) + 7}($t2)
    addiu $t1, $t1, 1
    b     point
    sw    $t1, {lo(QUEUE)}($t0)
next:
    addiu $s0, $s0, {REC_STRIDE:#x}
    addiu $s1, $s1, {PERSONA_STRIDE:#x}
    lui   $t0, {hi(REC + 5 * REC_STRIDE):#x}
    addiu $t0, $t0, {lo(REC + 5 * REC_STRIDE)}
    bne   $s0, $t0, slot
    addiu $s6, $s6, 4
done:
    move  $v0, $s4
    lw    $ra, 0x1C($sp)
    lw    $s0, 0($sp)
    lw    $s1, 4($sp)
    lw    $s2, 8($sp)
    lw    $s3, 0xC($sp)
    lw    $s4, 0x10($sp)
    lw    $s5, 0x14($sp)
    lw    $s6, 0x18($sp)
    jr    $ra
    addiu $sp, $sp, 0x30
"""
SHARE = CAVE + 0x14     # after add1 (5 instructions)
POLL = POLL_CAVE + 0x24  # after refill (9 instructions)

# poll: replaces the display's mailbox check; when the mailbox is empty, move the oldest
# queued rank-up into it. Returns with s0 and a0 as the replaced instructions leave them.
# refill: entered where the display has just shown and cleared a rank-up message; shows the
# next queued one straight away, otherwise carries on with the replaced instructions.
POLL_SRC = f"""
    .set noreorder
refill:
    bal   poll
    nop
    beqz  $a0, resume
    nop
    j     {SHOW:#x}
    nop
resume:
    lw    $a1, 8($sp)
    j     {SHOWN + 8:#x}
    lbu   $v0, 0xC5($a1)
poll:
    lui   $s0, {hi(MAILBOX):#x}
    addiu $s0, $s0, {lo(MAILBOX)}
    lw    $a0, -0x9F0($s0)
    bnez  $a0, out
    lui   $t0, {hi(QUEUE):#x}
    lw    $t1, {lo(QUEUE)}($t0)
    sltiu $t2, $t1, {QUEUE_MAX + 1}
    beqz  $t2, reset
    nop
    beqz  $t1, out
    lbu   $t3, {lo(QUEUE) + 4}($t0)
    sw    $t3, -0x9F4($s0)
    lbu   $t3, {lo(QUEUE) + 6}($t0)
    sw    $t3, -0x9EC($s0)
    lbu   $t3, {lo(QUEUE) + 7}($t0)
    sw    $t3, -0x9E8($s0)
    lbu   $a0, {lo(QUEUE) + 5}($t0)
    sw    $a0, -0x9F0($s0)
    addiu $t1, $t1, -1
    sw    $t1, {lo(QUEUE)}($t0)
    addiu $t2, $t0, {lo(QUEUE) + 4}
shift:
    beqz  $t1, out
    lw    $t3, 4($t2)
    sw    $t3, 0($t2)
    addiu $t1, $t1, -1
    b     shift
    addiu $t2, $t2, 4
reset:
    sw    $zero, {lo(QUEUE)}($t0)
out:
    jr    $ra
    nop
"""


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def patches():
    ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 | keystone.KS_MODE_LITTLE_ENDIAN)
    code = bytes(ks.asm(SRC, CAVE)[0])
    assert CAVE + len(code) <= POLL_CAVE
    out = [(CAVE + i, w) for i, (w,) in zip(range(0, len(code), 4), struct.iter_unpack('<I', code))]
    poll = bytes(ks.asm(POLL_SRC, POLL_CAVE)[0])
    assert len(poll) <= 0x100
    out += [(POLL_CAVE + i, w) for i, (w,) in zip(range(0, len(poll), 4), struct.iter_unpack('<I', poll))]
    return out + [(SITE, jal(SHARE)), (POLL_SITE, jal(POLL)), (POLL_SITE + 4, 0),
                  (SHOWN, 0x08000000 | ((POLL_CAVE >> 2) & 0x03FFFFFF)), (SHOWN + 4, 0)]


def cheat_lines():
    lines = patches()
    head = f'_L 0xE0{len(lines):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}'
    return [head] + [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in lines]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        with open(sys.argv[2], 'w', newline='\n') as f:
            f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n_C1 Rank Share\n')
            f.write('\n'.join(cheat_lines()) + '\n')
        return
    from ppdbg import Debugger
    d = Debugger(port=int(os.environ.get('PPDBG_PORT', 64301)))
    cur = d.call('memory.disasm', address=SITE, count=1)['lines'][0]['encoding']
    if cur not in (jal(USE), jal(SHARE)):
        raise SystemExit(f'unexpected instruction at {SITE:08x}: {cur:08x}')
    if cmd == 'install':
        writes = patches()
    elif cmd == 'uninstall':
        writes = [(SITE, jal(USE)), (POLL_SITE, 0x00438021), (POLL_SITE + 4, 0x8E04F610),
                  (SHOWN, 0x8FA50008), (SHOWN + 4, 0x90A200C5)]
    else:
        raise SystemExit(__doc__)
    for a, w in writes:
        d.call('memory.write', address=a, base64=base64.b64encode(struct.pack('<I', w)).decode())


if __name__ == '__main__':
    main()
