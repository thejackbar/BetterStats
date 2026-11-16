"""Builds composition/index.html: a 4:5 Meta feed ad that gets clubs to sign up to BetterCricket
(free trial). Look borrowed from the Player Cards launch video (italic caps, foil-edged panels, card
sounds, same music) in BetterCricket colours (#16c784 green on navy). Content: your history (synced or
entered by hand, back before MyCricket), easy uploads, historical imports, milestone tracking and six
illustrated features. Every name and figure is illustrative and marked "Example club"."""
from pathlib import Path

HERE = Path(__file__).parent
W, H, DUR = 1080, 1350, 30.0
FOIL = "conic-gradient(from 0deg,#16c784,#a7f3d0,#3ee6a4,#7dd3fc,#3b82f6,#16c784)"

# ---- intro wall: 24 different features, one each, all on the same dark tile ------------------------
def bars(vals):
    return '<div class="tb">' + "".join(f'<i style="height:{v}%"></i>' for v in vals) + "</div>"

WALL = [
    ("Most runs", '<b class="tn">9,247</b><span class="ts">J. Mercer</span>'),
    ("Hat-tricks", '<div class="balls"><i></i><i></i><i></i></div><span class="ts">3 in 3 · 2019/20</span>'),
    ("Highest partnership", '<b class="tn">214</b><span class="ts">3rd wicket</span>'),
    ("Player dashboard", '<div class="pd"><i class="av">TO</i><div><em></em><em></em><em class="s"></em></div></div>'),
    ("Player card", '<div class="pc"><i>99</i><em></em></div><span class="ts">Legendary</span>'),
    ("Best bowling", '<b class="tn">8/23</b><span class="ts">R. Singh</span>'),
    ("Most wickets", bars([40, 62, 88, 70, 95])),
    ("Centuries", '<b class="tn">47</b><span class="ts">all time</span>'),
    ("Club records", '<div class="rows"><em></em><em></em><em></em></div>'),
    ("Highest score", '<b class="tn">186*</b><span class="ts">D. Nguyen</span>'),
    ("Most catches", '<b class="tn">231</b><span class="ts">A. Papadakis</span>'),
    ("Season summary", bars([55, 30, 75, 45, 90, 60])),
    ("Five-fors", '<b class="tn">63</b><span class="ts">all time</span>'),
    ("Head to head", '<div class="hh"><i class="av">JM</i><b>vs</b><i class="av">TO</i></div>'),
    ("Debuts", '<b class="tn">1,236</b><span class="ts">players</span>'),
    ("Scorecards", '<div class="rows"><em></em><em class="s"></em><em></em></div>'),
    ("Honour board", '<div class="hb"><em></em><em></em></div><span class="ts">Club champion</span>'),
    ("Premierships", '<b class="tn">12</b><span class="ts">flags</span>'),
    ("Fall of wickets", '<div class="fow">' + "".join(f'<i style="left:{x}%"></i>' for x in (8, 21, 30, 52, 61, 77, 90)) + "</div>"),
    ("StatLab", '<b class="tn">200+</b><span class="ts">reports</span>'),
    ("Family stats", '<div class="hh"><i class="av">M</i><i class="av">M</i><i class="av">M</i></div>'),
    ("Club awards", '<b class="tn">★ 18</b><span class="ts">this season</span>'),
    ("Yearbook", '<b class="tn">2025/26</b><span class="ts">fills itself</span>'),
    ("Milestones", '<div class="mini"><i style="width:94%"></i></div><span class="ts">49 / 50 catches</span>'),
]
wall_html = "".join(f'<div class="st"><div class="st-in"><span class="tk">{k}</span>{body}</div></div>' for k, body in WALL)

seasons = [f"{y}/{str(y + 1)[-2:]}" for y in range(2025, 1992, -1)]          # 2025/26 back to 1993/94
season_html = "".join(f'<div class="yr">{s}</div>' for s in seasons)

sheet_rows = [("J. Mercer", "1998/99", "412"), ("T. Okafor", "1998/99", "388"), ("R. Singh", "1999/00", "361"),
              ("D. Nguyen", "1999/00", "297"), ("A. Papadakis", "2000/01", "254")]
sheet_html = "".join(f'<div class="sr"><i>{i + 2}</i><span>{a}</span><span>{b}</span><span>{c}</span></div>'
                     for i, (a, b, c) in enumerate(sheet_rows))
