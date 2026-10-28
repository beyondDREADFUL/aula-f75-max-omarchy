"""Draw the AULA F75 Max panel in three states as one SVG for the README.

    cd docs && python3 widget-art.py && rsvg-convert -z 2 widget.svg -o widget.png && rm widget.svg

It also writes preview.svg, the same drawing padded to 16:9 for the marketplace card (which
crops to 16:9):

    rsvg-convert -z 2 preview.svg -o ../preview.png && rm preview.svg

A drawing of the panel (AulaF75.qml), not a screenshot: update it when the panel changes."""
import math

FONT = "JetBrainsMono Nerd Font"
FG, DIM, FAINT, LINE = "#E6E6E3", "#9A9C9E", "#6E7275", "#2B2E31"
BG, PANEL, FIELD = "#0B0C0D", "#0F1011", "#131517"
THEME = "#D64831"
THEME_ROW = [THEME, "#E3DEDE", "#3AB4CB", "#6A4FD6"]
PRESETS = ["#FF0000", "#FF8000", "#FFD000", "#00C853", "#00A0FF", "#8839EF", "#FF2D95"]
W = 380                      # panel width
PAD = 20


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


class Panel:
    def __init__(self, x, y):
        self.x, self.y, self.cy, self.out = x, y, y + PAD, []

    def add(self, s):
        self.out.append(s)

    def text(self, x, y, s, size=13, color=FG, weight=400, anchor="start", spacing=0):
        self.add(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" '
                 f'font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{esc(s)}</text>')

    def sep(self):
        self.cy += 12
        self.add(f'<rect x="{self.x + PAD}" y="{self.cy}" width="{W - 2 * PAD}" height="1" fill="{LINE}"/>')
        self.cy += 14

    def section(self, title, right=None):
        self.cy += 14
        self.text(self.x + PAD, self.cy, title.upper(), 11, DIM, 700, spacing=1.3)
        if right:
            right(self.x + W - PAD, self.cy - 4)
        self.cy += 10

    def caption(self, s):
        self.cy += 14
        self.text(self.x + PAD, self.cy, s, 11.5, DIM)
        self.cy += 8

    def switch(self, rx, cy, on, dim=False):
        w, h = 40, 22
        x = rx - w
        op = ' opacity="0.5"' if dim else ""
        track = FG if on else "#2A2D30"
        self.add(f'<g{op}><rect x="{x}" y="{cy - h / 2}" width="{w}" height="{h}" rx="{h / 2}" fill="{track}" '
                 f'stroke="#3A3E42"/><circle cx="{x + (w - 11 if on else 11)}" cy="{cy}" r="8" '
                 f'fill="{"#111" if on else FG}"/></g>')

    def swatch(self, cx, cy, colour, selected=False, rainbow=False):
        r = 14
        if selected:
            self.add(f'<circle cx="{cx}" cy="{cy}" r="{r + 3}" fill="none" stroke="{FG}" stroke-width="2"/>')
        if rainbow:
            hues = ["#FF0000", "#FF8000", "#FFE000", "#00D040", "#00C0FF", "#3050FF", "#8030FF", "#FF2D95"]
            for i, c in enumerate(hues):
                a0, a1 = i / len(hues) * 2 * math.pi, (i + 1) / len(hues) * 2 * math.pi
                p0 = (cx + r * math.sin(a0), cy - r * math.cos(a0))
                p1 = (cx + r * math.sin(a1), cy - r * math.cos(a1))
                self.add(f'<path d="M{cx},{cy} L{p0[0]:.2f},{p0[1]:.2f} A{r},{r} 0 0 1 {p1[0]:.2f},{p1[1]:.2f} Z" fill="{c}"/>')
            self.add(f'<circle cx="{cx}" cy="{cy}" r="5" fill="#FFFFFF" opacity="0.85"/>')
        else:
            self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{colour}"/>')

    def swatch_row(self, colours, selected=None, rainbow_first=False, rainbow_on=False):
        self.cy += 18
        x = self.x + PAD + 15
        if rainbow_first:
            self.swatch(x, self.cy, None, rainbow_on, rainbow=True)
            x += 38
        for c in colours:
            self.swatch(x, self.cy, c, c == selected)
            x += 38
        self.cy += 26

    def field(self, x, y, w, h, label, value=None, faded=False, arrow=False):
        col = FAINT if faded else FG
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{FIELD}" stroke="{"#33373A" if faded else "#4A4F53"}"/>')
        if value is not None:
            self.text(x + 12, y + h / 2 + 5, value, 13, col)
        if arrow:
            self.add(f'<path d="M{x + w - 20},{y + h / 2 - 2} l4,4 l4,-4" stroke="{col}" stroke-width="1.6" fill="none"/>')

    def row_label(self, s, faded=False):
        self.text(self.x + PAD, self.cy + 22, s, 12.5, FAINT if faded else FG)

    def dropdown_row(self, label, value, faded=False):
        self.cy += 6
        self.row_label(label, faded)
        self.field(self.x + W - PAD - 184, self.cy + 2, 184, 34, label, value, faded, arrow=True)
        self.cy += 38

    def slider_row(self, label, level, ticks):
        self.cy += 6
        self.row_label(label)
        x0, x1 = self.x + W - PAD - 184, self.x + W - PAD - 6
        y = self.cy + 18
        seg = (x1 - x0) / (ticks - 1)
        knob = x0 + seg * level
        for i in range(ticks - 1):
            a, b = x0 + i * seg + 2, x0 + (i + 1) * seg - 2
            on = x0 + (i + 1) * seg <= knob + 0.5
            self.add(f'<rect x="{a}" y="{y - 1.5}" width="{b - a}" height="3" rx="1.5" fill="{FG if on else "#3A3E42"}"/>')
        self.add(f'<circle cx="{knob}" cy="{y}" r="7" fill="{FG}"/>')
        self.cy += 34

    def buttons_row(self, label, items, selected):
        self.cy += 6
        self.row_label(label)
        bw, gap = 46, 6
        x = self.x + W - PAD - len(items) * bw - (len(items) - 1) * gap
        for it in items:
            sel = it == selected
            self.add(f'<rect x="{x}" y="{self.cy + 3}" width="{bw}" height="32" rx="7" '
                     f'fill="{"#2A2D30" if sel else "none"}" stroke="#4A4F53"/>')
            self.text(x + bw / 2, self.cy + 24, it, 11.5, FG, 700 if sel else 400, "middle")
            x += bw + gap
        self.cy += 38

    def hero(self, chip, title, meta, pill, reset):
        self.cy += 8
        cy = self.cy + 18
        cx = self.x + PAD
        if chip == "music":
            self.add(f'<rect x="{cx}" y="{cy - 11}" width="22" height="22" rx="6" fill="none" stroke="#4A4F53"/>')
            self.text(cx + 11, cy + 5, "\U000F075A", 14, FG, anchor="middle")
        else:
            self.add(f'<rect x="{cx}" y="{cy - 11}" width="22" height="22" rx="6" fill="{chip}" stroke="#4A4F53"/>')
        self.text(cx + 36, cy - 1, title, 17, FG, 700)
        self.text(cx + 36, cy + 17, meta.upper(), 10.5, DIM, 700, spacing=1.4)
        right = self.x + W - PAD
        if reset:
            self.add(f'<rect x="{right - 62}" y="{cy - 17}" width="62" height="34" rx="7" fill="none" stroke="#5A5F63"/>')
            self.text(right - 31, cy + 5, "Reset", 12.5, FG, anchor="middle")
            right -= 74
        pw = len(pill) * 8.2 + 16
        self.add(f'<rect x="{right - pw}" y="{cy - 22}" width="{pw}" height="24" rx="6" fill="none" stroke="#4A4F53"/>')
        self.text(right - pw / 2, cy - 5, pill, 12.5, DIM, 700, "middle")
        self.cy += 40

    def finish(self):
        return "".join(self.out), self.cy + PAD + 4 - self.y


