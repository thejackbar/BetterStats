"""Builds composition/index.html: a 4:5 Meta feed ad for the free trial that sells Player Cards, in the
look of the Player Cards launch video. Card faces, pack art and the flip cards are lifted verbatim from
that video's generated index.html (branch claude/wizardly-brahmagupta-rj4ypg) and only resized."""
import re
from pathlib import Path

HERE = Path(__file__).parent
# The Player Cards video project (git archive it next to this folder).
OLD_PATH = HERE.parent / "brag-output-2026-10-29-045309/composition/index.html"
if not OLD_PATH.exists():
    OLD_PATH = HERE.parent / "pc/brag-output-2026-10-29-045309/composition/index.html"
OLD = OLD_PATH.read_text()
W, H, DUR = 1080, 1350, 23.0

old_css = OLD[OLD.find("<style>") + 7: OLD.find("</style>")]
CARD_CSS = "\n".join(l for l in old_css.splitlines() if l.startswith(
    ("@font-face", ".cf", ".fr", ".pn", ".sc{", ".si", ".holo", ".glare", ".sheen", ".face", ".flip", ".pstar", ".pk-rule")))


def block_at(start):
    depth = 0
    for m in re.finditer(r"<div\b|</div>", OLD[start:]):
        depth += -1 if m.group(0) == "</div>" else 1
        if depth == 0:
            return OLD[start:start + m.end()]


CARDS = {}
for m in re.finditer(r'<div class="sc"', OLD):
    b = block_at(m.start())
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))
    name = re.search(r'white-space:nowrap;padding-right:\.16em">([^<]+)<', b)
    if not name:
        continue
    CARDS.setdefault(name.group(1) + ("*" if " Special " in txt else ""), b)


def card(key, scale):
    b = CARDS[key]
    b = re.sub(r'^<div class="sc" style="width:[\d.]+px;height:[\d.]+px;',
               f'<div class="sc" style="width:{360*scale:.2f}px;height:{492*scale:.2f}px;', b, count=1)
    return re.sub(r'<div class="si" style="transform:scale\([\d.]+\)', f'<div class="si" style="transform:scale({scale})', b, count=1)


def find(pattern, nth=0):
    starts = [m.start() for m in re.finditer(pattern, OLD)]
    return block_at(starts[nth])


packs = [find(r'<div class="pk"', i) for i in range(4)]          # starter, weekly, runs, wickets
sealed = find(r'<div id="sealed-in"')
flips = []
for i in range(3):                                               # common, rare, legendary
    b = find(r'<div class="fw"', i)
    b = re.sub(r'^<div class="fw" id="c(\d)" style="[^"]*"', rf'<div class="fw" id="c\1"', b, count=1)
    flips.append(b)

WALL = ["Fletcher", "Shakespeare", "Camarda", "Wijesinghe", "Wilton", "Edwards", "Bhave", "Barendse", "Blakey",
        "Rogerson", "Castley", "Cooper", "Hutton", "Campbell", "Bateman", "Athulathmudali", "Sivapalan",
        "Bhave*", "Cooper*", "Campbell*", "Blakey*", "Fletcher*", "Edwards*", "Camarda", "Wilton"]
wall_html = "".join(f'<div class="wc">{card(k, 0.62)}</div>' for k in WALL)
pack_html = "".join(f'<div class="pkw" id="pk{i}">{p}</div>' for i, p in enumerate(packs))
flip_html = "".join(flips)
tiers = [("Common", "t0"), ("Rare", "t1"), ("Legendary", "t3")]
lab_html = "".join(f'<div class="lab" id="lab{i}"><span class="lt {c}">{n}</span><span class="new">New</span></div>'
                   for i, (n, c) in enumerate(tiers))
spec = ["Bhave*", "Cooper*", "Campbell*", "Blakey*"]
spec_lab = ["Centuries", "Five-fors", "Games milestones", "Career milestones"]
spec_html = "".join(f'<div class="spc" id="sp{i}">{card(k, 0.74)}<div class="spl">{spec_lab[i]}</div></div>'
                    for i, k in enumerate(spec))