dig_rows = [("L. Whitfield", "c Barry b Lane", "64"), ("J. Mercer", "b Holt", "31"), ("T. Okafor", "lbw b Lane", "22"),
            ("R. Singh", "not out", "18")]
dig_html = "".join(f'<div class="dr"><span>{a}</span><em>{b}</em><b>{c}</b></div>' for a, b, c in dig_rows)
scribbles = "".join(f'<div class="scr" style="top:{70 + i * 46}px;width:{150 + (i * 53) % 120}px"></div>'
                    f'<div class="scr" style="top:{70 + i * 46}px;left:300px;width:{40 + (i * 29) % 40}px"></div>' for i in range(8))
MILES = [("J. Mercer", "Catches", 49, 50), ("T. Okafor", "Club games", 92, 100),
         ("L. Whitfield", "Wickets", 187, 200), ("R. Singh", "Career runs", 4640, 5000)]
mile_html = "".join(
    f'<div class="mr"><div class="mt"><b>{n}</b><span>{lab}</span><i class="badge" id="mb{i}">{goal - have:,} to go</i></div>'
    f'<div class="mbar"><div class="mfill" id="mf{i}"></div></div><div class="mnum"><b id="mn{i}">0</b> / {goal:,}</div></div>'
    for i, (n, lab, have, goal) in enumerate(MILES))

# ---- "And plenty more": six illustrated features -----------------------------------------------
FEAT = [
    ("Player profile pages", """<div class="pp"><i class="av big">JM</i><div><b>J. Mercer</b><span>Example club · since 1998/99</span></div></div>
      <div class="pps"><div><b>211</b><span>Matches</span></div><div><b>4,034</b><span>Runs</span></div><div><b>205</b><span>Wickets</span></div></div>"""),
    ("Leaderboards", """<div class="lbh">Most runs</div>
      <div class="lb"><i>1</i><span>J. Mercer</span><em style="width:100%"></em><b>9,247</b></div>
      <div class="lb"><i>2</i><span>T. Okafor</span><em style="width:86%"></em><b>7,950</b></div>
      <div class="lb"><i>3</i><span>R. Singh</span><em style="width:71%"></em><b>6,561</b></div>"""),
    ("New records identified", """<div class="nr"><span class="flag" id="flag">New record</span><div class="nrb"><b>187*</b><span>3rd wicket partnership</span></div>
      <div class="nrp">D. Nguyen &amp; L. Whitfield · was 164</div></div>"""),
    ("StatLab reports", """<div class="chips"><i class="on">1st XI</i><i>2015 to now</i><i>Batting</i></div>
      <div class="rows2"><em style="width:92%"></em><em style="width:74%"></em><em style="width:58%"></em><em style="width:40%"></em></div>"""),
    ("Honour boards", """<div class="hbd"><div><span>2025/26</span><b>T. Okafor</b></div><div><span>2024/25</span><b>J. Mercer</b></div><div><span>2023/24</span><b>R. Singh</b></div></div>"""),
    ("Season yearbooks", """<div class="yb"><div class="ybc"><span>Yearbook</span><b>2025/26</b></div><div class="ybp"><em></em><em></em><em></em><em class="s"></em></div></div>"""),
]
feat_html = "".join(f'<div class="ft" id="ft{i}"><div class="ft-in"><div class="ftt">{t}</div><div class="ftb">{b}</div></div></div>'
                    for i, (t, b) in enumerate(FEAT))

