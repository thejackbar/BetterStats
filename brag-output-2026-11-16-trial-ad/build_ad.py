"""Builds composition/index.html: a 4:5 Meta feed ad that gets clubs to sign up to BetterCricket
(free trial). Content: your club's history, the sync, easy uploads, historical imports, milestone
tracking and more. Look borrowed from the Player Cards launch video (dark red stage, italic Montserrat
caps, foil-edged panels, card sound effects, the same music bed) but no player cards in it.
Names and numbers are illustrative and marked "Example club"."""
from pathlib import Path

HERE = Path(__file__).parent
W, H, DUR = 1080, 1350, 25.0
FOIL = "conic-gradient(from 0deg,#16c784,#a7f3d0,#3ee6a4,#7dd3fc,#3b82f6,#16c784)"

# ---- season tile wall (hook) ---------------------------------------------------------------------
grades = ["1st XI", "2nd XI", "3rd XI", "4th XI", "T20", "Women's", "Under 16"]
SHOTS = ["leaderboard", "hero-career-card", "feature-milestones", "premierships", "feature-honours", "yearbook",
         "club-dashboard-hero", "statlab-team-records", "stats-by-competition", "front-page-profile",
         "showcase-scorecard", "feature-leaderboard"]
CRESTS = ["applecross-cc", "gosnells-cc", "kalamunda-cc", "leeming-spartan-cc"]
# 7 rows x 5: a repeating pattern so no two neighbours are the same kind
PATTERN = "SPCPS" "PSPSC" "CPSPP" "PSCSP" "SPPCS" "PCSPS" "SPSPC"
tiles, si, pi, ci = [], 0, 0, 0
for kind in PATTERN:
    if kind == "S":
        y = 2025 - si * 3
        tiles.append(f'<div class="st"><div class="st-in"><b>{y}/{str(y + 1)[-2:]}</b>'
                     f'<span>{grades[si % len(grades)]} · {10 + (si * 7) % 9} games</span></div></div>')
        si += 1
    elif kind == "P":
        tiles.append(f'<div class="st sh"><img src="assets/img/wall/{SHOTS[pi % len(SHOTS)]}.jpg" alt=""></div>')
        pi += 1
    else:
        tiles.append(f'<div class="st cr"><div class="cr-in"><img src="assets/img/wall/{CRESTS[ci % len(CRESTS)]}.png" alt=""></div></div>')
        ci += 1
wall_html = "".join(tiles)

sheet_rows = [("J. Mercer", "1998/99", "412"), ("T. Okafor", "1998/99", "388"), ("R. Singh", "1999/00", "361"),
              ("D. Nguyen", "1999/00", "297"), ("A. Papadakis", "2000/01", "254")]
sheet_html = "".join(f'<div class="sr" id="sr{i}"><i>{i + 2}</i><span>{a}</span><span>{b}</span><span>{c}</span></div>'
                     for i, (a, b, c) in enumerate(sheet_rows))
dig_rows = [("L. Whitfield", "c Barry b Lane", "64"), ("J. Mercer", "b Holt", "31"), ("T. Okafor", "lbw b Lane", "22"),
            ("R. Singh", "not out", "18")]
dig_html = "".join(f'<div class="dr" id="dr{i}"><span>{a}</span><em>{b}</em><b>{c}</b></div>' for i, (a, b, c) in enumerate(dig_rows))
scribbles = "".join(f'<div class="scr" style="top:{70 + i * 46}px;width:{150 + (i * 53) % 120}px"></div>'
                    f'<div class="scr" style="top:{70 + i * 46}px;left:300px;width:{40 + (i * 29) % 40}px"></div>' for i in range(8))
miles = [("J. Mercer", "Catches", 49, 50, "1 to go"), ("T. Okafor", "Club games", 99, 100, "1 to go"),
         ("R. Singh", "Career runs", 4998, 5000, "2 to go")]
mile_html = "".join(
    f'<div class="mr" id="mr{i}"><div class="mt"><b>{n}</b><span>{lab}</span><i class="badge" id="mb{i}">{tg}</i></div>'
    f'<div class="mbar"><div class="mfill" id="mf{i}"></div></div><div class="mnum"><b id="mn{i}">0</b> / {goal:,}</div></div>'
    for i, (n, lab, have, goal, tg) in enumerate(miles))