def panel(x, y, state):
    p = Panel(x, y)
    p.cy += 14
    p.text(x + PAD, p.cy, "AULA F75 Max", 17, FG, 700)
    p.text(x + W - PAD, p.cy, "CABLE", 11.5, DIM, 700, "end", 1.6)
    p.cy += 6
    music = state == "music"
    if state == "theme":
        p.hero(THEME, "Theme colour", "Matches the theme", "Static", False)
    elif state == "custom":
        p.hero("#00A0FF", "#00A0FF", "Theme " + THEME, "Breath", True)
    else:
        p.hero("music", "Music", "Bars over dark", "Rainbow", False)
    p.sep()

    keys = "#00A0FF" if state == "custom" else THEME
    lock_start = len(p.out)
    p.section("Colour")
    if music:
        p.caption("Music is driving the keys")
    p.caption("Theme")
    p.swatch_row(THEME_ROW, keys if state != "custom" else None)
    p.caption("Presets")
    p.swatch_row(PRESETS, "#00A0FF" if state == "custom" else None, rainbow_first=True)
    p.cy += 8
    p.field(x + PAD, p.cy, W - 2 * PAD - 76, 36, "hex", "#RRGGBB", faded=True)
    p.add(f'<rect x="{x + W - PAD - 66}" y="{p.cy}" width="66" height="36" rx="7" fill="none" stroke="#4A4F53"/>')
    p.text(x + W - PAD - 33, p.cy + 23, "Apply", 12.5, FG, anchor="middle")
    p.cy += 58
    p.text(x + PAD, p.cy + 6, "Keep when the theme changes", 12.5, FG)
    p.switch(x + W - PAD, p.cy + 1, False)
    p.cy += 14
    p.sep()
    p.section("Light")
    p.slider_row("Brightness", 4, 5)
    p.dropdown_row("Effect", "Breath" if state == "custom" else "Static")
    if state == "custom":
        p.slider_row("Speed", 3, 6)
    else:
        p.buttons_row("Colour change", ["None", "Fade", "Wave", "Burst"], "Wave")
    if music:      # Colour and Light are locked while music drives the keys
        p.out[lock_start:] = ['<g opacity="0.42">'] + p.out[lock_start:] + ['</g>']
    p.sep()
    p.section("Music", lambda rx, cy: p.switch(rx, cy, music))
    p.dropdown_row("Bars", "Rainbow", faded=not music)
    p.dropdown_row("Behind the bars", "Dark", faded=not music)
    return p.finish()


