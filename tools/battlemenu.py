"""Persona 5 style battle menus: commands laid out as a diamond, one button per command.

Each menu below binds its commands to buttons; a command runs as soon as its button is
pressed. The face-button commands are drawn as a diamond with the shoulder commands above
it, each with its button symbol beside it, in compact boxes (text at about 70%) at the
bottom right of the screen; the Select hint is shown bottom left. Nothing is highlighted
until a button is pressed: the pressed command then lights up briefly. The D-pad does
not move a cursor in these menus, and their slide animations run at double speed.

- Top menu: X Fight, Square Contact, Circle Analyze, R1 Form, Triangle Auto, L1 Escape.
  Select opens the party status overview (previously on L1).
- Fight: X Attack, Square Shoot, Triangle Skill, L1 Persona, Circle Item, R1 Guard.
- Auto: Triangle Replay, X Weapons, Square Guns, Circle Auto-Act, R1 Set Actions.
- Form: Triangle / Circle / X / Square pick formation 1-4; hold R1 and press one to edit it.
- Contact: Triangle / Square / Circle / X pick the four actions, top to bottom; R1 switches
  the info panel (previously Square).

Select works as Circle (back) everywhere the game tests for a Circle press, so menus that
bind Circle to a command still have a back button.

The game's own menu code does the rest: a pressed button sets the cursor and reports a
confirm, so the normal confirm path runs. Item positions are applied when the menu is
drawn (the struct position plus a per-item offset), which keeps the slide animations.

usage: battlemenu.py cheat OUT.ini | install | uninstall
"""
import base64, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keystone

PRESSED_TEST = 0x088050FC  # v0 = (pad & a0) newly pressed
PAD_NOW, PAD_PREV = 0x08AF57FC, 0x08AF57F8
FRAMES = 0x08AF5804        # counts every 1/60 s
HOLD = 30                  # frames a pressed item stays highlighted
DRAW = 0x08822238          # text: a0 text, a1 x, a2 y, a3/t0/t1 layout, t2 colour (ABGR), t3, stack arg
GUARD = (0x088834FC, 0x4000)  # li a0,0x4000 in the top menu's confirm test
CAVE = 0x08801000
# State the routines change lives past the cave: the cheat engine keeps rewriting the cave.
VARS = 0x08801F00

CROSS, CIRCLE, TRIANGLE, SQUARE, L, R, SELECT = 0x4000, 0x2000, 0x1000, 0x8000, 0x100, 0x200, 0x1

# PlayStation button colours (ABGR)
COL = {CROSS: 0xFFFFB07F, CIRCLE: 0xFF5A5AFF, TRIANGLE: 0xFFB0E040, SQUARE: 0xFFE090F0,
       L: 0xFFE6E6E6, R: 0xFFE6E6E6}
SYM = {CROSS: '×', CIRCLE: '○', TRIANGLE: '△', SQUARE: '□', L: 'L1', R: 'R1'}
GREY, WHITE = 0xFF9A9A9A, 0xFFE6E6E6
HINT_POS = (6, 232)

# Menu boxes, about 70% of the game's size: font, outline/box heights, the strip left of each
# box, text inset, and how much the pressed item grows and rises.
TEXT_SCALE = 179   # /256
OUTLINE_H, BOX_H = 13, 12
STRIP = 6
TEXT_X, TEXT_Y = 4, 1
TEXT_DRAW = 0x0882209C     # item text: a0 text, a1 x, a2 y
SPRITE_SITE = 0x08808554   # j z_un_08808260 in the sprite wrapper every glyph is drawn through
SPRITE = 0x08808260        # returns the sprite record; its 4 vertices are 10 bytes apart, x/y at +4/+6
SEL_W, SEL_H, SEL_RAISE = 4, 4, 2

# The diamond sits bottom right, above the last party portrait: right edge and bottom of its
# lowest box. Columns leave room for the right column's button symbols between them.
RIGHT, BOTTOM = 468, 182
GLYPH_GAP, COL_GAP, ROW_GAP = 13, 4, 3
OFF_RIGHT = 500   # the game slides items 96 px left to remove them; ours leave to the right


def slots(box_w, row_gap=ROW_GAP):
    xr = RIGHT - box_w - SEL_W
    xl = xr - (box_w + COL_GAP + GLYPH_GAP + STRIP)
    xm = (xl + xr) // 2
    gap = OUTLINE_H + row_gap
    y0 = BOTTOM - OUTLINE_H - 3 * gap
    return {L: (xl, y0), R: (xr, y0), TRIANGLE: (xm, y0 + gap),
            SQUARE: (xl, y0 + 2 * gap), CIRCLE: (xr, y0 + 2 * gap), CROSS: (xm, y0 + 3 * gap)}

REGS = {'v0': 2, 'a0': 4, 'a2': 6, 't0': 8, 't2': 10, 's3': 19, 'fp': 30}

# Menu animation handlers (slot +0x18) that slide items in or out; run twice a frame.
ANIMATORS = (0x0887C254, 0x0887C980, 0x0887CE08, 0x08880FBC, 0x0887F5A8, 0x088802D0, 0x088850D8)
DISPATCH_CALL = 0x088291E0  # jalr v0: the per-frame call of each menu slot's handler
DISPATCH_ORIG = 0x0040F809