get_html = "".join(f'<div class="swc" id="g{i}">{card(k, 0.5)}</div>' for i, k in enumerate(["Castley", "Fletcher*"]))
give_html = "".join(f'<div class="swc" id="v{i}">{card(k, 0.5)}</div>' for i, k in enumerate(["Hutton", "van Deuren"]))
end_cards = "".join(f'<div class="ec" id="ec{i}">{card(k, 0.62)}</div>' for i, k in enumerate(["Bhave*", "Fletcher", "Cooper*"]))

CSS = f"""{CARD_CSS}
:root{{--acc:#ff0000;--green:#34d399}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#04070b;font-family:'Inter',sans-serif;color:#fff}}
#root{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden}}
#bg{{position:absolute;inset:0;background:radial-gradient(circle at 50% 42%,color-mix(in srgb,#ff0000 28%,#0b1018),#04070b 80%)}}
#glow{{position:absolute;left:40px;top:180px;width:1000px;height:1000px;border-radius:50%;background:radial-gradient(circle,rgba(255,50,50,.42),transparent 66%);opacity:.45}}
.scene{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden}}
.kick{{font:700 26px 'JetBrains Mono',monospace;letter-spacing:6px;text-transform:uppercase;color:#ff6b6b}}
.t{{font:800 italic 92px/1.0 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-.5px;padding-right:.16em}}
.t em{{font-style:italic;color:#ff4b4b}}
.ttl{{position:absolute;left:70px;right:70px;top:110px;text-align:center}}
.ttl .kick{{margin-bottom:18px}}
/* s1 hook */
#wallrot{{position:absolute;left:50%;top:50%;width:1340px;height:1700px;margin-left:-670px;margin-top:-850px;transform:rotate(-7deg) scale(1.12)}}
#wall{{display:grid;grid-template-columns:repeat(5,223px);grid-auto-rows:305px;gap:22px;justify-content:center}}
#s1-scrim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 48%,rgba(4,7,11,.93) 0%,rgba(4,7,11,.82) 40%,rgba(4,7,11,.4) 100%)}}
#s1-badge{{position:absolute;left:90px;top:96px;padding:12px 24px 12px 14px;border-radius:999px;background:rgba(4,7,11,.85);border:1px solid rgba(255,255,255,.18);display:flex;align-items:center;gap:18px;font:700 22px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#e5e7eb}}
#s1-badge img{{width:70px;height:60px;object-fit:contain}}
#s1-head{{position:absolute;left:50px;right:50px;top:420px;text-align:center}}
.h1{{display:block;font:800 italic 158px/0.95 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em}}
.h1.r{{color:#ff4b4b}}
#s1-sub{{position:absolute;left:0;right:0;top:1090px;text-align:center;font:600 30px 'JetBrains Mono',monospace;letter-spacing:4px;text-transform:uppercase;color:#e5e7eb}}
/* s2 one card */
#hero{{position:absolute;left:270px;top:430px;perspective:1600px}}
#hero-in{{transform-style:preserve-3d}}
#hero-cap{{position:absolute;left:0;right:0;top:1180px;text-align:center;font:700 30px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#e5e7eb}}
#hero-cap b{{color:#fff}}
/* s3 packs */
#pkgrid{{position:absolute;left:0;right:0;top:440px;display:grid;grid-template-columns:repeat(2,218px);gap:34px 100px;justify-content:center}}
.pkw{{width:253px;zoom:0.86;opacity:0}}
/* s4 the pull */
#dim{{position:absolute;inset:0;background:#000;opacity:0}}
#sealed{{position:absolute;left:375px;top:470px;zoom:1}}
#flash{{position:absolute;left:540px;top:700px;width:340px;height:340px;margin-left:-170px;margin-top:-170px;border-radius:50%;opacity:0;background:radial-gradient(circle,#fff,rgba(255,255,255,0) 68%)}}
.fw{{position:absolute;top:714px;width:396px;height:541px;perspective:1600px;opacity:0;zoom:0.7}}
#c0{{left:143px}}#c1{{left:573px}}#c2{{left:1003px}}
#c0,#c1,#c2{{transform-origin:50% 50%}}
.lab{{position:absolute;top:910px;width:277px;text-align:center;opacity:0}}
#lab0{{left:100px}}#lab1{{left:401px}}#lab2{{left:702px}}
.lt{{display:block;font:800 italic 44px 'AC','Montserrat',sans-serif;text-transform:uppercase;padding-right:.16em}}
.t0{{color:#e5e7eb}}.t1{{color:#dbe4ee}}.t3{{color:#f0d0ff}}
.new{{display:inline-block;margin-top:10px;padding:3px 14px;border-radius:10px;background:#22c55e;color:#052e16;font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase}}
#pull-foot{{position:absolute;left:0;right:0;top:1090px;text-align:center;font:600 30px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#cbd5e1;opacity:0}}
/* s5 specials */
#sgrid{{position:absolute;left:0;right:0;top:430px;display:grid;grid-template-columns:repeat(2,266px);gap:30px 60px;justify-content:center}}
.spc{{opacity:0}}
.spl{{margin-top:14px;text-align:center;font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#e5e7eb}}
/* s6 swap */
#sw{{position:absolute;left:90px;top:470px;width:900px;padding:36px 44px 40px;border-radius:30px;background:rgba(14,20,30,.95);border:1px solid rgba(255,255,255,.2);box-shadow:0 30px 80px rgba(0,0,0,.6)}}
.sw-h{{display:flex;align-items:center;gap:22px}}
.av{{width:84px;height:84px;border-radius:50%;object-fit:cover;object-position:50% 22%;box-shadow:0 0 0 4px rgba(255,255,255,.35)}}
.sw-t{{font:500 36px/1.2 'Inter',sans-serif}}
.sw-t b{{font-weight:800}}
.sw-row{{display:flex;align-items:center;justify-content:space-between;margin-top:30px}}
.sl{{font:600 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#cbd5e1;margin-bottom:14px}}
.cr{{display:flex;gap:18px}}
.arrow{{font:700 72px 'Inter',sans-serif;color:#cbd5e1;padding:0 10px;margin-top:30px}}
#accept{{margin-top:30px;padding:24px;border-radius:16px;background:#d90000;text-align:center;font:700 32px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase}}
#done{{position:absolute;left:44px;right:44px;bottom:40px;padding:24px 30px;border-radius:16px;background:#14532d;font:700 34px 'Inter',sans-serif;opacity:0}}
#done i{{font-style:normal;display:inline-block;width:46px;height:46px;line-height:46px;text-align:center;border-radius:50%;background:#22c55e;color:#052e16;margin-right:16px}}
#cursor{{position:absolute;left:0;top:0;opacity:0}}
/* s7 end */
#e-brand{{position:absolute;left:0;right:0;top:120px;display:flex;justify-content:center;align-items:center;gap:24px;opacity:0}}
#e-brand img{{width:110px;height:94px;object-fit:contain}}
#e-word{{font:800 italic 76px/1 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-1px;padding-right:.16em}}
#e-word em{{font-style:italic;color:var(--green)}}
#e-kick{{position:absolute;left:0;right:0;top:250px;text-align:center;opacity:0}}
#e-head{{position:absolute;left:50px;right:50px;top:300px;text-align:center}}
.e1{{display:block;font:800 italic 128px/0.96 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em;opacity:0}}
.e1.r{{color:#ff4b4b}}
#e-sub{{position:absolute;left:80px;right:80px;top:580px;text-align:center;font:600 40px/1.3 'Inter',sans-serif;color:#e5e7eb;opacity:0}}
#e-btn{{position:absolute;left:190px;right:190px;top:730px;padding:34px 20px;border-radius:999px;background:var(--green);color:#052e16;text-align:center;font:800 46px 'Inter',sans-serif;opacity:0;box-shadow:0 0 60px rgba(52,211,153,.45)}}
#e-url{{position:absolute;left:0;right:0;top:868px;text-align:center;font:700 34px 'JetBrains Mono',monospace;letter-spacing:2px;color:#fff;opacity:0}}
.ec{{position:absolute;top:960px;opacity:0}}
#ec0{{left:150px;transform:rotate(-12deg)}}
#ec1{{left:428px;top:930px}}
#ec2{{left:706px;transform:rotate(12deg)}}
"""

