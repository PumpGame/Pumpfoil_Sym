import pygame, sys, random, math, random
import os
import json
import subprocess
import sys
import os

import os, sys, subprocess

import pygame, sys, math, struct, os, json, random

# Niski latency i 16-bit stereo
pygame.mixer.pre_init(44100, -16, 2, 512)

# na górze pliku (globalnie):
prev_pump_pressed = False
pump_cd = 0


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHAPES_PATH = os.path.join(BASE_DIR, "assets", "shapes_pumpfoil.json")

SAMPLE_RATE = 44100

def _envelope(i, n, a=0.01, d=0.15):
    # prosta ADS (A i D, bez S/R) – szybki atak i wygaszanie
    t = i / max(1, n-1)
    att = min(1.0, t / max(1e-6, a))
    dec = max(0.0, 1.0 - max(0.0, (t - a)) / max(1e-6, d))
    return max(0.0, min(1.0, att * dec))

def _tone(freq=440.0, ms=120, volume=0.4, wave='sine', sweep=0.0, noise=False):
    """Zwraca pygame.mixer.Sound z wygenerowanym dźwiękiem (stereo, 16-bit)."""
    n = int(SAMPLE_RATE * (ms/1000.0))
    frames = bytearray()
    phase = 0.0
    ph_inc = (2*math.pi*freq) / SAMPLE_RATE
    for i in range(n):
        # prosty sweep (dodatnia = w górę, ujemna = w dół)
        if sweep != 0.0:
            f = freq * (1.0 + sweep * (i/n))
            ph_inc = (2*math.pi*max(10.0, f)) / SAMPLE_RATE

        if noise:
            s = (random.random()*2.0 - 1.0)  # biały szum
        else:
            if wave == 'sine':
                s = math.sin(phase)
            elif wave == 'square':
                s = 1.0 if math.sin(phase) >= 0 else -1.0
            elif wave == 'tri':
                # trójkąt: przeskalowany sawtooth -> tri
                x = (phase / math.pi) % 2.0
                s = 2.0*(1.0 - abs(x-1.0)) - 1.0
            else:
                s = math.sin(phase)
        phase += ph_inc

        env = _envelope(i, n, a=0.01, d=0.2)
        val = int(32767 * volume * env * s)
        # stereo: L, R takie same
        frames += struct.pack('<hh', val, val)

    return pygame.mixer.Sound(buffer=bytes(frames))

# „Bank” dźwięków generowanych
SND = {}
def load_builtin_sounds():
    global SND
    SND = {
        # klik menu
        'click':  _tone(1000, ms=70,  volume=0.35, wave='square'),
        # start gry
        'start':  _tone(600,  ms=140, volume=0.35, wave='sine', sweep=+0.6),
        # pompka
        'pump':   _tone(160,  ms=120, volume=0.55, wave='sine', sweep=-0.5),
        # breach – wyjście skrzydła nad wodę
        'breach': _tone(700,  ms=160, volume=0.35, wave='sine', sweep=+1.2),
        # splash – deska w wodzie
        'splash': _tone(0,     ms=150, volume=0.5,  noise=True),
        # game over
        'go1':    _tone(500,  ms=130, volume=0.4,  wave='sine', sweep=-0.3),
        'go2':    _tone(300,  ms=180, volume=0.4,  wave='sine', sweep=-0.2),
        # --- Fale: dłuższy szum, zapętlany ---
        'waves': _waves_simple(ms=8000, base_vol=0.01),
    }

def _waves_simple(ms=8000, base_vol=0.25):
    """
    Prosty szum fal:
      - biały szum,
      - modulacja głośności sinusoidą (0.2 Hz ≈ 5s cykl),
      - długość 8s = pętla.
    """
    n = int(SAMPLE_RATE * (ms/1000.0))
    frames = bytearray()
    freq = 0.2  # częstotliwość modulacji (Hz) – wolne fale
    for i in range(n):
        noise = random.random()*2.0 - 1.0
        lfo = 0.7 + 0.3*math.sin(2*math.pi*freq * (i/SAMPLE_RATE))
        val = int(32767 * base_vol * noise * lfo)
        frames += struct.pack('<hh', val, val)
    return pygame.mixer.Sound(buffer=bytes(frames))