more = [("#1", "Leaderboards"), ("164", "Club records"), ("★", "Player pages"), ("200+", "StatLab reports"),
        ("1st", "Honour boards"), ("25/26", "Yearbooks")]
more_html = "".join(f'<div class="mo" id="mo{i}"><div class="mo-in"><b>{a}</b><span>{b}</span></div></div>' for i, (a, b) in enumerate(more))

CSS = f"""@font-face{{font-family:'AC';src:url('assets/fonts/applecross-display.ttf') format('truetype');font-weight:100 900;font-style:normal}}
:root{{--green:#16c784;--green2:#34d399;--hi:#3ee6a4;--blue:#3b82f6;--foil:{FOIL}}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#05080e;font-family:'Inter',sans-serif;color:#fff}}
#root{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden}}
#bg{{position:absolute;inset:0;background:radial-gradient(circle at 30% 28%,rgba(22,199,132,.30),transparent 55%),radial-gradient(circle at 78% 72%,rgba(59,130,246,.22),transparent 55%),#0a0d14}}
#glow{{position:absolute;left:40px;top:180px;width:1000px;height:1000px;border-radius:50%;background:radial-gradient(circle,rgba(22,199,132,.32),transparent 66%);opacity:.45}}
.scene{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden}}
.kick{{font:700 26px 'JetBrains Mono',monospace;letter-spacing:6px;text-transform:uppercase;color:#6ee7b7}}
.t{{font:800 italic 90px/1.0 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-.5px;padding-right:.16em}}
.t em{{font-style:italic;color:var(--hi)}}
.ttl{{position:absolute;left:60px;right:60px;top:110px;text-align:center}}
.ttl .kick{{margin-bottom:18px}}
.foil{{position:absolute;padding:5px;border-radius:30px;background:var(--foil);box-shadow:0 30px 80px rgba(0,0,0,.6),0 0 40px rgba(22,199,132,.25)}}
.pnl{{border-radius:25px;background:linear-gradient(170deg,#141c28,#0a0f17);padding:36px 40px;position:relative;overflow:hidden}}
.ex{{position:absolute;right:26px;top:22px;font:700 18px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#94a3b8}}
.sheen{{position:absolute;top:-10%;bottom:-10%;width:30%;left:0;opacity:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.22),transparent);pointer-events:none}}
.tick{{display:inline-block;width:46px;height:46px;line-height:46px;text-align:center;border-radius:50%;background:#22c55e;color:#052e16;margin-right:16px;font-style:normal}}
.ok{{margin-top:24px;padding:20px 26px;border-radius:16px;background:#14532d;font:700 32px 'Inter',sans-serif;opacity:0}}
/* s1 wall */
#wallrot{{position:absolute;left:50%;top:50%;width:1400px;height:1900px;margin-left:-700px;margin-top:-950px;transform:rotate(-8deg)}}
#wall{{display:grid;grid-template-columns:repeat(5,250px);grid-auto-rows:160px;gap:22px;justify-content:center}}
.st{{padding:4px;border-radius:20px;background:var(--foil)}}
.st:nth-child(3n+1){{background:linear-gradient(145deg,#6ee7b7,#065f46)}}
.st:nth-child(3n+2){{background:linear-gradient(145deg,#e5e7eb,#475569)}}
.st-in{{height:100%;border-radius:16px;background:linear-gradient(170deg,color-mix(in srgb,#16c784 55%,#000),#0b1018);display:flex;flex-direction:column;justify-content:center;padding:0 24px}}
.st-in b{{font:800 italic 54px/1 'AC','Montserrat',sans-serif;padding-right:.1em}}
.st-in span{{margin-top:10px;font:700 18px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;color:#d1fae5}}
.st.sh img{{width:100%;height:100%;object-fit:cover;object-position:50% 20%;border-radius:16px;display:block}}
.cr-in{{height:100%;border-radius:16px;background:#fff;display:grid;place-items:center}}
.cr-in img{{height:118px;width:200px;object-fit:contain}}
#s1-scrim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 48%,rgba(6,10,18,.88) 0%,rgba(6,10,18,.66) 40%,rgba(6,10,18,.12) 100%)}}
#s1-head{{position:absolute;left:40px;right:40px;top:400px;text-align:center}}
.h1{{display:block;font:800 italic 156px/0.95 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em}}
.h1.r{{color:var(--hi)}}
#s1-sub{{position:absolute;left:0;right:0;top:1090px;text-align:center;font:700 30px 'JetBrains Mono',monospace;letter-spacing:4px;text-transform:uppercase;color:#e5e7eb}}
/* s2 sync */
#syncw{{left:90px;top:440px;width:900px}}
#syncw .pnl{{padding:60px 50px 44px}}
#ringbox{{display:flex;align-items:center;gap:40px}}
#ring{{width:300px;height:300px;border-radius:50%;background:conic-gradient(var(--green) calc(var(--p,0)*1%),rgba(255,255,255,.1) 0);display:grid;place-items:center;flex:none}}
#ring div{{width:248px;height:248px;border-radius:50%;background:#0d131d;display:grid;place-items:center;font:800 italic 64px 'AC','Montserrat',sans-serif}}
.cnt{{margin-bottom:22px}}
.cnt span{{display:block;font:700 22px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#94a3b8}}
.cnt b{{display:block;font:800 italic 78px/1 'AC','Montserrat',sans-serif;font-variant-numeric:tabular-nums;padding-right:.12em}}
#syncbtn{{margin-top:40px;padding:28px;border-radius:16px;background:var(--green);color:#052e16;text-align:center;font:800 34px 'Inter',sans-serif}}
#s2-foot{{position:absolute;left:0;right:0;top:1110px;text-align:center;font:600 30px 'Inter',sans-serif;color:#e5e7eb}}
/* s3 spreadsheet */
#sheetw{{left:90px;top:430px;width:900px}}
.shh,.sr{{display:grid;grid-template-columns:50px 1.5fr 1fr 0.8fr;gap:0;font:600 28px 'Inter',sans-serif}}
.shh div,.sr span,.sr i{{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,.1)}}
.shh div{{font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#cbd5e1;background:rgba(255,255,255,.06)}}
.sr i{{font-style:normal;color:#64748b;font-size:22px}}
.hc{{border-radius:8px;transition:none}}
#fields{{display:flex;gap:18px;margin-top:26px;justify-content:center}}
.fd{{padding:14px 26px;border-radius:999px;border:2px solid var(--green);font:700 26px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:var(--green);opacity:0}}
/* s4 scorebook */
#paper{{position:absolute;left:120px;top:440px;width:430px;height:470px;background:#f3ead2;border-radius:10px;box-shadow:0 30px 60px rgba(0,0,0,.6);transform:rotate(-5deg);overflow:hidden}}
#paper .ln{{position:absolute;left:20px;right:20px;height:1px;background:rgba(70,90,140,.35)}}
#paper .scr{{position:absolute;left:34px;height:10px;border-radius:5px;background:rgba(30,40,80,.65);transform:skewX(-14deg)}}
#paper .hd{{position:absolute;left:30px;top:22px;font:700 22px 'JetBrains Mono',monospace;color:#1e293b;letter-spacing:2px}}
#scan{{position:absolute;left:0;right:0;height:60px;top:0;background:linear-gradient(to bottom,transparent,rgba(52,211,153,.55),transparent);opacity:0}}
#digw{{left:500px;top:520px;width:500px}}
#digw .pnl{{padding:26px 28px}}
.dr{{display:grid;grid-template-columns:1.2fr 1.3fr 50px;gap:10px;padding:14px 0;border-bottom:1px solid rgba(255,255,255,.1);font:600 24px 'Inter',sans-serif;opacity:0}}
.dr em{{font-style:normal;color:#94a3b8;font-size:20px;align-self:center}}
.dr b{{text-align:right;font:800 italic 30px 'AC','Montserrat',sans-serif}}
#chips{{position:absolute;left:0;right:0;top:1080px;display:flex;justify-content:center;gap:16px}}
.chip{{padding:14px 24px;border-radius:999px;background:rgba(14,20,30,.92);border:1px solid rgba(255,255,255,.25);font:700 24px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;opacity:0}}
/* s5 milestones */
#milew{{left:90px;top:440px;width:900px}}
#milew .pnl{{padding-top:66px}}
.mr{{margin-bottom:34px}}
.mr:last-child{{margin-bottom:0}}
.mt{{display:flex;align-items:baseline;gap:18px}}
.mt b{{font:800 34px 'Inter',sans-serif}}
.mt span{{font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#94a3b8}}
.badge{{margin-left:auto;font-style:normal;padding:6px 16px;border-radius:999px;background:#fbbf24;color:#422006;font:800 22px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;opacity:0}}
.mbar{{margin-top:14px;height:22px;border-radius:11px;background:rgba(255,255,255,.1);overflow:hidden}}
.mfill{{height:100%;width:100%;border-radius:11px;background:linear-gradient(90deg,#22c55e,#34d399);transform-origin:0 50%;transform:scaleX(0)}}
.mnum{{margin-top:10px;font:600 24px 'JetBrains Mono',monospace;color:#cbd5e1}}
.mnum b{{color:#fff;font-variant-numeric:tabular-nums}}
/* s6 and more */
#mgrid{{position:absolute;left:0;right:0;top:430px;display:grid;grid-template-columns:repeat(2,420px);grid-auto-rows:200px;gap:28px;justify-content:center}}
.mo{{padding:5px;border-radius:26px;background:var(--foil);opacity:0}}
.mo:nth-child(2){{background:linear-gradient(145deg,#7dd3fc,#0e7490)}}
.mo:nth-child(3){{background:linear-gradient(145deg,#6ee7b7,#065f46)}}
.mo:nth-child(4){{background:linear-gradient(145deg,#7dd3fc,#1d4ed8)}}
.mo:nth-child(5){{background:linear-gradient(145deg,#e5e7eb,#475569)}}
.mo:nth-child(6){{background:linear-gradient(145deg,#a7f3d0,#047857)}}
.mo-in{{height:100%;border-radius:21px;background:linear-gradient(170deg,#141c28,#0a0f17);display:flex;flex-direction:column;justify-content:center;padding:0 34px}}
.mo-in b{{font:800 italic 70px/1 'AC','Montserrat',sans-serif;padding-right:.12em}}
.mo-in span{{margin-top:12px;font:700 26px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#e5e7eb}}
/* s7 end */
#endwall{{position:absolute;inset:0;opacity:.18}}
#e-brand{{position:absolute;left:0;right:0;top:150px;display:flex;justify-content:center;align-items:center;gap:24px;opacity:0}}
#e-brand img{{width:116px;height:98px;object-fit:contain}}
#e-word{{font:800 italic 80px/1 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-1px;padding-right:.16em}}
#e-word em{{font-style:italic;color:var(--green)}}
#e-head{{position:absolute;left:50px;right:50px;top:330px;text-align:center}}
.e1{{display:block;font:800 italic 150px/0.95 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em;opacity:0}}
.e1.r{{color:var(--hi)}}
#e-sub{{position:absolute;left:80px;right:80px;top:660px;text-align:center;font:600 40px/1.3 'Inter',sans-serif;color:#e5e7eb;opacity:0}}
#e-btn{{position:absolute;left:170px;right:170px;top:830px;padding:36px 20px;border-radius:999px;background:var(--green);color:#052e16;text-align:center;font:800 48px 'Inter',sans-serif;opacity:0;box-shadow:0 0 60px rgba(52,211,153,.45)}}
#e-url{{position:absolute;left:0;right:0;top:980px;text-align:center;font:700 36px 'JetBrains Mono',monospace;letter-spacing:2px;color:#fff;opacity:0}}
#e-chips{{position:absolute;left:0;right:0;top:1080px;display:flex;justify-content:center;gap:16px}}
"""

