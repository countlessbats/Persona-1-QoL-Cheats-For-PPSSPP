"""Native turbo: hold Note (mapped to R2 in PPSSPP) to run 2.5 game frames per displayed frame.

The game logic steps once per frame, so skipping vblank waits speeds up gameplay while the
music, streamed on its own thread, keeps real time. On a skipped frame the buffer swap is
skipped too (PPSSPP paces swaps to vblank) and the pad read reuses the last sample (it blocks
until the next vblank sample otherwise).

usage: turbo.py install | uninstall | speed TENTHS | measure [SECONDS] | cheat OUT.ini
install/uninstall/speed act on the running game through the debugger; cheat writes a CWCheat
file that installs the same hooks at boot.
"""
import base64, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keystone

STATE = 0x08800000      # +0 speed in tenths (<=10 normal), +4 accumulator, +8 frame skipped,
                        # +0x10 last pad sample, +0x20 saved ra, +0x24 saved a0
TURBO = 25              # default speed in tenths
SPEEDS = (15, 20, 25, 30, 35, 40, 45, 50)
NOTE = 0x00800000

WAIT_CAVE = 0x08800100
WAIT_SITE = 0x08805854  # jal sceDisplayWaitVblankCB in the frame flip routine
WAIT = 0x08981194
SWAP_CAVE = 0x08800180
SWAP_SITE = 0x0880585C  # jal sceGuSwapBuffers right after the wait
SWAP = 0x089752DC
CTRL_CAVE = 0x088001C0
CTRL_SITE = 0x088051E4  # jal sceCtrlReadBufferPositive in the input poll
CTRL = 0x08981164
# Frame start picks the draw buffer (0 or 0x88000) from the frame counter's parity, which skipped
# frames break; draw into whichever buffer is not on display instead.
PARITY = 0x088055B4     # lw a0,0x5804(v0) .. ori s1,v0,0x8000
GU_DISP = 0x08B9ED80    # GU context +0x30: display buffer offset
OTHER_BUFFER = 0x88000
PARITY_ORIG = (0x8C445804, 0x8C655824, 0x24020001, 0x38840001, 0x30840001,
               0x14800003, 0x0045800B, 0x3C020008, 0x34518000)
GUARD = (0x088051E8, 0x57F8)  # low half of the store in CTRL_SITE's delay slot
FRAMES = 0x08AF5804     # game's frame counter

# Wait for vblank only when the accumulator says a displayed frame is due.
WAIT_SRC = f"""
    .set noreorder
    lui   $t0, 0x0880
    lw    $t1, 0($t0)
    slti  $t2, $t1, 11
    bnez  $t2, wait
    lw    $t3, 4($t0)
    addiu $t3, $t3, 10
    slt   $t2, $t3, $t1
    beqz  $t2, dowait
    li    $t2, 1
    sw    $t3, 4($t0)
    sw    $t2, 8($t0)
    jr    $ra
    move  $v0, $zero
dowait:
    subu  $t3, $t3, $t1
    sw    $t3, 4($t0)
wait:
    j     {WAIT:#x}
    sw    $zero, 8($t0)
"""

SWAP_SRC = f"""
    .set noreorder
    lui   $t0, 0x0880
    lw    $t1, 8($t0)
    bnez  $t1, skip
    nop
    j     {SWAP:#x}
    nop
skip:
    jr    $ra
    nop
"""

