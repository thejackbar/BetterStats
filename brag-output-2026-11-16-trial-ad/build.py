"""Builds trial-ad/composition/index.html: a 4:5 Meta feed ad for the free trial, in the look of the
Player Cards launch video (dark red stage, real Applecross cards, italic Montserrat caps, card SFX).
Card markup is lifted verbatim from that video's generated index.html and only resized."""
import re
from pathlib import Path

HERE = Path(__file__).parent
# The Player Cards video project, from branch claude/wizardly-brahmagupta-rj4ypg (git archive it next to this folder).
OLD = (HERE.parent / "brag-output-2026-10-29-045309/composition/index.html").read_text()
W, H, DUR = 1080, 1350, 21.0

# ---- lift CSS + cards from the old composition -------------------------------------------------
old_css = OLD[OLD.find("<style>") + 7: OLD.find("</style>")]
# keep only the font face, card-face rules and the shared helpers; drop old 1920x1080 scene layout
keep = []
for line in old_css.splitlines():
    if line.startswith(("@font-face", ".cf", ".fr", ".pn", ".sc{", ".si", ".holo", ".glare", ".sheen", ".face", ".flip")):
        keep.append(line)
CARD_CSS = "\n".join(keep)


def block(start):
    depth = 0
    for m in re.finditer(r"<div\b|</div>", OLD[start:]):
        depth += -1 if m.group(0) == "</div>" else 1
        if depth == 0:
            return OLD[start:start + m.end()]


CARDS = {}
for m in re.finditer(r'<div class="sc"', OLD):
    b = block(m.start())
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))
    special = " Special " in txt
    name = re.search(r'white-space:nowrap;padding-right:\.16em">([^<]+)<', b)
    key = (name.group(1) if name else "?") + ("*" if special else "")
    CARDS.setdefault(key, b)


def card(key, scale, extra_style=""):
    b = CARDS[key]
    b = re.sub(r'^<div class="sc" style="width:[\d.]+px;height:[\d.]+px;',
               f'<div class="sc" style="width:{360*scale:.2f}px;height:{492*scale:.2f}px;{extra_style}', b, count=1)
    b = re.sub(r'<div class="si" style="transform:scale\([\d.]+\)', f'<div class="si" style="transform:scale({scale})', b, count=1)
    return b


WALL = ["Fletcher", "Shakespeare", "Camarda", "Wijesinghe", "Wilton", "Edwards", "Bhave", "Barendse", "Blakey",
        "Rogerson", "Castley", "Cooper", "Hutton", "Campbell", "Bateman", "Athulathmudali", "Sivapalan",
        "Bhave*", "Cooper*", "Campbell*", "Blakey*", "Fletcher*", "Edwards*", "Camarda", "Wilton"]
for k in WALL:
    assert k in CARDS, (k, sorted(CARDS))

wall_html = "".join(f'<div class="wc">{card(k, 0.62)}</div>' for k in WALL)
best = [("Wilton", "Most runs", 9247), ("Fletcher", "Most wickets", 711), ("Castley", "Most games", 445)]
best_html = "".join(
    f'<div class="bc" id="bc{i}">{card(k, 0.8)}<div class="bl"><span>{lab}</span><b id="bn{i}">0</b></div></div>'
    for i, (k, lab, _) in enumerate(best))
spec = ["Bhave*", "Cooper*", "Campbell*", "Blakey*"]
spec_lab = ["Centuries", "Five-fors", "Games milestones", "Career milestones"]
spec_html = "".join(f'<div class="spc" id="sp{i}">{card(k, 0.74)}<div class="spl">{spec_lab[i]}</div></div>'
                    for i, k in enumerate(spec))
