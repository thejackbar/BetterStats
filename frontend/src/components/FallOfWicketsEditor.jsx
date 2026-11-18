import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { PbSpinner } from '../lib/presskit'

// A club types the fall of wickets from its own scorebook for its own innings of a synced match.
// Cricket Australia's card is sometimes short (six wickets, four rows). The typed wickets replace
// the synced ones for that innings and the partnerships are worked out from them on the server.

const blankRow = () => ({ score: '', pid: '' })
// Wickets down starts at 0 (an opener retiring before the first wicket), so a left-alone box is not refused.
const blankRetirement = () => ({ score: '', pid: '', after: '0' })
const str = v => (v == null ? '' : String(v))

function draftFrom(inn) {
  const rows = {}
  for (const f of inn.fow || []) {
    rows[f.wicket_number] = {
      score: str(f.score_at_fall),
      pid: f.participant_id || '',
    }
  }
  return rows
}

// Retirements and the unbroken last stand: what ends a partnership without a wicket.
function extrasFrom(inn) {
  return {
    retirements: (inn.retirements || []).map(r => ({
      score: str(r.score), pid: r.participant_id || '', after: str(r.after_wicket),
    })),
    unbroken: !!inn.unbroken,
    unbrokenScore: inn.unbroken ? str(inn.unbroken_score) : '',
  }
}

const inputCls = 'w-full min-w-0 px-2 py-1.5 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text'

function ordinal(n) {
  if (n % 100 >= 11 && n % 100 <= 13) return 'th'
  return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'
}