# Real read after a vblank: take Note out of the buttons, set the speed from it, cache the sample.
# After a skipped vblank: return the cached sample instead of blocking.
CTRL_SRC = f"""
    .set noreorder
    lui   $t0, 0x0880
    lw    $t1, 8($t0)
    bnez  $t1, cached
    sw    $ra, 0x20($t0)
    jal   {CTRL:#x}
    sw    $a0, 0x24($t0)
    lui   $t0, 0x0880
    lw    $a0, 0x24($t0)
    lw    $ra, 0x20($t0)
    lw    $t1, 4($a0)
    lui   $t2, {NOTE >> 16:#x}
    and   $t3, $t1, $t2
    xor   $t1, $t1, $t3
    sw    $t1, 4($a0)
    li    $t2, 10
    li    $t4, SPEED
    movn  $t2, $t4, $t3
    sw    $t2, 0($t0)
    lw    $t1, 0($a0)
    sw    $t1, 0x10($t0)
    lw    $t1, 4($a0)
    sw    $t1, 0x14($t0)
    lw    $t1, 8($a0)
    sw    $t1, 0x18($t0)
    lw    $t1, 12($a0)
    jr    $ra
    sw    $t1, 0x1C($t0)
cached:
    lw    $t1, 0x10($t0)
    sw    $t1, 0($a0)
    lw    $t1, 0x14($t0)
    sw    $t1, 4($a0)
    lw    $t1, 0x18($t0)
    sw    $t1, 8($a0)
    lw    $t1, 0x1C($t0)
    sw    $t1, 12($a0)
    jr    $ra
    li    $v0, 1
"""


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def patches(speed=TURBO):
    """(address, word) pairs: caves first, then the calls into them."""
    ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 | keystone.KS_MODE_LITTLE_ENDIAN)
    out = []
    caves = [(WAIT_CAVE, WAIT_SRC, SWAP_CAVE), (SWAP_CAVE, SWAP_SRC, CTRL_CAVE), (CTRL_CAVE, CTRL_SRC.replace('SPEED', str(speed)), 0x08800300)]
    for addr, src, limit in caves:
        code = bytes(ks.asm(src, addr)[0])
        assert addr + len(code) <= limit, hex(addr)
        out += [(addr + i, w) for i, (w,) in zip(range(0, len(code), 4), struct.iter_unpack('<I', code))]
    parity = bytes(ks.asm(f"""
        .set noreorder
        lui   $a0, {(GU_DISP + 0x8000) >> 16:#x}
        lw    $a1, 0x5824($v1)
        li    $v0, 1
        lw    $s1, {(GU_DISP & 0xFFFF) - ((GU_DISP & 0x8000) << 1)}($a0)
        lui   $a0, {OTHER_BUFFER >> 16:#x}
        ori   $a0, $a0, {OTHER_BUFFER & 0xFFFF:#x}
        movn  $s0, $v0, $a1
        xor   $s1, $s1, $a0
        nop
    """, PARITY)[0])
    out += [(PARITY + i, w) for i, (w,) in zip(range(0, len(parity), 4), struct.iter_unpack('<I', parity))]
    out += [(WAIT_SITE, jal(WAIT_CAVE)), (SWAP_SITE, jal(SWAP_CAVE)), (CTRL_SITE, jal(CTRL_CAVE))]
    return out


def cheat_lines(speed):
    lines = patches(speed)
    assert len(lines) <= 0xFF
    body = [f'_L 0xE0{len(lines):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}']
    return body + [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in lines]


def cheat(path, speeds=SPEEDS, enabled=TURBO):
    """One cheat per speed; only the default is switched on."""
    with open(path, 'w', newline='\n') as f:
        f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n')
        for sp in speeds:
            f.write(f'_C{int(sp == enabled)} Turbo {sp / 10:g}x (hold Note) - enable only one\n')
            f.write('\n'.join(cheat_lines(sp)) + '\n')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        cheat(sys.argv[2])
        return
    from ppdbg import Debugger
    d = Debugger()

    def write(addr, data):
        d.pause()
        try:
            d.call('memory.write', address=addr, base64=base64.b64encode(data).decode())
        finally:
            d.resume()

    if cmd == 'install':
        # raw reads show JIT block markers, so check the call sites through the disassembler
        for site, orig, cave in ((WAIT_SITE, WAIT, WAIT_CAVE), (SWAP_SITE, SWAP, SWAP_CAVE), (CTRL_SITE, CTRL, CTRL_CAVE)):
            cur = d.call('memory.disasm', address=site, count=1)['lines'][0]['encoding']
            if cur not in (jal(orig), jal(cave)):
                raise SystemExit(f'unexpected instruction at {site:08x}: {cur:08x}')
        for a, w in patches():
            write(a, struct.pack('<I', w))
    elif cmd == 'uninstall':
        for site, orig in ((WAIT_SITE, WAIT), (SWAP_SITE, SWAP), (CTRL_SITE, CTRL)):
            write(site, struct.pack('<I', jal(orig)))
        write(PARITY, struct.pack(f'<{len(PARITY_ORIG)}I', *PARITY_ORIG))
        write(STATE, bytes(12))
    elif cmd == 'speed':
        write(STATE, struct.pack('<I', int(sys.argv[2])))
    elif cmd == 'measure':
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else 2
        a, t = d.u32(FRAMES), time.time()
        time.sleep(secs)
        b, t2 = d.u32(FRAMES), time.time()
        print(f'{(b - a) / (t2 - t):.1f} game frames/s')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
