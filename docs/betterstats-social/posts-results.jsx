// ─────────────────────────────────────────────────────────────────────────────
// RESULTS — new single-result variants + results roundups (1080×1080)
//   Single:   A · Margin Hero (Forest)  B · Broadcast (Cobalt)  C · Versus Columns (Midnight)
//   Roundup:  A · Weekend Wrap list (Midnight)  B · W/L Scoreboard grid (Graphite)  C · Record Strip (Crimson)
// ─────────────────────────────────────────────────────────────────────────────

const { Post, Grain, Halftone, Stripes, Shield, Monogram, Slab, Kicker, Bug, SponsorFooter, AutoFit, DISPLAY, MONO, BODY, WIN, LOSS, TIE } = window;

// ════════════════ SINGLE RESULT ════════════════

// ── A · MARGIN HERO ───────────────────────────────────────────────────────────
function ResultMarginHero({ pal }) {
  const r = window.RESULT1;
  const won = r.winner === 'us';
  const winnerName = won ? r.us.name : r.them.name;
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.04} gap={28} angle={-20} />
      <div style={{ position: 'absolute', left: -60, bottom: -40, fontFamily: DISPLAY, fontSize: 760, lineHeight: 0.72, color: pal.accent, opacity: 0.08, letterSpacing: -20, userSelect: 'none' }}>W</div>

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 28px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={26} style={{ padding: '8px 16px' }}>FULL TIME</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`${r.comp} · ${r.round} · ${r.date}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={84} />
      </div>

      {/* hero headline */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 280 }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 60, letterSpacing: 2, color: pal.ink, opacity: 0.55, lineHeight: 1 }}>{winnerName}</div>
        <AutoFit max={260} min={120} style={{ fontFamily: DISPLAY, color: pal.ink, letterSpacing: -4, lineHeight: 0.82, marginTop: 2 }}>WIN</AutoFit>
        <div style={{ fontFamily: DISPLAY, fontSize: 92, letterSpacing: 1, color: pal.accent, lineHeight: 1, marginTop: 4 }}>{r.margin}</div>
      </div>

      {/* scoreline */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 700, display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 22 }}>
        <div style={{ padding: '18px 22px', background: won ? `${pal.accent}1f` : `${pal.ink}0c`, border: `2px solid ${won ? pal.accent : pal.ink + '22'}`, display: 'flex', alignItems: 'center', gap: 16 }}>
          <Monogram text={r.us.mono} size={56} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}33`} />
          <div>
            <div style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 1, lineHeight: 1, whiteSpace: 'nowrap' }}>{r.us.name}</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 52, letterSpacing: -0.5, lineHeight: 1, marginTop: 4 }}>{r.us.score} <span style={{ fontSize: 22, opacity: 0.6 }}>({r.us.overs})</span></div>
          </div>
        </div>
        <div style={{ fontFamily: DISPLAY, fontSize: 40, letterSpacing: 1, color: pal.accent }}>v</div>
        <div style={{ padding: '18px 22px', background: !won ? `${pal.accent}1f` : `${pal.ink}0c`, border: `2px solid ${!won ? pal.accent : pal.ink + '22'}`, display: 'flex', alignItems: 'center', gap: 16, justifyContent: 'flex-end', textAlign: 'right' }}>
          <div>
            <div style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 1, lineHeight: 1, whiteSpace: 'nowrap' }}>{r.them.name}</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 52, letterSpacing: -0.5, lineHeight: 1, marginTop: 4 }}>{r.them.score} <span style={{ fontSize: 22, opacity: 0.6 }}>({r.them.overs})</span></div>
          </div>
          <Monogram text={r.them.mono} size={56} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}33`} />
        </div>
      </div>

      {/* potm + footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 92, padding: '0 56px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}` }}>
          <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 2, color: pal.accent, whiteSpace: 'nowrap', flexShrink: 0 }}>★ POTM</span>
          <span style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, whiteSpace: 'nowrap', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.potm.first} {r.potm.last}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: pal.ink, opacity: 0.75, whiteSpace: 'nowrap', flexShrink: 0 }}>{r.potm.line}</span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rmh-g" />
    </Post>
  );
}

