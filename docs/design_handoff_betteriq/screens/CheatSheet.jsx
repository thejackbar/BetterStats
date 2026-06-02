import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'

/* Captain's Cheat Sheet (analytics brief §16.6) — a clean, print-ready one-pager
 * composed from the opposition report + live dossier we already build. Light
 * theme on purpose (prints cleanly, looks like a proper team sheet); "Print /
 * Save as PDF" uses the browser's print dialog. */

const INK = '#0f172a', MUTED = '#64748b', LINE = '#e2e8f0', ACCENT = '#6d28d9'
const RED = '#dc2626', GREEN = '#16a34a'
const POLL_MS = 2500
const num = (v, d = '—') => (v === null || v === undefined ? d : v)

function Section({ title, children, style }) {
  return (
    <div style={{ marginBottom: 14, ...style }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: ACCENT, marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  )
}

function PlayerLine({ name, stat, note }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '3px 0', borderBottom: `1px solid ${LINE}`, fontSize: 12.5 }}>
      <div style={{ minWidth: 0 }}>
        <span style={{ fontWeight: 600 }}>{name}</span>
        {note && <div style={{ color: MUTED, fontSize: 11, marginTop: 1 }}>{note}</div>}
      </div>
      <span style={{ whiteSpace: 'nowrap', color: INK, fontVariantNumeric: 'tabular-nums' }}>{stat}</span>
    </div>
  )
}