def run_editor():
    # UPEWNIJ SIĘ, ŻE NAZWA PLIKU SIĘ ZGADZA:
    editor_path = os.path.join(BASE_DIR, "pumpfoil_shape_editor.py")
    if not os.path.exists(editor_path):
        print("[ERR] Nie znaleziono edytora:", editor_path)
        return
    try:
        # przekazujemy ścieżkę do skina, by gra i edytor używały tego samego pliku
        subprocess.Popen([sys.executable, editor_path, SHAPES_PATH])
        print("[OK] Odpalono edytor:", editor_path)
    except Exception as e:
        print("[ERR] Błąd uruchamiania edytora:", e)


# ---------------------------------------------
#  Pumpfoil NES pumpfoil_shape_editor_pygame_wektorowy_edytor_skorek– rozbudowany prototyp
#  - Menu główne (Start / Wyjście)
#  - Rozgrywka: utrzymaj wysokość pompując (SPACJA / STRZAŁKA GÓRA)
#  - Game Over: wynik i opcje ponownej gry/menu
#  - Efekty: scrollujące tło, wodorosty, większy zakres masztu
# ---------------------------------------------

pygame.init()
load_builtin_sounds()


# -- USTAWIENIA OKNA
WIDTH, HEIGHT = 800, 450
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pumpfoil NES – retro")
clock = pygame.time.Clock()

# -- KOLORY
SKY   = (164, 200, 255)
WATER = (80, 180, 255)
WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
GRAY  = (160, 160, 160)
DARK  = (30, 30, 30)
GREEN = (0, 190, 110)
RED   = (220, 60, 60)
SKIN  = (255, 204, 170)
SUIT  = (60, 80, 180)
ACCENT= (250, 200, 40)

# -- CZCIONKI
font_small  = pygame.font.SysFont("Arial", 18)
font_medium = pygame.font.SysFont("Arial", 24, bold=True)
font_big    = pygame.font.SysFont("Arial", 36, bold=True)

# -- STANY GRY
STATE_MENU = "MENU"
STATE_PLAY = "PLAYING"
STATE_OVER = "GAME_OVER"

# -- PARAMETRY FIZYKI FOILA
water_line   = HEIGHT // 2                 # poziom wody
mast_length  = 200  # JESZCZE DŁUŻSZY maszt                          # DŁUŻSZY maszt (większy zakres pracy)
margin_top_px   = 10                        # minimalna głębokość skrzydła pod wodą (bardziej wybaczająca)
board_thickness = 20

# wolniejsze tempo / więcej czasu na reakcję
base_gravity = 0.1
base_pump    = -0.5
max_fall_vel = 1

# -- ZMIENNE ROZGRYWKI
score = 0
high_score = 0
board_x = 150
board_y = water_line - 28
velocity = 0.0

# -- PARALLAX / SKROL / OZDOBY
SCROLL_SPEED = 2
bg_far_x = 0
bg_mid_x = 0
seaweeds = []  # list[dict(x, y, sway, h)]
weed_timer = 0
WEED_SPAWN_FRAMES = 70

# -- SCROLL TŁA I WODOROSTY
scroll_x = 0
seaweed_list = []

def spawn_seaweed():
    h = random.randint(30, 80)
    x = WIDTH + random.randint(0, 200)
    seaweed_list.append(pygame.Rect(x, water_line - h, 12, h))

# -- PRZYCISKI
BTN_W, BTN_H = 320, 52