// ── B · BROADCAST (structured rows) ───────────────────────────────────────────
function ResultBroadcast({ pal }) {
  const r = window.RESULT1;
  const won = r.winner === 'us';
  const TeamRow = ({ t, isWinner }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 22, padding: '24px 26px', background: isWinner ? `${pal.accent}1a` : `${pal.ink}08`, borderLeft: `6px solid ${isWinner ? pal.accent : pal.ink + '22'}`, position: 'relative' }}>
      <Monogram text={t.mono} size={78} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}40`} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 44, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</div>
        <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1.5, color: pal.ink, opacity: 0.6, marginTop: 6 }}>{t.overs} OVERS</div>
      </div>
      {isWinner && <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 2, color: pal.primary, background: pal.accent, padding: '4px 11px' }}>WON</span>}
      <div style={{ fontFamily: DISPLAY, fontSize: 76, letterSpacing: -1, lineHeight: 1 }}>{t.score}</div>
    </div>
  );
  const Col = ({ title, items, accent }) => (
    <div>
      <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.8, color: pal.ink, opacity: 0.55, marginBottom: 8 }}>{title}</div>
      {items.map((p, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, padding: '5px 0', borderBottom: `1px solid ${pal.ink}14`, fontFamily: DISPLAY }}>
          <span style={{ fontSize: 22, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.n}</span>
          <span style={{ fontSize: 18, color: accent, letterSpacing: 0.5, whiteSpace: 'nowrap', flexShrink: 0 }}>{p.l}</span>
        </div>
      ))}
    </div>
  );
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={10} />
      <Stripes color={pal.accent} opacity={0.03} gap={30} angle={0} />

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={28} style={{ padding: '9px 17px' }}>FULL TIME</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`${r.comp} · ${r.round} · ${r.date} · ${r.venue}`}</Kicker>
        </div>
        <div style={{ fontFamily: DISPLAY, fontSize: 56, letterSpacing: 2, color: pal.ink, opacity: 0.9 }}>RESULT</div>
      </div>

      {/* team rows */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 222, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <TeamRow t={r.us} isWinner={won} />
        <div style={{ textAlign: 'center', fontFamily: DISPLAY, fontSize: 28, letterSpacing: 3, color: pal.accent, margin: '2px 0' }}>{window.CLUB.name} {r.margin}</div>
        <TeamRow t={r.them} isWinner={!won} />
      </div>

      {/* performers */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 656, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40 }}>
        <div>
          <div style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 2, color: pal.accent, marginBottom: 12 }}>{r.us.mono} · TOP PERFORMERS</div>
          <Col title="BATTING" items={r.topBat.us} accent={pal.accent} />
          <div style={{ height: 14 }} />
          <Col title="BOWLING" items={r.topBowl.us} accent={pal.accent} />
        </div>
        <div>
          <div style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 2, color: pal.ink, opacity: 0.85, marginBottom: 12 }}>{r.them.mono} · TOP PERFORMERS</div>
          <Col title="BATTING" items={r.topBat.them} accent={pal.ink} />
          <div style={{ height: 14 }} />
          <Col title="BOWLING" items={r.topBowl.them} accent={pal.ink} />
        </div>
      </div>

      {/* potm + footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 92, padding: '0 56px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}` }}>
          <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 2, color: pal.accent, whiteSpace: 'nowrap', flexShrink: 0 }}>★ POTM</span>
          <span style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, whiteSpace: 'nowrap', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.potm.first} {r.potm.last}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: pal.ink, opacity: 0.75, whiteSpace: 'nowrap', flexShrink: 0 }}>{r.potm.line}</span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rb-g" />
    </Post>
  );
}