BODY = f"""
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="{W}" data-height="{H}">
<div id="bg"></div><div id="glow"></div>

<div id="s1" class="clip scene" data-start="0" data-duration="3.4" data-track-index="1">
 <div id="wallrot" data-layout-ignore><div id="wall">{wall_html}</div></div>
 <div id="s1-scrim"></div>
 <div id="s1-head"><span class="h1" id="h1a">Your club's</span><span class="h1" id="h1b">whole</span><span class="h1 r" id="h1c">history.</span></div>
 <div id="s1-sub">Every season · Every scorecard</div>
</div>

<div id="s2" class="clip scene" data-start="3.4" data-duration="3.8" data-track-index="1">
 <div class="ttl" id="s2-t"><div class="kick">From Cricket Australia</div><div class="t">Synced<br><em>for you.</em></div></div>
 <div class="foil" id="syncw"><div class="pnl"><div class="ex">Example club</div><div class="sheen" id="sh2"></div>
  <div id="ringbox"><div id="ring"><div id="pct">0%</div></div>
   <div><div class="cnt"><span>Games</span><b id="n0">0</b></div><div class="cnt"><span>Players</span><b id="n1">0</b></div><div class="cnt" style="margin:0"><span>Seasons</span><b id="n2">0</b></div></div></div>
  <div id="syncbtn">Sync now</div>
 </div></div>
 <div id="s2-foot">New games come in with one click.</div>
</div>

<div id="s3" class="clip scene" data-start="7.2" data-duration="3.7" data-track-index="1">
 <div class="ttl" id="s3-t"><div class="kick">Easy uploads</div><div class="t">Drop in a<br><em>spreadsheet.</em></div></div>
 <div class="foil" id="sheetw"><div class="pnl"><div class="ex">old-stats.xlsx</div><div class="sheen" id="sh3"></div>
  <div class="shh" style="margin-top:20px"><div></div><div class="hc" id="hc0">Name</div><div class="hc" id="hc1">Year</div><div class="hc" id="hc2">R</div></div>
  {sheet_html}
  <div id="fields"><div class="fd" id="fd0">Player</div><div class="fd" id="fd1">Season</div><div class="fd" id="fd2">Runs</div></div>
  <div class="ok" id="ok3"><i class="tick">&#10003;</i>312 rows imported</div>
 </div></div>
</div>

<div id="s4" class="clip scene" data-start="10.9" data-duration="3.8" data-track-index="1">
 <div class="ttl" id="s4-t"><div class="kick">Historical imports</div><div class="t">Old scorecards?<br><em>Snap a photo.</em></div></div>
 <div id="paper"><div class="hd">1ST XI · RD 6 · 1994</div>{"".join(f'<div class="ln" style="top:{64 + i*46}px"></div>' for i in range(9))}{scribbles}<div id="scan"></div></div>
 <div class="foil" id="digw"><div class="pnl"><div class="sheen" id="sh4"></div>{dig_html}
  <div class="ok" id="ok4" style="font-size:26px;padding:16px 20px"><i class="tick" style="width:38px;height:38px;line-height:38px">&#10003;</i>Read. You check it.</div></div></div>
 <div id="chips"><div class="chip" id="ch0">Scorebook photos</div><div class="chip" id="ch1">CricketStatz</div><div class="chip" id="ch2">CSV</div></div>
</div>

<div id="s5" class="clip scene" data-start="14.7" data-duration="3.7" data-track-index="1">
 <div class="ttl" id="s5-t"><div class="kick">Milestone tracking</div><div class="t">One off a<br><em>milestone?</em></div></div>
 <div class="foil" id="milew"><div class="pnl"><div class="ex">Example club</div><div class="sheen" id="sh5"></div>{mile_html}</div></div>
</div>

<div id="s6" class="clip scene" data-start="18.4" data-duration="2.6" data-track-index="1">
 <div class="ttl" id="s6-t"><div class="kick">All in one place</div><div class="t">And<br><em>plenty more.</em></div></div>
 <div id="mgrid">{more_html}</div>
</div>

<div id="s7" class="clip scene" data-start="21" data-duration="4" data-track-index="1">
 <div id="e-brand"><img src="assets/img/bettercricket-logo.png" alt=""><div id="e-word">Better<em>Cricket</em></div></div>
 <div id="e-head"><span class="e1">Find your</span><span class="e1 r">club.</span></div>
 <div id="e-sub">Free 14-day trial.<br>No credit card.</div>
 <div id="e-btn">Start your free trial</div>
 <div id="e-url">betterat.cricket/trial</div>
 <div id="e-chips"><div class="chip ec">Your history</div><div class="chip ec">Easy uploads</div><div class="chip ec">Milestones</div></div>
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
S(3.52, "casino/card-place-1", 0.7, 0.7)
S(5.52, "interface/bong_001", 0.5, 0.2)
S(6.22, "interface/click_003", 0.8, 0.05)
S(7.32, "casino/card-place-2", 0.7, 0.5)
for i, t in enumerate([8.02, 8.27, 8.52]):
    S(t, "ui/rollover2", 0.55, 0.1)
S(9.6, "interface/bong_001", 0.55, 0.2)
S(11.02, "casino/card-slide-1", 0.55)
S(11.5, "casino/card-shuffle", 0.35, 1.2)
for i, t in enumerate([12.0, 12.25, 12.5, 12.75]):
    S(t, "interface/click_002", 0.4, 0.05)
S(13.1, "interface/bong_001", 0.55, 0.2)
S(14.82, "casino/card-place-1", 0.7, 0.7)
S(16.52, "impact/impactBell_heavy_000", 0.45, 1.4)
for i, t in enumerate([18.62, 18.82, 19.02, 19.22, 19.42, 19.62]):
    S(t, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4"][i % 3], 0.45)
S(21.12, "casino/card-fan-1", 0.55, 0.7)
S(21.52, "impact/impactBell_heavy_000", 0.7, 1.4)
audio = [f'<audio id="music" data-timeline-role="music" data-start="0" data-duration="{DUR}" data-media-start="3" '
         f'data-track-index="2" data-volume="0.55" data-fade-out="1.5" src="assets/music/bed.mp3"></audio>']
for i, (t, f, v, d) in enumerate(sfx):
    audio.append(f'<audio id="sfx{i}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{3 + i % 12}" '
                 f'data-volume="{v}" src="assets/sfx/{f}.ogg"></audio>')

JS = """
const tl = gsap.timeline({ paused: true });
const F = (s, a, b, t) => tl.fromTo(s, a, b, t);
const count = (id, to, t, d, fmt) => { const o = { v: 0 }; tl.to(o, { v: to, duration: d, ease: 'power2.out', onUpdate: () => { document.getElementById(id).textContent = fmt(o.v); } }, t); };
const n = (v) => Math.round(v).toLocaleString('en-AU');
const title = (id, t) => F(id, { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, t);
const panel = (id, t) => F(id, { opacity: 0, y: 120, rotation: -3, scale: 0.92 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.45, ease: 'back.out(1.3)' }, t);
const sheen = (id, t) => tl.fromTo(id, { opacity: 0, xPercent: -130 }, { opacity: 1, xPercent: 360, duration: 0.9, ease: 'power1.inOut' }, t);
// S1 hook
F('.st', { y: 140, opacity: 0.35 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out', stagger: { each: 0.025, from: 'center', grid: [7, 5] } }, 0.0);
F('#wallrot', { scale: 1.2, y: 0 }, { scale: 1.06, y: -80, duration: 3.4, ease: 'none' }, 0.0);
F('#h1a', { opacity: 1, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }, 0.0);
F('#h1b', { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.28, ease: 'back.out(2)' }, 0.5);
F('#h1c', { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.32, ease: 'back.out(2.2)' }, 1.0);
F('#s1-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 1.5);
tl.to('#s1-head', { scale: 1.04, duration: 1.6, ease: 'sine.inOut' }, 1.7);
// S2 sync
title('#s2-t', 3.45); panel('#syncw', 3.5);
tl.fromTo('#ring', { '--p': 0 }, { '--p': 100, duration: 1.9, ease: 'power2.inOut' }, 3.8);
count('pct', 100, 3.8, 1.9, (v) => Math.round(v) + '%');
count('n0', 4812, 3.9, 1.8, n); count('n1', 1236, 4.0, 1.7, n); count('n2', 38, 4.1, 1.6, n);
sheen('#sh2', 5.6);
tl.to('#syncbtn', { scale: 0.95, duration: 0.07 }, 6.22); tl.to('#syncbtn', { scale: 1, duration: 0.1 }, 6.29);
F('#s2-foot', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 6.0);
// S3 spreadsheet
title('#s3-t', 7.25); panel('#sheetw', 7.3);
F('.sr', { opacity: 0, x: -40 }, { opacity: 1, x: 0, duration: 0.25, stagger: 0.06 }, 7.6);
[8.0, 8.25, 8.5].forEach((t, i) => {
  tl.to('#hc' + i, { backgroundColor: 'rgba(52,211,153,.35)', color: '#fff', duration: 0.15 }, t);
  F('#fd' + i, { opacity: 0, y: -30, scale: 0.7 }, { opacity: 1, y: 0, scale: 1, duration: 0.3, ease: 'back.out(2)' }, t + 0.05);
});
tl.to('.fd', { backgroundColor: 'rgba(52,211,153,.18)', duration: 0.2 }, 9.2);
F('#ok3', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 9.6);
sheen('#sh3', 9.7);
// S4 scorebook photo
title('#s4-t', 10.95);
F('#paper', { opacity: 0, y: 140, rotation: -14 }, { opacity: 1, y: 0, rotation: -5, duration: 0.45, ease: 'back.out(1.3)' }, 11.0);
F('#scan', { opacity: 1, y: -60 }, { opacity: 1, y: 480, duration: 1.2, ease: 'power1.inOut' }, 11.5);
tl.to('#scan', { opacity: 0, duration: 0.2 }, 12.7);
panel('#digw', 11.7);
F('.dr', { opacity: 0, x: 30 }, { opacity: 1, x: 0, duration: 0.25, stagger: 0.25 }, 12.0);
F('#ok4', { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 13.1);
F('.chip', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.12, ease: 'back.out(1.8)' }, 13.3);
// S5 milestones
title('#s5-t', 14.75); panel('#milew', 14.8);
const mh = [[49, 0.98], [99, 0.99], [4998, 0.9996]];
mh.forEach(([have, frac], i) => {
  const t = 15.15 + i * 0.3;
  tl.fromTo('#mf' + i, { scaleX: 0 }, { scaleX: frac, duration: 1.0, ease: 'power2.out' }, t);
  count('mn' + i, have, t, 1.0, n);
  F('#mb' + i, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(2.4)' }, 16.5 + i * 0.12);
});
tl.to('.badge', { scale: 1.12, duration: 0.25, yoyo: true, repeat: 3, ease: 'sine.inOut' }, 17.0);
sheen('#sh5', 17.2);
// S6 and more
title('#s6-t', 18.45);
[18.6, 18.8, 19.0, 19.2, 19.4, 19.6].forEach((t, i) => {
  F('#mo' + i, { opacity: 0, y: 140, rotation: (i % 2 ? 6 : -6), scale: 0.8 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.38, ease: 'back.out(1.5)' }, t);
});
tl.to('#mgrid', { scale: 1.03, duration: 1.0, ease: 'sine.inOut' }, 20.0);
// S7 end card
F('#e-brand', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, 21.05);
F('.e1', { opacity: 0, y: 40, scale: 1.2 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'back.out(1.6)', stagger: 0.2 }, 21.2);
F('#e-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 21.65);
F('#e-btn', { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.8)' }, 21.8);
F('#e-url', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 22.0);
F('.ec', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.12, ease: 'back.out(1.8)' }, 22.2);
tl.to('#e-btn', { scale: 1.04, duration: 0.5, ease: 'sine.inOut', repeat: 4, yoyo: true }, 22.3);
tl.to('#glow', { opacity: 0.6, duration: 0.25, ease: 'sine.inOut', repeat: 99, yoyo: true }, 0.02);
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
print("bytes:", len(html))
