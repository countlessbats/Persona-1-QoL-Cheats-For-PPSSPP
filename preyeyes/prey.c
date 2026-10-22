/* Prey Eyes for Persona (PSP): affinity results while choosing skills and targets, an affinity
 * board for the targeted enemy, and per-species knowledge of what you have learned.
 *
 * Built for MIPS II, soft float, o32. The game calls in only through the shims in hooks.S, which
 * give each call a fresh frame and keep the registers the game expects. */
typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;
typedef short s16;
typedef unsigned char u8;

#define R8(a)  (*(volatile u8 *)(a))
#define R16(a) (*(volatile u16 *)(a))
#define S16(a) (*(volatile s16 *)(a))
#define R32(a) (*(volatile u32 *)(a))

/* Battle unit records: 5 party members, then up to 9 enemies. */
#define RECS        0x08D03DC8u
#define REC(i)      (RECS + (u32)(i) * 0x118u)
#define FIRST_ENEMY 5
#define RECORDS     14
/* record: +0 HP, +0x20 weapon, +0x22 gun, +0x3E species (enemies) or character, +0x7C affinity
 * row, +0x80 actor (+0xA4 column in half cells, +0xA5 row), +0xDB skill being targeted */

#define SKILLS      0x08A6B548u   /* 0x30 per skill, attack type at +0x2A */
#define ITEMS       0x08A6E338u   /* 0x40 per item, attack type at +0x36 */
#define AFFINITY    0x08AA5368u   /* 17 bytes per row, a nibble per attack type, high nibble first */
#define DEMONS      0x08A75600u   /* 0x58 per species */
#define FONT        0x08A6854Cu   /* 8 bytes per glyph, width at +4 */
#define FRAMES      0x08AF5804u   /* counts every 1/60 s */
#define GRID        0x08D05ADCu   /* target overlay cells; cell (row r, column k) at 0x12 + r + 15k */
#define CMD_MODE    0x08D05A98u   /* 2 while Analyze picks a target */
#define CMD_KIND    0x08D05A99u   /* 0 Attack, 1 Shoot, 2 Skill */
#define CMD_ACTOR   0x08D05A9Eu   /* party member choosing a command, 0xFF outside the Fight menus */
#define DMG_TARGET  0x08CD670Cu   /* s16: record the damage being worked out is aimed at */

#define SAVE_PARAM  0x08B008E4u   /* the game's SceUtilitySavedataParam */
#define SAVE_SIZE   0x4B88u       /* size of the game's save data (the system file is smaller) */

#define f_skill_help ((u32 (*)(u32))0x08822D44)
#define f_analysis   ((u32 (*)(u32))0x08822D30)
#define f_io_open    ((int (*)(const char *, int, int))0x08980EBC)
#define f_io_read    ((int (*)(int, void *, int))0x08980E7C)
#define f_io_write   ((int (*)(int, const void *, int))0x08980E6C)
#define f_io_close   ((int (*)(int))0x08980E94)
void draw_text(const u8 *text, int x, int y, u32 abgr);      /* hooks.S */

enum { R_NONE, R_UNKNOWN, R_WEAK, R_NORMAL, R_RESIST, R_NULL, R_REPEL, R_ABSORB };

/* ---- knowledge ------------------------------------------------------------------ */

#define KNOW_MAX 224
#define ALL      0x80000000u
static u32 known[KNOW_MAX];      /* per species: bit t = attack type t known, ALL = everything */

/* Attack types the player can use: weapons, guns, the eight elements, Death, Nerve, Curse, Expel. */
static int shown(int t)
{
    return (t >= 0x02 && t <= 0x0D) || (t >= 0x12 && t <= 0x1B) || t == 0x1D || t == 0x1E;
}

static int affinity_code(int row, int t)
{
    u8 b = R8(AFFINITY + (u32)row * 17 + (u32)(t >> 1));
    return (t & 1) ? b & 15 : b >> 4;
}

/* 0 null, 1-3 resist (x0.25-0.75), 4 normal, 5-9 weak (x1.25-2.5), 10-12 repel, 13-15 absorb */
static int category(int c)
{
    if (c == 0) return R_NULL;
    if (c < 4) return R_RESIST;
    if (c == 4) return R_NORMAL;
    if (c < 10) return R_WEAK;
    if (c < 13) return R_REPEL;
    return R_ABSORB;
}

static int species(u32 rec) { return R16(rec + 0x3E); }

static int is_known(u32 rec, int t)
{
    int s = species(rec);
    return s < KNOW_MAX && (known[s] & (ALL | 1u << t));
}