function InningsEditor({ gameId, inn, onChanged }) {
  const [rows, setRows] = useState(() => draftFrom(inn))
  const [extras, setExtras] = useState(() => extrasFrom(inn))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState(null)

  useEffect(() => { setRows(draftFrom(inn)); setExtras(extrasFrom(inn)) }, [inn])

  const recorded = Object.keys(draftFrom(inn)).map(Number)
  const slots = Math.max(inn.wickets, ...recorded, 0)
  const used = useMemo(() => new Set(Object.values(rows).map(r => r.pid).filter(Boolean)), [rows])
  const dirty = JSON.stringify(rows) !== JSON.stringify(draftFrom(inn))
    || JSON.stringify(extras) !== JSON.stringify(extrasFrom(inn))
  const allBatters = inn.all_batters || inn.batters || []

  const set = (w, patch) => setRows(r => ({ ...r, [w]: { ...(r[w] || blankRow()), ...patch } }))
  const setRet = (i, patch) => setExtras(x => ({
    ...x, retirements: x.retirements.map((r, j) => (j === i ? { ...r, ...patch } : r)),
  }))

  async function run(fn) {
    setBusy(true); setErr(null); setNote(null)
    try {
      const res = await fn()
      onChanged(res.innings)
      setNote([res.summary, ...(res.warnings || [])].join(' '))
    } catch (e) {
      setErr(e.message || 'That did not save.')
    } finally {
      setBusy(false)
    }
  }

  const save = () => {
    const out = []
    for (let w = 1; w <= slots; w++) {
      const r = rows[w] || blankRow()
      if (r.score === '' && !r.pid) continue
      out.push({
        wicket_number: w,
        score_at_fall: r.score === '' ? null : Number(r.score),
        participant_id: r.pid || null,
      })
    }
    const retirements = extras.retirements
      .filter(r => r.score !== '' || r.pid || r.after !== '')
      .map(r => ({
        participant_id: r.pid || null,
        score: r.score === '' ? null : Number(r.score),
        after_wicket: r.after === '' ? null : Number(r.after),
      }))
    return run(() => api.saveFow(gameId, inn.innings_number, out, {
      retirements,
      unbroken: extras.unbroken,
      unbroken_score: extras.unbroken && extras.unbrokenScore !== '' ? Number(extras.unbrokenScore) : null,
    }))
  }

  // A stand a wicket ended belongs to that wicket's row; a retirement's or the unbroken one is listed below.
  const standByWicket = Object.fromEntries(
    (inn.stands || []).filter(s => !s.is_unbroken).map(s => [s.wicket_number, s]))
  const unbrokenStands = (inn.stands || []).filter(s => s.is_unbroken)
  const missing = inn.missing || {}

  return (
    <div>
      <p className="text-xs text-pb-faint mb-3">
        {recorded.length} of {inn.wickets} wickets recorded
        {inn.edited ? ', typed by the club' : ' by Cricket Australia'}.
      </p>

      {!slots && (
        <p className="text-xs text-pb-faint mb-3">The batting card shows no wickets in this innings.</p>
      )}
      {slots > 0 && (
      <div className="grid grid-cols-[2.25rem_4.75rem_minmax(0,1fr)] gap-x-2 gap-y-2 items-center">
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">WKT</span>
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">SCORE</span>
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">BATTER OUT</span>
        {Array.from({ length: slots }, (_, i) => i + 1).map(w => {
          const r = rows[w] || blankRow()
          const stand = standByWicket[w]
          return (
            <div key={w} className="contents">
              <span className="font-mono text-sm text-pb-faint pb-num">{w}</span>
              <input
                type="number" inputMode="numeric" min="0" value={r.score}
                aria-label={`Score at wicket ${w}`}
                onChange={e => set(w, { score: e.target.value })}
                className="w-full min-w-0 px-2 py-1.5 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text font-mono"
              />
              <select
                value={r.pid} aria-label={`Batter out at wicket ${w}`}
                onChange={e => set(w, { pid: e.target.value })}
                className="w-full min-w-0 px-2 py-1.5 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text"
              >
                <option value="">Not sure</option>
                {inn.batters.map(b => (
                  <option key={b.participant_id} value={b.participant_id}
                    disabled={used.has(b.participant_id) && r.pid !== b.participant_id}>
                    {b.name}{b.runs != null ? ` (${b.runs})` : ''}
                  </option>
                ))}
              </select>
              {(stand || missing[w]) && (
                <p className="col-span-3 -mt-1 mb-1 pl-[2.75rem] text-[11px] text-pb-faintest">
                  {stand
                    ? `Partnership: ${stand.runs} (${[stand.batter1_name, stand.batter2_name].filter(Boolean).join(' and ')})`
                    : `No partnership for this wicket: ${missing[w]}.`}
                </p>
              )}
            </div>
          )
        })}
      </div>
      )}

      <div className="mt-5 pt-4 pb-hairline-t">
        <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest mb-1">RETIREMENTS</p>
        <p className="text-[11px] text-pb-faint mb-2">
          A batter who retired ends the partnership without a wicket. Enter the score when they retired and how many
          wickets were down (0 if no wicket had fallen). A retired batter is taken to come back once everyone else has
          batted.
        </p>
        {extras.retirements.length > 0 && (
          <div className="grid grid-cols-[4.25rem_minmax(0,1fr)_4.25rem_1.25rem] gap-x-2 gap-y-2 items-center mb-2">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">SCORE</span>
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">BATTER RETIRED</span>
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">WKTS DOWN</span>
            <span />
            {extras.retirements.map((r, i) => (
              <div key={i} className="contents">
                <input type="number" inputMode="numeric" min="0" value={r.score}
                  aria-label={`Score at retirement ${i + 1}`}
                  onChange={e => setRet(i, { score: e.target.value })}
                  className={`${inputCls} font-mono`} />
                <select value={r.pid} aria-label={`Batter who retired, retirement ${i + 1}`}
                  onChange={e => setRet(i, { pid: e.target.value })} className={inputCls}>
                  <option value="">Pick a batter</option>
                  {allBatters.map(b => (
                    <option key={b.participant_id} value={b.participant_id}>
                      {b.name}{b.runs != null ? ` (${b.runs})` : ''}
                    </option>
                  ))}
                </select>
                <input type="number" inputMode="numeric" min="0" max="10" value={r.after}
                  aria-label={`Wickets down at retirement ${i + 1}`}
                  onChange={e => setRet(i, { after: e.target.value })}
                  className={`${inputCls} font-mono`} />
                <button type="button" aria-label={`Remove retirement ${i + 1}`}
                  onClick={() => setExtras(x => ({ ...x, retirements: x.retirements.filter((_, j) => j !== i) }))}
                  className="text-pb-faint hover:text-pb-text text-sm">×</button>
              </div>
            ))}
          </div>
        )}
        <button type="button"
          onClick={() => setExtras(x => ({ ...x, retirements: [...x.retirements, blankRetirement()] }))}
          className="font-mono text-[10px] tracking-wide2 hover:underline" style={{ color: 'var(--pb-accent)' }}>
          + ADD A RETIREMENT
        </button>

        <div className="flex items-start gap-2 mt-4 text-sm text-pb-text">
          <input id={`unbroken-${inn.innings_number}`} type="checkbox" checked={extras.unbroken} className="mt-1"
            onChange={e => setExtras(x => ({ ...x, unbroken: e.target.checked }))} />
          <label htmlFor={`unbroken-${inn.innings_number}`}>
            Last partnership unbroken at the end of the innings
            <span className="block text-[11px] text-pb-faint">
              Records the stand between the two batters still in. Needs every wicket entered with its batter.
            </span>
          </label>
        </div>
        {extras.unbroken && (
          <div className="flex flex-wrap items-center gap-2 mt-2 pl-6">
            <span className="text-[11px] text-pb-faint">Score at the end</span>
            <input type="number" inputMode="numeric" min="0" value={extras.unbrokenScore}
              aria-label="Score at the end of the innings"
              placeholder={inn.innings_total != null ? String(inn.innings_total) : ''}
              onChange={e => setExtras(x => ({ ...x, unbrokenScore: e.target.value }))}
              className={`${inputCls} font-mono !w-24`} />
            {inn.innings_total != null && extras.unbrokenScore === '' && (
              <span className="text-[11px] text-pb-faintest">blank uses the card&apos;s total</span>
            )}
          </div>
        )}

        {unbrokenStands.length > 0 && (
          <ul className="mt-3 space-y-0.5">
            {unbrokenStands.map((s, i) => (
              <li key={i} className="text-[11px] text-pb-faintest">
                Unbroken {s.wicket_number}{ordinal(s.wicket_number)} wicket partnership: {s.runs}*
                {' '}({[s.batter1_name, s.batter2_name].filter(Boolean).join(' and ')})
              </li>
            ))}
          </ul>
        )}
      </div>

      {err && <p className="text-pb-red text-xs mt-3">{err}</p>}
      {note && !err && <p className="text-xs text-pb-faint mt-3">{note}</p>}

      <div className="flex flex-wrap justify-end gap-2 mt-4">
        {inn.edited && (
          <button type="button" disabled={busy}
            onClick={() => {
              if (window.confirm("Go back to Cricket Australia's fall of wickets for this innings? The wickets you typed are removed.")) {
                run(() => api.resetFow(gameId, inn.innings_number))
              }
            }}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text disabled:opacity-50">
            RESET TO CRICKET AUSTRALIA
          </button>
        )}
        <button type="button" onClick={save} disabled={busy || !dirty}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
          style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
          {busy ? 'SAVING…' : 'SAVE WICKETS'}
        </button>
      </div>
    </div>
  )
}

