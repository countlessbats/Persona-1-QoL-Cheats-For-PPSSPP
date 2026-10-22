# Persona 1 QoL Cheats for PPSSPP

Quality-of-life cheats for *Shin Megami Tensei: Persona* on PSP (USA, ULUS-10432), played in PPSSPP.

## Installing

1. Copy `ULUS10432.ini` into PPSSPP's cheat folder, `memstick/PSP/Cheats/` (on Windows usually `Documents\PPSSPP\PSP\Cheats\`). If a `ULUS10432.ini` is already there, add these cheats to the end of it.
2. In PPSSPP, turn on **Settings > System > Enable cheats**.
3. Start the game, open the pause menu and choose **Cheats** to switch cheats on or off.

Every cheat except the extra Turbo speeds is on by default.

## The cheats

### Turbo (hold Note)

Hold the Note button to run the game faster. Map Note to a spare button in PPSSPP's control mapping. There is one cheat per speed, from 1.5x to 5x; turn on only one of them (2.5x is on by default).

Music keeps playing at normal speed.

### EXP Share

Everyone in the battle party gets the same character EXP and Persona EXP, the party average. The total the party earns doesn't change.

### Rank Share

When someone casts a skill, the Persona rank points it earns are split across the whole party's equipped Personas. Rank-ups, stat growth and new skills happen as usual, and each member's rank-up message is shown.

### Contact Hints

The Contact menu shows, next to each action, which mood it will raise, in that mood's colour. Contact becomes deterministic: the mood with the highest chance always wins, and the demon no longer randomly repeats its previous mood.

### Skip Post-Battle Jingle (music mod)

This is only for players using the PSX music mod. It removes the mod's victory jingle and the pause after it, so the field loads straight after a battle. Without the music mod it does nothing.

### Button Battle Menus

Battle menu commands are laid out as a diamond, one button per command, in compact boxes at the bottom right. A command runs as soon as its button is pressed:

| Menu | Commands |
|---|---|
| Top | X Fight, Square Contact, Circle Analyze, R1 Form, Triangle Auto, L1 Escape. Select opens the party status overview. |
| Fight | X Attack, Square Shoot, Triangle Skill, L1 Persona, Circle Item, R1 Guard. |
| Auto | Triangle Replay, X Weapons, Square Guns, Circle Auto-Act, R1 Set Actions. |
| Form | Triangle / Circle / X / Square pick formation 1-4. Hold R1 and press one to edit it. |
| Contact | Triangle / Square / Circle / X pick the four actions, top to bottom. R1 switches the info panel. |

Select works as Back everywhere.

### Prey Eyes

Prey Eyes shows enemy affinities as you learn them:

- **Skill preview.** While you choose a skill, each enemy you know to be weak to it, or to resist, null, repel or absorb it, shows the result.
- **Target results.** While you target an Attack, Shoot or skill, every enemy it would hit shows its result, including everyone inside an area skill's area. Enemies you don't know yet show "?".
- **Affinity board.** While targeting and in Analyze, a list at the left shows what you know about the targeted enemy (Weak, Resist, Null, Repel, Absorb) and how many attack types you haven't seen yet.

Hitting an enemy with an attack type teaches that type for its whole species. Defeating an enemy, or opening its Analyze details page, teaches everything about it.

What you've learned is kept with each save, in a `PREYEYES.BIN` file inside that save's folder. Saves made before installing start with nothing known.

## Building from source

The generators in `tools/` produce the cheats; `tools/build.py` runs all of them and writes `ULUS10432.ini`. You need:

- Python 3 with `keystone-engine`, `pyelftools` and `capstone`;
- [zig](https://ziglang.org/) 0.16 for Prey Eyes, which is written in C (`preyeyes/`). Point the `ZIG` environment variable at `zig.exe` if it isn't on `PATH`.

```
python tools/build.py
```

Each generator also accepts `cheat OUT.ini` to write just its own cheat. Most also accept `install` / `uninstall`, which patch a running game through PPSSPP's debugger (`websockets` is needed for this).

The cheats keep their code in the unused RAM at 0x08800000-0x08804000, so other cheats that use that area will conflict with them.