static int result(u32 rec, int t)
{
    if (!shown(t)) return R_NONE;
    if (!is_known(rec, t)) return R_UNKNOWN;
    return category(affinity_code(R8(rec + 0x7C), t));
}

static void learn(u32 rec, int t)
{
    int s = species(rec);
    if (s > 0 && s < KNOW_MAX) known[s] |= t < 0 ? ALL : 1u << t;
}

static int present(u32 rec) { return R32(rec + 0x80) != 0; }
static int alive(u32 rec) { return present(rec) && (s32)R32(rec) > 0; }

/* A defeated enemy reveals everything about its species. The game clears a defeated enemy's
 * record (species included), so the species of each record is kept from when it was last hit. */
static u16 hit_species[RECORDS];

static void learn_kills(void)
{
    for (int i = FIRST_ENEMY; i < RECORDS; i++) {
        u32 rec = REC(i);
        int s = hit_species[i];
        if (!s) continue;
        if ((s32)R32(rec) <= 0) {
            if (s < KNOW_MAX) known[s] |= ALL;
            hit_species[i] = 0;
        } else if (species(rec) != s) {
            hit_species[i] = 0;          /* a different enemy took the place */
        }
    }
}

/* ---- text ------------------------------------------------------------------------ */

static u8 text[256];

static u16 glyph(int c)
{
    if (c >= 'A' && c <= 'Z') return 0xE0 + c - 'A';
    if (c >= 'a' && c <= 'z') return 0x101 + c - 'a';
    if (c >= '0' && c <= '9') return 0xCF + c - '0';
    if (c == '?') return 0x08;
    if (c == ':') return 0x06;
    if (c == '-') return 0x3C;
    if (c == '\n') return 0xFF02;
    return 0;
}

static int glyph_width(u16 g)
{
    if (g == 0) return 5;
    if (g >= 0x120) return 12;
    return (int)R32(FONT + g * 8u + 4) + 1;
}

static int put(int n, const char *s)
{
    for (; *s && n < 126; s++) {
        u16 g = glyph(*s);
        text[2 * n] = g >> 8;
        text[2 * n + 1] = g;
        n++;
    }
    return n;
}

static void end(int n) { text[2 * n] = 0xFF; text[2 * n + 1] = 0x01; }

static int width(const char *s)
{
    int w = 0;
    for (; *s; s++) w += glyph_width(glyph(*s));
    return w;
}

static void say(const char *s, int x, int y, u32 col)
{
    end(put(0, s));
    draw_text(text, x, y, col);
}

static void say_centred(const char *s, int x, int y, u32 col) { say(s, x - width(s) / 2, y, col); }

/* colours are ABGR */
static const u32 tint[8] = { 0, 0xFFE6E6E6, 0xFF58E058, 0xFFE6E6E6, 0xFFF0C070, 0xFFA8A8A8, 0xFF40A8FF, 0xFF6868FF };
static const char *const word[8] = { "", "?", "Weak", "", "Resist", "Null", "Repel", "Absorb" };

/* ---- where enemies stand ----------------------------------------------------------- */

static int cell_x(int r, int k) { return 0x12E - 0x11 * r + 25 * k + 8; }
static int cell_y(int r, int k) { return 0x48 + 6 * r + 8 * k + 0x0E; }

/* ---- the affinity board ------------------------------------------------------------- */

#define BOARD_X  8
#define BOARD_Y  88
#define BOARD_W  250
#define LINE_H   14

static const char *const type_name[0x1F] = {
    [0x02] = "Sword", [0x03] = "Two-Hand", [0x04] = "Spear", [0x05] = "Axe", [0x06] = "Whip",
    [0x07] = "Thrown", [0x08] = "Arrow", [0x09] = "Fist", [0x0A] = "Handgun", [0x0B] = "Machine Gun",
    [0x0C] = "Shotgun", [0x0D] = "Rifle", [0x12] = "Fire", [0x13] = "Ice", [0x14] = "Wind",
    [0x15] = "Earth", [0x16] = "Elec", [0x17] = "Nuclear", [0x18] = "Blast", [0x19] = "Gravity",
    [0x1A] = "Death", [0x1B] = "Nerve", [0x1D] = "Curse", [0x1E] = "Expel",
};

/* Groups the game's own Analyze text uses; a group shows as one word when all of it agrees. */
static const struct { const char *name; u8 first, last; } groups[] = {
    { "Physical", 0x02, 0x09 }, { "Gun", 0x0A, 0x0D }, { "Element", 0x12, 0x15 }, { "Force", 0x16, 0x19 },
    { 0, 0x1A, 0x1A }, { 0, 0x1B, 0x1B }, { 0, 0x1D, 0x1D }, { 0, 0x1E, 0x1E },
};
#define GROUPS (int)(sizeof groups / sizeof groups[0])