export default function FallOfWicketsEditor({ gameId, onClose, onSaved }) {
  const [state, setState] = useState({ loading: true, innings: [], error: null })
  const [changed, setChanged] = useState(false)

  useEffect(() => {
    let alive = true
    api.getFowEditor(gameId)
      .then(d => { if (alive) setState({ loading: false, innings: d.innings || [], error: null }) })
      .catch(e => { if (alive) setState({ loading: false, innings: [], error: e.message }) })
    return () => { alive = false }
  }, [gameId])

  function replace(updated) {
    setChanged(true)
    setState(s => ({ ...s, innings: s.innings.map(i => (i.innings_number === updated.innings_number ? updated : i)) }))
  }

  const close = () => (changed ? onSaved() : onClose())

  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/60 px-4 py-6 overflow-y-auto" onClick={close}>
      <div className="pb-card w-full max-w-lg p-5" onClick={e => e.stopPropagation()}>
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">EDIT FALL OF WICKETS</p>
        <p className="text-xs text-pb-faint mb-4">
          Enter the score and the batter out at each wicket from your scorebook. You can leave a wicket out, or leave
          its batter as &quot;Not sure&quot;. Partnerships are worked out from what you enter, for the wickets where the
          figures settle who was at the crease. Add any retirements, and tick the last partnership if it was unbroken.
        </p>

        {state.loading && <div className="py-6 flex justify-center"><PbSpinner /></div>}
        {state.error && <p className="text-pb-red text-sm">{state.error}</p>}

        {state.innings.map(inn => (
          <div key={inn.innings_number} className="mb-6 last:mb-0">
            {state.innings.length > 1 && (
              <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest mb-2 uppercase">Innings {inn.innings_number}</p>
            )}
            <InningsEditor gameId={gameId} inn={inn} onChanged={replace} />
          </div>
        ))}

        <div className="flex justify-end mt-5">
          <button type="button" onClick={close}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            {changed ? 'DONE' : 'CLOSE'}
          </button>
        </div>
      </div>
    </div>
  )
}