seasons = [f"{y}/{str(y+1)[-2:]}" for y in range(2025, 1999, -1)]
season_html = "".join(f'<div class="chip">{s}</div>' for s in seasons)
end_cards = "".join(f'<div class="ec" id="ec{i}">{card(k, 0.62)}</div>' for i, k in enumerate(["Castley", "Wilton", "Fletcher"]))

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
.ttl{{position:absolute;left:90px;right:90px;top:120px;text-align:center}}
.ttl .kick{{margin-bottom:18px}}
/* s1 hook */
#wallrot{{position:absolute;left:50%;top:50%;width:1340px;height:1700px;margin-left:-670px;margin-top:-850px;transform:rotate(-7deg) scale(1.12)}}
#wall{{display:grid;grid-template-columns:repeat(5,223px);grid-auto-rows:305px;gap:22px;justify-content:center}}
#s1-scrim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 48%,rgba(4,7,11,.93) 0%,rgba(4,7,11,.82) 40%,rgba(4,7,11,.4) 100%)}}
#s1-badge{{position:absolute;left:90px;top:96px;padding:12px 24px 12px 14px;border-radius:999px;background:rgba(4,7,11,.85);border:1px solid rgba(255,255,255,.18);display:flex;align-items:center;gap:18px;font:700 22px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#e5e7eb}}
#s1-badge img{{width:70px;height:60px;object-fit:contain}}
#s1-head{{position:absolute;left:60px;right:60px;top:430px;text-align:center}}
.h1{{display:block;font:800 italic 150px/0.96 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em}}
.h1.r{{color:#ff4b4b}}
/* s2 best ever */
#brow{{position:absolute;left:0;right:0;top:470px;display:flex;justify-content:center;gap:24px}}
.bc{{width:288px;opacity:0}}
.bl{{margin-top:26px;text-align:center}}
.bl span{{display:block;font:700 22px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#cbd5e1}}
.bl b{{display:block;margin-top:6px;font:800 italic 78px/1 'AC','Montserrat',sans-serif;color:#fff;font-variant-numeric:tabular-nums;padding-right:.16em}}
/* s3 seasons */
#win{{position:absolute;left:310px;top:440px;width:460px;height:600px;overflow:hidden;-webkit-mask-image:linear-gradient(to bottom,transparent,#000 18%,#000 82%,transparent);mask-image:linear-gradient(to bottom,transparent,#000 18%,#000 82%,transparent)}}
#strip{{position:absolute;left:0;top:0;width:100%}}
.chip{{height:112px;margin:0 0 16px;border-radius:24px;display:grid;place-items:center;font:800 italic 72px 'AC','Montserrat',sans-serif;background:rgba(14,20,30,.9);border:2px solid rgba(255,255,255,.18);padding-right:.1em}}
#s3-foot{{position:absolute;left:90px;right:90px;top:1110px;text-align:center;font:600 30px 'Inter',sans-serif;color:#e5e7eb}}
/* s4 milestones */
#sgrid{{position:absolute;left:0;right:0;top:430px;display:grid;grid-template-columns:repeat(2,266px);gap:30px 60px;justify-content:center}}
.spc{{opacity:0}}
.spl{{margin-top:14px;text-align:center;font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#e5e7eb}}
/* s5 claim */
#ui{{position:absolute;left:110px;top:440px;width:860px;padding:44px 48px 48px;border-radius:30px;background:rgba(14,20,30,.95);border:1px solid rgba(255,255,255,.2);box-shadow:0 30px 80px rgba(0,0,0,.6)}}
.srch{{display:flex;align-items:center;gap:20px;padding:24px 30px;border-radius:18px;border:3px solid var(--green);font:600 40px 'Inter',sans-serif}}
.srch i{{font-style:normal;color:#94a3b8}}
#typed{{white-space:pre}}
#caret{{display:inline-block;width:3px;height:44px;background:#fff;vertical-align:middle}}
#stepbox{{position:relative;height:430px}}
#step1,#step2{{position:absolute;left:0;right:0;top:0}}
#res{{margin-top:22px;display:flex;align-items:center;gap:22px;padding:22px 26px;border-radius:18px;background:rgba(255,255,255,.07);opacity:0}}
#res img{{width:76px;height:64px;object-fit:contain}}
#res b{{display:block;font:700 36px 'Inter',sans-serif}}
#res span{{display:block;margin-top:4px;font:500 24px 'Inter',sans-serif;color:#94a3b8}}
#claim{{margin-top:26px;padding:28px;border-radius:18px;background:var(--green);color:#052e16;text-align:center;font:800 40px 'Inter',sans-serif;opacity:0}}
#fields{{margin-top:26px;opacity:0}}
.fld{{margin-top:16px}}
.fld label{{display:block;font:600 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;margin-bottom:10px}}
.fld div{{padding:20px 26px;border-radius:14px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.06);font:600 36px 'Inter',sans-serif}}
#ok{{margin-top:26px;padding:22px 28px;border-radius:16px;background:#14532d;font:700 32px 'Inter',sans-serif;opacity:0}}
#ok i{{font-style:normal;display:inline-block;width:46px;height:46px;line-height:46px;text-align:center;border-radius:50%;background:#22c55e;color:#052e16;margin-right:16px}}
#cursor{{position:absolute;left:0;top:0;opacity:0}}
/* s6 end */
#e-brand{{position:absolute;left:0;right:0;top:150px;display:flex;justify-content:center;align-items:center;gap:26px;opacity:0}}
#e-brand img{{width:120px;height:102px;object-fit:contain}}
#e-word{{font:800 italic 84px/1 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-1px;padding-right:.16em}}
#e-word em{{font-style:italic;color:var(--green)}}
#e-head{{position:absolute;left:60px;right:60px;top:330px;text-align:center}}
.e1{{display:block;font:800 italic 138px/0.96 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em;opacity:0}}
.e1.r{{color:#ff4b4b}}
#e-sub{{position:absolute;left:90px;right:90px;top:640px;text-align:center;font:600 42px 'Inter',sans-serif;color:#e5e7eb;opacity:0}}
#e-btn{{position:absolute;left:190px;right:190px;top:740px;padding:34px 20px;border-radius:999px;background:var(--green);color:#052e16;text-align:center;font:800 46px 'Inter',sans-serif;opacity:0;box-shadow:0 0 60px rgba(52,211,153,.45)}}
#e-url{{position:absolute;left:0;right:0;top:880px;text-align:center;font:700 34px 'JetBrains Mono',monospace;letter-spacing:2px;color:#fff;opacity:0}}
.ec{{position:absolute;top:960px;opacity:0}}
#ec0{{left:150px;transform:rotate(-12deg)}}
#ec1{{left:428px;top:930px}}
#ec2{{left:706px;transform:rotate(12deg)}}
"""

BODY = f"""
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="{W}" data-height="{H}">
<div id="bg"></div><div id="glow"></div>

<div id="s1" class="clip scene" data-start="0" data-duration="3.4" data-track-index="1">
 <div id="wallrot" data-layout-ignore><div id="wall">{wall_html}</div></div>
 <div id="s1-scrim"></div>
 <div id="s1-badge"><img src="assets/img/applecross-logo.png" alt=""><span>Example club · Applecross CC</span></div>
 <div id="s1-head"><span class="h1" id="h1a">Who's your</span><span class="h1" id="h1b">club's</span><span class="h1 r" id="h1c">best ever?</span></div>
</div>

<div id="s2" class="clip scene" data-start="3.4" data-duration="4.4" data-track-index="1">
 <div class="ttl" id="s2-t"><div class="kick">From every scorecard</div><div class="t">Already<br><em>worked out.</em></div></div>
 <div id="brow">{best_html}</div>
</div>

<div id="s3" class="clip scene" data-start="7.8" data-duration="3.2" data-track-index="1">
 <div class="ttl" id="s3-t"><div class="kick">Your club's history</div><div class="t" style="font-size:80px">Every season.<br><em>Every scorecard.</em></div></div>
 <div id="win"><div id="strip">{season_html}</div></div>
 <div id="s3-foot">Synced from Cricket Australia. Kept up to date.</div>
</div>

<div id="s4" class="clip scene" data-start="11" data-duration="3.4" data-track-index="1">
 <div class="ttl" id="s4-t"><div class="kick">Milestones and records</div><div class="t">Flagged<br><em>for you.</em></div></div>
 <div id="sgrid">{spec_html}</div>
</div>

<div id="s5" class="clip scene" data-start="14.4" data-duration="3.0" data-track-index="1">
 <div class="ttl" id="s5-t"><div class="kick">About a minute</div><div class="t">Find your club.<br><em>Claim it.</em></div></div>
 <div id="ui">
  <div class="srch"><i>&#9906;</i><span id="typed"></span><span id="caret"></span></div>
  <div id="stepbox"><div id="step1"><div id="res"><img src="assets/img/applecross-logo.png" alt=""><div><b>Applecross Cricket Club</b><span>Applecross, WA</span></div></div>
  <div id="claim">Claim Applecross</div></div>
  <div id="step2"><div id="fields"><div class="fld"><label>First name</label><div>Sam</div></div><div class="fld"><label>Email</label><div>sam@yourclub.com.au</div></div></div>
  <div id="ok"><i>&#10003;</i>Your club is live</div></div></div>
 </div>
 <svg id="cursor" width="44" height="54" viewBox="0 0 22 27"><path d="M1 1 L1 22 L7 17 L11 26 L15 24 L11 15 L19 15 Z" fill="#fff" stroke="#000" stroke-width="1.5"/></svg>
</div>

<div id="s6" class="clip scene" data-start="17.4" data-duration="3.6" data-track-index="1">
 <div id="e-brand"><img src="assets/img/bettercricket-logo.png" alt=""><div id="e-word">Better<em>Cricket</em></div></div>
 <div id="e-head"><span class="e1">Find your</span><span class="e1 r">club.</span></div>
 <div id="e-sub">Free 14-day trial · No credit card</div>
 <div id="e-btn">Start your free trial</div>
 <div id="e-url">betterat.cricket/trial</div>
 {end_cards}
</div>
"""

# ---- audio --------------------------------------------------------------------------------------
sfx = []
def S(t, f, vol=0.5, d=0.6):
    sfx.append((t, f, vol, d))
for i in range(6):
    S(0.08 + i * 0.09, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4"][i % 3], 0.35)
S(0.52, "impact/impactSoft_medium_001", 0.7, 0.2)
S(1.02, "impact/impactSoft_medium_002", 0.6, 0.2)
S(1.52, "impact/impactSoft_heavy_001", 0.8, 0.5)
for i, t in enumerate([4.02, 4.52, 5.02]):
    S(t, "casino/card-place-1" if i % 2 == 0 else "casino/card-place-2", 0.7)
S(5.6, "interface/bong_001", 0.5, 0.2)
S(7.82, "ui/rollover2", 0.6, 0.1)
S(8.3, "casino/card-shuffle", 0.45, 1.2)
for i, t in enumerate([11.52, 11.77, 12.02, 12.27]):
    S(t, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4", "casino/card-slide-1"][i], 0.5)
S(12.6, "impact/impactBell_heavy_000", 0.4, 1.4)
for i in range(10):
    S(14.75 + i * 0.07, "interface/click_002", 0.35, 0.05)
S(15.62, "interface/click_003", 0.8, 0.05)
S(16.62, "interface/bong_001", 0.6, 0.2)
S(17.52, "casino/card-fan-1", 0.55, 0.7)
S(18.02, "impact/impactBell_heavy_000", 0.7, 1.4)
audio = [f'<audio id="music" data-timeline-role="music" data-start="0" data-duration="{DUR}" data-media-start="3" '
         f'data-track-index="2" data-volume="0.55" data-fade-out="1.5" src="assets/music/bed.mp3"></audio>']
for i, (t, f, v, d) in enumerate(sfx):
    audio.append(f'<audio id="sfx{i}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{3 + i % 12}" '
                 f'data-volume="{v}" src="assets/sfx/{f}.ogg"></audio>')

# ---- timeline -----------------------------------------------------------------------------------
JS = """
const tl = gsap.timeline({ paused: true });
const F = (s, a, b, t) => tl.fromTo(s, a, b, t);
// S1 hook: wall rises, three words punch on the beat
F('.wc', { y: 140, opacity: 0.35 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out', stagger: { each: 0.03, from: 'center', grid: [5, 5] } }, 0.0);
F('#wallrot', { scale: 1.2 }, { scale: 1.08, duration: 3.4, ease: 'none' }, 0.0);
F('#s1-badge', { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.35 }, 0.2);
F('#h1a', { opacity: 1, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }, 0.0);
F('#h1b', { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.28, ease: 'back.out(2)' }, 0.5);
F('#h1c', { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.32, ease: 'back.out(2.2)' }, 1.0);
tl.to('#s1-head', { scale: 1.04, duration: 1.6, ease: 'sine.inOut' }, 1.8);
// S2 best ever: cards land on beats, counters roll
F('#s2-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 3.45);
const best = [9247, 711, 445];
[4.0, 4.5, 5.0].forEach((t, i) => {
  F('#bc' + i, { opacity: 0, y: -260, rotation: i === 1 ? 0 : (i ? 10 : -10), scale: 1.25 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.4, ease: 'back.out(1.3)' }, t - 0.02);
  const o = { v: 0 };
  tl.to(o, { v: best[i], duration: 1.1, ease: 'power2.out', onUpdate: () => { document.getElementById('bn' + i).textContent = Math.round(o.v).toLocaleString('en-AU'); } }, t + 0.2);
});
tl.to('#bc0, #bc1, #bc2', { y: -10, duration: 1.4, ease: 'sine.inOut' }, 6.3);
// S3 seasons roll back
F('#s3-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 7.85);
F('#win', { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.3 }, 8.0);
F('#strip', { y: 0 }, { y: -(128 * 21), duration: 2.4, ease: 'power3.inOut' }, 8.2);
F('#s3-foot', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 8.8);
// S4 special cards
F('#s4-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 11.05);
[11.5, 11.75, 12.0, 12.25].forEach((t, i) => {
  F('#sp' + i, { opacity: 0, y: 160, rotation: (i % 2 ? 8 : -8), scale: 0.8 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.42, ease: 'back.out(1.4)' }, t);
});
tl.to('.spc .holo', { backgroundPosition: '90% 80%', duration: 1.8, ease: 'sine.inOut' }, 12.4);
tl.to('#sgrid', { scale: 1.03, duration: 1.8, ease: 'sine.inOut' }, 12.6);
// S5 claim flow
F('#s5-t', { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 14.45);
F('#ui', { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power3.out' }, 14.5);
const word = 'Applecross';
for (let i = 1; i <= word.length; i++) tl.set('#typed', { textContent: word.slice(0, i) }, 14.75 + (i - 1) * 0.07);
tl.to('#caret', { opacity: 0, duration: 0.01, repeat: 5, yoyo: true, repeatDelay: 0.25 }, 14.5);
F('#res', { opacity: 0, y: -16 }, { opacity: 1, y: 0, duration: 0.25 }, 15.3);
F('#claim', { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.25, ease: 'back.out(2)' }, 15.4);
F('#cursor', { x: 980, y: 1250, opacity: 0 }, { x: 560, y: 840, opacity: 1, duration: 0.4, ease: 'power2.inOut' }, 15.2);
tl.to('#claim', { scale: 0.95, duration: 0.07 }, 15.62);
tl.to('#claim', { scale: 1, duration: 0.1 }, 15.69);
tl.to('#cursor', { opacity: 0, duration: 0.15 }, 15.8);
tl.to('#step1', { opacity: 0, y: -20, duration: 0.2 }, 15.85);
F('#fields', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, 15.95);
F('#ok', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 16.6);
// S6 end card
F('#e-brand', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, 17.45);
F('.e1', { opacity: 0, y: 40, scale: 1.2 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'back.out(1.6)', stagger: 0.2 }, 17.6);
F('#e-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 18.0);
F('#e-btn', { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.8)' }, 18.1);
F('#e-url', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 18.3);
F('#ec0', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 17.5);
F('#ec1', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 17.6);
F('#ec2', { opacity: 0, y: 260 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' }, 17.7);
tl.to('#e-btn', { scale: 1.04, duration: 0.5, ease: 'sine.inOut', repeat: 4, yoyo: true }, 18.6);
// stage glow breathes with the beat (0.5s at 120 BPM)
tl.to('#glow', { opacity: 0.6, duration: 0.25, ease: 'sine.inOut', repeat: 83, yoyo: true }, 0.02);
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
print("cards:", len(CARDS), sorted(CARDS)[:40])
print("bytes:", len(html))