GAP, MARGIN, LABEL = 40, 48, 44
parts, heights = [], []
for i, state in enumerate(["theme", "custom", "music"]):
    svg, h = panel(MARGIN + i * (W + GAP), MARGIN, state)
    parts.append(svg)
    heights.append(h)
width = 2 * MARGIN + 3 * W + 2 * GAP
height = MARGIN + max(heights) + LABEL + MARGIN - 8
captions = ["Theme colour", "A colour of your own", "Music visualiser"]
tallest = max(heights)
for i in range(3):
    parts[i] = (f'<rect x="{MARGIN + i * (W + GAP)}" y="{MARGIN}" width="{W}" height="{tallest}" rx="14" '
                f'fill="{PANEL}" stroke="#3A3E42"/>') + parts[i]
for i, c in enumerate(captions):
    cx = MARGIN + i * (W + GAP) + W / 2
    parts.append(f'<text x="{cx}" y="{MARGIN + max(heights) + 34}" font-family="{FONT}" font-size="14" '
                 f'fill="{DIM}" text-anchor="middle">{c}</text>')
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
       f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" rx="18" fill="{BG}"/>'
       + "".join(parts) + "</svg>")
open("widget.svg", "w", encoding="utf-8").write(svg)

# the marketplace card: the same drawing centred on a 16:9 canvas
pw = round(height * 16 / 9)
pad = (pw - width) / 2
inner = svg[svg.index(">") + 1:-len("</svg>")]
preview = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}" height="{height}" '
           f'viewBox="0 0 {pw} {height}"><rect width="{pw}" height="{height}" fill="{BG}"/>'
           f'<g transform="translate({pad},0)">{inner}</g></svg>')
open("preview.svg", "w", encoding="utf-8").write(preview)
print(width, height, pw)