def lh(rt, off, base):
    return 0x84000000 | (REGS[base] << 21) | (REGS[rt] << 16) | off


def lw_sp(rt, off):
    return 0x8FA00000 | ({'ra': 31, 'fp': 30}[rt] << 16) | off


class Menu:
    """One list menu; the draw functions all follow the same pattern.
    buttons:   button for each item, in the game's item order
    rest:      y of the first item and the row step when the list is at rest
    btn_site:  jal PRESSED_TEST testing Cross (confirm); cursor sets t6 to the cursor word
    pos_site:  two loads of item y (0x6A) and x (0x2A) from base = menu + 4 * index;
               index sets t5 to the item index
    fill_site: li a1,0 / move a3,s1 drawing the fill from the screen edge to the item
    exit_site: an instruction of the draw function's epilogue after ra is loaded from
               ra_slot(sp); menu loads the menu into s0
    labels:    extra text: (text, colour, x, y)
    labels_need_input: draw the labels only while this menu takes input
    box_w:     width of every box (fits the longest command at TEXT_SCALE)
    cptr:      register holding the cursor's address at pos_site, and the cursor's offset in it;
               pointed at NO_ITEM until a button is pressed, so no item is highlighted
    geom:      (address, patched, original) for the draw function's sizes and the D-pad
    hold_block: while this button is held, the command buttons do nothing
    """

    def __init__(self, name, buttons, rest, btn_site, cursor, pos_site, base, xreg, yreg, index,
                 fill_site, exit_site, menu, ra_slot, labels, box_w, cptr, geom, exit_orig=None,
                 pos_orig=None, labels_need_input=False, extra=(),
                 hold_block=0, row_gap=ROW_GAP):
        self.name, self.buttons, (self.rest_y, self.rest_step) = name, buttons, rest
        self.btn_site, self.cursor = btn_site, cursor
        self.pos_site, self.base, self.xreg, self.yreg, self.index = pos_site, base, xreg, yreg, index
        self.pos_orig = pos_orig or (lh(xreg, 0x2A, base), lh(yreg, 0x6A, base))
        self.fill_site = fill_site
        self.exit_site, self.menu, self.ra_slot = exit_site, menu, ra_slot
        self.exit_orig = exit_orig or lw_sp('ra', ra_slot)
        self.labels, self.labels_need_input = labels, labels_need_input
        self.box_w, self.slot = box_w, slots(box_w, row_gap)
        self.cptr = cptr
        self.hold_block = hold_block
        self.extra = list(extra) + list(geom)  # (address, patched, original)


def imm(addr, orig, value):
    """(address, patched, original) replacing the 16-bit immediate of the instruction."""
    return addr, (orig & 0xFFFF0000) | (value & 0xFFFF), orig


def sizes(box_w, unsel, sel, outline_x, text_x, text_y, text_call, raise_):
    """Box sizes; unsel/sel = sites of (box w, outline w, outline h, box h) as (address, original);
    text_y = (address, original) of the item text's y offset; text_call = its jal TEXT_DRAW."""
    out = []
    for sites, grow in ((unsel, 0), (sel, 1)):
        vals = (box_w + grow * SEL_W, box_w + STRIP + grow * SEL_W, OUTLINE_H + grow * SEL_H, BOX_H + grow * SEL_H)
        out += [imm(a, o, v) for (a, o), v in zip(sites, vals)]
    return out + [imm(outline_x, 0x2625FFF0, -STRIP), imm(text_x, 0x26250008, TEXT_X),
                  imm(*text_y, TEXT_Y), ('small_text', text_call), imm(raise_, 0x24020003, SEL_RAISE)]


def dpad_off(up, down):
    """Up/Down no longer move the cursor."""
    return [imm(up, 0x24040010, 0), imm(down, 0x24040040, 0)]


def select_hint(word):
    return [('Select', GREY, HINT_POS[0], HINT_POS[1]), (word, WHITE, HINT_POS[0], HINT_POS[1] + 16)]


TOP_W, FIGHT_W, AUTO_W, FORM_W = 36, 36, 50, 48
FORM_ICON_X = FORM_W - 18  # icons marking a formation, inside the right end of its box