def btn_rect(center_x, y):
    return pygame.Rect(center_x - BTN_W//2, y, BTN_W, BTN_H)

btn_start = btn_rect(WIDTH//2, water_line - 60)
btn_quit  = btn_rect(WIDTH//2, water_line + 0)
btn_retry = btn_rect(WIDTH//2, water_line + 30)
btn_menu  = btn_rect(WIDTH//2, water_line + 90)
btn_editor = btn_rect(WIDTH//2, water_line + 100)


# -- FUNKCJE UTYLITY
def run_editor():
    editor_path = os.path.join(BASE_DIR, "pumpfoil_shape_editor.py")
    try:
        subprocess.Popen([sys.executable, editor_path])
    except Exception as e:
        print("Błąd uruchamiania edytora:", e)


def draw_button(rect: pygame.Rect, label: str, active: bool=False, color=GREEN):
    outline = (255, 255, 255) if active else (220, 220, 220)
    pygame.draw.rect(screen, color, rect, border_radius=10)
    pygame.draw.rect(screen, outline, rect, width=3, border_radius=10)

    # auto-dobór czcionki: medium, a jeśli nie mieści się - small
    f = font_medium
    if f.size(label)[0] > rect.width - 16:
        f = font_small

    txt = f.render(label, True, WHITE)
    screen.blit(txt, txt.get_rect(center=rect.center))



def reset_game():
    global board_y, velocity, score, seaweeds, weed_timer, bg_far_x, bg_mid_x
    board_y = water_line - 28
    velocity = 0.0
    score = 0
    seaweeds = []
    weed_timer = 0
    bg_far_x = 0
    bg_mid_x = 0
    scroll_x = 0
    seaweed_list = []


def update_physics():
    global board_y, velocity, score, bg_far_x, bg_mid_x, weed_timer, seaweeds

    # Sterowanie: pompowanie
    keys = pygame.key.get_pressed()
    if keys[pygame.K_SPACE] or keys[pygame.K_UP]:
        velocity = min(velocity, -1.0)
        velocity += base_pump

    # Grawitacja i ograniczenie opadania
    velocity += base_gravity
    velocity = min(velocity, max_fall_vel)

    # Aktualizacja pozycji
    board_y += velocity

    # Skrol tła
    bg_far_x  = (bg_far_x  - SCROLL_SPEED * 0.5) % WIDTH
    bg_mid_x  = (bg_mid_x  - SCROLL_SPEED * 1.0) % WIDTH

    # Spawn wodorostów (tylko w wodzie)
    weed_timer += 1
    if weed_timer >= WEED_SPAWN_FRAMES:
        weed_timer = 0
        base_y = random.randint(water_line + 12, HEIGHT - 18)
        height = random.randint(20, 46)
        seaweeds.append({
            'x': WIDTH + 10,
            'y': base_y,
            'h': height,
            'sway': random.random() * math.tau
        })

    # Ruch wodorostów i czyszczenie listy
    for w in seaweeds:
        w['x'] -= SCROLL_SPEED
        w['sway'] += 0.03
    seaweeds = [w for w in seaweeds if w['x'] > -20]

    # Wynik
    score += 1

    # spawn wodorostów
    if random.random() < 0.02:
        spawn_seaweed()

    # przesuwanie wodorostów
    for sw in seaweed_list:
        sw.x -= 2
    seaweed_list[:] = [sw for sw in seaweed_list if sw.right > 0]

    global prev_pump_pressed, pump_cd
    is_pump = keys[pygame.K_SPACE] or keys[pygame.K_UP]
    if pump_cd > 0: pump_cd -= 1
    if is_pump and not prev_pump_pressed and pump_cd == 0:
        snd = SND.get('pump')
        if snd: snd.play()
        pump_cd = 6  # krótki cooldown
    prev_pump_pressed = is_pump


def check_fail():
    foil_tip = board_y + mast_length
    board_bottom = board_y + board_thickness/2
    if foil_tip <= water_line + margin_top_px:
        return True, "Za wysoko – skrzydło wyszło do powierzchni"
    if board_bottom >= water_line:
        return True, "Za nisko – deska dotknęła wody"
    return False, ""


def draw_scene_base():
    # Niebo i woda (woda poniżej linii wody)
    screen.fill(SKY)

    # --- PARALLAX: daleki pas nad horyzontem (prosty piksel-art) ---
    # Rysujemy dwa segmenty przesuwane o WIDTH, by uzyskać pętlę
    def draw_far(offset):
        y = water_line - 50
        # garbiki jak odległe brzegi / chmury
        for i in range(-1, 8):
            cx = offset + i*90
            pygame.draw.polygon(screen, (200,220,255), [(cx-20,y+18),(cx+20,y+18),(cx,y)])
    draw_far(bg_far_x)
    draw_far(bg_far_x - WIDTH)

    # Warstwa wody
    pygame.draw.rect(screen, WATER, (0, water_line, WIDTH, HEIGHT - water_line))

    # --- PARALLAX: fale na wodzie (pas średni) ---
    def draw_mid(offset):
        y = water_line + 16
        for i in range(-1, 11):
            x = offset + i*64
            pygame.draw.arc(screen, WHITE, (x, y, 64, 18), math.pi, 2*math.pi, 2)
    draw_mid(bg_mid_x)
    draw_mid(bg_mid_x - WIDTH)

    # Linia wody
    pygame.draw.line(screen, WHITE, (0, water_line), (WIDTH, water_line), 3)

    # --- Wodorosty (ozdobne) ---
    for w in seaweeds:
        draw_seaweed(w)

    # prosty efekt scrollu fal (paski)
    for x in range(scroll_x, WIDTH, 40):
        pygame.draw.line(screen, (70,160,230), (x, water_line+2), (x+20, water_line+2), 3)

    # rysowanie wodorostów
    for sw in seaweed_list:
        pygame.draw.rect(screen, GREEN, sw)

# --- Definicja funkcji ---
def load_shapes(path=SHAPES_PATH):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print("[!] Błąd wczytywania shapes:", e)
        return []


# --- Globalne wczytanie przy starcie ---
shapes_data = load_shapes(SHAPES_PATH)



def _anchor_board_center(shapes_data):
    """Zwraca (ax, ay) – średni środek prostokątów group='board' z JSON.
       Dzięki temu kotwiczymy całą skórkę do pozycji board_x/board_y w grze."""
    xs, ys = [], []
    for s in shapes_data:
        if s.get('kind') == 'rect' and s.get('group') == 'board':
            xs.append(s['x'] + s['w']/2)
            ys.append(s['y'] + s['h']/2)
    if xs:
        return sum(xs)/len(xs), sum(ys)/len(ys)
    return 0.0, 0.0   # gdy brak 'board' – nic nie przesuwamy

def draw_shapes(shapes_data):
    ax, ay = _anchor_board_center(shapes_data)
    for s in shapes_data:
        kind  = s.get('kind')
        color = tuple(s.get('color', [255,255,255]))

        if kind == 'rect':
            x, y, w, h = s['x']-ax, s['y']-ay, s['w'], s['h']
            radius     = s.get('radius', 0)
            pygame.draw.rect(
                screen, color,
                (board_x + x, int(board_y) + y, w, h),
                border_radius=radius
            )

        elif kind == 'line':
            x1, y1 = s['x1']-ax, s['y1']-ay
            x2, y2 = s['x2']-ax, s['y2']-ay
            width  = s.get('width', 3)
            pygame.draw.line(
                screen, color,
                (board_x + x1, int(board_y) + y1),
                (board_x + x2, int(board_y) + y2),
                width
            )

def infer_mast_length(shapes_data, default_value=200):
    """
    Szuka 'masztu' w skórce i zwraca jego długość w pikselach.
    Kandydaci:
      - linie (kind='line') w group 'foil'/'mast' (albo bez group) – bierzemy |y2 - y1|
      - wysokie, wąskie prostokąty (kind='rect') w group 'foil'/'mast' – bierzemy 'h'
    Jeśli nic nie znajdzie, zwraca default_value.
    """
    candidates = []
    for s in shapes_data:
        grp = s.get('group', '')
        if s.get('kind') == 'line' and grp in ('foil', 'mast', ''):
            candidates.append(abs(s.get('y2', 0) - s.get('y1', 0)))
        elif s.get('kind') == 'rect' and grp in ('foil', 'mast', ''):
            w, h = s.get('w', 0), s.get('h', 0)
            if h > w * 1.5:  # “masztowe” proporcje
                candidates.append(h)
    return max(candidates) if candidates else default_value

# --- Wyliczanie długości masztu z JSON ---
def infer_mast_length(shapes_data, default_value=200):
    """
    Szuka masztu w skórce i zwraca jego długość (w px).
    Kandydaci:
      - linie (kind='line') w group 'foil'/'mast' (albo bez group): |y2 - y1|
      - wąskie, wysokie prostokąty (kind='rect') w group 'foil'/'mast': 'h'
    Jeśli nic nie znajdzie, zwraca default_value.
    """
    candidates = []

    # 1) jawna metadana, jeśli kiedyś dodasz {"kind":"meta","mast_length":...}
    for s in shapes_data:
        if s.get("kind") == "meta" and "mast_length" in s:
            try:
                ml = float(s["mast_length"])
                if ml > 0:
                    return int(ml)
            except Exception:
                pass

    # 2) linie i „masztowe” prostokąty
    for s in shapes_data:
        grp = (s.get("group") or "").lower()
        if s.get("kind") == "line" and grp in ("foil", "mast", ""):
            y1, y2 = s.get("y1", 0), s.get("y2", 0)
            candidates.append(abs(y2 - y1))
        elif s.get("kind") == "rect" and grp in ("foil", "mast", ""):
            w, h = s.get("w", 0), s.get("h", 0)
            if h > max(1, w) * 1.5:  # pionowa, „masztowa” proporcja
                candidates.append(h)

    return int(max(candidates)) if candidates else int(default_value)


# --- Globalne wczytanie skina i ustawienie mast_length przy starcie ---
print(f"[GAME] Using skin path: {SHAPES_PATH}")
shapes_data = load_shapes(SHAPES_PATH)  # ładowanie tylko raz
# Jeśli w kodzie wcześniej ustawiłeś mast_length, użyj go jako domyślnego fallbacku:
_default_ml = globals().get("mast_length", 200)
mast_length = infer_mast_length(shapes_data, default_value=_default_ml)
print(f"[GAME] mast_length from skin = {mast_length} px")


# --- Przeładowanie skina w trakcie gry (np. po zapisie w edytorze) ---
def reload_skin():
    global shapes_data, mast_length
    shapes_data = load_shapes(SHAPES_PATH)
    mast_length = infer_mast_length(shapes_data, default_value=mast_length)
    print(f"[GAME] Skin reloaded → mast_length={mast_length}, elements={len(shapes_data)}")


def draw_player():
    global shapes_data
    if shapes_data:
        draw_shapes(shapes_data)
        return
    # fallback – stary rysunek z prostokątów


    # Pozycje pomocnicze
    foil_tip = int(board_y + mast_length)
    by = int(board_y)

    # Maszt (przez taflę)
    pygame.draw.line(screen, BLACK, (board_x, by), (board_x, foil_tip), 5)

    # Deska – lekko szersza, retro
    board_w = 54
    pygame.draw.rect(screen, WHITE, (board_x - board_w//2, by - board_thickness//2, board_w, board_thickness), border_radius=4)

    # Skrzydło (pod wodą) – proste u-kształtowane skrzydło
    pygame.draw.rect(screen, GRAY, (board_x - 34, foil_tip - 5, 68, 10), border_radius=3)

    # --- POSTAĆ W STYLU 8-bit ---
    # Głowa
    head_w = 10; head_h = 10
    head_x = board_x - head_w//2
    head_y = by - board_thickness//2 - head_h - 6
    pygame.draw.rect(screen, SKIN, (head_x, head_y, head_w, head_h))

    # Tułów
    torso_w = 12; torso_h = 14
    torso_x = board_x - torso_w//2
    torso_y = head_y + head_h
    pygame.draw.rect(screen, SUIT, (torso_x, torso_y, torso_w, torso_h))

    # Ręce
    arm_w = 4; arm_h = 10
    pygame.draw.rect(screen, SUIT, (torso_x - arm_w, torso_y + 2, arm_w, arm_h))
    pygame.draw.rect(screen, SUIT, (torso_x + torso_w, torso_y + 2, arm_w, arm_h))

    # Nogi (dwie wąskie prostokąty w lekkim rozkroku)
    leg_w = 4; leg_h = 12
    leg_gap = 4
    leg_y = torso_y + torso_h
    pygame.draw.rect(screen, DARK, (board_x - leg_gap//2 - leg_w, leg_y, leg_w, leg_h))
    pygame.draw.rect(screen, DARK, (board_x + leg_gap//2,          leg_y, leg_w, leg_h))

def draw_seaweed(w):
    # proste łodygi z odgałęzieniami, kołyszą się delikatnie
    x = int(w['x'])
    base_y = int(w['y'])
    h = w['h']
    sway = math.sin(w['sway']) * 4
    stem_color = (20,120,70)
    leaf_color = (30,160,90)

    # łodyga
    pygame.draw.line(screen, stem_color, (x, base_y), (x+int(sway), base_y - h), 3)

    # listki
    for k in range(4):
        ly = base_y - int(h*(k+1)/5)
        pygame.draw.line(screen, leaf_color, (x+int(sway*0.6), ly), (x-10, ly-4), 2)
        pygame.draw.line(screen, leaf_color, (x+int(sway*0.6), ly), (x+10, ly-4), 2)

def draw_hud():
    s = font_small.render(f"Wynik: {score}", True, WHITE)
    hs = font_small.render(f"Rekord: {high_score}", True, WHITE)
    screen.blit(s, (10, 10))
    screen.blit(hs, (10, 30))


# --- MENU, GRA I GAME OVER FUNKCJE ---

def menu_loop():
    while True:
        for event in pygame.event.get():
            # --- wyjście okna ---
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # --- klawiatura ---
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    s_start = SND.get('start') if 'SND' in globals() else None
                    if s_start: s_start.play()
                    return

                elif event.key == pygame.K_F2:
                    s_click = SND.get('click') if 'SND' in globals() else None
                    if s_click: s_click.play()
                    run_editor()

                elif event.key == pygame.K_F5:
                    reload_skin()

            # --- mysz ---
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Bezpieczne pobranie dźwięków (mogą nie istnieć)
                s_click = SND.get('click') if 'SND' in globals() else None
                s_start = SND.get('start') if 'SND' in globals() else None

                if btn_start.collidepoint(event.pos):
                    if s_start: s_start.play()
                    return

                elif 'btn_editor' in globals() and btn_editor.collidepoint(event.pos):
                    if s_click: s_click.play()
                    run_editor()

                elif btn_quit.collidepoint(event.pos):
                    if s_click: s_click.play()
                    pygame.quit(); sys.exit()

        # --- rysowanie menu ---
        draw_scene_base()
        title = font_big.render("Pumpfoil NES", True, WHITE)
        subtitle = font_small.render("SPACE/↑ – Start  |  F2 – Edytor  |  F5 – Przeładuj skina", True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 90))
        screen.blit(subtitle, (WIDTH//2 - subtitle.get_width()//2, 130))

        mx, my = pygame.mouse.get_pos()
        draw_button(btn_start,  "Start",               btn_start.collidepoint((mx, my)))
        draw_button(btn_quit,   "Wyjście",             btn_quit.collidepoint((mx, my)), color=RED)
        if 'btn_editor' in globals():
            draw_button(btn_editor, "Edytor skórek (F2)", btn_editor.collidepoint((mx, my)), color=GRAY)
            bottom_y = max(btn_quit.bottom, btn_editor.bottom)
        else:
            bottom_y = btn_quit.bottom

        hint = font_small.render("ENTER/SPACE – Start  |  ESC – Wyjście", True, WHITE)
        screen.blit(hint, (WIDTH//2 - hint.get_width()//2, bottom_y + 16))

        pygame.display.flip()
        clock.tick(60)



def game_loop():
    global high_score
    reset_game()

    amb = SND.get('waves')  # jeśli generujesz/masz taki SFX
    if amb: amb.play(loops=-1)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pygame.quit(); sys.exit()

        update_physics()
        failed, reason = check_fail()

        draw_scene_base()
        draw_player()
        draw_hud()

        if failed:
            high_score = max(high_score, score)
            pygame.display.flip()
            return reason

        pygame.display.flip()
        clock.tick(50)


def game_over_loop(reason: str):
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_r:
                    return "RETRY"
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return "MENU"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_retry.collidepoint(event.pos):
                    return "RETRY"
                if btn_menu.collidepoint(event.pos):
                    return "MENU"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_editor.collidepoint(event.pos):
                    run_editor()

            

        draw_scene_base()
        title = font_big.render("GAME OVER", True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
        reason_txt = font_small.render(reason, True, WHITE)
        screen.blit(reason_txt, (WIDTH//2 - reason_txt.get_width()//2, 130))
        s = font_medium.render(f"Wynik: {score}", True, WHITE)
        hs = font_medium.render(f"Rekord: {high_score}", True, WHITE)
        screen.blit(s, (WIDTH//2 - s.get_width()//2, 170))
        screen.blit(hs, (WIDTH//2 - hs.get_width()//2, 200))
        mx, my = pygame.mouse.get_pos()
        draw_button(btn_retry, "Zagraj ponownie (R)", btn_retry.collidepoint((mx, my)))
        draw_button(btn_menu,  "Powrót do menu (ENTER)", btn_menu.collidepoint((mx, my)))
        hint = font_small.render("ESC – Wyjście", True, WHITE)
        screen.blit(hint, (WIDTH//2 - hint.get_width()//2, btn_menu.bottom + 16))
        pygame.display.flip()
        clock.tick(60)


# ---------------------------------------------
# PĘTLA APLIKACJI
# ---------------------------------------------
if __name__ == "__main__":
    state = STATE_MENU
    while True:
        if state == STATE_MENU:
            menu_loop()
            state = STATE_PLAY
        elif state == STATE_PLAY:
            reason = game_loop()
            state = STATE_OVER
        elif state == STATE_OVER:
            next_action = game_over_loop(reason)
            if next_action == "RETRY":
                state = STATE_PLAY
            else:
                state = STATE_MENU
