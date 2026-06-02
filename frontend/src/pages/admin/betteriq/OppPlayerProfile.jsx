// Shared opposition-player profile — the closest thing to our own player-trends
// deep-dive that the data supports for an opponent: current-season batting &
// bowling, recent form, dismissal patterns and their full record vs us. Built
// from the live dossier (we don't store opponents' multi-season history).
const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const fmt2 = (v) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(2)

export function MiniStat({ label, value }) {
  return (
    <div className="text-center px-2 py-1">
      <div className="font-display font-bold text-lg pb-num leading-none">{value}</div>
      <div className="text-pb-faintest text-[10px] uppercase tracking-wide2 mt-0.5">{label}</div>
    </div>
  )
}

// Merge a dossier's batting + bowling lists into a per-player index.
export function buildOppPlayerIndex(dossier) {
  const m = new Map()
  for (const b of dossier?.batting || []) m.set(b.player_id, { name: b.name, bat: b, bowl: null })
  for (const w of dossier?.bowling || []) {
    const e = m.get(w.player_id) || { name: w.name, bat: null, bowl: null }
    e.bowl = w; m.set(w.player_id, e)
  }
  return m
}

export function OppPlayerDetail({ entry, enriched, opponentName }) {
  if (!entry) return null
  const { bat, bowl } = entry
  const formColor = bat?.form === 'hot' ? 'var(--pb-red)' : bat?.form === 'cold' ? 'var(--pb-faint)' : 'var(--pb-accent)'
  const dism = bat?.dismissals && Object.entries(bat.dismissals).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="font-display font-bold text-xl">{entry.name}</span>
        {opponentName && <span className="text-pb-faint text-sm">· {opponentName}</span>}
        {bat?.form && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${formColor} 16%, transparent)`, color: formColor }}>{bat.form}</span>}
        {enriched?.alert?.level === 'danger' && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-red) 16%, transparent)', color: 'var(--pb-red)' }}>Danger</span>}
        {enriched?.alert?.level === 'caution' && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-amber) 16%, transparent)', color: 'var(--pb-amber)' }}>Paper tiger?</span>}
      </div>

      {enriched?.key_note && <div className="text-sm mb-3" style={{ color: 'var(--pb-accent)' }}>{enriched.key_note}</div>}
      {enriched?.plan && <div className="text-[13px] mb-3 text-pb-faint">Plan: {enriched.plan}</div>}

      {bat && bat.innings > 0 && (
        <div className="mb-3">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Batting · this season</div>
          <div className="flex flex-wrap items-center gap-1">
            <MiniStat label="Inns" value={num(bat.innings)} />
            <MiniStat label="Runs" value={num(bat.runs)} />
            <MiniStat label="Avg" value={fmt2(bat.average)} />
            <MiniStat label="SR" value={fmt2(bat.strike_rate)} />
            <MiniStat label="HS" value={num(bat.high_score)} />
            <MiniStat label="50/100" value={`${num(bat.fifties, 0)}/${num(bat.hundreds, 0)}`} />
            {bat.boundary_pct != null && <MiniStat label="Bndry%" value={`${bat.boundary_pct}%`} />}
          </div>
          {bat.recent_scores?.length > 0 && <div className="text-pb-faintest text-[12px] mt-1">Recent: <span className="pb-num">{bat.recent_scores.join(', ')}</span></div>}
          {dism?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {dism.map(([k, v]) => <span key={k} className="text-[11px] px-1.5 py-0.5 rounded-full capitalize" style={{ background: 'var(--pb-surface2)' }}>{k} <span className="pb-num text-pb-faint">{v}</span></span>)}
            </div>
          )}
        </div>
      )}

      {bat?.vs_us && (
        <div className="mb-3 rounded-lg p-2.5" style={{ background: 'color-mix(in srgb, var(--pb-red) 8%, transparent)' }}>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Their batting vs us</div>
          <div className="text-sm pb-num">{bat.vs_us.innings} inns · {bat.vs_us.runs} runs @ <b>{fmt2(bat.vs_us.average)}</b> · HS {num(bat.vs_us.high_score)}{bat.vs_us.fifties ? ` · ${bat.vs_us.fifties}×50` : ''}{bat.vs_us.hundreds ? ` · ${bat.vs_us.hundreds}×100` : ''}</div>
        </div>
      )}

      {bowl && bowl.wickets > 0 && (
        <div className="mb-3">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Bowling · this season</div>
          <div className="flex flex-wrap items-center gap-1">
            <MiniStat label="Overs" value={num(bowl.overs)} />
            <MiniStat label="Wkts" value={num(bowl.wickets)} />
            <MiniStat label="Avg" value={fmt2(bowl.average)} />
            <MiniStat label="Econ" value={fmt2(bowl.economy)} />
            <MiniStat label="Best" value={num(bowl.best)} />
            {bowl.five_fors ? <MiniStat label="5wi" value={num(bowl.five_fors)} /> : null}
          </div>
          {bowl.recent_wickets?.length > 0 && <div className="text-pb-faintest text-[12px] mt-1">Recent wkts: <span className="pb-num">{bowl.recent_wickets.join(', ')}</span></div>}
        </div>
      )}

      {bowl?.vs_us && (
        <div className="rounded-lg p-2.5" style={{ background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' }}>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Their bowling vs us</div>
          <div className="text-sm pb-num">{bowl.vs_us.wickets} wkts @ <b>{fmt2(bowl.vs_us.average)}</b> · econ {fmt2(bowl.vs_us.economy)}{bowl.vs_us.best ? ` · best ${bowl.vs_us.best}` : ''}</div>
        </div>
      )}

      {!bat?.innings && !bowl?.wickets && (
        <div className="text-pb-faintest text-sm">No current-season scorecard data for this player yet.</div>
      )}
    </div>
  )
}