// ── C · VERSUS COLUMNS ────────────────────────────────────────────────────────
function ResultVersusColumns({ pal }) {
  const r = window.RESULT1;
  const won = r.winner === 'us';
  const Column = ({ t, bat, bowl, isWinner }) => (
    <div style={{ flex: 1, position: 'relative', background: isWinner ? `${pal.accent}16` : 'transparent', border: `2px solid ${isWinner ? pal.accent : pal.ink + '1f'}`, padding: '28px 26px', display: 'flex', flexDirection: 'column' }}>
      {isWinner && <div style={{ position: 'absolute', top: -15, left: 26, padding: '4px 12px', background: pal.accent, color: pal.primary, fontFamily: DISPLAY, fontSize: 15, letterSpacing: 2 }}>WINNER</div>}
      <Shield monogram={t.mono} color={pal.ink} size={76} />
      <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 0.5, lineHeight: 1, marginTop: 16, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</div>
      <div style={{ fontFamily: DISPLAY, fontSize: 96, letterSpacing: -2, lineHeight: 0.95, marginTop: 6 }}>{t.score}</div>
      <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1.5, color: pal.ink, opacity: 0.6 }}>{t.overs} OVERS</div>
      <div style={{ marginTop: 22, paddingTop: 16, borderTop: `1px solid ${pal.ink}22` }}>
        <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.8, color: pal.accent, marginBottom: 8 }}>TOP BAT · TOP BOWL</div>
        {[bat[0], bowl[0]].map((p, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, padding: '5px 0', fontFamily: DISPLAY }}>
            <span style={{ fontSize: 24, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.n}</span>
            <span style={{ fontSize: 18, color: pal.ink, opacity: 0.85, whiteSpace: 'nowrap', flexShrink: 0 }}>{p.l}</span>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={26} angle={-22} />

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={28} style={{ padding: '9px 17px' }}>FULL TIME</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`${r.comp} · ${r.round} · ${r.date}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={78} />
      </div>

      {/* two columns */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 224, bottom: 268, display: 'flex', alignItems: 'stretch', gap: 0 }}>
        <Column t={r.us} bat={r.topBat.us} bowl={r.topBowl.us} isWinner={won} />
        <div style={{ width: 90, display: 'grid', placeItems: 'center' }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 56, letterSpacing: 1, color: pal.accent }}>VS</div>
        </div>
        <Column t={r.them} bat={r.topBat.them} bowl={r.topBowl.them} isWinner={!won} />
      </div>

      {/* result slab */}
      <div style={{ position: 'absolute', left: 56, right: 56, bottom: 178, padding: '20px 26px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}`, textAlign: 'center' }}>
        <Kicker color={pal.accent} size={12} style={{ marginBottom: 8 }}>{`// MATCH RESULT`}</Kicker>
        <div style={{ fontFamily: DISPLAY, fontSize: 48, letterSpacing: 0, lineHeight: 1.02 }}>{window.CLUB.name} WIN {r.margin}</div>
        <div style={{ display: 'inline-block', marginTop: 12, padding: '6px 14px', background: `${pal.ink}10`, border: `1px solid ${pal.accent}`, fontFamily: MONO, fontSize: 12, letterSpacing: 1.5, color: pal.ink, opacity: 0.9 }}>★ MOTM · {r.potm.first} {r.potm.last} · {r.potm.line}</div>
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rvc-g" />
    </Post>
  );
}

// ════════════════ RESULTS ROUNDUP ════════════════

function record(rows) {
  const w = rows.filter(r => r.outcome === 'W').length;
  const l = rows.filter(r => r.outcome === 'L').length;
  return { w, l };
}

// ── A · WEEKEND WRAP (list) ───────────────────────────────────────────────────
function ResultsList({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const rec = record(rows);
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.03} gap={28} angle={0} />

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 28px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={30} style={{ padding: '9px 18px' }}>RESULTS</Slab>
          <Kicker color={pal.ink} size={14} style={{ marginTop: 14, opacity: 0.72 }}>{`// ${m.round} · ${m.date}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: DISPLAY, fontSize: 40, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap' }}><span style={{ color: WIN }}>{rec.w}W</span> · <span style={{ color: LOSS }}>{rec.l}L</span></div>
            <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 2, color: pal.ink, opacity: 0.6, marginTop: 4 }}>ROUND RECORD</div>
          </div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={74} />
        </div>
      </div>

      {/* rows */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 200, bottom: 150, display: 'flex', flexDirection: 'column' }}>
        {rows.map((r, i) => {
          const w = r.outcome === 'W';
          const c = w ? WIN : LOSS;
          return (
            <div key={i} style={{ flex: 1, display: 'grid', gridTemplateColumns: '6px 150px minmax(0,1fr) 232px', alignItems: 'center', gap: 16, borderBottom: i < rows.length - 1 ? `1px solid ${pal.ink}1a` : 'none' }}>
              <div style={{ width: 6, height: 52, background: c }} />
              <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 0.92 }}>{r.grade}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: -0.5, color: pal.ink, opacity: w ? 1 : 0.85, flexShrink: 0 }}>{r.us}</span>
                <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1.5, color: c, fontWeight: 700, flexShrink: 0 }}>{w ? 'DEF' : 'DEF BY'}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 0.5, lineHeight: 1, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.85 }}>{r.opp} {r.them}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'flex-end' }}>
                <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1, color: pal.ink, opacity: 0.6, whiteSpace: 'nowrap' }}>{r.margin}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 20, letterSpacing: 1, color: pal.primary, background: c, padding: '5px 12px', minWidth: 72, textAlign: 'center', flexShrink: 0 }}>{w ? 'WON' : 'LOST'}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rl-g" />
    </Post>
  );
}

// ── B · W/L SCOREBOARD (grid) ─────────────────────────────────────────────────
function ResultsScoreboard({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const rec = record(rows);
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={12} />
      <Stripes color={pal.accent} opacity={0.03} gap={30} angle={-18} />

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontFamily: DISPLAY, fontSize: 76, letterSpacing: -1, lineHeight: 0.9 }}>RESULTS</div>
          <Kicker color={pal.accent} size={15} style={{ marginTop: 8 }}>{`// ${m.round} · ${m.date}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 30 }}><span style={{ color: WIN }}>{rec.w}W</span> · <span style={{ color: LOSS }}>{rec.l}L</span></div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={66} />
        </div>
      </div>

      {/* grid */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 188, bottom: 142, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr 1fr', gap: 18 }}>
        {rows.map((r, i) => {
          const w = r.outcome === 'W';
          const c = w ? WIN : LOSS;
          return (
            <div key={i} style={{ position: 'relative', background: pal.secondary, borderTop: `3px solid ${c}`, padding: '18px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', right: -10, bottom: -40, fontFamily: DISPLAY, fontSize: 200, lineHeight: 0.7, color: c, opacity: 0.1, letterSpacing: -8 }}>{w ? 'W' : 'L'}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', position: 'relative' }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap' }}>{r.grade}</div>
                <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 1.5, padding: '4px 11px', background: c, color: pal.primary, flexShrink: 0 }}>{w ? 'WON' : 'LOST'}</span>
              </div>
              <div style={{ position: 'relative' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Monogram text={window.CLUB.mono} size={40} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}33`} />
                  <span style={{ fontFamily: DISPLAY, fontSize: 32, letterSpacing: -0.5 }}>{r.us}</span>
                  <span style={{ fontFamily: DISPLAY, fontSize: 18, color: pal.accent, opacity: 0.8 }}>v</span>
                  <span style={{ fontFamily: DISPLAY, fontSize: 32, letterSpacing: -0.5, opacity: 0.85 }}>{r.them}</span>
                  <Monogram text={r.oppMono} size={40} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}33`} />
                </div>
                <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1.2, color: pal.ink, opacity: 0.65, marginTop: 10 }}>{r.opp} · {r.margin}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '20px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rs-g" />
    </Post>
  );
}