BODY = f"""
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="{W}" data-height="{H}">
<div id="bg"></div><div id="glow"></div>

<div id="s1" class="clip scene" data-start="0" data-duration="3.2" data-track-index="1">
 <div id="wallrot" data-layout-ignore><div id="wall">{wall_html}</div></div>
 <div id="s1-scrim"></div>
 <div id="s1-badge"><img src="assets/img/applecross-logo.png" alt=""><span>Example club · Applecross CC</span></div>
 <div id="s1-head"><span class="h1" id="h1a">Every player</span><span class="h1" id="h1b">gets a</span><span class="h1 r" id="h1c">card.</span></div>
 <div id="s1-sub">BetterCricket Player Cards</div>
</div>

<div id="s2" class="clip scene" data-start="3.2" data-duration="3.4" data-track-index="1">
 <div class="ttl" id="s2-t"><div class="kick">Their real numbers</div><div class="t">Built from<br><em>career stats.</em></div></div>
 <div id="hero"><div id="hero-in">{card("Fletcher", 1.5)}</div></div>
 <div id="hero-cap">Ramon Fletcher · <b>711 wickets</b> · Rarity 99</div>
</div>

<div id="s3" class="clip scene" data-start="6.6" data-duration="2.8" data-track-index="1">
 <div class="ttl" id="s3-t"><div class="kick">Packs</div><div class="t" style="font-size:74px">Earned on the field.<br><em>Nothing to buy.</em></div></div>
 <div id="pkgrid">{pack_html}</div>
</div>

<div id="s4" class="clip scene" data-start="9.4" data-duration="4.0" data-track-index="1">
 <div id="dim"></div>
 <div class="ttl" id="s4-t"><div class="kick">Weekly pack</div><div class="t">Open your<br><em>packs.</em></div></div>
 <div id="sealed">{sealed}</div>
 <div id="flash"></div>
 {flip_html}
 {lab_html}
 <div id="pull-foot">Plus two more in the pack</div>
</div>

<div id="s5" class="clip scene" data-start="13.4" data-duration="2.6" data-track-index="1">
 <div class="ttl" id="s5-t"><div class="kick">Special cards</div><div class="t">For the<br><em>big moments.</em></div></div>
 <div id="sgrid">{spec_html}</div>
</div>

<div id="s6" class="clip scene" data-start="16.0" data-duration="2.7" data-track-index="1">
 <div class="ttl" id="s6-t"><div class="kick">Swaps</div><div class="t" style="font-size:78px">Swap with<br><em>your team-mates.</em></div></div>
 <div id="sw">
  <div class="sw-h"><img class="av" src="assets/photos/Jack_photo.webp" alt=""><div class="sw-t"><b>Jack Barendse</b> wants to swap with you</div></div>
  <div class="sw-row">
   <div><div class="sl">You get</div><div class="cr">{get_html}</div></div>
   <div class="arrow">&#8644;</div>
   <div><div class="sl">You give</div><div class="cr">{give_html}</div></div>
  </div>
  <div id="accept">Accept</div>
  <div id="done"><i>&#10003;</i>Swap done</div>
 </div>
 <svg id="cursor" width="44" height="54" viewBox="0 0 22 27"><path d="M1 1 L1 22 L7 17 L11 26 L15 24 L11 15 L19 15 Z" fill="#fff" stroke="#000" stroke-width="1.5"/></svg>
</div>

<div id="s7" class="clip scene" data-start="18.7" data-duration="4.3" data-track-index="1">
 <div id="e-brand"><img src="assets/img/bettercricket-logo.png" alt=""><div id="e-word">Better<em>Cricket</em></div></div>
 <div id="e-kick" class="kick">Player Cards</div>
 <div id="e-head"><span class="e1">Your club's</span><span class="e1 r">own cards.</span></div>
 <div id="e-sub">In the free 14-day trial.<br>No credit card.</div>
 <div id="e-btn">Start your free trial</div>
 <div id="e-url">betterat.cricket/trial</div>
 {end_cards}
</div>
"""