export default function CheatSheet() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const opponent = params.get('opponent') || undefined
  const fixtureId = params.get('fixture') || undefined
  const team = params.get('team') || undefined

  const [report, setReport] = useState(null)
  const [dossier, setDossier] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    api.iqOppositionReport({ opponent, fixtureId }).then(setReport).catch(() => setReport({ error: true }))
    let tries = 0
    const poll = () => {
      api.iqOppositionDossier({ opponent, fixtureId, team }).then(d => {
        setDossier(d)
        if (d.status === 'building' && tries++ < 12) pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => setDossier({ status: 'error' }))
    }
    poll()
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, []) // once

  const oppName = dossier?.opponent?.name || report?.opponent?.name || 'Opponent'
  const ready = dossier && dossier.status !== 'building' && dossier.status !== 'error' && dossier.status !== 'unavailable'
  const gp = ready ? dossier.game_plan : null
  const h2h = report?.head_to_head
  const matchups = report?.matchups?.bowler_dominance || []
  const ourBat = report?.our_performers?.batting || []
  const ourBowl = report?.our_performers?.bowling || []
  const bestVenue = (report?.venues || []).filter(v => v.wins > (v.losses || 0)).sort((a, b) => b.played - a.played)[0]

  return (
    <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
      <style>{`@media print { .cs-noprint{display:none!important} body{background:#fff!important} .cs-sheet{box-shadow:none!important;margin:0!important;max-width:none!important} @page{margin:12mm} }`}</style>

      {/* toolbar */}
      <div className="cs-noprint" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', maxWidth: 820, margin: '0 auto', padding: '14px 8px' }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', color: MUTED, cursor: 'pointer', fontSize: 13 }}>← Back to scout</button>
        <button onClick={() => window.print()} style={{ background: ACCENT, color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>Print / Save as PDF</button>
      </div>

      {/* sheet */}
      <div className="cs-sheet" style={{ maxWidth: 820, margin: '0 auto 40px', background: '#fff', color: INK, padding: 32, borderRadius: 8, boxShadow: '0 4px 24px rgba(0,0,0,0.08)', fontFamily: 'ui-sans-serif, system-ui, sans-serif' }}>
        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `2px solid ${INK}`, paddingBottom: 12, marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, textTransform: 'uppercase', color: ACCENT }}>Captain's Cheat Sheet</div>
            <div style={{ fontSize: 28, fontWeight: 800, lineHeight: 1.1, marginTop: 2 }}>{oppName}</div>
            <div style={{ color: MUTED, fontSize: 12, marginTop: 3 }}>
              {dossier?.selected_team_name ? `${dossier.selected_team_name} · ` : ''}{bestVenue ? `we're strongest at ${bestVenue.venue}` : ''}
            </div>
          </div>
          <div style={{ textAlign: 'right', fontSize: 12, color: MUTED }}>
            {h2h?.meetings ? <div style={{ fontSize: 18, fontWeight: 700, color: INK }}>{h2h.wins}–{h2h.losses}</div> : null}
            {h2h?.meetings ? <div>record vs them</div> : null}
            <div style={{ marginTop: 4 }}>BetterIQ · {new Date().toLocaleDateString()}</div>
          </div>
        </div>

        {/* game plan banner */}
        {gp && (
          <div style={{ background: '#f5f3ff', border: `1px solid ${'#ddd6fe'}`, borderRadius: 8, padding: 14, marginBottom: 16 }}>
            {gp.one_liner && <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 10 }}>{gp.one_liner}</div>}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              {[['Remove early', gp.remove_early], ['See off', gp.see_off], ['Target', gp.target_bowler]].map(([label, v]) => (
                <div key={label} style={{ background: '#fff', borderRadius: 6, padding: 10, border: `1px solid ${LINE}` }}>
                  <div style={{ fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8, color: MUTED }}>{label}</div>
                  <div style={{ fontWeight: 700, fontSize: 14, marginTop: 2 }}>{v?.name || '—'}</div>
                  {v?.economy != null && <div style={{ fontSize: 11, color: MUTED }}>econ {v.economy}</div>}
                </div>
              ))}
            </div>
            {gp.key_warning && <div style={{ marginTop: 10, fontSize: 12.5, color: RED }}>⚠ {gp.key_warning}</div>}
          </div>
        )}
        {!gp && (
          <div className="cs-noprint" style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12.5, color: '#9a3412' }}>
            {dossier?.status === 'building' ? 'Building their live dossier… the game plan will fill in shortly.' : 'Live dossier not available — open the scout first to build it.'}
          </div>
        )}

        {/* two columns */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          <div>
            <Section title="Danger batters">
              {ready && dossier.danger_batters?.length
                ? dossier.danger_batters.slice(0, 5).map(b => (
                  <PlayerLine key={b.player_id} name={b.name} stat={`${b.runs} @ ${num(b.average)}`} note={b.plan || (b.vs_us ? `${b.vs_us.runs} vs us` : null)} />
                ))
                : <div style={{ color: MUTED, fontSize: 12 }}>—</div>}
            </Section>
            <Section title="Danger bowlers">
              {ready && dossier.danger_bowlers?.length
                ? dossier.danger_bowlers.slice(0, 5).map(b => (
                  <PlayerLine key={b.player_id} name={b.name} stat={`${b.wickets}w @ ${num(b.average)}`} note={b.plan} />
                ))
                : <div style={{ color: MUTED, fontSize: 12 }}>—</div>}
            </Section>
            {ready && dossier.partnership_insight && (
              <Section title="Their batting shape"><div style={{ fontSize: 12.5, color: INK }}>{dossier.partnership_insight}</div></Section>
            )}
          </div>

          <div>
            {matchups.length > 0 && (
              <Section title="Our bowler match-ups">
                {matchups.slice(0, 6).map((m, i) => (
                  <PlayerLine key={i} name={`${m.bowler} ▸ ${m.batter}`} stat={`${m.dismissals}×`} />
                ))}
                <div style={{ fontSize: 10.5, color: MUTED, marginTop: 4 }}>Save these bowlers for these batters.</div>
              </Section>
            )}
            {ready && (dossier.how_they_win?.length || dossier.how_they_lose?.length) ? (
              <Section title="Win / lose">
                {(dossier.how_they_win || []).slice(0, 2).map((b, i) => <div key={`w${i}`} style={{ fontSize: 12, padding: '2px 0' }}><span style={{ color: GREEN }}>▲</span> {b}</div>)}
                {(dossier.how_they_lose || []).slice(0, 2).map((b, i) => <div key={`l${i}`} style={{ fontSize: 12, padding: '2px 0' }}><span style={{ color: RED }}>▼</span> {b}</div>)}
              </Section>
            ) : null}
            {(ourBat.length > 0 || ourBowl.length > 0) && (
              <Section title="Our edge vs them">
                {ourBat.slice(0, 3).map(p => <PlayerLine key={p.player_id} name={p.name} stat={`${p.runs} @ ${num(p.average)}`} />)}
                {ourBowl.slice(0, 2).map(p => <PlayerLine key={p.player_id} name={p.name} stat={`${p.wickets}w @ ${num(p.average)}`} />)}
              </Section>
            )}
          </div>
        </div>

        <div style={{ borderTop: `1px solid ${LINE}`, marginTop: 12, paddingTop: 8, fontSize: 10.5, color: MUTED }}>
          Built from scorecards — a starting plan, not gospel. {h2h?.recent_form?.length ? `Recent form vs them: ${h2h.recent_form.join(' ')}.` : ''}
        </div>
      </div>
    </div>
  )
}