// ── C · RECORD STRIP (summary) ────────────────────────────────────────────────
function ResultsRecord({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const rec = record(rows);
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.07} size={10} />
      <Stripes color={pal.accent} opacity={0.04} gap={26} angle={-20} />
      <div style={{ position: 'absolute', right: -50, top: 120, fontFamily: DISPLAY, fontSize: 620, lineHeight: 0.74, color: pal.ink, opacity: 0.05, letterSpacing: -18, userSelect: 'none' }}>{rec.w}–{rec.l}</div>

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '48px 56px 30px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Kicker color={pal.accent} size={15}>{`// ${m.round} · ${m.date}`}</Kicker>
          <div style={{ fontFamily: DISPLAY, fontSize: 110, letterSpacing: -2, lineHeight: 0.85, marginTop: 6 }}>WEEKEND<br />WRAP</div>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={84} />
      </div>

      {/* record banner */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 360, display: 'flex', alignItems: 'center', gap: 26, padding: '20px 28px', background: pal.accent }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 58, letterSpacing: -1, lineHeight: 1, color: pal.primary, whiteSpace: 'nowrap', flexShrink: 0 }}>{rec.w} WINS</div>
        <div style={{ width: 3, height: 52, background: pal.primary, opacity: 0.4, flexShrink: 0 }} />
        <div style={{ fontFamily: DISPLAY, fontSize: 58, letterSpacing: -1, lineHeight: 1, color: pal.primary, opacity: 0.6, whiteSpace: 'nowrap', flexShrink: 0 }}>{rec.l} LOSSES</div>
        <div style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 12, letterSpacing: 2, color: pal.primary, textAlign: 'right', lineHeight: 1.5, flexShrink: 0 }}>{window.CLUB.full}<br />{m.season}</div>
      </div>

      {/* result list */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 510, bottom: 150, display: 'flex', flexDirection: 'column' }}>
        {rows.map((r, i) => {
          const w = r.outcome === 'W';
          const c = w ? WIN : LOSS;
          return (
            <div key={i} style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 18, borderBottom: i < rows.length - 1 ? `1px solid ${pal.ink}1a` : 'none' }}>
              <span style={{ fontFamily: DISPLAY, fontSize: 18, letterSpacing: 1, color: pal.primary, background: c, width: 44, height: 32, display: 'grid', placeItems: 'center', flexShrink: 0 }}>{w ? 'W' : 'L'}</span>
              <div style={{ width: 150, fontFamily: DISPLAY, fontSize: 26, letterSpacing: 0.5, flexShrink: 0 }}>{r.grade}</div>
              <div style={{ flex: 1, minWidth: 0, fontFamily: DISPLAY, fontSize: 24, letterSpacing: 0.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                <span style={{ color: w ? pal.ink : c }}>{w ? 'DEF' : 'LOST TO'}</span> {r.opp}
              </div>
              <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: pal.ink, opacity: 0.7, flexShrink: 0 }}>{r.us} v {r.them}</div>
              <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1, color: c, width: 130, textAlign: 'right', flexShrink: 0 }}>{r.margin}</div>
            </div>
          );
        })}
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.32} id="rr-g" />
    </Post>
  );
}