CSS = f"""@font-face{{font-family:'AC';src:url('assets/fonts/applecross-display.ttf') format('truetype');font-weight:100 900;font-style:normal}}
:root{{--green:#16c784;--hi:#3ee6a4;--blue:#3b82f6;--foil:{FOIL}}}
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
.av{{display:inline-grid;place-items:center;width:52px;height:52px;border-radius:50%;background:linear-gradient(145deg,#3ee6a4,#0e7490);color:#04261a;font:800 20px 'Inter',sans-serif;font-style:normal;flex:none}}
/* s1 wall */
#wallrot{{position:absolute;left:50%;top:50%;width:1400px;height:1800px;margin-left:-700px;margin-top:-900px;transform:rotate(-8deg)}}
#wall{{display:grid;grid-template-columns:repeat(4,300px);grid-auto-rows:200px;gap:24px;justify-content:center}}
.st{{padding:4px;border-radius:20px;background:var(--foil)}}
.st-in{{height:100%;border-radius:16px;background:linear-gradient(170deg,#12302a,#0b1018 70%);display:flex;flex-direction:column;justify-content:center;padding:0 26px;overflow:hidden}}
.tk{{font:700 17px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#6ee7b7;margin-bottom:10px;white-space:nowrap}}
.tn{{font:800 italic 58px/1 'AC','Montserrat',sans-serif;padding-right:.1em;white-space:nowrap}}
.ts{{margin-top:8px;font:600 18px 'Inter',sans-serif;color:#cbd5e1;white-space:nowrap}}
.tb{{display:flex;align-items:flex-end;gap:10px;height:90px}}
.tb i{{flex:1;border-radius:6px 6px 0 0;background:linear-gradient(180deg,#3ee6a4,#0e7490)}}
.balls{{display:flex;gap:14px}}
.balls i{{width:46px;height:46px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#fff,#3ee6a4 30%,#0e7490)}}
.pd{{display:flex;gap:16px;align-items:center}}
.pd div{{flex:1}}
.pd em,.rows em,.hb em{{display:block;height:14px;border-radius:7px;background:rgba(255,255,255,.18);margin:8px 0}}
.pd em.s,.rows em.s{{width:60%}}
.rows em{{height:18px}}
.pc{{width:80px;height:104px;border-radius:12px;padding:3px;background:var(--foil);position:relative}}
.pc em{{display:block;height:100%;border-radius:9px;background:linear-gradient(170deg,#16c784,#0b1018)}}
.pc i{{position:absolute;right:8px;top:6px;font:800 italic 26px 'AC','Montserrat',sans-serif;font-style:italic}}
.hh{{display:flex;align-items:center;gap:14px}}
.hh b{{font:800 italic 26px 'AC','Montserrat',sans-serif;color:#94a3b8}}
.hb em{{background:linear-gradient(90deg,#fbbf24,rgba(251,191,36,.2));height:12px}}
.fow{{position:relative;height:30px;border-bottom:3px solid rgba(255,255,255,.3)}}
.fow i{{position:absolute;bottom:-9px;width:16px;height:16px;border-radius:50%;background:#3ee6a4}}
.mini{{height:16px;border-radius:8px;background:rgba(255,255,255,.12);overflow:hidden}}
.mini i{{display:block;height:100%;border-radius:8px;background:#3ee6a4}}
#s1-scrim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 46%,rgba(6,10,18,.92) 0%,rgba(6,10,18,.74) 42%,rgba(6,10,18,.18) 100%)}}
#s1-head{{position:absolute;left:40px;right:40px;top:400px;text-align:center}}
.h1{{display:block;font:800 italic 156px/0.95 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em}}
.h1.r{{color:var(--hi)}}
#s1-sub{{position:absolute;left:0;right:0;top:1090px;text-align:center;font:700 30px 'JetBrains Mono',monospace;letter-spacing:4px;text-transform:uppercase;color:#e5e7eb}}
/* s2 history */
#histw{{left:90px;top:420px;width:900px}}
#histw .pnl{{padding:56px 46px 40px;display:flex;gap:40px;align-items:center}}
#ywin{{position:relative;width:380px;height:330px;overflow:hidden;flex:none;-webkit-mask-image:linear-gradient(to bottom,transparent,#000 22%,#000 78%,transparent);mask-image:linear-gradient(to bottom,transparent,#000 22%,#000 78%,transparent)}}
#ystrip{{position:absolute;left:0;right:0;top:0}}
.yr{{height:110px;display:grid;place-items:center;font:800 italic 76px 'AC','Montserrat',sans-serif;padding-right:.1em}}
.cnt{{margin-bottom:20px}}
.cnt span{{display:block;font:700 22px 'JetBrains Mono',monospace;letter-spacing:3px;text-transform:uppercase;color:#94a3b8}}
.cnt b{{display:block;font:800 italic 70px/1 'AC','Montserrat',sans-serif;font-variant-numeric:tabular-nums;padding-right:.12em}}
#pre{{display:inline-block;margin-top:6px;padding:10px 20px;border-radius:999px;background:#fbbf24;color:#422006;font:800 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;opacity:0}}
#modes{{position:absolute;left:0;right:0;top:930px;display:flex;justify-content:center;gap:18px}}
.mode{{padding:18px 30px;border-radius:999px;background:rgba(14,20,30,.92);border:2px solid var(--green);font:700 26px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;opacity:0}}
#s2-foot{{position:absolute;left:0;right:0;top:1040px;text-align:center;font:600 30px 'Inter',sans-serif;color:#e5e7eb}}
/* s3 spreadsheet */
#sheetw{{left:90px;top:430px;width:900px}}
.shh,.sr{{display:grid;grid-template-columns:50px 1.5fr 1fr 0.8fr;font:600 28px 'Inter',sans-serif}}
.shh div,.sr span,.sr i{{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,.1)}}
.shh div{{font:700 22px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#cbd5e1;background:rgba(255,255,255,.06)}}
.sr i{{font-style:normal;color:#64748b;font-size:22px}}
.hc{{border-radius:8px}}
#fields{{display:flex;gap:18px;margin-top:26px;justify-content:center}}
.fd{{padding:14px 26px;border-radius:999px;border:2px solid #3ee6a4;font:700 26px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#3ee6a4;opacity:0}}
/* s4 scorebook */
#paper{{position:absolute;left:120px;top:440px;width:430px;height:470px;background:#f3ead2;border-radius:10px;box-shadow:0 30px 60px rgba(0,0,0,.6);transform:rotate(-5deg);overflow:hidden}}
#paper .ln{{position:absolute;left:20px;right:20px;height:1px;background:rgba(70,90,140,.35)}}
#paper .scr{{position:absolute;left:34px;height:10px;border-radius:5px;background:rgba(30,40,80,.65);transform:skewX(-14deg)}}
#paper .hd{{position:absolute;left:30px;top:22px;font:700 22px 'JetBrains Mono',monospace;color:#1e293b;letter-spacing:2px}}
#scan{{position:absolute;left:0;right:0;height:60px;top:0;background:linear-gradient(to bottom,transparent,rgba(22,199,132,.6),transparent);opacity:0}}
#digw{{left:500px;top:520px;width:500px}}
#digw .pnl{{padding:26px 28px}}
.dr{{display:grid;grid-template-columns:1.2fr 1.3fr 50px;gap:10px;padding:14px 0;border-bottom:1px solid rgba(255,255,255,.1);font:600 24px 'Inter',sans-serif;opacity:0}}
.dr em{{font-style:normal;color:#94a3b8;font-size:20px;align-self:center}}
.dr b{{text-align:right;font:800 italic 30px 'AC','Montserrat',sans-serif}}
#chips{{position:absolute;left:0;right:0;top:1080px;display:flex;justify-content:center;gap:16px}}
.chip{{padding:14px 24px;border-radius:999px;background:rgba(14,20,30,.92);border:1px solid rgba(255,255,255,.25);font:700 24px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;opacity:0}}
/* s5 milestones */
#milew{{left:90px;top:420px;width:900px}}
#milew .pnl{{padding-top:62px}}
.mr{{margin-bottom:26px}}
.mr:last-child{{margin-bottom:0}}
.mt{{display:flex;align-items:baseline;gap:18px}}
.mt b{{font:800 32px 'Inter',sans-serif}}
.mt span{{font:700 21px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#94a3b8}}
.badge{{margin-left:auto;font-style:normal;padding:6px 16px;border-radius:999px;background:rgba(62,230,164,.18);border:2px solid #3ee6a4;color:#a7f3d0;font:800 21px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;opacity:0}}
#mb0{{background:#fbbf24;border-color:#fbbf24;color:#422006}}
.mbar{{margin-top:12px;height:20px;border-radius:10px;background:rgba(255,255,255,.1);overflow:hidden}}
.mfill{{height:100%;width:100%;border-radius:10px;background:linear-gradient(90deg,#16c784,#3ee6a4);transform-origin:0 50%;transform:scaleX(0)}}
.mnum{{margin-top:8px;font:600 22px 'JetBrains Mono',monospace;color:#cbd5e1}}
.mnum b{{color:#fff;font-variant-numeric:tabular-nums}}
/* s6 features */
#fgrid{{position:absolute;left:0;right:0;top:405px;display:grid;grid-template-columns:repeat(2,450px);grid-auto-rows:272px;gap:26px 28px;justify-content:center}}
.ft{{padding:4px;border-radius:24px;background:var(--foil);opacity:0;box-shadow:0 20px 50px rgba(0,0,0,.5)}}
.ft-in{{height:100%;border-radius:20px;background:linear-gradient(170deg,#141c28,#0a0f17);padding:22px 26px;display:flex;flex-direction:column}}
.ftt{{font:700 20px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#6ee7b7;margin-bottom:16px}}
.ftb{{flex:1;display:flex;flex-direction:column;justify-content:center}}
.pp{{display:flex;gap:18px;align-items:center}}
.av.big{{width:84px;height:84px;font-size:30px}}
.pp b{{display:block;font:800 32px 'Inter',sans-serif}}
.pp span{{display:block;margin-top:4px;font:500 18px 'Inter',sans-serif;color:#94a3b8}}
.pps{{display:flex;gap:12px;margin-top:20px}}
.pps div{{flex:1;padding:12px 10px;border-radius:12px;background:rgba(255,255,255,.06);text-align:center}}
.pps b{{display:block;font:800 italic 34px/1 'AC','Montserrat',sans-serif;padding-right:.1em}}
.pps span{{display:block;margin-top:6px;font:700 15px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase;color:#94a3b8}}
.lbh{{font:800 italic 32px 'AC','Montserrat',sans-serif;text-transform:uppercase;margin-bottom:12px;padding-right:.1em}}
.lb{{display:grid;grid-template-columns:28px 130px 1fr 80px;gap:12px;align-items:center;margin:9px 0;font:600 20px 'Inter',sans-serif}}
.lb i{{font-style:normal;color:#6ee7b7;font-weight:800}}
.lb em{{height:14px;border-radius:7px;background:linear-gradient(90deg,#16c784,#3ee6a4);transform-origin:0 50%}}
.lb b{{text-align:right;font:800 italic 22px 'AC','Montserrat',sans-serif}}
.nr{{position:relative}}
.flag{{position:absolute;right:0;top:-4px;padding:6px 14px;border-radius:999px;background:#fbbf24;color:#422006;font:800 17px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase}}
.nrb b{{display:block;font:800 italic 92px/1 'AC','Montserrat',sans-serif;color:var(--hi);padding-right:.1em}}
.nrb span{{display:block;margin-top:6px;font:700 19px 'JetBrains Mono',monospace;letter-spacing:1px;text-transform:uppercase}}
.nrp{{margin-top:12px;font:500 19px 'Inter',sans-serif;color:#94a3b8}}
.chips{{display:flex;gap:10px;margin-bottom:18px}}
.chips i{{font-style:normal;padding:8px 14px;border-radius:999px;border:1px solid rgba(255,255,255,.3);font:600 17px 'Inter',sans-serif}}
.chips i.on{{background:var(--green);border-color:var(--green);color:#04261a}}
.rows2 em{{display:block;height:20px;margin:10px 0;border-radius:6px;background:linear-gradient(90deg,rgba(62,230,164,.75),rgba(62,230,164,.15));transform-origin:0 50%}}
.hbd{{border-radius:12px;padding:6px 16px;background:linear-gradient(180deg,#3b2a12,#1d140a);border:2px solid #b45309}}
.hbd div{{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(251,191,36,.25)}}
.hbd div:last-child{{border:0}}
.hbd span{{font:700 19px 'JetBrains Mono',monospace;color:#fcd34d}}
.hbd b{{font:700 22px 'Inter',sans-serif;color:#fde68a}}
.yb{{display:flex;gap:18px;align-items:center}}
.ybc{{width:150px;height:170px;border-radius:10px;padding:16px 12px;background:linear-gradient(160deg,#16c784,#0e7490);display:flex;flex-direction:column;justify-content:flex-end;box-shadow:6px 6px 0 rgba(255,255,255,.12)}}
.ybc span{{font:700 14px 'JetBrains Mono',monospace;letter-spacing:2px;text-transform:uppercase;color:#04261a}}
.ybc b{{font:800 italic 26px 'AC','Montserrat',sans-serif;color:#04261a;padding-right:.1em}}
.ybp{{flex:1}}
.ybp em{{display:block;height:14px;border-radius:7px;background:rgba(255,255,255,.16);margin:14px 0}}
.ybp em.s{{width:55%}}
/* s7 end */
#e-brand{{position:absolute;left:0;right:0;top:150px;display:flex;justify-content:center;align-items:center;gap:24px;opacity:0}}
#e-brand img{{width:116px;height:98px;object-fit:contain}}
#e-word{{font:800 italic 80px/1 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-1px;padding-right:.16em}}
#e-word em{{font-style:italic;color:var(--hi)}}
#e-head{{position:absolute;left:50px;right:50px;top:330px;text-align:center}}
.e1{{display:block;font:800 italic 150px/0.95 'AC','Montserrat',sans-serif;text-transform:uppercase;letter-spacing:-2px;padding-right:.16em;opacity:0}}
.e1.r{{color:var(--hi)}}
#e-sub{{position:absolute;left:80px;right:80px;top:660px;text-align:center;font:600 40px/1.3 'Inter',sans-serif;color:#e5e7eb;opacity:0}}
#e-btn{{position:absolute;left:170px;right:170px;top:830px;padding:36px 20px;border-radius:999px;background:var(--green);color:#04261a;text-align:center;font:800 48px 'Inter',sans-serif;opacity:0;box-shadow:0 0 60px rgba(22,199,132,.45)}}
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

<div id="s2" class="clip scene" data-start="3.4" data-duration="4.2" data-track-index="1">
 <div class="ttl" id="s2-t"><div class="kick">Automated or manual entry</div><div class="t" style="font-size:76px">Every season.<br><em>Even pre-MyCricket.</em></div></div>
 <div class="foil" id="histw"><div class="pnl"><div class="ex">Example club</div><div class="sheen" id="sh2"></div>
  <div id="ywin"><div id="ystrip">{season_html}</div></div>
  <div><div class="cnt"><span>Seasons</span><b id="n2">0</b></div><div class="cnt"><span>Games</span><b id="n0">0</b></div><div id="pre">Pre-MyCricket</div></div>
 </div></div>
 <div id="modes"><div class="mode" id="md0">Synced automatically</div><div class="mode" id="md1">Added by hand</div></div>
 <div id="s2-foot">Back as far as your club's records go.</div>
</div>

<div id="s3" class="clip scene" data-start="7.6" data-duration="3.7" data-track-index="1">
 <div class="ttl" id="s3-t"><div class="kick">Easy uploads</div><div class="t">Drop in a<br><em>spreadsheet.</em></div></div>
 <div class="foil" id="sheetw"><div class="pnl"><div class="ex">old-stats.xlsx</div><div class="sheen" id="sh3"></div>
  <div class="shh" style="margin-top:20px"><div></div><div class="hc" id="hc0">Name</div><div class="hc" id="hc1">Year</div><div class="hc" id="hc2">R</div></div>
  {sheet_html}
  <div id="fields"><div class="fd" id="fd0">Player</div><div class="fd" id="fd1">Season</div><div class="fd" id="fd2">Runs</div></div>
  <div class="ok" id="ok3"><i class="tick">&#10003;</i>312 rows imported</div>
 </div></div>
</div>

<div id="s4" class="clip scene" data-start="11.3" data-duration="3.8" data-track-index="1">
 <div class="ttl" id="s4-t"><div class="kick">Historical imports</div><div class="t">Old scorecards?<br><em>Snap a photo.</em></div></div>
 <div id="paper"><div class="hd">1ST XI · RD 6 · 1994</div>{"".join(f'<div class="ln" style="top:{64 + i*46}px"></div>' for i in range(9))}{scribbles}<div id="scan"></div></div>
 <div class="foil" id="digw"><div class="pnl"><div class="sheen" id="sh4"></div>{dig_html}
  <div class="ok" id="ok4" style="font-size:26px;padding:16px 20px"><i class="tick" style="width:38px;height:38px;line-height:38px">&#10003;</i>Read. You check it.</div></div></div>
 <div id="chips"><div class="chip" id="ch0">Scorebook photos</div><div class="chip" id="ch1">CricketStatz</div><div class="chip" id="ch2">CSV</div></div>
</div>

<div id="s5" class="clip scene" data-start="15.1" data-duration="3.9" data-track-index="1">
 <div class="ttl" id="s5-t"><div class="kick">Milestone tracking</div><div class="t">Who's next<br><em>to a milestone?</em></div></div>
 <div class="foil" id="milew"><div class="pnl"><div class="ex">Example club</div><div class="sheen" id="sh5"></div>{mile_html}</div></div>
</div>

<div id="s6" class="clip scene" data-start="19.0" data-duration="6.5" data-track-index="1">
 <div class="ttl" id="s6-t"><div class="kick">All in one place</div><div class="t">And<br><em>plenty more.</em></div></div>
 <div id="fgrid">{feat_html}</div>
</div>

<div id="s7" class="clip scene" data-start="25.5" data-duration="4.5" data-track-index="1">
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
S(3.9, "casino/card-shuffle", 0.35, 1.2)
S(5.62, "interface/bong_001", 0.55, 0.2)
S(6.1, "ui/rollover2", 0.5, 0.1)
S(6.4, "ui/rollover2", 0.5, 0.1)
S(7.72, "casino/card-place-2", 0.7, 0.5)
for t in (8.42, 8.67, 8.92):
    S(t, "ui/rollover2", 0.55, 0.1)
S(10.0, "interface/bong_001", 0.55, 0.2)
S(11.42, "casino/card-slide-1", 0.55)
S(11.9, "casino/card-shuffle", 0.35, 1.2)
for t in (12.4, 12.65, 12.9, 13.15):
    S(t, "interface/click_002", 0.4, 0.05)
S(13.5, "interface/bong_001", 0.55, 0.2)
S(15.22, "casino/card-place-1", 0.7, 0.7)
S(17.02, "impact/impactBell_heavy_000", 0.4, 1.4)
for i, t in enumerate([19.42, 19.72, 20.02, 20.32, 20.62, 20.92]):
    S(t, ["casino/card-slide-1", "casino/card-slide-2", "casino/card-slide-4"][i % 3], 0.45)
S(21.72, "impact/impactBell_heavy_000", 0.35, 1.4)
S(25.62, "casino/card-fan-1", 0.55, 0.7)
S(26.02, "impact/impactBell_heavy_000", 0.7, 1.4)
audio = [f'<audio id="music" data-timeline-role="music" data-start="0" data-duration="{DUR}" data-media-start="3" '
         f'data-track-index="2" data-volume="0.55" data-fade-out="1.5" src="assets/music/bed.mp3"></audio>']
for i, (t, f, v, d) in enumerate(sfx):
    audio.append(f'<audio id="sfx{i}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{3 + i % 12}" '
                 f'data-volume="{v}" src="assets/sfx/{f}.ogg"></audio>')

MILE_JS = ", ".join(f"[{h}, {h / g:.4f}]" for _, _, h, g in MILES)
JS = """
const tl = gsap.timeline({ paused: true });
const F = (s, a, b, t) => tl.fromTo(s, a, b, t);
const count = (id, to, t, d) => { const o = { v: 0 }; tl.to(o, { v: to, duration: d, ease: 'power2.out', onUpdate: () => { document.getElementById(id).textContent = Math.round(o.v).toLocaleString('en-AU'); } }, t); };
const title = (id, t) => F(id, { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }, t);
const panel = (id, t) => F(id, { opacity: 0, y: 120, rotation: -3, scale: 0.92 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.45, ease: 'back.out(1.3)' }, t);
const sheen = (id, t) => tl.fromTo(id, { opacity: 0, xPercent: -130 }, { opacity: 1, xPercent: 360, duration: 0.9, ease: 'power1.inOut' }, t);
// S1 hook
F('.st', { y: 140, opacity: 0.35 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out', stagger: { each: 0.03, from: 'center', grid: [6, 4] } }, 0.0);
F('#wallrot', { scale: 1.18, y: 0 }, { scale: 1.05, y: -70, duration: 3.4, ease: 'none' }, 0.0);
F('#h1a', { opacity: 1, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }, 0.0);
F('#h1b', { opacity: 0, scale: 1.5 }, { opacity: 1, scale: 1, duration: 0.28, ease: 'back.out(2)' }, 0.5);
F('#h1c', { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.32, ease: 'back.out(2.2)' }, 1.0);
F('#s1-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 1.5);
tl.to('#s1-head', { scale: 1.04, duration: 1.6, ease: 'sine.inOut' }, 1.7);
// S2 history: seasons roll back to 1993/94, the pre-MyCricket tag lights up on the way
title('#s2-t', 3.45); panel('#histw', 3.5);
F('#ystrip', { y: 110 }, { y: 110 - 110 * 32, duration: 2.3, ease: 'power2.inOut' }, 3.8);
count('n2', 33, 3.8, 2.3); count('n0', 4812, 3.9, 2.2);
F('#pre', { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(2.4)' }, 5.0);
sheen('#sh2', 5.9);
F('#md0', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.8)' }, 6.1);
F('#md1', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.8)' }, 6.4);
F('#s2-foot', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 6.7);
// S3 spreadsheet
title('#s3-t', 7.65); panel('#sheetw', 7.7);
F('.sr', { opacity: 0, x: -40 }, { opacity: 1, x: 0, duration: 0.25, stagger: 0.06 }, 8.0);
[8.4, 8.65, 8.9].forEach((t, i) => {
  tl.to('#hc' + i, { backgroundColor: 'rgba(22,199,132,.4)', color: '#fff', duration: 0.15 }, t);
  F('#fd' + i, { opacity: 0, y: -30, scale: 0.7 }, { opacity: 1, y: 0, scale: 1, duration: 0.3, ease: 'back.out(2)' }, t + 0.05);
});
F('#ok3', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 10.0);
sheen('#sh3', 10.1);
// S4 scorebook photo
title('#s4-t', 11.35);
F('#paper', { opacity: 0, y: 140, rotation: -14 }, { opacity: 1, y: 0, rotation: -5, duration: 0.45, ease: 'back.out(1.3)' }, 11.4);
F('#scan', { opacity: 1, y: -60 }, { opacity: 1, y: 480, duration: 1.2, ease: 'power1.inOut' }, 11.9);
tl.to('#scan', { opacity: 0, duration: 0.2 }, 13.1);
panel('#digw', 12.1);
F('.dr', { opacity: 0, x: 30 }, { opacity: 1, x: 0, duration: 0.25, stagger: 0.25 }, 12.4);
F('#ok4', { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.3, ease: 'back.out(1.6)' }, 13.5);
F('.chip', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.12, ease: 'back.out(1.8)' }, 13.7);
// S5 milestones: four players at different distances
title('#s5-t', 15.15); panel('#milew', 15.2);
[MILE_JS].forEach(([have, frac], i) => {
  const t = 15.55 + i * 0.25;
  tl.fromTo('#mf' + i, { scaleX: 0 }, { scaleX: frac, duration: 1.0, ease: 'power2.out' }, t);
  count('mn' + i, have, t, 1.0);
  F('#mb' + i, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(2.4)' }, 16.8 + i * 0.12);
});
tl.to('#mb0', { scale: 1.12, duration: 0.25, yoyo: true, repeat: 3, ease: 'sine.inOut' }, 17.4);
sheen('#sh5', 17.6);
// S6 six features, then a long hold so people can read them
title('#s6-t', 19.05);
[19.4, 19.7, 20.0, 20.3, 20.6, 20.9].forEach((t, i) => {
  F('#ft' + i, { opacity: 0, y: 120, rotation: (i % 2 ? 5 : -5), scale: 0.85 }, { opacity: 1, y: 0, rotation: 0, scale: 1, duration: 0.4, ease: 'back.out(1.4)' }, t);
});
F('#ft1 .lb em', { scaleX: 0 }, { scaleX: 1, duration: 0.6, ease: 'power2.out', stagger: 0.12 }, 20.0);
F('#ft3 .rows2 em', { scaleX: 0 }, { scaleX: 1, duration: 0.6, ease: 'power2.out', stagger: 0.1 }, 20.6);
F('#flag', { scale: 0.3, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.35, ease: 'back.out(2.6)' }, 21.7);
tl.to('#flag', { scale: 1.12, duration: 0.3, yoyo: true, repeat: 5, ease: 'sine.inOut' }, 22.1);
tl.to('#fgrid', { scale: 1.02, duration: 3.0, ease: 'sine.inOut' }, 22.2);
// S7 end card
F('#e-brand', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, 25.55);
F('.e1', { opacity: 0, y: 40, scale: 1.2 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'back.out(1.6)', stagger: 0.2 }, 25.7);
F('#e-sub', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, 26.15);
F('#e-btn', { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.8)' }, 26.3);
F('#e-url', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 26.5);
F('.ec', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.12, ease: 'back.out(1.8)' }, 26.7);
tl.to('#e-btn', { scale: 1.04, duration: 0.5, ease: 'sine.inOut', repeat: 4, yoyo: true }, 26.9);
tl.to('#glow', { opacity: 0.6, duration: 0.25, ease: 'sine.inOut', repeat: 119, yoyo: true }, 0.02);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
tl.seek(0);
""".replace("[MILE_JS]", "[" + MILE_JS + "]")

html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
<script src="assets/gsap.min.js"></script>
<style>{CSS}</style></head><body>
{BODY}
{''.join(audio)}
</div>
<script>{JS}</script></body></html>"""
(HERE / "composition/index.html").write_text(html)
print("bytes:", len(html), "wall tiles:", len(WALL), "unique:", len({k for k, _ in WALL}))