MENUS = [
    # handler z_un_088834b8, draw z_un_0887c410; items Fight Contact Analyze Form Auto Escape
    Menu('top', (CROSS, SQUARE, CIRCLE, R, TRIANGLE, L), (4, 21),
         0x088834F8, 'move $t6, $s1',
         0x0887C71C, 'a0', 'a0', 'a2', 'lw $t5, 0x1F4($sp)',
         0x0887C5F0, 0x0887C824, 'lw $s0, 0x1FC($sp)', 0x224, select_hint('Status'),
         box_w=TOP_W, cptr=('v1', 0), labels_need_input=True,
         geom=sizes(TOP_W, ((0x0887C520, 0x240A0055), (0x0887C540, 0x24070065), (0x0887C544, 0x24080012),
                         (0x0887C54C, 0x24140011)),
                    ((0x0887C800, 0x2403006D), (0x0887C810, 0x2407007D), (0x0887C814, 0x24080018),
                     (0x0887C818, 0x24140017)), 0x0887C56C, 0x0887C620, (0x0887C624, 0x26460002), 0x0887C638, 0x0887C80C)
         + [(0x0887C614, 0, 0x106200AC),            # pressed item: no icon, text stays put
            imm(0x0887C63C, 0x24090017, 0x15),      # text in front of the pressed item's box
            (0x0887C648, 0x1000001F, 0x1040001F)]   # no submenu arrows
         + dpad_off(0x08883600, 0x08883640),
         extra=[(0x088836A0, 0x24040000 | SELECT, 0x24040100)]),  # party status: L1 -> Select
    # handler z_un_0888784c, draw z_un_088813bc; items Attack Shoot Skill Persona Item Guard
    Menu('fight', (CROSS, SQUARE, TRIANGLE, L, CIRCLE, R), (25, 21),
         0x088878E0, 'move $t6, $s0',
         0x088816D8, 't0', 't0', 't2', 'lw $t5, 0x1F4($sp)',
         0x08881640, 0x088813F8, 'move $s0, $s5', 0x224, select_hint('Back'),
         box_w=FIGHT_W, cptr=('a2', 0),
         geom=sizes(FIGHT_W, ((0x0888159C, 0x24120055), (0x08881594, 0x24070065), (0x08881598, 0x24080012),
                         (0x088815A0, 0x24160011)),
                    ((0x088817CC, 0x2412006D), (0x088817C4, 0x2407007D), (0x088817C8, 0x24080018),
                     (0x088817D0, 0x24160017)), 0x088815C4, 0x08881670, (0x08881674, 0x26860002), 0x08881688, 0x088817C0)
         + [(0x08881664, 0, 0x1062005D), imm(0x0888168C, 0x24090017, 0x15)]
         + dpad_off(0x08887D48, 0x08888204)),
    # handler z_un_08882be0, draw z_un_088808e8; items Replay Weapons Guns Auto-Act Set-Actions
    Menu('auto', (TRIANGLE, CROSS, SQUARE, CIRCLE, R), (32, 20),
         0x08882C2C, 'move $t6, $s0',
         0x08880B10, 'fp', 't0', 't2', 'lw $t5, 0x1CC($sp)',
         0x08880A90, 0x08880C14, 'lw $s0, 0x1D0($sp)', 0x204, select_hint('Back'),
         box_w=AUTO_W, cptr=('a2', 0),
         geom=sizes(AUTO_W, ((0x088809C0, 0x2404007C), (0x088809E0, 0x2407008C), (0x088809E4, 0x24080011),
                         (0x088809EC, 0x24140010)),
                    ((0x08880BEC, 0x24030084), (0x08880BFC, 0x24070094), (0x08880C00, 0x24080018),
                     (0x08880C04, 0x24140017)), 0x08880A10, 0x08880AB4, (0x08880AB8, 0x26460002), 0x08880AC8, 0x08880BF8)
         + [(0x08880AD8, 0, 0x1082005B)]            # no arrow on Set Actions
         + dpad_off(0x08882C84, 0x08882E9C)),
    # handler z_un_08886650, draw z_un_0887ea14; items Data 1-4
    Menu('form', (TRIANGLE, CIRCLE, CROSS, SQUARE), (32, 26),
         0x088866C4, 'addiu $t6, $s3, 0x20',
         0x0887EC18, 'v0', 'a2', 's3', 'move $t5, $fp',
         0x0887ED14, 0x0887F084, 'lw $s0, 0xB0($sp)', 0xE4,
         select_hint('Back'), box_w=FORM_W, cptr=('a1', 0x20), labels_need_input=True, hold_block=R,
         row_gap=9,  # room for the formation icons that hang below the right end of a box
         exit_orig=lw_sp('fp', 0xE0), pos_orig=(lh('s3', 0x6A, 'v0'), lh('a2', 0x2A, 'a2')),
         # the outline height doubled as the layer (0x18) in t0; load the layer separately
         geom=sizes(FORM_W, ((0x0887EC50, 0x240A0062), (0x0887EC70, 0x24070072), (0x0887EC48, 0x24080018),
                         (0x0887EC54, 0x24140017)),
                    ((0x0887EFE0, 0x2404006E), (0x0887F000, 0x2407007E), (0x0887F004, 0x2408001E),
                     (0x0887F008, 0x2414001D)), 0x0887EC94, 0x0887ED38, (0x0887ED3C, 0x26460005), 0x0887ED4C, 0x0887EFFC)
         + [(0x0887EC68, 0x24040018, 0xAFA800A0),   # li a0,0x18 (was sw t0,0xA0(sp))
            (0x0887EC78, 0xAFA400A0, 0x01002021),   # sw a0,0xA0(sp) (was move a0,t0)
            imm(0x0887EC28, 0x2663001C, 0),         # camp Formation: same place as in battle (was y+0x1C)
            imm(0x0887ED80, 0x24C60042, FORM_ICON_X), imm(0x0887F144, 0x24420042, FORM_ICON_X),
            imm(0x0887F0D0, 0x2451FFF8, FORM_ICON_X - FORM_W),        # party icon (box w - 8 / - 4)
            imm(0x0887F0D4, 0x2451FFFC, FORM_ICON_X - FORM_W + 4)]
         + dpad_off(0x088874B4, 0x08887640)),
]
FORM_EDIT_SITE = 0x08886B6C  # jal PRESSED_TEST testing Square: edit the formation at the cursor