// ── D · STAR OF THE DAY (player-of-the-match hero) ────────────────────────────
function ResultStar({ pal }) {
  const r = window.RESULT1;
  const p = r.potm;
  const initials = (p.first[0] || '') + (p.last[0] || '');
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.04} gap={28} angle={-22} />
      <div style={{ position: 'absolute', left: -30, bottom: 110, fontFamily: DISPLAY, fontSize: 360, lineHeight: 0.8, color: pal.ink, opacity: 0.05, letterSpacing: -8, userSelect: 'none', whiteSpace: 'nowrap' }}>{p.last}</div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={26} style={{ padding: '8px 16px' }}>FULL TIME</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`${r.comp} · ${r.round} · ${r.date}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={78} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 230, display: 'flex', alignItems: 'center', gap: 44 }}>
        <div style={{ width: 300, height: 300, borderRadius: '50%', border: `4px solid ${pal.accent}`, background: `${pal.accent}14`, display: 'grid', placeItems: 'center', fontFamily: DISPLAY, fontSize: 150, color: pal.ink, letterSpacing: 2, flexShrink: 0 }}>{initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Slab bg={pal.accent} fg={pal.primary} size={17} style={{ padding: '6px 12px' }}>★ STAR OF THE DAY</Slab>
          <div style={{ fontFamily: DISPLAY, fontSize: 44, letterSpacing: 1, opacity: 0.7, lineHeight: 1, marginTop: 18 }}>{p.first.toUpperCase()}</div>
          <div style={{ fontFamily: DISPLAY, fontSize: 116, letterSpacing: -1, lineHeight: 0.86, whiteSpace: 'nowrap' }}>{p.last}</div>
          <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, color: pal.accent, marginTop: 8 }}>{p.role}</div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 576, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {[['BATTING', p.bat], ['BOWLING', p.bowl]].map(([lab, val], i) => (
          <div key={i} style={{ padding: '16px 22px', background: i === 0 ? pal.accent : `${pal.ink}0c`, border: `1.5px solid ${pal.accent}`, color: i === 0 ? pal.primary : pal.ink }}>
            <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, opacity: 0.75 }}>{lab}</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 54, lineHeight: 0.95, letterSpacing: -0.5, marginTop: 4 }}>{val}</div>
          </div>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 92, padding: '0 56px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 20px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}` }}>
          <span style={{ fontFamily: DISPLAY, fontSize: 24, letterSpacing: 0.5, whiteSpace: 'nowrap', flexShrink: 0 }}>{window.CLUB.name} WIN {r.margin}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: pal.ink, opacity: 0.7, marginLeft: 'auto', whiteSpace: 'nowrap', flexShrink: 0 }}>{r.us.mono} {r.us.score} · {r.them.mono} {r.them.score}</span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rst-g" />
    </Post>
  );
}