static int line_n, line_w;

static void add_word(const char *s, int indent)
{
    int w = width(s) + glyph_width(0);
    if (line_w + w > BOARD_W && line_w > indent) {
        line_n = put(line_n, "\n");
        line_n = put(line_n, "   ");
        line_w = indent;
    }
    line_n = put(line_n, s);
    line_n = put(line_n, " ");
    line_w += w;
}

static int board_line(u32 rec, int cat, const char *label, int y)
{
    line_n = put(0, label);
    line_w = width(label);
    int indent = width("   "), any = 0;
    for (int g = 0; g < GROUPS; g++) {
        int whole = groups[g].name != 0;
        for (int t = groups[g].first; t <= groups[g].last && whole; t++)
            if (result(rec, t) != cat) whole = 0;
        if (whole) { add_word(groups[g].name, indent); any = 1; continue; }
        for (int t = groups[g].first; t <= groups[g].last; t++)
            if (shown(t) && result(rec, t) == cat) { add_word(type_name[t], indent); any = 1; }
    }
    if (!any) return y;
    end(line_n);
    draw_text(text, BOARD_X, y, tint[cat]);
    int lines = 1;
    for (int i = 0; i < line_n; i++)
        if (text[2 * i] == 0xFF && text[2 * i + 1] == 0x02) lines++;
    return y + lines * LINE_H;
}

static void draw_board(u32 rec)
{
    int y = BOARD_Y;
    y = board_line(rec, R_WEAK, "Weak: ", y);
    y = board_line(rec, R_RESIST, "Resist: ", y);
    y = board_line(rec, R_NULL, "Null: ", y);
    y = board_line(rec, R_REPEL, "Repel: ", y);
    y = board_line(rec, R_ABSORB, "Absorb: ", y);
    int unknown = 0;
    for (int t = 0; t < 0x1F; t++) if (shown(t) && result(rec, t) == R_UNKNOWN) unknown++;
    if (unknown) {
        char digits[3] = { 0, 0, 0 };
        if (unknown >= 10) { digits[0] = '0' + unknown / 10; digits[1] = '0' + unknown % 10; }
        else digits[0] = '0' + unknown;
        int n = put(0, "? ");
        n = put(n, digits);
        n = put(n, " not yet seen");
        end(n);
        draw_text(text, BOARD_X, y, tint[R_UNKNOWN]);
    }
}

/* ---- what the command being chosen would hit with ------------------------------------- */

static int action_type(void)
{
    if (R8(CMD_MODE) == 2) return -1;
    int a = R8(CMD_ACTOR);
    if (a >= FIRST_ENEMY) return -1;
    u32 rec = REC(a);
    switch (R8(CMD_KIND)) {
    case 0: return R8(ITEMS + R16(rec + 0x20) * 0x40u + 0x36);
    case 1: return R8(ITEMS + R16(rec + 0x22) * 0x40u + 0x36);
    case 2: return R8(SKILLS + R8(rec + 0xDB) * 0x30u + 0x2A);
    }
    return -1;
}

static u32 reticle_frame;

/* Overlay cell of an enemy: low nibble 5 under the cursor, 6 in the rest of an area skill's area,
 * high nibble set where a reticle is drawn. */
static int cell_of(u32 rec, int *r, int *k)
{
    u32 act = R32(rec + 0x80);
    *r = R8(act + 0xA5);
    *k = R8(act + 0xA4) >> 1;
    if (*r >= 15 || *k >= 5) return 0;
    return R8(GRID + 0x12 + *r + 15 * *k);
}

static int targeted(int c) { return (c & 0xF0) || (c & 0x0F) == 5 || (c & 0x0F) == 6; }

/* The game draws a reticle on each target (hooks.S passes its overlay cell). The first one each
 * frame puts the result over every enemy the command would hit and the board for the one under
 * the cursor. */
void pe_reticle(u32 cell)
{
    u32 now = R32(FRAMES);
    if (reticle_frame == now) return;
    reticle_frame = now;
    learn_kills();
    int t = action_type(), r, k;
    u32 main = 0;
    for (int i = FIRST_ENEMY; i < RECORDS; i++) {
        u32 rec = REC(i);
        if (!alive(rec)) continue;
        int c = cell_of(rec, &r, &k);
        if (!targeted(c)) continue;
        if ((c & 0xF0) == 0x10 || (c & 0x0F) == 5 || (!main && GRID + 0x12 + r + 15 * k == cell)) main = rec;
        if (t < 0) continue;
        int res = result(rec, t);
        if (res != R_NONE && res != R_NORMAL)
            say_centred(word[res], cell_x(r, k), cell_y(r, k) - 0x21 - 18, tint[res]);
    }
    if (main) draw_board(main);
}

