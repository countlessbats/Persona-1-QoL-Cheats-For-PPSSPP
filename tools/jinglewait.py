"""Skip the post-battle victory jingle added by the PSX music mod.

When a battle ends, the music mod's hook (around 0x08A60420) stops the battle music, plays a
victory jingle to the end and then sleeps a further 2-4 s (sceKernelDelayThread, length chosen
by jingle) before the field is loaded, with the screen black the whole time (~5 s). This cheat
removes both calls, so the hook loads the field straight away as the unmodded game does; the
field music is restarted by the field load itself.

Only applies when the music mod's code is present (guarded on its own instruction).

usage: jinglewait.py cheat OUT.ini | install | uninstall
"""
import base64, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

JINGLE_CALL = 0x08A60480  # jal 0x08A60684: stop BGM, play jingle, wait for it to end
JINGLE_ORIG = 0x0E2981A1
SLEEP_CALL = 0x08A6048C   # jal 0x08A604F4: sleep by jingle id
SLEEP_ORIG = 0x0E29813D
GUARD = (0x08A60494, 0x33B1)  # low half of jal 0x0880CEC4 right after the sleep


def patches():
    return [(JINGLE_CALL, 0), (SLEEP_CALL, 0)]


def cheat_lines():
    lines = patches()
    head = f'_L 0xE0{len(lines):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}'
    return [head] + [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in lines]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        with open(sys.argv[2], 'w', newline='\n') as f:
            f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n_C1 Skip Post-Battle Jingle (music mod)\n')
            f.write('\n'.join(cheat_lines()) + '\n')
        return
    from ppdbg import Debugger
    d = Debugger(port=int(os.environ.get('PPDBG_PORT', 64301)))
    if cmd == 'install':
        writes = patches()
    elif cmd == 'uninstall':
        writes = [(JINGLE_CALL, JINGLE_ORIG), (SLEEP_CALL, SLEEP_ORIG)]
    else:
        raise SystemExit(__doc__)
    for a, w in writes:
        d.call('memory.write', address=a, base64=base64.b64encode(struct.pack('<I', w)).decode())


if __name__ == '__main__':
    main()
