import pygame, sys, json, os
from dataclasses import dataclass, asdict



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAVE = os.path.join(BASE_DIR, "assets", "shapes_pumpfoil.json")

# Jeśli gra uruchamia edytor z argumentem (ścieżką do skina), użyj tego.
SAVE_PATH = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SAVE
os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)

print(f"[EDITOR] SAVE_PATH = {SAVE_PATH}")

# ------------------------------------------------------
# Pumpfoil Shape Editor – prosty wektorowy edytor skórek
# ------------------------------------------------------
# Pozwala tworzyć i edytować prostokąty oraz linie,
# żeby "narysować" deskę, maszt, foil i ridera bez PNG.
# Zapis/odczyt do JSON. Działa w pikselowym stylu.
#
# Sterowanie (skrót):
#  - LPM: wybierz/ przeciągnij element
#  - Shift + LPM: duplikuj element i przeciągnij kopię
#  - Scroll: zmiana grubości (dla linii) / promienia narożników (dla rect)
#  - Strzałki: przesuwaj o 1 px (Shift: 5 px)
#  - Q/W: zmieniaj szerokość (rect)  (Shift: 5 px)
#  - A/S: zmieniaj wysokość (rect)  (Shift: 5 px)
#  - C: zmień kolor (cykl palety)
#  - G: włącz/wyłącz przyciąganie do siatki (grid)
#  - [: wyślij w dół warstwy, ]: wyślij w górę (Z-order)
#  - 1/2/3/4: ustaw grupę: board / foil / rider / extras
#  - R: przełącz tryb zaokrąglenia narożników (rect: 0 ↔ 6 ↔ 12)
#  - N: nowy prostokąt   |   K: nowa linia
#  - Del: usuń zaznaczony
#  - Ctrl+S: zapisz JSON (assets/shapes_pumpfoil.json)
#  - Ctrl+O: wczytaj JSON  (assets/shapes_pumpfoil.json)
#  - F1: pomoc (skrót klawiszy)
#
# Format JSON: lista obiektów z polami:
#   kind: "rect" | "line"
#   x,y,w,h  (dla rect)
#   x1,y1,x2,y2,width (dla line)
#   color: [r,g,b]
#   radius: int (dla rect)
#   group: "board"|"foil"|"rider"|"extras"
# ------------------------------------------------------

pygame.init()
WIDTH, HEIGHT = 900, 540
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pumpfoil Shape Editor – wektorowy")
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("Arial", 16)
BIG  = pygame.font.SysFont("Arial", 22, bold=True)

GRID = 8
snap_enabled = True

# --- Uchwyty końcówek linii (np. masztu) ---
HANDLE_R = 8

def _near(px, py, x, y, r=HANDLE_R):
    return (px - x)**2 + (py - y)**2 <= r*r

PALETTE = [
    (245,245,245), # WHITE
    (20,20,20),    # BLACK
    (160,160,160), # GRAY
    (60,80,180),   # SUIT blue
    (255,204,170), # SKIN
    (250,200,40),  # ACCENT
    (0,190,110),   # GREEN
    (200,220,255), # SKY-ish
    (80,180,255),  # WATER-ish
    (220,60,60),   # RED
]

# (Używamy SAVE_PATH zdefiniowanego na górze – zgodnego z argumentem linii poleceń)