/* The battle skill list asks for the hovered skill's help text every frame. Each enemy gets the
 * result the skill would have on it, when that is known and not a plain hit. */
u32 pe_hover(u32 skill)
{
    u32 now = R32(FRAMES);
    if (now - reticle_frame > 2 && R8(CMD_ACTOR) < FIRST_ENEMY && skill < 0x180) {
        learn_kills();
        int t = R8(SKILLS + skill * 0x30u + 0x2A);
        if (shown(t)) {
            for (int i = FIRST_ENEMY; i < RECORDS; i++) {
                u32 rec = REC(i);
                if (!alive(rec)) continue;
                int r = result(rec, t);
                if (r == R_UNKNOWN || r == R_NORMAL) continue;
                u32 act = R32(rec + 0x80);
                int row = R8(act + 0xA5), col = R8(act + 0xA4) >> 1;
                say_centred(word[r], cell_x(row, col), cell_y(row, col) - 0x21 - 18, tint[r]);
            }
        }
    }
    return f_skill_help(skill);
}

/* Analyze's details page looks up the demon's affinity text: everything about it is now known. */
u32 pe_details(u32 analysis, u32 demon)
{
    if (demon >= DEMONS) {
        u32 s = (demon - DEMONS) / 0x58;
        if (s > 0 && s < KNOW_MAX) known[s] |= ALL;
    }
    return f_analysis(analysis);
}

/* The damage routines look up the affinity of the record they are hitting: that attack type is
 * now known for its species. */
void pe_learn(int t, int row)
{
    int i = S16(DMG_TARGET);
    if (i < FIRST_ENEMY || i >= RECORDS) return;
    u32 rec = REC(i);
    if (R8(rec + 0x7C) != row) return;
    hit_species[i] = species(rec);
    if (shown(t)) learn(rec, t);
}

/* Battle rewards are being worked out: every defeated enemy is known in full. */
void pe_award(void) { learn_kills(); }

/* ---- keeping knowledge with each save -------------------------------------------- */

/* The game's save holds no spare room, so the knowledge goes in a file of its own inside the save's
 * folder: written when a save completes, read when a load completes (a save without one starts
 * with nothing known). */
#define MAGIC 0x31594550u   /* "PEY1" */
static char path[64];

static int save_path(void)
{
    const char *head = "ms0:/PSP/SAVEDATA/ULUS10432";
    const char *tail = "/PREYEYES.BIN";
    int n = 0;
    while (*head) path[n++] = *head++;
    for (int i = 0; i < 20; i++) {
        char c = R8(SAVE_PARAM + 0x4C + i);
        if (!c) break;
        if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))) return 0;
        path[n++] = c;
    }
    if (n == 27) return 0;
    while (*tail) path[n++] = *tail++;
    path[n] = 0;
    return 1;
}

/* The save utility has just been shut down with the game's parameters still in place. */
void pe_utility_done(void)
{
    u32 mode = R32(SAVE_PARAM + 0x30);
    if (R32(SAVE_PARAM + 0x1C) != 0 || !save_path()) return;      /* failed or cancelled */
    int save = mode == 1 || mode == 3 || mode == 5;
    int load = mode == 0 || mode == 2 || mode == 4;
    if (save && R32(SAVE_PARAM + 0x7C) == SAVE_SIZE) {
        static const u32 magic = MAGIC;
        int fd = f_io_open(path, 0x602, 0x1B6);                    /* write, create, truncate */
        if (fd >= 0) {
            f_io_write(fd, &magic, 4);
            f_io_write(fd, known, sizeof known);
            f_io_close(fd);
        }
    } else if (load && R32(SAVE_PARAM + 0x78) == SAVE_SIZE) {
        for (int i = 0; i < KNOW_MAX; i++) known[i] = 0;
        for (int i = 0; i < RECORDS; i++) hit_species[i] = 0;
        int fd = f_io_open(path, 1, 0);
        if (fd >= 0) {
            u32 magic = 0;
            if (f_io_read(fd, &magic, 4) == 4 && magic == MAGIC && f_io_read(fd, known, sizeof known) != (int)sizeof known)
                for (int i = 0; i < KNOW_MAX; i++) known[i] = 0;
            f_io_close(fd);
        }
    }
}
