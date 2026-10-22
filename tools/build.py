"""Build ULUS10432.ini from every cheat generator in this folder.

usage: build.py [OUT.ini]   (default: ULUS10432.ini in the repository root)
Environment: ZIG = path to zig.exe (zig 0.16), needed for Prey Eyes.
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHEATS = ('turbo', 'expshare', 'rankshare', 'contacthint', 'jinglewait', 'battlemenu', 'preyeyes')
HEADER = ['_S ULUS-10432', '_G Shin Megami Tensei: Persona']


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'ULUS10432.ini')
    lines = list(HEADER)
    with tempfile.TemporaryDirectory() as tmp:
        for name in CHEATS:
            part = os.path.join(tmp, name + '.ini')
            subprocess.run([sys.executable, os.path.join(HERE, name + '.py'), 'cheat', part], check=True)
            with open(part, encoding='ascii') as f:
                lines += [l for l in f.read().splitlines() if not l.startswith(('_S ', '_G '))]
    with open(out, 'w', encoding='ascii', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'{out}: {len(lines)} lines')


if __name__ == '__main__':
    main()