# Contact action list (z_un_088cac8c input, z_un_088ca960 draw); state block at 0x08B96914:
# +0 result, +4 cursor, +0x18 state (2 = choosing an action)
CONTACT = 0x08B96914
CONTACT_BUTTONS = (TRIANGLE, SQUARE, CIRCLE, CROSS)
CONTACT_BTN_SITE = 0x088CACD8    # jal PRESSED_TEST testing Cross
CONTACT_BACK_SITE = 0x088C9570   # jal PRESSED_TEST testing Circle: leave Contact
CONTACT_LIST_END = 0x088CAB2C    # addiu a0,fp,0x6914 after the four action names are drawn
CONTACT_NAME_X = 0x088CAAE0      # li a1,0x128
CONTACT_ROWS = (0x8E, 0x14)
CONTACT_INFO_KEY = 0x088BB1FC    # ori a0,zero,0x8000: switch the info panel
NAME_X, NAME_SHIFT = 0x128, 16
CONTACT_FIXED = [                # no cursor: names stay white, the cursor bar is drawn off-screen
    (0x088CAAF4, 0, 0x1056001D),                 # beq to the cursor row's yellow name colour
    imm(0x088CABD4, 0x2508008B, 0x28B),          # cursor bar y (0x8B + 20 * cursor)
] + dpad_off(0x088CAD04, 0x088CAD64)


# The game's help-bar prompts are pictures of the old buttons; these replace them with text.
# site: jal to the prompt drawer z_un_08827bf8 (a1 x, a2 y, a3 prompt); None removes the prompt
PROMPT_Y = 6
PROMPTS = [
    (0x0887EEF0, [('R1+Button', WHITE, 0x107, PROMPT_Y), ('Edit', WHITE, 0x146, PROMPT_Y),  # Form list: X Confirm
                  ('Select', GREY, 0x160, PROMPT_Y), ('Back', WHITE, 0x185, PROMPT_Y)]),
    (0x0887EF04, None),                                                                # Form list: Square Edit
    (0x0887EF18, None),                                                                # Form list: Circle Back
    (0x0887EB04, [('R1+Button', WHITE, 0x127, PROMPT_Y), ('Edit', WHITE, 0x166, PROMPT_Y),  # camp Formation: X Confirm
                  ('Select', GREY, 0x180, PROMPT_Y), ('Back', WHITE, 0x1A5, PROMPT_Y)]),
    (0x0887EB18, None),                                                                # camp Formation: Square Edit
    (0x0887EB2C, None),                                                                # camp Formation: Circle Back
    (0x088BAE48, [('Select', GREY, 0x103, PROMPT_Y), ('Back', WHITE, 0x128, PROMPT_Y),  # Contact info panel:
                  ('R1', WHITE, 0x147, PROMPT_Y), ('Switch Info', WHITE, 0x159, PROMPT_Y)]),  # Square Switch Info
]
PROMPT_DRAW = 0x08827BF8


def hi(x):
    return (x + 0x8000) >> 16


def lo(x):
    return x - (hi(x) << 16)


GLYPH = {'×': 0x3E, '○': 0x5B, '△': 0x62, '□': 0x60, '+': 0x3B, ' ': 0}


def encode(text):
    """Game text: big-endian u16 per character, ended by 0xFF01."""
    out = b''
    for c in text:
        if 'a' <= c <= 'z':
            code = 0x100 + ord(c) - 0x60
        elif 'A' <= c <= 'Z':
            code = 0xE0 + ord(c) - 0x41
        elif '0' <= c <= '9':
            code = 0xCF + ord(c) - 0x30
        else:
            code = GLYPH[c]
        out += struct.pack('>H', code)
    return out + b'\xff\x01'


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x03FFFFFF)


def j(target):
    return 0x08000000 | ((target >> 2) & 0x03FFFFFF)


def glyph_offset(sym):
    return -STRIP - (9 if len(sym) == 1 else 13)


def la(reg, addr):
    return f"    lui   ${reg}, {hi(addr):#x}\n    addiu ${reg}, ${reg}, {lo(addr)}\n"


def draw_call(w=0xA, h=0xE):
    return f"""
    li    $a3, {w:#x}
    li    $t0, {h:#x}
    li    $t1, 5
    li    $t3, -0xFF
    li    $v0, 0x20
    jal   {DRAW:#x}
    sw    $v0, 0($sp)
"""


DRAW_CALL = draw_call()


def src_pressed(a):
    """Select counts as Circle in every Circle press test."""
    return f"""
    andi  $t9, $a0, {CIRCLE:#x}
    beqz  $t9, go
    nop
    ori   $a0, $a0, {SELECT:#x}
go:
    lui   $v0, {hi(PAD_NOW):#x}
    j     {PRESSED_TEST + 8:#x}
    lw    $v1, {lo(PAD_NOW)}($v0)
"""