// ── E · INNINGS BARS (proportional score comparison) ──────────────────────────
function ResultInningsBars({ pal }) {
  const r = window.RESULT1;
  const won = r.winner === 'us';
  const runs = (s) => parseInt(String(s).includes('/') ? String(s).split('/')[1] : s, 10);
  const oversNum = (o) => { const [a, b] = String(o).split('.').map(Number); return a + (b || 0) / 6; };
  const usR = runs(r.us.score), themR = runs(r.them.score);
  const maxR = Math.max(usR, themR);
  const usRR = (usR / oversNum(r.us.overs)).toFixed(2);
  const themRR = (themR / oversNum(r.them.overs)).toFixed(2);
  const Bar = ({ t, val, rr, win, fill }) => (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0, flex: 1 }}>
          <Monogram text={t.mono} size={52} fg={pal.ink} bg={`${pal.ink}14`} ring={win ? pal.accent : `${pal.ink}40`} />
          <span style={{ fontFamily: DISPLAY, fontSize: 34, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</span>
          {win && <span style={{ fontFamily: DISPLAY, fontSize: 14, letterSpacing: 2, color: pal.primary, background: pal.accent, padding: '3px 9px', flexShrink: 0 }}>WON</span>}
        </div>
        <span style={{ fontFamily: DISPLAY, fontSize: 56, letterSpacing: -1, lineHeight: 1, flexShrink: 0, marginLeft: 16 }}>{t.score}</span>
      </div>
      <div style={{ height: 46, background: `${pal.ink}10`, position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(val / maxR) * 100}%`, background: fill }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 12, letterSpacing: 1, color: pal.ink, opacity: 0.7, marginTop: 8 }}>
        <span>{t.overs} OVERS</span><span>RUN RATE {rr}</span>
      </div>
    </div>
  );
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.03} gap={30} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={28} style={{ padding: '9px 17px' }}>FULL TIME</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`${r.comp} · ${r.round} · ${r.date} · ${r.venue}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={78} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 256, display: 'flex', flexDirection: 'column', gap: 50 }}>
        <Bar t={r.us} val={usR} rr={usRR} win={won} fill={pal.accent} />
        <Bar t={r.them} val={themR} rr={themRR} win={!won} fill={`${pal.ink}55`} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 648, padding: '24px 28px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}`, textAlign: 'center' }}>
        <Kicker color={pal.accent} size={12} style={{ marginBottom: 8 }}>{`// MATCH RESULT`}</Kicker>
        <div style={{ fontFamily: DISPLAY, fontSize: 52, letterSpacing: 0, lineHeight: 1.02 }}>{window.CLUB.name} WIN {r.margin}</div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 92, padding: '0 56px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: pal.secondary, borderLeft: `4px solid ${pal.accent}` }}>
          <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 2, color: pal.accent, whiteSpace: 'nowrap', flexShrink: 0 }}>★ POTM</span>
          <span style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, whiteSpace: 'nowrap', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.potm.first} {r.potm.last}</span>
          <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: pal.ink, opacity: 0.75, whiteSpace: 'nowrap', flexShrink: 0 }}>{r.potm.line}</span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rib-g" />
    </Post>
  );
}

// ── F · MATCH TICKET (ticket-stub aesthetic) ──────────────────────────────────
function ResultTicket({ pal }) {
  const r = window.RESULT1;
  const won = r.winner === 'us';
  const notch = (side) => ({ position: 'absolute', [side]: -17, top: '50%', transform: 'translateY(-50%)', width: 32, height: 32, borderRadius: '50%', background: pal.primary });
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.04} gap={26} angle={-20} />
      <div style={{ position: 'absolute', left: 80, right: 80, top: 108, bottom: 150, background: pal.secondary, border: `2px solid ${pal.accent}`, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '24px 36px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: `2px dashed ${pal.accent}66`, position: 'relative' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 3, color: pal.accent }}>MATCH TICKET · FULL TIME</div>
            <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 1, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.comp}</div>
          </div>
          <div style={{ textAlign: 'right', fontFamily: MONO, fontSize: 12, letterSpacing: 1.5, color: pal.ink, opacity: 0.72, lineHeight: 1.7, flexShrink: 0, marginLeft: 16 }}>{r.round}<br />{r.date}<br />{r.venue}</div>
          <div style={notch('left')} /><div style={notch('right')} />
        </div>
        <div style={{ flex: 1, padding: '28px 36px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 16 }}>
          {[[r.us, won], [r.them, !won]].map(([t, win], i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
              <Monogram text={t.mono} size={62} fg={pal.ink} bg={`${pal.ink}14`} ring={win ? pal.accent : `${pal.ink}40`} />
              <span style={{ fontFamily: DISPLAY, fontSize: 38, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: win ? 1 : 0.85 }}>{t.name}</span>
              {win && <span style={{ fontFamily: DISPLAY, fontSize: 14, letterSpacing: 2, color: pal.primary, background: pal.accent, padding: '4px 10px', flexShrink: 0 }}>WON</span>}
              <span style={{ fontFamily: DISPLAY, fontSize: 62, letterSpacing: -1, lineHeight: 1, flexShrink: 0 }}>{t.score}</span>
            </div>
          ))}
          <div style={{ marginTop: 8, paddingTop: 18, borderTop: `1px solid ${pal.ink}1a`, textAlign: 'center' }}>
            <div style={{ fontFamily: DISPLAY, fontSize: 46, letterSpacing: 0 }}>{window.CLUB.name} WIN {r.margin}</div>
            <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1.5, color: pal.ink, opacity: 0.75, marginTop: 8 }}>★ POTM · {r.potm.first} {r.potm.last} · {r.potm.line}</div>
          </div>
        </div>
        <div style={{ padding: '16px 36px', borderTop: `2px dashed ${pal.accent}66`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', position: 'relative' }}>
          <div style={notch('left')} /><div style={notch('right')} />
          <div style={{ display: 'flex', gap: 3, alignItems: 'center', height: 40 }}>
            {Array.from({ length: 30 }).map((_, i) => (<div key={i} style={{ width: i % 4 === 0 ? 4 : 2, height: 30, background: pal.ink, opacity: 0.8 }} />))}
          </div>
          <div style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 2, color: pal.ink, opacity: 0.85 }}>BETTERSTATS · ADMIT ONE</div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 80, right: 80, bottom: 44, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 18 }}>
        <span style={{ fontFamily: BODY, fontSize: 11, letterSpacing: 2.5, color: pal.ink, opacity: 0.5, fontWeight: 600 }}>PRESENTED BY</span>
        {window.SPONSORS.map((s, i) => (
          <span key={i} style={{ fontFamily: DISPLAY, fontSize: 18, letterSpacing: 1, color: pal.ink, opacity: 0.78 }}>{s}</span>
        ))}
      </div>
      <Grain opacity={0.3} id="rtk-g" />
    </Post>
  );
}

