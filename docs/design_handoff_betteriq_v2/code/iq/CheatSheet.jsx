/* BetterIQ — printable match Cheat Sheet.
   A self-contained one-pager (landscape) a captain takes to the toss. Rendered
   in a fixed LIGHT palette (independent of app theme) so it always prints clean
   on paper. Opens as an overlay; the Print button calls window.print(), and the
   @media print rules in iq-theme.css isolate .iq-print-area. */
const { useEffect: useEffectCS } = React;

const CS = {
  ink: '#13151c', dim: '#565d70', faint: '#8a90a2', line: '#e6e7ec', line2: '#d6d8e0',
  paper: '#ffffff', wash: '#f4f5f8', violet: '#6d5de6', violetWash: '#efedfb',
  win: '#0c9b66', loss: '#d8443f', amber: '#c8860e',
};
const csMono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" };
const csEye = { ...csMono, fontSize: 8.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: CS.faint, fontWeight: 600, whiteSpace: 'nowrap' };

function CSStat({ label, value, color }) {
  return (
    <div>
      <div style={{ ...csEye }}>{label}</div>
      <div className="iq-display" style={{ fontWeight: 800, fontSize: 20, color: color || CS.ink, lineHeight: 1.1, marginTop: 2, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{value}</div>
    </div>
  );
}

function CSColumn({ title, accent, children }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="iq-display" style={{ fontWeight: 800, fontSize: 12.5, color: accent, paddingBottom: 6, marginBottom: 8, borderBottom: `2px solid ${accent}` }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>{children}</div>
    </div>
  );
}

function CSPlayer({ name, line, note }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <span className="iq-display" style={{ fontWeight: 700, fontSize: 13, color: CS.ink, whiteSpace: 'nowrap' }}>{name}</span>
        <span style={{ ...csMono, fontSize: 10.5, color: CS.dim, whiteSpace: 'nowrap' }}>{line}</span>
      </div>
      {note && <div style={{ fontSize: 10.5, color: CS.dim, lineHeight: 1.35, marginTop: 2 }}>{note}</div>}
    </div>
  );
}

function CheatSheet({ onClose }) {
  const r = IQ_REPORT, d = IQ_DOSSIER, h = r.head_to_head, lm = r.last_meeting, gp = d.game_plan;
  useEffectCS(() => {
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dismissPlan = name => {
    const rows = r.matchups.bowler_dominance.filter(m => m.batter === name.split(' ').pop());
    if (!rows.length) return null;
    const best = rows.sort((a, b) => b.dismissals - a.dismissals)[0];
    return `${best.bowler} has him ${best.dismissals}× (${best.how.join('/')})`;
  };

  return (
    <div className="iq-cs-overlay" style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(4,5,10,0.72)', backdropFilter: 'blur(6px)', overflow: 'auto', padding: '28px 18px' }}>
      {/* toolbar (screen only) */}
      <div className="iq-no-print" style={{ maxWidth: 1040, margin: '0 auto 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ color: '#fff' }}>
          <div className="iq-display" style={{ fontWeight: 700, fontSize: 16 }}>Match cheat sheet</div>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>One page for the toss — prints clean on paper.</div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => window.print()} className="iq-display" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 13.5, padding: '10px 16px', borderRadius: 10, background: '#fff', color: '#13151c', border: 'none', cursor: 'pointer' }}>
            <Icon name="print" size={16} /> Print / Save PDF
          </button>
          <button onClick={onClose} className="iq-display" style={{ fontWeight: 600, fontSize: 13.5, padding: '10px 16px', borderRadius: 10, background: 'rgba(255,255,255,0.12)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)', cursor: 'pointer' }}>Close</button>
        </div>
      </div>

      {/* the sheet */}
      <div className="iq-print-area" style={{ maxWidth: 1040, margin: '0 auto', background: CS.paper, color: CS.ink, borderRadius: 14, overflow: 'hidden', boxShadow: '0 30px 80px -30px rgba(0,0,0,0.7)', fontFamily: "'Archivo', system-ui, sans-serif" }}>
        <div style={{ padding: '22px 26px' }}>
          {/* header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, paddingBottom: 14, borderBottom: `1px solid ${CS.line}` }}>
            <div>
              <div style={{ ...csEye, color: CS.violet }}>Match cheat sheet</div>
              <div className="iq-display" style={{ fontWeight: 800, fontSize: 28, letterSpacing: '-0.01em', marginTop: 4 }}>Applecross <span style={{ color: CS.faint, fontWeight: 600 }}>vs</span> {d.opponent.name}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 12, color: CS.dim, whiteSpace: 'nowrap' }}>{IQ_PREVIEW.when} · {IQ_PREVIEW.home_away} · {IQ_PREVIEW.venue}</div>
              <div style={{ ...csMono, fontSize: 11, color: CS.faint, marginTop: 3 }}>{IQ_PREVIEW.grade}</div>
              <div className="iq-display" style={{ fontWeight: 700, fontSize: 13, marginTop: 6 }}>Better<span style={{ color: CS.violet }}>IQ</span></div>
            </div>
          </div>

          {/* stat strip */}
          <div style={{ display: 'flex', gap: 26, padding: '14px 0', borderBottom: `1px solid ${CS.line}`, flexWrap: 'wrap' }}>
            <CSStat label="Head to head" value={`${h.wins}–${h.losses}–${h.draws + h.ties}`} />
            <CSStat label="Win rate" value={`${h.win_pct}%`} color={CS.violet} />
            <div>
              <div style={{ ...csEye }}>Recent (newest →)</div>
              <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                {h.recent_form.map((f, i) => {
                  const c = f === 'W' ? CS.win : f === 'L' ? CS.loss : CS.amber;
                  return <span key={i} className="iq-display" style={{ width: 20, height: 20, borderRadius: 5, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: c, background: `${c}1f` }}>{f}</span>;
                })}
              </div>
            </div>
            <CSStat label="Last meeting" value={lm.result} color={lm.result === 'WIN' ? CS.win : CS.loss} />
            <div>
              <div style={{ ...csEye }}>Last scoreline</div>
              <div style={{ ...csMono, fontSize: 13, fontWeight: 600, marginTop: 5 }}>{lm.our_runs} v {lm.opp_runs}</div>
            </div>
          </div>

          {/* game plan banner */}
          <div style={{ background: CS.violetWash, borderRadius: 10, padding: '13px 16px', margin: '14px 0', display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ flex: 2, minWidth: 260 }}>
              <div style={{ ...csEye, color: CS.violet }}>The plan</div>
              <div className="iq-display" style={{ fontWeight: 800, fontSize: 16, lineHeight: 1.2, marginTop: 3 }}>{gp.one_liner}</div>
            </div>
            <div style={{ display: 'flex', gap: 18, flex: 1, minWidth: 240 }}>
              <div><div style={{ ...csEye, color: CS.loss }}>Remove early</div><div className="iq-display" style={{ fontWeight: 700, fontSize: 13, marginTop: 3 }}>{gp.remove_early.name}</div></div>
              <div><div style={{ ...csEye, color: CS.amber }}>See off</div><div className="iq-display" style={{ fontWeight: 700, fontSize: 13, marginTop: 3 }}>{gp.see_off.name}</div></div>
              <div><div style={{ ...csEye, color: CS.win }}>Target</div><div className="iq-display" style={{ fontWeight: 700, fontSize: 13, marginTop: 3 }}>{gp.target_bowler.name}</div></div>
            </div>
          </div>

          {/* three columns */}
          <div style={{ display: 'flex', gap: 22 }}>
            <CSColumn title="Get these out" accent={CS.loss}>
              {d.danger_batters.slice(0, 3).map(b => (
                <CSPlayer key={b.player_id} name={b.name} line={`${b.runs} @ ${Number(b.average).toFixed(2)}`} note={dismissPlan(b.name) || b.plan} />
              ))}
            </CSColumn>
            <div style={{ width: 1, background: CS.line }} />
            <CSColumn title="New-ball threat" accent={CS.violet}>
              {d.danger_bowlers.slice(0, 3).map(b => (
                <CSPlayer key={b.player_id} name={b.name} line={`${b.wickets}w @ ${Number(b.average).toFixed(2)}`} note={b.plan} />
              ))}
            </CSColumn>
            <div style={{ width: 1, background: CS.line }} />
            <CSColumn title="Our edge" accent={CS.win}>
              {r.our_performers.batting.slice(0, 2).map(p => (
                <CSPlayer key={p.player_id} name={p.name} line={`${p.runs} @ ${Number(p.average).toFixed(2)}`} note="Scores heavily against them" />
              ))}
              {r.our_performers.bowling.slice(0, 2).map(p => (
                <CSPlayer key={p.player_id} name={p.name} line={`${p.wickets}w @ ${Number(p.average).toFixed(2)}`} note="Has their number — bowl him long" />
              ))}
            </CSColumn>
          </div>

          {/* footer */}
          <div style={{ display: 'flex', gap: 22, marginTop: 16, paddingTop: 13, borderTop: `1px solid ${CS.line}`, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ ...csEye, color: CS.win }}>They lose when</div>
              <div style={{ fontSize: 11.5, color: CS.dim, lineHeight: 1.4, marginTop: 4 }}>{d.how_they_lose[0]}</div>
            </div>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ ...csEye, color: CS.loss }}>They win when</div>
              <div style={{ fontSize: 11.5, color: CS.dim, lineHeight: 1.4, marginTop: 4 }}>{d.how_they_win[0]}</div>
            </div>
            <div style={{ minWidth: 150 }}>
              <div style={{ ...csEye }}>At the toss</div>
              <div className="iq-display" style={{ fontWeight: 700, fontSize: 13, marginTop: 4 }}>Bat first · par {IQ_PREVIEW.par.score}</div>
              <div style={{ fontSize: 10.5, color: CS.faint, marginTop: 2 }}>They rarely chase 230+</div>
            </div>
          </div>

          <div style={{ ...csMono, fontSize: 8.5, color: CS.faint, marginTop: 14, textAlign: 'center' }}>
            Generated by BetterIQ from scorecard data · {new Date(d.built_at).toLocaleDateString()} · indicative, not gospel
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CheatSheet });