def src_btncommon(a):
    """t9 = button table (u16 masks, 0 ends), t6 = cursor word, t5 = press time.
    v0 = 1 if a button was pressed; the press time records when."""
    return f"""
    lui   $t7, {hi(PAD_NOW):#x}
    lw    $t8, {lo(PAD_NOW)}($t7)
    lw    $t7, {lo(PAD_PREV)}($t7)
    nor   $t7, $t7, $zero
    and   $t8, $t8, $t7
    move  $v0, $zero
loop:
    lhu   $t7, 0($t9)
    beqz  $t7, none
    and   $t7, $t7, $t8
    bnez  $t7, hit
    addiu $t9, $t9, 2
    b     loop
    addiu $v0, $v0, 1
hit:
    sw    $v0, 0($t6)
    lui   $t7, {hi(FRAMES):#x}
    lw    $t7, {lo(FRAMES)}($t7)
    sw    $t7, 0($t5)
    jr    $ra
    li    $v0, 1
none:
    jr    $ra
    move  $v0, $zero
"""


def held(button, target):
    """Branch to target while button is held (uses t7)."""
    return f"""
    lui   $t7, {hi(PAD_NOW):#x}
    lw    $t7, {lo(PAD_NOW)}($t7)
    andi  $t7, $t7, {button:#x}
    bnez  $t7, {target}
    nop
"""


def src_btn(m, a):
    block = held(m.hold_block, 'blocked') if m.hold_block else ''
    return block + la('t9', a[f'{m.name}_btn']) + la('t5', a[f'{m.name}_flag']) + f"""
    j     {a['btncommon']:#x}
    {m.cursor}
blocked:
    jr    $ra
    move  $v0, $zero
"""


def src_form_edit(a):
    """Formation edit: hold R1 and press the formation's button."""
    m = next(m for m in MENUS if m.name == 'form')
    return held(R, 'edit') + f"""
    jr    $ra
    move  $v0, $zero
edit:
""" + la('t9', a['form_btn']) + la('t5', a['form_flag']) + f"""
    j     {a['btncommon']:#x}
    {m.cursor}
"""


def recent(stamp, tmp, target):
    """Branch to target if the press time in register stamp is less than HOLD frames ago."""
    return f"""
    lui   ${tmp}, {hi(FRAMES):#x}
    lw    ${tmp}, {lo(FRAMES)}(${tmp})
    subu  ${tmp}, ${tmp}, ${stamp}
    sltiu ${tmp}, ${tmp}, {HOLD}
    bnez  ${tmp}, {target}
    nop
"""


def src_place(a):
    """Screen position of item t5 at t4 (menu + 4 * index), layout table t6, t7 items.
    Returns x in t4, y in t5. An item on its rest row goes to its diamond slot; the game's
    slide (x from 0 to -96) is mirrored and scaled so the item leaves past the right edge.
    An item the game moves off its row (the header of an opened submenu) stays in its slot
    while it is highlighted after being pressed, then is hidden."""
    return """
    lh    $t8, 0x6A($t4)
    sltu  $t7, $t5, $t7
    beqz  $t7, raw
    sll   $t7, $t5, 2
    sll   $t5, $t5, 3
    addu  $t5, $t5, $t7
    addu  $t6, $t6, $t5
    lh    $t7, 6($t6)
    bne   $t7, $t8, header
    lh    $t7, 4($t6)
    lh    $t4, 0x2A($t4)
    mult  $t4, $t7
    mflo  $t4
    sra   $t4, $t4, 8
    lh    $t7, 0($t6)
    addu  $t4, $t4, $t7
    jr    $ra
    lh    $t5, 2($t6)
header:
    lw    $t7, 8($t6)
    lw    $t7, 0($t7)
    lh    $t4, 0($t6)
    lh    $t5, 2($t6)
""" + recent('t7', 't8', 'held') + """
    li    $t4, -0x200
held:
    jr    $ra
    nop
raw:
    lh    $t4, 0x2A($t4)
    jr    $ra
    move  $t5, $t8
"""


def src_pos(m, a):
    """Item position, and no highlight until one of the menu's buttons has been pressed."""
    reg, off = m.cptr
    return f"""
    move  $t9, $ra
    move  $t4, ${m.base}
    {m.index}
""" + la('t6', a[f'{m.name}_pos']) + f"""
    jal   {a['place']:#x}
    li    $t7, {len(m.buttons)}
    move  ${m.xreg}, $t4
    move  ${m.yreg}, $t5
""" + la('t8', a[f'{m.name}_flag']) + """
    lw    $t8, 0($t8)
""" + recent('t8', 't7', 'pressed') + la(reg, a['no_item'] - off) + """
pressed:
    jr    $t9
    nop
"""