// ════════════════ RESULTS ROUNDUP (new) ════════════════

// ── D · HEADLINE RESULT (marquee + others) ────────────────────────────────────
function ResultsHeadline({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const rec = record(rows);
  const f = rows[0];
  const rest = rows.slice(1);
  const fw = f.outcome === 'W';
  const fc = fw ? WIN : LOSS;
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.03} gap={28} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 22px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={26} style={{ padding: '8px 16px' }}>RESULTS</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`// ${m.round} · ${m.date}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 36, whiteSpace: 'nowrap' }}><span style={{ color: WIN }}>{rec.w}W</span> · <span style={{ color: LOSS }}>{rec.l}L</span></div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={70} />
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 196, height: 340, background: pal.secondary, borderTop: `3px solid ${fc}`, padding: '26px 32px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, color: pal.accent }}>{`// FEATURE · ${f.grade}`}</span>
          <span style={{ fontFamily: DISPLAY, fontSize: 18, letterSpacing: 2, color: pal.primary, background: fc, padding: '5px 12px' }}>{fw ? 'WON' : 'LOST'}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 26, marginTop: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Monogram text={window.CLUB.mono} size={66} fg={pal.ink} bg={`${pal.ink}14`} ring={fw ? pal.accent : `${pal.ink}40`} />
            <span style={{ fontFamily: DISPLAY, fontSize: 64, letterSpacing: -1, lineHeight: 1 }}>{f.us}</span>
          </div>
          <span style={{ fontFamily: DISPLAY, fontSize: 34, color: pal.accent }}>v</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontFamily: DISPLAY, fontSize: 64, letterSpacing: -1, lineHeight: 1, opacity: 0.85 }}>{f.them}</span>
            <Monogram text={f.oppMono} size={66} fg={pal.ink} bg={`${pal.ink}14`} ring={!fw ? pal.accent : `${pal.ink}40`} />
          </div>
        </div>
        <div style={{ textAlign: 'center', fontFamily: DISPLAY, fontSize: 40, letterSpacing: 0, marginTop: 20, lineHeight: 1 }}>{window.CLUB.name} {fw ? 'DEF' : 'LOST TO'} {f.opp} {f.margin}</div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 560, bottom: 150 }}>
        <Kicker color={pal.ink} size={12} style={{ opacity: 0.55, marginBottom: 8 }}>{`// OTHER RESULTS`}</Kicker>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {rest.map((r, i) => {
            const w = r.outcome === 'W';
            const c = w ? WIN : LOSS;
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '9px 0', borderBottom: `1px solid ${pal.ink}14` }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 16, letterSpacing: 1, color: pal.primary, background: c, width: 40, height: 28, display: 'grid', placeItems: 'center', flexShrink: 0 }}>{w ? 'W' : 'L'}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 22, width: 132, flexShrink: 0, lineHeight: 1 }}>{r.grade}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 22, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}><span style={{ color: w ? pal.ink : c }}>{w ? 'def' : 'lost to'}</span> {r.opp}</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: pal.ink, opacity: 0.65, flexShrink: 0, whiteSpace: 'nowrap' }}>{r.us} v {r.them}</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: c, width: 124, textAlign: 'right', flexShrink: 0 }}>{r.margin}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '20px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rhd-g" />
    </Post>
  );
}

