import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { WINDOW_OPTIONS, rollupSeasons } from '../lib/seasonRollup'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar } from '../components/ScoutUi'
import { Btn, Segmented } from '../../pages/admin/betterselect/ui'
import { bowlingLabel } from '../lib/watchlistOptions'

const TABS = ['batting', 'bowling', 'fielding', 'career']

const RECRUITING_FIELDS = [
  ['visa_status', 'Visa / eligibility'],
  ['transfer_preference', 'Transfer preference'],
  ['availability_window', 'Availability'],
  ['fee_expectations', 'Fee expectations'],
  ['agent_contact', 'Agent / contact'],
]

const NOTE_KINDS = [
  ['watched_live', 'Watched live'],
  ['phone', 'Phone'],
  ['scorecard_review', 'Scorecard review'],
  ['other', 'Other'],
]

const inputCls = 'w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm'

function Stat({ label, value, accent }) {
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="font-mono text-[21px] font-bold mt-0.5" style={accent ? { color: 'var(--pb-accent)' } : undefined}>{value ?? '—'}</div>
    </div>
  )
}

export default function ScoutPlayerProfile() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [player, setPlayer] = useState(undefined)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState('batting')
  const [windowN, setWindowN] = useState(null)
  const [notes, setNotes] = useState([])
  const [selectedCardId, setSelectedCardId] = useState(null)
  const fileRef = useRef(null)

  const load = () => {
    scoutApi.getPlayer(id).then((p) => {
      setPlayer(p)
      if (p.cards?.length) setSelectedCardId((cur) => cur && p.cards.some((c) => c.id === cur) ? cur : p.cards[0].id)
      const bat = p.stats?.totals
      if (bat && (bat.wickets || 0) > (bat.runs || 0) / 20) setActiveTab('bowling')
    }).catch((err) => setError(err.message))
  }
  useEffect(() => { load() }, [id])
  useEffect(() => { scoutApi.listNotes(id).then(setNotes).catch(() => {}) }, [id])

  const refresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      await scoutApi.refreshPlayer(id)
      setTimeout(load, 2500)
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      await scoutApi.uploadPlayerPhoto(id, file)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const selectedCard = player?.cards?.find((c) => c.id === selectedCardId)

  const seasons = player?.stats?.seasons || []
  const latestActiveYear = useMemo(() => {
    let max = null
    for (const s of seasons) if (s.matches > 0 && (max === null || s.year > max)) max = s.year
    return max
  }, [seasons])
  const cutoffYear = windowN != null && latestActiveYear ? latestActiveYear - (windowN - 1) : null
  const windowedSeasons = cutoffYear != null ? seasons.filter((s) => s.year >= cutoffYear) : seasons
  const totals = useMemo(() => rollupSeasons(windowedSeasons), [windowedSeasons])

  const moveStage = async (columnId) => {
    if (!selectedCard) return
    const prevBoard = player.cards
    setPlayer((p) => ({ ...p, cards: p.cards.map((c) => c.id === selectedCard.id ? { ...c, column_id: columnId } : c) }))
    try {
      await scoutApi.moveCard(selectedCard.id, columnId, 0)
      load()
    } catch (err) {
      setError(err.message)
      setPlayer((p) => ({ ...p, cards: prevBoard }))
    }
  }

  if (error && player === undefined) {
    return <ScoutModuleLayout title="Player"><p className="text-sm text-pb-red">{error}</p></ScoutModuleLayout>
  }
  if (player === undefined) {
    return <ScoutModuleLayout title="Player"><p className="text-sm text-pb-dim">Loading…</p></ScoutModuleLayout>
  }

  return (
    <ScoutModuleLayout
      title={player.name}
      caption={[player.club_name, player.grade_name].filter(Boolean).join(' · ') || 'No club recorded'}
      actions={
        <div className="flex items-center gap-2">
          {player.source === 'au_grassroots' && (
            <Btn variant="ghost" sm onClick={refresh} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh stats'}</Btn>
          )}
          <Btn variant="ghost" sm onClick={() => navigator.clipboard?.writeText(window.location.href)}>Share profile</Btn>
          <Btn variant="primary" sm onClick={() => navigate(`/betterscout/app/compare?players=${player.id}`)}>Compare</Btn>
        </div>
      }
    >
      <div className="space-y-5 max-w-[1200px]">
        <Link to="/betterscout/app/players" className="text-sm text-pb-faint hover:text-pb-text">← My players</Link>
        {error && <p className="text-sm text-pb-red">{error}</p>}

        <div className="flex items-start gap-4 flex-wrap">
          <button onClick={() => fileRef.current?.click()}
            className="w-[76px] h-[92px] shrink-0 rounded-lg border border-dashed border-pb-hairline2 flex flex-col items-center justify-center gap-1.5 bg-pb-surface hover:border-pb-faint">
            <PlayerAvatar name={player.name} photoUrl={player.photo_url} size={44} dashed />
            <span className="font-mono text-[7.5px] text-pb-faintest text-center leading-tight px-1">
              {player.photo_url ? 'Change photo' : 'Drop photo or paste URL'}
            </span>
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={uploadPhoto} />

          <div className="flex-1 min-w-0 space-y-2">
            {selectedCard && (
              <div className="flex flex-wrap gap-1.5">
                {[selectedCard.role, selectedCard.batting_hand, bowlingLabel(selectedCard.bowling_action, selectedCard.bowling_type), selectedCard.region]
                  .filter((v) => v && v !== 'None' && v !== '—')
                  .map((v, i) => <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-pb-surface2 text-pb-dim">{v}</span>)}
                {(selectedCard.tags || []).map((t) => (
                  <span key={t} className="text-xs px-2 py-0.5 rounded-full border border-pb-accent/40 text-pb-accent">{t}</span>
                ))}
              </div>
            )}

            {player.cards?.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  {player.cards.length > 1 && (
                    <select value={selectedCardId} onChange={(e) => setSelectedCardId(e.target.value)}
                      className="font-mono text-[10px] uppercase tracking-wide2 bg-pb-surface2 border border-pb-hairline rounded px-1.5 py-1 text-pb-faint">
                      {player.cards.map((c) => <option key={c.id} value={c.id}>{c.watchlist_name}</option>)}
                    </select>
                  )}
                  {player.cards.length === 1 && (
                    <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{selectedCard?.watchlist_name} stage</span>
                  )}
                </div>
                {selectedCard && <StageControl card={selectedCard} onMove={moveStage} />}
              </div>
            )}
          </div>
        </div>

        {!totals.matches && !totals.wickets ? (
          <p className="text-sm text-pb-dim">
            {player.source === 'manual' ? 'No automated stats — manually added.' : 'No stats available yet.'}
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_356px] gap-5">
            <div className="space-y-5">
              <div className="pb-card p-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex gap-4">
                    {TABS.map((t) => (
                      <button key={t} onClick={() => setActiveTab(t)}
                        className="font-mono text-[11px] uppercase tracking-wide2 pb-1.5 border-b-2 transition-colors"
                        style={{ borderColor: activeTab === t ? 'var(--pb-accent)' : 'transparent', color: activeTab === t ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
                        {t}
                      </button>
                    ))}
                  </div>
                  <Segmented
                    options={WINDOW_OPTIONS.map((o) => ({ value: o.n ?? 'full', label: o.label.replace('Last ', '').replace(' seasons', ' SEASONS').replace(' season', ' SEASON').toUpperCase() }))}
                    value={windowN ?? 'full'} onChange={(v) => setWindowN(v === 'full' ? null : v)} sm
                  />
                </div>

                <DisciplineGrid tab={activeTab} totals={totals} />

                <SeasonChart seasons={seasons} activeYears={cutoffYear != null ? new Set(Array.from({ length: latestActiveYear - cutoffYear + 1 }, (_, i) => cutoffYear + i)) : null} />

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-pb-hairline font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest">
                        <th className="text-left px-2 py-1.5">Season</th>
                        <th className="text-left px-2 py-1.5">Grade</th>
                        <th className="text-right px-2 py-1.5">Mat</th>
                        <th className="text-right px-2 py-1.5">Runs</th>
                        <th className="text-right px-2 py-1.5">Avg</th>
                        <th className="text-right px-2 py-1.5">SR</th>
                        <th className="text-right px-2 py-1.5">HS</th>
                        <th className="text-right px-2 py-1.5">Wkts</th>
                        <th className="text-right px-2 py-1.5">Econ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {seasons.map((s) => (
                        <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                          <td className="px-2 py-1.5 font-mono">{s.year}</td>
                          <td className="px-2 py-1.5">{s.grade || '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.matches}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.runs}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.average ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.strike_rate ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.high_score ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.wickets}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.economy ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="space-y-5">
              {selectedCard && <RecruitingPanel card={selectedCard} onSaved={load} />}
              <NotesPanel playerId={id} notes={notes} onChange={setNotes} />
              {player.cards?.length > 0 && (
                <div className="pb-card p-4 space-y-2">
                  <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">On watchlists</div>
                  {player.cards.map((c) => (
                    <div key={c.id} className="flex items-center justify-between text-sm py-1">
                      <span>{c.watchlist_name}</span>
                      <span className="font-mono text-[9.5px] uppercase px-1.5 py-0.5 rounded"
                        style={c.id === selectedCardId ? { background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)' } : { background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }}>
                        {c.column_name}
                      </span>
                    </div>
                  ))}
                  <Link to="/betterscout/app/watchlists" className="text-xs text-pb-faint hover:text-pb-text underline block pt-1">+ Add to another watchlist</Link>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </ScoutModuleLayout>
  )
}

function DisciplineGrid({ tab, totals: t }) {
  if (tab === 'bowling') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Wickets" value={t.wickets} accent />
        <Stat label="Overs" value={t.overs} />
        <Stat label="Economy" value={t.economy} />
        <Stat label="Bowl avg" value={t.bowling_average} />
        <Stat label="Best" value={t.best} />
        <Stat label="5-fors" value={t.five_fors} />
      </div>
    )
  }
  if (tab === 'fielding') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Catches" value={t.catches} accent />
        <Stat label="Wk catches" value={t.catches_wk} />
        <Stat label="Stumpings" value={t.stumpings} />
        <Stat label="Run outs" value={t.run_outs} />
      </div>
    )
  }
  if (tab === 'career') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Matches" value={t.matches} accent />
        <Stat label="Runs" value={t.runs} />
        <Stat label="Wickets" value={t.wickets} />
        <Stat label="Catches" value={t.catches} />
        <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
        <Stat label="5-fors" value={t.five_fors} />
      </div>
    )
  }
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
      <Stat label="Innings" value={t.innings} />
      <Stat label="Runs" value={t.runs} />
      <Stat label="Average" value={t.average} accent />
      <Stat label="Strike rate" value={t.strike_rate} />
      <Stat label="High score" value={t.high_score} />
      <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
    </div>
  )
}

function SeasonChart({ seasons, activeYears }) {
  if (!seasons.length) return null
  const maxRuns = Math.max(1, ...seasons.map((s) => s.runs || 0))
  const maxWkts = Math.max(1, ...seasons.map((s) => s.wickets || 0))
  const sorted = [...seasons].sort((a, b) => a.year - b.year)
  return (
    <div>
      <div className="flex items-center gap-4 mb-2">
        <span className="flex items-center gap-1.5 text-xs text-pb-dim"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--pb-accent)' }} />Runs</span>
        <span className="flex items-center gap-1.5 text-xs text-pb-dim"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: '#3b82f6' }} />Wickets</span>
      </div>
      <div className="flex items-end gap-[26px] overflow-x-auto pb-2" style={{ height: 120 }}>
        {sorted.map((s) => {
          const inWindow = !activeYears || activeYears.has(s.year)
          const rh = Math.max(2, Math.round(((s.runs || 0) / maxRuns) * 100))
          const wh = Math.max(2, Math.round(((s.wickets || 0) / maxWkts) * 100))
          return (
            <div key={s.year} className="flex flex-col items-center gap-1.5 shrink-0" style={{ opacity: inWindow ? 1 : 0.5 }}>
              <div className="flex items-end gap-1" style={{ height: 100 }}>
                <div style={{ width: 22, height: rh, background: 'var(--pb-accent)', borderRadius: 2 }} title={`${s.runs} runs`} />
                <div style={{ width: 22, height: wh, background: '#3b82f6', borderRadius: 2 }} title={`${s.wickets} wickets`} />
              </div>
              <div className="font-mono text-[10px]" style={{ color: inWindow ? 'var(--pb-text)' : 'var(--pb-faint)' }}>{s.year}</div>
              <div className="text-[9.5px] text-pb-faint">{s.grade || ''}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StageControl({ card, onMove }) {
  const [board, setBoard] = useState(null)
  useEffect(() => { scoutApi.getBoard(card.watchlist_id).then(setBoard).catch(() => {}) }, [card.watchlist_id])
  if (!board) return <span className="text-xs text-pb-faint">{card.column_name}</span>
  return (
    <Segmented
      options={board.columns.map((c) => ({ value: c.id, label: c.name.toUpperCase() }))}
      value={card.column_id} onChange={onMove}
    />
  )
}

function RecruitingPanel({ card, onSaved }) {
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    setForm(Object.fromEntries(RECRUITING_FIELDS.map(([k]) => [k, card[k] || ''])))
  }, [card.id])

  const dirty = RECRUITING_FIELDS.some(([k]) => (form[k] || '') !== (card[k] || ''))

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await scoutApi.updateCard(card.id, form)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Recruiting</div>
        <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest">Never shared</span>
      </div>
      {error && <p className="text-xs text-pb-red">{error}</p>}
      {RECRUITING_FIELDS.map(([key, label]) => (
        <label key={key} className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">{label}</div>
          <input value={form[key] || ''} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} className={inputCls} />
        </label>
      ))}
      {dirty && (
        <Btn variant="primary" sm onClick={save} disabled={saving} className="w-full justify-center">
          {saving ? 'Saving…' : 'Save'}
        </Btn>
      )}
      <p className="text-[11px] text-pb-faint">These five fields stay internal — a shared profile carries stats, tags and notes only.</p>
    </div>
  )
}

function NotesPanel({ playerId, notes, onChange }) {
  const [adding, setAdding] = useState(false)
  const [body, setBody] = useState('')
  const [kind, setKind] = useState('other')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!body.trim()) return
    setBusy(true)
    try {
      const note = await scoutApi.createNote(playerId, body.trim(), kind)
      onChange((prev) => [note, ...prev])
      setBody('')
      setAdding(false)
    } catch { /* keep the form open with the entered text on failure */ }
    finally { setBusy(false) }
  }

  const remove = async (id) => {
    await scoutApi.deleteNote(id)
    onChange((prev) => prev.filter((n) => n.id !== id))
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Scouting notes</div>
        <button onClick={() => setAdding((v) => !v)} className="text-xs text-pb-accent hover:underline">+ Add note</button>
      </div>
      {adding && (
        <form onSubmit={submit} className="space-y-2">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={inputCls}>
            {NOTE_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="What did you see?" className={inputCls} autoFocus />
          <Btn variant="primary" sm type="submit" disabled={busy || !body.trim()}>{busy ? 'Saving…' : 'Save note'}</Btn>
        </form>
      )}
      <div className="space-y-3">
        {notes.length === 0 && !adding && <p className="text-xs text-pb-faint">No notes yet.</p>}
        {notes.map((n) => (
          <div key={n.id} className="group">
            <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2 flex items-center justify-between">
              <span>{new Date(n.occurred_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })} · {n.author_name || 'Unknown'} · {NOTE_KINDS.find(([v]) => v === n.kind)?.[1] || n.kind}</span>
              <button onClick={() => remove(n.id)} className="opacity-0 group-hover:opacity-100 text-pb-faint hover:text-pb-red transition-opacity">✕</button>
            </div>
            <p className="text-[13px] mt-0.5">{n.body}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