def src_exit(m, a):
    n = len(m.buttons)
    gate = """
    lw    $t9, 8($s0)
    beqz  $t9, done
    nop
""" if m.labels_need_input else ''
    return f"""
    {m.menu}
    lw    $t9, 0xC($s0)
    beqz  $t9, done
    lw    $s3, 0x24($s0)
    slti  $t9, $s3, {n + 1}
    li    $t8, {n}
    movz  $s3, $t8, $t9
    move  $s1, $zero
""" + la('s2', a[f'{m.name}_glyph']) + f"""
glyphs:
    slt   $t9, $s1, $s3
    beqz  $t9, labels
    sll   $t4, $s1, 2
    addu  $t4, $t4, $s0
    move  $t5, $s1
""" + la('t6', a[f'{m.name}_pos']) + f"""
    jal   {a['place']:#x}
    li    $t7, {n}
    lh    $t7, 8($s2)
    addu  $a1, $t4, $t7
    addiu $a2, $t5, {TEXT_Y}
    lw    $a0, 0($s2)
    lw    $t2, 4($s2)
""" + la('t9', a['scale']) + f"""
    li    $t8, 1
    sw    $t8, 0($t9)
    sw    $a1, 4($t9)
    sw    $a2, 8($t9)
""" + DRAW_CALL + la('t9', a['scale']) + f"""
    sw    $zero, 0($t9)
    addiu $s1, $s1, 1
    b     glyphs
    addiu $s2, $s2, 12
labels:
""" + gate + la('a0', a[f'{m.name}_labels']) + f"""
    jal   {a['labels']:#x}
    nop
done:
    lw    $ra, {m.ra_slot:#x}($sp)
    .word {m.exit_orig:#x}
    j     {m.exit_site + 4:#x}
    nop
"""


def src_small_text(a):
    """Item text (TEXT_DRAW) drawn at TEXT_SCALE."""
    return la('t9', a['scale']) + f"""
    li    $t8, 1
    sw    $t8, 0($t9)
    sw    $a1, 4($t9)
    sw    $a2, 8($t9)
    addiu $sp, $sp, -0x10
    sw    $ra, 0($sp)
    jal   {TEXT_DRAW:#x}
    nop
""" + la('t9', a['scale']) + f"""
    sw    $zero, 0($t9)
    lw    $ra, 0($sp)
    jr    $ra
    addiu $sp, $sp, 0x10
"""


def src_sprite(a):
    """Sprite wrapper tail: while scaling is on, shrink the quad towards the text origin."""
    return la('t9', a['scale']) + f"""
    lw    $t8, 0($t9)
    bnez  $t8, scaled
    nop
    j     {SPRITE:#x}
    nop
scaled:
    addiu $sp, $sp, -0x10
    sw    $ra, 0($sp)
    jal   {SPRITE:#x}
    nop
""" + la('t9', a['scale']) + f"""
    lw    $t8, 4($t9)
    lw    $t7, 8($t9)
    li    $t3, {TEXT_SCALE}
    li    $t6, 4
    move  $t5, $v0
vertex:
    lh    $t4, 4($t5)
    subu  $t4, $t4, $t8
    mult  $t4, $t3
    mflo  $t4
    sra   $t4, $t4, 8
    addu  $t4, $t4, $t8
    sh    $t4, 4($t5)
    lh    $t4, 6($t5)
    subu  $t4, $t4, $t7
    mult  $t4, $t3
    mflo  $t4
    sra   $t4, $t4, 8
    addu  $t4, $t4, $t7
    sh    $t4, 6($t5)
    addiu $t6, $t6, -1
    bnez  $t6, vertex
    addiu $t5, $t5, 10
    lw    $ra, 0($sp)
    jr    $ra
    addiu $sp, $sp, 0x10
"""


def src_dispatch(a):
    """Runs a menu slot's handler (a0 = slot); slide animations run a second time, so they
    take half as long."""
    return f"""
    addiu $sp, $sp, -0x10
    sw    $ra, 0($sp)
    sw    $v0, 4($sp)
    jalr  $v0
    move  $a0, $s0
    lw    $v0, 0x18($s0)
    lw    $t8, 4($sp)
    bne   $v0, $t8, done
    nop
""" + la('t9', a['animators']) + f"""
find:
    lw    $t8, 0($t9)
    beqz  $t8, done
    addiu $t9, $t9, 4
    bne   $t8, $v0, find
    nop
    jalr  $v0
    move  $a0, $s0
done:
    lw    $ra, 0($sp)
    jr    $ra
    addiu $sp, $sp, 0x10
"""


def src_labels(a):
    """Draw the label table at a0: (text, colour, x(h), y(h)) entries, ended by a zero text."""
    return """
    addiu $sp, $sp, -0x20
    sw    $ra, 0x1C($sp)
    sw    $s0, 0x18($sp)
    move  $s0, $a0
loop:
    lw    $a0, 0($s0)
    beqz  $a0, done
    lw    $t2, 4($s0)
    lh    $a1, 8($s0)
    lh    $a2, 10($s0)
""" + DRAW_CALL + """
    b     loop
    addiu $s0, $s0, 12
done:
    lw    $ra, 0x1C($sp)
    lw    $s0, 0x18($sp)
    jr    $ra
    addiu $sp, $sp, 0x20
"""


def src_prompt(k, a):
    return la('a0', a[f'prompt{k}_labels']) + f"""
    j     {a['labels']:#x}
    nop
"""


def src_contact_btn(a):
    return la('t9', a['contact_btn']) + la('t5', a['contact_flag']) + f"""
    lui   $t6, {hi(CONTACT + 4):#x}
    j     {a['btncommon']:#x}
    addiu $t6, $t6, {lo(CONTACT + 4)}
"""