// ── E · RESULTS BOARD (tabular) ───────────────────────────────────────────────
function ResultsBoard({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const rec = record(rows);
  const cols = '140px minmax(0,1fr) 184px 86px';
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.05} size={11} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 22px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={30} style={{ padding: '9px 18px' }}>RESULTS</Slab>
          <Kicker color={pal.ink} size={14} style={{ marginTop: 14, opacity: 0.72 }}>{`// ${m.round} · ${m.date}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 36, whiteSpace: 'nowrap' }}><span style={{ color: WIN }}>{rec.w}W</span> · <span style={{ color: LOSS }}>{rec.l}L</span></div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={70} />
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 196, display: 'grid', gridTemplateColumns: cols, gap: 18, padding: '0 14px 10px', borderBottom: `1px solid ${pal.ink}22` }}>
        {['GRADE', 'RESULT', 'SCORE', ''].map((h, i) => (
          <div key={i} style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.8, color: pal.ink, opacity: 0.5, textAlign: i === 2 ? 'right' : i === 3 ? 'center' : 'left' }}>{h}</div>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 242, bottom: 150, display: 'flex', flexDirection: 'column' }}>
        {rows.map((r, i) => {
          const w = r.outcome === 'W';
          const c = w ? WIN : LOSS;
          return (
            <div key={i} style={{ flex: 1, display: 'grid', gridTemplateColumns: cols, gap: 18, alignItems: 'center', padding: '0 14px', background: i % 2 ? `${pal.ink}08` : 'transparent' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 26, letterSpacing: 0.5, lineHeight: 0.92 }}>{r.grade}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 24, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}><span style={{ color: w ? pal.ink : c }}>{w ? 'DEF' : 'LOST TO'}</span> {r.opp}</div>
                <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1, color: c, marginTop: 4 }}>{r.margin}</div>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 0.5, color: pal.ink, opacity: 0.85, textAlign: 'right', whiteSpace: 'nowrap' }}>{r.us} v {r.them}</div>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 18, letterSpacing: 1, color: pal.primary, background: c, width: 60, textAlign: 'center', padding: '5px 0' }}>{w ? 'WON' : 'LOST'}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rbd-g" />
    </Post>
  );
}

// ── F · WIN/LOSS SPLIT (wins vs losses columns) ───────────────────────────────
function ResultsSplit({ pal }) {
  const m = window.RESULTS_META;
  const rows = window.RESULTS;
  const wins = rows.filter(r => r.outcome === 'W');
  const losses = rows.filter(r => r.outcome === 'L');
  const Side = ({ title, items, color, count }) => (
    <div style={{ flex: 1, background: `${color}12`, border: `2px solid ${color}`, display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '16px 22px', background: color, color: pal.primary, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 1 }}>{title}</span>
        <span style={{ fontFamily: DISPLAY, fontSize: 42, letterSpacing: -1, lineHeight: 1 }}>{count}</span>
      </div>
      <div style={{ flex: 1, padding: '8px 22px' }}>
        {items.map((r, i) => (
          <div key={i} style={{ padding: '14px 0', borderBottom: i < items.length - 1 ? `1px solid ${pal.ink}1a` : 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 0.5, flexShrink: 0, whiteSpace: 'nowrap' }}>{r.grade}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1, color: pal.ink, opacity: 0.5, marginLeft: 'auto', flexShrink: 0, whiteSpace: 'nowrap' }}>{r.margin}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 4 }}>
              <span style={{ fontFamily: DISPLAY, fontSize: 26, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: pal.ink, opacity: 0.7, flexShrink: 0 }}>{r.us} v {r.them}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.03} gap={28} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={30} style={{ padding: '9px 18px' }}>RESULTS</Slab>
          <Kicker color={pal.ink} size={14} style={{ marginTop: 14, opacity: 0.72 }}>{`// ${m.round} · ${m.date} · HOW THE GRADES WENT`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={74} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 200, bottom: 150, display: 'flex', gap: 22, alignItems: 'stretch' }}>
        <Side title="WON" items={wins} color={WIN} count={wins.length} />
        <Side title="LOST" items={losses} color={LOSS} count={losses.length} />
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="rsp-g" />
    </Post>
  );
}

Object.assign(window, {
  ResultMarginHero, ResultBroadcast, ResultVersusColumns, ResultStar, ResultInningsBars, ResultTicket,
  ResultsList, ResultsScoreboard, ResultsRecord, ResultsHeadline, ResultsBoard, ResultsSplit,
});