@dataclass
class RectShape:
    kind: str = "rect"
    x: int = 100
    y: int = 100
    w: int = 40
    h: int = 20
    color: tuple = (245,245,245)
    radius: int = 6
    group: str = "board"   # board/foil/rider/extras

    def draw(self, surf):
        pygame.draw.rect(surf, self.color, (self.x, self.y, self.w, self.h), border_radius=self.radius)

    def bbox(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def to_json(self):
        d = asdict(self)
        d["color"] = list(self.color)
        return d

@dataclass
class LineShape:
    kind: str = "line"
    x1: int = 120
    y1: int = 100
    x2: int = 120
    y2: int = 200
    width: int = 5
    color: tuple = (20,20,20)
    group: str = "extras"

    def draw(self, surf):
        pygame.draw.line(surf, self.color, (self.x1, self.y1), (self.x2, self.y2), self.width)

    def bbox(self):
        left = min(self.x1, self.x2)
        top = min(self.y1, self.y2)
        w = abs(self.x2 - self.x1) or 1
        h = abs(self.y2 - self.y1) or 1
        return pygame.Rect(left, top, w, h)

    def to_json(self):
        d = asdict(self)
        d["color"] = list(self.color)
        return d

shapes = []
selected = None
selected_handle = None  # 'rect' / 'line' / 'p1' / 'p2'
palette_idx = 0

help_visible = False

# Jeśli istnieje zapis, wczytaj go na start
if os.path.exists(SAVE_PATH):
    try:
        with open(SAVE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        shapes = []
        for d in data:
            if d.get('kind') == 'rect':
                d['color'] = tuple(d.get('color', [245,245,245]))
                shapes.append(RectShape(**{k:d[k] for k in ['kind','x','y','w','h','color','radius','group'] if k in d}))
            elif d.get('kind') == 'line':
                d['color'] = tuple(d.get('color', [20,20,20]))
                shapes.append(LineShape(**{k:d[k] for k in ['kind','x1','y1','x2','y2','width','color','group'] if k in d}))
        print(f"[OK] Autoload: {SAVE_PATH} ({len(shapes)} elementów)")
    except Exception as e:
        print("[!] Autoload error:", e)

# przykładowy startowy zestaw – deska + maszt + foil + rider
# (Domyślny zestaw usunięty — używamy zapisu/wczytania JSON).

def current_mast_length():
    """Znajdź długość masztu w shapes (linia/rect z group 'foil'/'mast')."""
    candidates = []
    for s in shapes:
        grp = getattr(s, "group", "").lower()
        if s.kind == "line" and grp in ("foil", "mast", ""):
            candidates.append(abs(s.y2 - s.y1))
        elif s.kind == "rect" and grp in ("foil", "mast", ""):
            if s.h > max(1, s.w) * 1.5:
                candidates.append(s.h)
    return max(candidates) if candidates else None



def snap(v):
    return (v // GRID) * GRID if snap_enabled else v


def draw_grid():
    color = (220, 230, 240)
    for x in range(0, WIDTH, GRID):
        pygame.draw.line(screen, color, (x, 0), (x, HEIGHT), 1)
    for y in range(0, HEIGHT, GRID):
        pygame.draw.line(screen, color, (0, y), (WIDTH, y), 1)


def draw_ui():
    # Pasek info u góry
    pygame.draw.rect(screen, (40,60,80), (0,0, WIDTH, 32))
    txt = BIG.render("Pumpfoil Shape Editor", True, (255,255,255))
    screen.blit(txt, (10, 5))
    sub = FONT.render("LPM: wybierz/przeciągnij | N: rect | K: line | C: kolor | G: siatka | Ctrl+S: zapisz | F1: pomoc", True, (230,230,230))
    screen.blit(sub, (10, 32))
    # Ścieżka pliku
    path_txt = FONT.render(f"Plik: {SAVE_PATH}", True, (210, 220, 230))
    screen.blit(path_txt, (10, 52))

    # Panel statusu
    y = HEIGHT - 24
    pygame.draw.rect(screen, (40,60,80), (0, y, WIDTH, 24))
    group = getattr(selected, 'group', '-') if selected else '-'
    sel = f"Sel: {selected.kind if selected else '-'} | group={group}"
    screen.blit(FONT.render(sel, True, (255,255,255)), (10, y+4))
    screen.blit(FONT.render(f"snap={'ON' if snap_enabled else 'OFF'}", True, (255,255,255)), (WIDTH-120, y+4))
    ml = current_mast_length()
    if ml:
        mast_txt = FONT.render(f"Mast length: {ml}px", True, (1, 1, 1))
        screen.blit(mast_txt, (10, 72))

    


def help_overlay():
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0,0,0,160))
    screen.blit(overlay, (0,0))
    lines = [
        "Skróty:",
        "LPM – wybór/przeciąganie (Shift: duplikuj)",
        "Końcówki linii: przeciągaj uchwyty (kółka)",
        "I/K – końcówka p2 ↑/↓,  J/L – p1 ↑/↓,  Ctrl+↑/↓ – szybciej",
        "Strzałki – przesuwaj (Shift: x5)",
        "Q/W – szerokość (rect) | A/S – wysokość (rect)",
        "Scroll – grubość (line) / promień (rect)",
        "C – zmień kolor | G – grid ON/OFF",
        "[ / ] – zmiana Z-order (w dół / w górę)",
        "1/2/3/4 – group: board/foil/rider/extras",
        "R – cykl promienia narożników (rect)",
        "N – nowy rect | K – nowa linia | Del – usuń",
        "Ctrl+S – zapisz JSON | Ctrl+O – wczytaj JSON",
        f"Plik: {SAVE_PATH}",
    ]
    x, y = 120, 80
    for i, line in enumerate(lines):
        screen.blit(BIG.render(line, True, (255,255,255)), (x, y + i*26))


def save_json(path=SAVE_PATH):
    data = []
    for s in shapes:
        data.append(s.to_json())
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Zapisano: {path}")


def load_json(path=SAVE_PATH):
    global shapes
    if not os.path.exists(path):
        print(f"[!] Brak pliku: {path}")
        return
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    new_shapes = []
    for d in data:
        if d.get('kind') == 'rect':
            d['color'] = tuple(d.get('color', [245,245,245]))
            new_shapes.append(RectShape(**{k:d[k] for k in ['kind','x','y','w','h','color','radius','group'] if k in d}))
        elif d.get('kind') == 'line':
            d['color'] = tuple(d.get('color', [20,20,20]))
            new_shapes.append(LineShape(**{k:d[k] for k in ['kind','x1','y1','x2','y2','width','color','group'] if k in d}))
    shapes = new_shapes
    print(f"[OK] Wczytano: {path} ({len(shapes)} elementów)")


def hit_test(mx, my):
    """Zwraca (shape, which): which ∈ {'rect','line','p1','p2'}"""
    # od góry (ostatnie narysowane na wierzchu)
    for s in reversed(shapes):
        if s.kind == 'rect' and s.bbox().collidepoint(mx, my):
            return s, 'rect'
        if s.kind == 'line':
            x1, y1 = s.x1, s.y1
            x2, y2 = s.x2, s.y2
            # priorytet – końcówki
            if _near(mx, my, x2, y2):
                return s, 'p2'
            if _near(mx, my, x1, y1):
                return s, 'p1'
            bb = s.bbox().inflate(8, 8)
            if bb.collidepoint(mx, my):
                return s, 'line'
    return None, None


def cycle_color(s):
    global palette_idx
    palette_idx = (palette_idx + 1) % len(PALETTE)
    s.color = PALETTE[palette_idx]


def reorder(selected, direction):
    # direction: -1 w dół, +1 w górę
    if selected is None:
        return
    i = shapes.index(selected)
    j = i + direction
    if 0 <= j < len(shapes):
        shapes[i], shapes[j] = shapes[j], shapes[i]


def main():
    global selected, snap_enabled, help_visible
    dragging = False
    drag_dx = drag_dy = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Auto-zapis przy wyjściu
                try:
                    save_json()
                except Exception as e:
                    print('[!] Auto-save error:', e)
                pygame.quit(); sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if event.button == 1:
                    s, which = hit_test(mx, my)
                    if s:
                        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                            # duplikuj
                            s2 = RectShape(**asdict(s)) if s.kind == 'rect' else LineShape(**asdict(s))
                            shapes.append(s2)
                            selected = s2
                            selected_handle = which if which in ('rect','line') else 'line'
                        else:
                            selected = s
                            selected_handle = which
                        dragging = True
                        if s.kind == 'rect' and selected_handle == 'rect':
                            drag_dx = mx - s.x
                            drag_dy = my - s.y
                        elif s.kind == 'line' and selected_handle == 'line':
                            drag_dx = mx - s.x1
                            drag_dy = my - s.y1
                        else:
                            drag_dx = drag_dy = 0  # łapiemy końcówkę – bez offsetu
                    else:
                        selected = None
                        selected_handle = None
                if event.button == 4 and selected:  # scroll up
                    if selected.kind == 'line':
                        selected.width = max(1, selected.width + 1)
                    else:
                        selected.radius = min(16, selected.radius + 1)
                if event.button == 5 and selected:  # scroll down
                    if selected.kind == 'line':
                        selected.width = max(1, selected.width - 1)
                    else:
                        selected.radius = max(0, selected.radius - 1)

            if event.type == pygame.MOUSEBUTTONUP:
                dragging = False
                selected_handle = None

            if event.type == pygame.MOUSEMOTION and dragging and selected:
                mx, my = event.pos
                if selected.kind == 'rect' and selected_handle == 'rect':
                    nx, ny = mx - drag_dx, my - drag_dy
                    selected.x = snap(nx)
                    selected.y = snap(ny)
                elif selected.kind == 'line':
                    if selected_handle == 'line':
                        nx1, ny1 = mx - drag_dx, my - drag_dy
                        dx = selected.x2 - selected.x1
                        dy = selected.y2 - selected.y1
                        selected.x1 = snap(nx1)
                        selected.y1 = snap(ny1)
                        selected.x2 = snap(nx1 + dx)
                        selected.y2 = snap(ny1 + dy)
                    elif selected_handle == 'p1':
                        selected.x1 = snap(mx)
                        selected.y1 = snap(my)
                    elif selected_handle == 'p2':
                        selected.x2 = snap(mx)
                        selected.y2 = snap(my)

            if event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                step = 5 if (mods & pygame.KMOD_SHIFT) else 1

                if (mods & pygame.KMOD_CTRL) and event.key == pygame.K_s:
                    save_json()
                elif (mods & pygame.KMOD_CTRL) and event.key == pygame.K_o:
                    load_json()

                elif event.key == pygame.K_F1:
                    help_visible = not help_visible
                elif event.key == pygame.K_g:
                    snap_enabled = not snap_enabled
                elif event.key == pygame.K_c and selected:
                    cycle_color(selected)
                elif event.key == pygame.K_LEFT and selected:
                    if selected.kind == 'rect': selected.x -= step
                    else:
                        selected.x1 -= step; selected.x2 -= step
                elif event.key == pygame.K_RIGHT and selected:
                    if selected.kind == 'rect': selected.x += step
                    else:
                        selected.x1 += step; selected.x2 += step
                elif event.key == pygame.K_UP and selected:
                    if selected.kind == 'rect': selected.y -= step
                    else:
                        selected.y1 -= step; selected.y2 -= step
                elif event.key == pygame.K_DOWN and selected:
                    if selected.kind == 'rect': selected.y += step
                    else:
                        selected.y1 += step; selected.y2 += step
                elif event.key == pygame.K_q and selected and selected.kind == 'rect':
                    selected.w = max(1, selected.w - step)
                elif event.key == pygame.K_w and selected and selected.kind == 'rect':
                    selected.w += step
                elif event.key == pygame.K_a and selected and selected.kind == 'rect':
                    selected.h = max(1, selected.h - step)
                elif event.key == pygame.K_s and selected and selected.kind == 'rect':
                    selected.h += step
                elif event.key == pygame.K_r and selected and selected.kind == 'rect':
                    selected.radius = {0:6, 6:12}.get(selected.radius, 0)
                elif event.key == pygame.K_n:
                    shapes.append(RectShape())
                elif event.key == pygame.K_k:
                    shapes.append(LineShape())
                # Skróty do regulacji końcówek linii (np. masztu)
                if selected and getattr(selected, 'kind', None) == 'line':
                    # I/K – p2 góra/dół; J/L – p1 góra/dół
                    if event.key == pygame.K_i: selected.y2 -= step
                    if event.key == pygame.K_k: selected.y2 += step
                    if event.key == pygame.K_j: selected.y1 -= step
                    if event.key == pygame.K_l: selected.y1 += step
                    # Ctrl+strzałki – szybciej na p2
                    if (mods & pygame.KMOD_CTRL) and event.key == pygame.K_UP:
                        selected.y2 -= 5
                    if (mods & pygame.KMOD_CTRL) and event.key == pygame.K_DOWN:
                        selected.y2 += 5
                elif event.key == pygame.K_DELETE and selected:
                    shapes.remove(selected); selected = None
                elif event.key == pygame.K_LEFTBRACKET and selected:
                    reorder(selected, -1)
                elif event.key == pygame.K_RIGHTBRACKET and selected:
                    reorder(selected, +1)
                elif event.key == pygame.K_1 and selected:
                    selected.group = 'board'
                elif event.key == pygame.K_2 and selected:
                    selected.group = 'foil'
                elif event.key == pygame.K_3 and selected:
                    selected.group = 'rider'
                elif event.key == pygame.K_4 and selected:
                    selected.group = 'extras'

        # RYSOWANIE
        screen.fill((230,238,246))
        draw_grid()
        for s in shapes:
            s.draw(screen)
            # uchwyty końcówek dla linii
            if isinstance(s, LineShape):
                pygame.draw.circle(screen, (255,255,255), (int(s.x1), int(s.y1)), HANDLE_R, 1)
                pygame.draw.circle(screen, (255,255,255), (int(s.x2), int(s.y2)), HANDLE_R, 1)

        if selected:
            # podświetlenie bboxa
            pygame.draw.rect(screen, (255, 120, 0), selected.bbox().inflate(6,6), 1)
            # wyróżnij uchwyty wybranego masztu
            if isinstance(selected, LineShape):
                pygame.draw.circle(screen, (255,120,0), (int(selected.x1), int(selected.y1)), HANDLE_R, 2)
                pygame.draw.circle(screen, (255,120,0), (int(selected.x2), int(selected.y2)), HANDLE_R, 2)

        draw_ui()
        if help_visible:
            help_overlay()

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[BŁĄD]", e)
        pygame.quit()
        sys.exit(1)