def src_contact_back(a):
    """While an action is being chosen Circle picks an action, so only Select leaves."""
    return f"""
    lui   $t9, {hi(CONTACT + 0x18):#x}
    lw    $t9, {lo(CONTACT + 0x18)}($t9)
    addiu $t9, $t9, -2
    bnez  $t9, go
    nop
    li    $a0, {SELECT:#x}
go:
    j     {a['pressed']:#x}
    nop
"""


def src_contact_glyphs(a):
    """Button symbols left of the four action names."""
    return """
    addiu $sp, $sp, -0x30
    sw    $ra, 0x2C($sp)
    sw    $s0, 0x28($sp)
    sw    $s1, 0x24($sp)
    sw    $s2, 0x20($sp)
""" + la('s2', a['contact_glyph']) + f"""
    li    $s0, 4
    li    $s1, {CONTACT_ROWS[0]}
loop:
    lw    $a0, 0($s2)
    lw    $t2, 4($s2)
    li    $a1, {NAME_X + NAME_SHIFT - 18}
    move  $a2, $s1
""" + DRAW_CALL + f"""
    addiu $s0, $s0, -1
    addiu $s1, $s1, {CONTACT_ROWS[1]}
    bnez  $s0, loop
    addiu $s2, $s2, 12
    lw    $ra, 0x2C($sp)
    lw    $s0, 0x28($sp)
    lw    $s1, 0x24($sp)
    lw    $s2, 0x20($sp)
    addiu $sp, $sp, 0x30
    jr    $ra
    addiu $a0, $fp, 0x6914
"""


def routines():
    out = [('pressed', src_pressed), ('btncommon', src_btncommon), ('place', src_place),
           ('contact_btnhook', src_contact_btn), ('contact_backhook', src_contact_back),
           ('contact_glyphhook', src_contact_glyphs), ('labels', src_labels),
           ('form_edithook', src_form_edit), ('dispatch', src_dispatch),
           ('small_text', src_small_text), ('sprite', src_sprite)]
    for k, (_, labels) in enumerate(PROMPTS):
        if labels:
            out.append((f'prompt{k}', lambda a, k=k: src_prompt(k, a)))
    for m in MENUS:
        out += [(f'{m.name}_btnhook', lambda a, m=m: src_btn(m, a)),
                (f'{m.name}_poshook', lambda a, m=m: src_pos(m, a)),
                (f'{m.name}_exithook', lambda a, m=m: src_exit(m, a))]
    return out


def data_blobs():
    """(label, bytes or [(string label, colour, x, y)] or a function of the label addresses
    returning bytes) for every table and string."""
    blobs = [(f'sym{b}', encode(SYM[b])) for b in SYM]
    blobs.append(('no_item', struct.pack('<i', -1)))
    blobs.append(('animators', struct.pack(f'<{len(ANIMATORS) + 1}I', *ANIMATORS, 0)))
    blobs.append(('contact_btn', b''.join(struct.pack('<H', b) for b in CONTACT_BUTTONS) + bytes(2)))
    blobs.append(('contact_glyph', [(f'sym{b}', COL[b], 0, 0) for b in CONTACT_BUTTONS]))
    for k, (_, labels) in enumerate(PROMPTS):
        if labels:
            for n, (text, _, _, _) in enumerate(labels):
                blobs.append((f'prompt{k}_text{n}', encode(text)))
            blobs.append((f'prompt{k}_labels', [(f'prompt{k}_text{n}', c, x, y)
                                                for n, (_, c, x, y) in enumerate(labels)] + [None]))
    for m in MENUS:
        blobs.append((f'{m.name}_btn', b''.join(struct.pack('<H', b) for b in m.buttons) + b'\0\0'))
        blobs.append((f'{m.name}_pos', lambda a, m=m: b''.join(
            struct.pack('<hhhhI', *m.slot[b], round((m.slot[b][0] - OFF_RIGHT) * 256 / 96),
                        m.rest_y + m.rest_step * i, a[f'{m.name}_flag'])
            for i, b in enumerate(m.buttons))))
        blobs.append((f'{m.name}_glyph', [(f'sym{b}', COL[b], glyph_offset(SYM[b]), 0) for b in m.buttons]))
        for k, (text, _, _, _) in enumerate(m.labels):
            blobs.append((f'{m.name}_text{k}', encode(text)))
        blobs.append((f'{m.name}_labels', [(f'{m.name}_text{k}', c, x, y)
                                           for k, (_, c, x, y) in enumerate(m.labels)] + [None]))
    return blobs


def assemble(addrs):
    ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 | keystone.KS_MODE_LITTLE_ENDIAN)
    code, at = b'', CAVE
    for name, fn in routines():
        addrs[name] = at
        blob = bytes(ks.asm('.set noreorder\n' + fn(addrs), at)[0])
        code += blob
        at += len(blob)
    return code


def variables():
    """Address of each variable: press times, then text scaling (on, origin x, origin y)."""
    names = [f'{m.name}_flag' for m in MENUS] + ['contact_flag', 'scale']
    return {name: VARS + 4 * k for k, name in enumerate(names)}


