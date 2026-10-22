"""Prey Eyes: affinity results while choosing skills and targets, an affinity board for the
targeted enemy, and knowledge of what you have learned about each species.

The mod is C (preyeyes/prey.c) and a few assembly entry points (preyeyes/hooks.S), compiled with
zig for MIPS II (soft float, o32) and linked at 0x08802000. The cheat writes the code and these hooks (calls redirected, or a routine's first instruction turned into a jump with a nop after it):

- 0x0886B1D4  target reticle sprite      -> reticle_shim (result over each target, board)
- 0x0887D900  battle skill list help     -> hover_shim   (results over every enemy)
- 0x0882CF30  Analyze details text       -> details_shim (species fully known)
- 0x0888B3D8  damage multiplier lookup   -> learn_shim   (attack type known for the species)
- 0x088B7084  battle rewards             -> award_shim   (defeated species fully known)
- calls to sceUtilitySavedataShutdownStart -> shutdown_shim (knowledge file written or read)

usage: preyeyes.py cheat OUT.ini | install | uninstall
  install/uninstall write the running test instance through the debugger (PPDBG_PORT, 64301).
Environment: ZIG = path to zig.exe (zig 0.16).
"""
import base64, io, os, struct, subprocess, sys
from elftools.elf.elffile import ELFFile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'preyeyes')
OUT = os.path.join(ROOT, 'build', 'preyeyes')
ZIG = os.environ.get('ZIG') or 'zig'
CFLAGS = ['-target', 'mipsel-freestanding-none', '-mcpu=mips2', '-msoft-float', '-Os', '-fno-pic',
          '-Xclang', '-target-feature', '-Xclang', '+noabicalls', '-G0', '-ffreestanding', '-fno-builtin',
          '-nostdlib', '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
          '-fomit-frame-pointer', '-mno-check-zero-division', '-Wall']
TITLE = 'Prey Eyes'
GUARD = (0x0882CF36, 0x2475)   # high half of addiu s5,v1,0xC5 beside the details hook

HOOKS = [  # site, original words, (kind, symbol); a 'j' hook also turns the next word into a nop
    (0x0886B1D4, (0x0E202147,), ('jal', 'reticle_shim')),
    (0x0887D900, (0x0E208B51,), ('jal', 'hover_shim')),
    (0x0882CF30, (0x0E208B4C,), ('jal', 'details_shim')),
    (0x0888B3D8, (0x27BDFFE0, 0xAFBF0018), ('j', 'learn_shim')),
    (0x088B7084, (0x27BDFF50, 0x24040738), ('j', 'award_shim')),
]
# Every call to the sceUtilitySavedataShutdownStart stub (0x08981444).
SHUTDOWN_CALLS = (0x08816CB8, 0x08816DDC, 0x08816EE0, 0x08818800, 0x08818A74, 0x08818CB8, 0x08818F28,
                  0x08819088, 0x08819164, 0x0881925C, 0x088192F0, 0x0881D808)
HOOKS += [(site, (0x0E260511,), ('jal', 'shutdown_shim')) for site in SHUTDOWN_CALLS]


def build():
    os.makedirs(OUT, exist_ok=True)
    objs = []
    for name in ('prey.c', 'hooks.S'):
        o = os.path.join(OUT, name.split('.')[0] + '.o')
        subprocess.run([ZIG, 'cc', *CFLAGS, '-c', os.path.join(SRC, name), '-o', o], check=True)
        objs.append(o)
    elf = os.path.join(OUT, 'prey.elf')
    subprocess.run([ZIG, 'ld.lld', '-m', 'elf32ltsmip', '-T', os.path.join(SRC, 'prey.ld'),
                    '--no-relax', '-o', elf, *objs], check=True)
    with open(elf, 'rb') as fh:
        f = ELFFile(io.BytesIO(fh.read()))
    text = f.get_section_by_name('.text')
    syms = {s.name: s['st_value'] for s in f.get_section_by_name('.symtab').iter_symbols() if s.name}
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
    for i in md.disasm(text.data(), text['sh_addr']):
        if '$gp' in i.op_str or i.mnemonic in ('teq', 'tne', 'tge', 'tlt', 'll', 'sc', 'sdc1', 'ldc1'):
            raise SystemExit(f'unsupported instruction at {i.address:08x}: {i.mnemonic} {i.op_str}')
    return text['sh_addr'], text.data(), syms


def patches():
    base, code, syms = build()
    code += b'\0' * (-len(code) % 4)
    words = [(base + i, struct.unpack_from('<I', code, i)[0]) for i in range(0, len(code), 4)]
    for site, _, (kind, sym) in HOOKS:
        op = 0x0C000000 if kind == 'jal' else 0x08000000
        words.append((site, op | ((syms[sym] >> 2) & 0x03FFFFFF)))
        if kind == 'j':
            words.append((site + 4, 0))
    return words, base, len(code), syms


def cheat_lines(lines):
    out = [f'_C1 {TITLE}']
    for i in range(0, len(lines), 0xFF):
        chunk = lines[i:i + 0xFF]
        out.append(f'_L 0xE0{len(chunk):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}')
        out += [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in chunk]
    return out


def debugger():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ppdbg import Debugger
    return Debugger(port=int(os.environ.get('PPDBG_PORT', 64301)))


def write(d, a, data):
    d.call('memory.write', address=a, base64=base64.b64encode(data).decode())


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        words, base, size, _ = patches()
        lines = cheat_lines(words)
        with open(sys.argv[2], 'w', encoding='ascii', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        print(f'{len(lines)} lines, code {base:08x}..{base + size:08x} ({size} bytes)')
    elif cmd == 'install':
        words, base, size, _ = patches()
        d = debugger()
        code = b''.join(struct.pack('<I', w) for a, w in words if base <= a < base + size)
        write(d, base, code)                              # code first, then the hooks into it
        for a, w in words:
            if not base <= a < base + size:
                write(d, a, struct.pack('<I', w))
        print(f'installed {size} bytes and {len(HOOKS)} hooks')
    elif cmd == 'uninstall':
        d = debugger()
        for site, orig, _ in HOOKS:
            write(d, site, b''.join(struct.pack('<I', w) for w in orig))
        print('hooks restored')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