sfx = []
def S(t, f, vol=0.5, d=0.6):
    sfx.append((t, f, vol, d))
for i in range(6):
    S(0.08 + i * 0.09, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4"][i % 3], 0.35)
S(0.52, "impact/impactSoft_medium_001", 0.7, 0.2)
S(1.02, "impact/impactSoft_medium_002", 0.6, 0.2)
S(1.52, "impact/impactSoft_heavy_001", 0.8, 0.5)
S(3.52, "casino/card-place-1", 0.8, 0.7)
S(4.4, "ui/rollover2", 0.5, 0.1)
for i, t in enumerate([7.02, 7.27, 7.52, 7.77]):
    S(t, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4", "casino/card-slide-1"][i], 0.5)
for i in range(6):
    S(10.1 + i * 0.05, "interface/click_002", 0.25, 0.05)
S(10.52, "casino/cards-pack-open-1", 0.85, 0.94)
S(10.9, "casino/card-slide-1", 0.5)
S(11.32, "casino/card-place-1", 0.6, 0.7)
S(11.82, "casino/card-place-2", 0.6, 0.5)
S(12.32, "impact/impactSoft_heavy_001", 0.8, 0.5)
S(12.36, "impact/impactBell_heavy_000", 0.55, 1.4)
for i, t in enumerate([13.82, 14.07, 14.32, 14.57]):
    S(t, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4", "casino/card-slide-1"][i], 0.5)
S(16.1, "casino/card-slide-2", 0.5)
S(17.32, "interface/click_003", 0.9, 0.05)
S(17.45, "casino/card-slide-4", 0.6)
S(17.8, "interface/bong_001", 0.6, 0.2)
S(18.82, "casino/card-fan-1", 0.55, 0.7)
S(19.32, "impact/impactBell_heavy_000", 0.7, 1.4)
audio = [f'<audio id="music" data-timeline-role="music" data-start="0" data-duration="{DUR}" data-media-start="3" '
         f'data-track-index="2" data-volume="0.55" data-fade-out="1.5" src="assets/music/bed.mp3"></audio>']
for i, (t, f, v, d) in enumerate(sfx):
    audio.append(f'<audio id="sfx{i}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{3 + i % 12}" '
                 f'data-volume="{v}" src="assets/sfx/{f}.ogg"></audio>')

JS = """
const tl = gsap.timeline({ paused: true });
const F = (s, a, b, t) => tl.fromTo(s, a, b, t);
// S1 hook
F('.wc', { y: 140, opacity: 0.35 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out', stagger: { each: 0.03, from: 'center', grid: [5, 5] } }, 0.0);
F('#wallrot', { scale: 1.2 }, { scale: 1.08, duration: 3.2, ease: 'none' }, 0.0);
F('#s1-badge', { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.35 }, 0.2);
F('#h1a', { opacity: 1, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }, 0.0);
F('#h1b', { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.28, ease: 'back.out(2)' }, 0.5);
F('#h1c', { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.32, ease: 'back.out(2.2)' }, 1.0);
F('#s1-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 1.4);
tl.to('#s1-head', { scale: 1.04, duration: 1.6, ease: 'sine.inOut' }, 1.6);
// S2 one legendary card
F('#s2-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 3.25);
F('#hero', { opacity: 0, y: 200, scale: 0.6, rotation: -8 }, { opacity: 1, y: 0, scale: 1, rotation: 0, duration: 0.5, ease: 'back.out(1.4)' }, 3.3);
F('#hero-in', { rotationY: -16, rotationX: 6 }, { rotationY: 14, rotationX: -4, duration: 3.0, ease: 'sine.inOut' }, 3.4);
tl.to('#hero .holo', { backgroundPosition: '90% 80%', duration: 2.6, ease: 'sine.inOut' }, 3.6);
F('#hero-cap', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 4.3);
// S3 packs
F('#s3-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 6.65);
[7.0, 7.25, 7.5, 7.75].forEach((t, i) => {
  F('#pk' + i, { opacity: 0, y: 180, rotation: (i % 2 ? 7 : -7) }, { opacity: 1, y: 0, rotation: 0, duration: 0.4, ease: 'back.out(1.4)' }, t);
});
tl.to('#pkgrid', { scale: 1.03, duration: 1.2, ease: 'sine.inOut' }, 8.1);
// S4 the pull
F('#s4-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 9.45);
F('#sealed-in', { scale: 0.7, opacity: 0, y: 60 }, { scale: 1, opacity: 1, y: 0, duration: 0.4, ease: 'back.out(1.5)' }, 9.45);
tl.to('#sealed-in', { x: 9, duration: 0.05, yoyo: true, repeat: 7, ease: 'none' }, 10.1);
tl.to('#sealed-in', { scale: 1.1, duration: 0.2, ease: 'power2.in' }, 10.45);
tl.to('#tstrip', { x: 240, y: -190, rotation: 40, opacity: 0, duration: 0.5, ease: 'power2.out' }, 10.5);
F('#flash', { opacity: 0, scale: 0.2 }, { opacity: 1, scale: 3, duration: 0.35, ease: 'power2.out' }, 10.52);
tl.to('#tbody', { scaleY: 0.9, y: 50, opacity: 0, duration: 0.4, ease: 'power2.in' }, 10.6);
tl.to('#flash', { opacity: 0, duration: 0.4 }, 10.9);
tl.to('#sealed', { opacity: 0, duration: 0.01 }, 11.0);
const flipAt = [11.25, 11.75, 12.2];
for (let i = 0; i < 3; i++) {
  F('#c' + i, { y: 140, scale: 0.4, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.45, ease: 'power3.out' }, 10.8 + i * 0.1);
  tl.fromTo('#f' + i, { rotationY: 0 }, { rotationY: 180, duration: i === 2 ? 0.6 : 0.45, ease: 'power2.inOut' }, flipAt[i]);
  F('#lab' + i, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, flipAt[i] + 0.4);
}
tl.to('#dim', { opacity: 0.55, duration: 0.4 }, 12.0);
tl.to('#c2', { scale: 1.1, duration: 0.35, yoyo: true, repeat: 1, ease: 'sine.inOut' }, 12.6);
F('#pull-foot', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 12.75);
// S5 specials
F('#s5-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 13.45);
[13.8, 14.05, 14.3, 14.55].forEach((t, i) => {
  F('#sp' + i, { opacity: 0, y: 160, rotation: (i % 2 ? 8 : -8), scale: 0.8 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.4, ease: 'back.out(1.4)' }, t);
});
tl.to('.spc .holo', { backgroundPosition: '90% 80%', duration: 1.2, ease: 'sine.inOut' }, 14.7);
// S6 swap
F('#s6-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 16.05);
F('#sw', { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power3.out' }, 16.1);
F('.swc', { opacity: 0, y: 30, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.3, ease: 'power2.out', stagger: 0.08 }, 16.3);
F('#cursor', { x: 960, y: 1300, opacity: 0 }, { x: 560, y: 1080, opacity: 1, duration: 0.5, ease: 'power2.inOut' }, 16.75);
tl.to('#accept', { scale: 0.95, duration: 0.07 }, 17.32);
tl.to('#accept', { scale: 1, duration: 0.1 }, 17.39);
tl.to('#cursor', { opacity: 0, duration: 0.15 }, 17.5);
tl.to('#v0, #v1', { x: 260, opacity: 0, duration: 0.4, ease: 'power2.in', stagger: 0.06 }, 17.45);
tl.to('#g0, #g1', { boxShadow: '0 0 0 5px #22c55e, 0 0 40px rgba(34,197,94,.65)', duration: 0.3 }, 17.45);
tl.to('#accept', { opacity: 0, duration: 0.15 }, 17.6);
F('#done', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 17.75);
// S7 end card
F('#e-brand', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, 18.75);
F('#e-kick', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 18.9);
F('.e1', { opacity: 0, y: 40, scale: 1.2 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'back.out(1.6)', stagger: 0.2 }, 18.95);
F('#e-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 19.4);
F('#e-btn', { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.8)' }, 19.5);
F('#e-url', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 19.7);
F('#ec0', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 18.8);
F('#ec1', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 18.9);
F('#ec2', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 19.0);
tl.to('#e-btn', { scale: 1.04, duration: 0.5, ease: 'sine.inOut', repeat: 4, yoyo: true }, 20.0);
tl.to('#glow', { opacity: 0.6, duration: 0.25, ease: 'sine.inOut', repeat: 91, yoyo: true }, 0.02);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
tl.seek(0);
"""

html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
<script src="assets/gsap.min.js"></script>
<style>{CSS}</style></head><body>
{BODY}
{''.join(audio)}
</div>
<script>{JS}</script></body></html>"""
(HERE / "composition/index.html").write_text(html)
print("bytes:", len(html), "packs:", len(packs), "flips:", len(flips), "sealed ids:", re.findall(r'id="(t\w+)"', sealed))