def build():
    """Cave bytes and the address of every routine and data label."""
    blobs = data_blobs()
    addrs = {label: CAVE for label, _ in blobs}
    addrs.update(variables())
    addrs.update({name: CAVE for name, _ in routines()})
    size = len(assemble(dict(addrs)))
    data, at = b'', CAVE + size
    for label, blob in blobs:
        addrs[label] = at + len(data)
        if callable(blob):
            blob = blob(dict.fromkeys(addrs, 0))
        data += (12 * len(blob) if isinstance(blob, list) else len(blob)) * b'\0'
        data += b'\0' * (-len(data) % 4)
    code = assemble(addrs)
    assert len(code) == size
    out = bytearray(code + data)
    for label, blob in blobs:
        off = addrs[label] - CAVE
        if callable(blob):
            blob = blob(addrs)
        elif isinstance(blob, list):
            blob = b''.join(struct.pack('<IIhh', addrs[e[0]], e[1], e[2], e[3]) if e else b'\0' * 12
                            for e in blob)
        out[off:off + len(blob)] = blob
    return bytes(out), addrs


def site_patches(e):
    """(address, patched, original) for every hooked instruction."""
    out = [(PRESSED_TEST, j(e['pressed']), 0x3C0208AF), (PRESSED_TEST + 4, 0, 0x8C4357FC),
           (CONTACT_BTN_SITE, jal(e['contact_btnhook']), jal(PRESSED_TEST)),
           (CONTACT_BACK_SITE, jal(e['contact_backhook']), jal(PRESSED_TEST)),
           (CONTACT_LIST_END, jal(e['contact_glyphhook']), 0x27C46914),
           (CONTACT_NAME_X, 0x24050000 | (NAME_X + NAME_SHIFT), 0x24050000 | NAME_X),
           (CONTACT_INFO_KEY, 0x34040000 | R, 0x34040000 | SQUARE),
           *CONTACT_FIXED,
           (FORM_EDIT_SITE, jal(e['form_edithook']), jal(PRESSED_TEST)),
           (DISPATCH_CALL, jal(e['dispatch']), DISPATCH_ORIG),
           (SPRITE_SITE, j(e['sprite']), j(SPRITE))]
    for k, (site, labels) in enumerate(PROMPTS):
        out.append((site, jal(e[f'prompt{k}']) if labels else 0, jal(PROMPT_DRAW)))
    for m in MENUS:
        out += [
            (m.btn_site, jal(e[f'{m.name}_btnhook']), jal(PRESSED_TEST)),
            (m.pos_site, jal(e[f'{m.name}_poshook']), m.pos_orig[0]),
            (m.pos_site + 4, 0, m.pos_orig[1]),
            (m.fill_site, 0x26250000 | (-STRIP & 0xFFFF), 0x00002821),  # addiu a1,s1,-STRIP: fill only the
            (m.fill_site + 4, 0x24070000 | STRIP, 0x02203821),         # strip left of the label (li a3,STRIP)
            (m.exit_site, j(e[f'{m.name}_exithook']), m.exit_orig),
        ] + [(x[1], jal(e[x[0]]), jal(TEXT_DRAW)) if isinstance(x[0], str) else x for x in m.extra]
    return out


def patches():
    cave, e = build()
    assert len(cave) <= VARS - CAVE
    cave += b'\0' * (-len(cave) % 4)
    out = [(CAVE + i, w) for i, (w,) in zip(range(0, len(cave), 4), struct.iter_unpack('<I', cave))]
    return out + [(a, w) for a, w, _ in site_patches(e)]


def originals():
    _, e = build()
    return [(a, o) for a, _, o in site_patches(e)]


def cheat_lines():
    lines = patches()
    out = []
    for i in range(0, len(lines), 0xFF):
        chunk = lines[i:i + 0xFF]
        out.append(f'_L 0xE0{len(chunk):02X}{GUARD[1]:04X} 0x0{GUARD[0] - 0x08800000:07X}')
        out += [f'_L 0x2{a - 0x08800000:07X} 0x{w:08X}' for a, w in chunk]
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'cheat':
        with open(sys.argv[2], 'w', newline='\n', encoding='ascii') as f:
            f.write('_S ULUS-10432\n_G Shin Megami Tensei: Persona\n_C1 Button Battle Menus\n')
            f.write('\n'.join(cheat_lines()) + '\n')
        return
    from ppdbg import Debugger
    d = Debugger(port=int(os.environ.get('PPDBG_PORT', 64301)))
    if cmd == 'install':
        # restore the sites first so no hook runs while the cave is rewritten, then write
        # the cave, then the sites with delay slots before the jumps into the cave
        cave, e = build()
        sites = site_patches(e)
        writes = [(a, o) for a, _, o in sites] + patches()[:-len(sites)] + [(a, w) for a, w, _ in sites][::-1]
    elif cmd == 'uninstall':
        writes = originals()
    else:
        raise SystemExit(__doc__)
    for a, w in writes:
        d.call('memory.write', address=a, base64=base64.b64encode(struct.pack('<I', w)).decode())


if __name__ == '__main__':
    main()
