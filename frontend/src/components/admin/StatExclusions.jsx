import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner } from '../../lib/presskit'
import { Badge, Button, Empty, Icon, Modal, Note, ON_ACCENT, TINT, TextInput, tone } from './ui'

// A club leaves a whole match out of its players' stats: a friendly, a pre-season cup, a social
// midweek T20 that sits in Cricket Australia's competition list. The match stays on Results and its
// scorecard; only this club's players lose it. Backed by routers/stat_exclusions.py; see
// services/stat_exclusions.py for how every figure follows.

const UNDO_MS = 8000
const RED = '#ef5b5b'

function dateParts(iso) {
  if (!iso) return null
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return null
  return {
    day: d.getDate(),
    mon: d.toLocaleDateString('en-AU', { month: 'short' }).toUpperCase(),
    year: d.getFullYear(),
    long: d.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }),
  }
}

function matchTitle(m) {
  return [m.home_team, m.away_team].filter(Boolean).join(' v ') || 'Match'
}

// The calendar tile at the left of every match row.
function DateTile({ iso, muted = false }) {
  const p = dateParts(iso)
  return (
    <div
      className="shrink-0 w-[52px] rounded-lg border text-center py-1.5 select-none"
      style={{ borderColor: muted ? 'var(--pb-hairline)' : TINT.border, background: muted ? 'var(--pb-surface2)' : TINT.panel }}
      aria-hidden="true"
    >
      <div className="font-mono text-[9px] tracking-wide2" style={{ color: muted ? 'var(--pb-faint)' : 'var(--pb-accent-ink)' }}>
        {p ? p.mon : '?'}
      </div>
      <div className="font-display font-bold text-[20px] leading-none text-pb-text pb-num mt-0.5">{p ? p.day : '?'}</div>
      <div className="font-mono text-[9px] text-pb-faint mt-0.5">{p ? p.year : ''}</div>
    </div>
  )
}

function MatchLine({ m, muted = false, link = true }) {
  const p = dateParts(m.played_at)
  return (
    <div className="flex items-start gap-3 min-w-0">
      <DateTile iso={m.played_at} muted={muted} />
      <div className="min-w-0 flex-1">
        <p className="text-[14.5px] font-semibold text-pb-text leading-snug break-words">
          {link
            ? <Link to={`/games/${m.game_id}`} className="hover:text-pb-accent transition-colors">{matchTitle(m)}</Link>
            : matchTitle(m)}
        </p>
        <p className="text-[12.5px] text-pb-faint mt-0.5 break-words">
          {[m.grade_name, m.season_name, p?.long].filter(Boolean).join(' · ')}
        </p>
        {m.result && <p className="text-[12px] text-pb-dim mt-0.5 break-words">{m.result}</p>}
      </div>
    </div>
  )
}

// What the exclusion takes away, as four figures.
function TakeawayStrip({ totals }) {
  const cells = [
    ['Players', totals.players],
    ['Runs', totals.runs],
    ['Wickets', totals.wickets],
    ['Dismissals', totals.dismissals],
  ]
  return (
    <div className="grid grid-cols-4 rounded-lg border border-pb-hairline overflow-hidden" data-testid="takeaway-strip">
      {cells.map(([label, v], i) => (
        <div key={label} className={`px-2 py-2.5 text-center ${i ? 'border-l border-pb-hairline' : ''}`}>
          <div className="font-display font-bold text-[19px] text-pb-text pb-num leading-none">{v ?? 0}</div>
          <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mt-1">{label}</div>
        </div>
      ))}
    </div>
  )
}

function PlayerChips({ players }) {
  if (!players?.length) return null
  return (
    <ul className="flex flex-wrap gap-1.5" data-testid="takeaway-players">
      {players.map(p => {
        const bits = []
        if (p.innings) bits.push(`${p.runs}`)
        if (p.wickets) bits.push(`${p.wickets}w`)
        if (p.dismissals) bits.push(`${p.dismissals}ct`)
        return (
          <li key={p.player_id}
            className="text-[12px] rounded-md px-2 py-[3px] border border-pb-hairline bg-pb-surface2 text-pb-dim">
            <span className="text-pb-text">{p.name}</span>
            {bits.length > 0 && <span className="font-mono text-[10.5px] text-pb-faint ml-1.5">{bits.join(' · ')}</span>}
          </li>
        )
      })}
    </ul>
  )
}

// "Are you sure you want to exclude this match?"
export function ExcludeConfirm({ match, onCancel, onDone }) {
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const go = async () => {
    setSaving(true)
    setError(null)
    try {
      const out = await api.excludeMatchFromStats({ link: match.game_id, note: note.trim() || null })
      onDone(out)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <Modal
      onClose={saving ? undefined : onCancel}
      width={520}
      title="Are you sure you want to exclude this match?"
      subtitle="It comes off your players' career stats. The scorecard stays on your site."
      footer={(
        <>
          <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={go} disabled={saving} data-testid="confirm-exclude"
            style={{ background: RED, color: '#fff' }}>
            {saving ? 'Excluding…' : 'Yes, exclude it'}
          </Button>
        </>
      )}
    >
      <div className="space-y-4 pb-2" data-testid="exclude-confirm">
        <div className="rounded-lg border border-pb-hairline p-3">
          <MatchLine m={match} link={false} />
        </div>
        <div>
          <p className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-1.5">What comes off your players' figures</p>
          <TakeawayStrip totals={match.totals} />
        </div>
        <PlayerChips players={match.players} />
        <Note title="What happens">
          Career and season totals, leaderboards, records, milestones and StatLab all leave this match out.
          {' '}{match.other_team ? `${match.other_team} players keep their figures.` : "The other side's players keep their figures."}
          {' '}You can count it again at any time.
        </Note>
        <label className="block">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1">REASON (OPTIONAL)</span>
          <TextInput value={note} maxLength={300} onChange={e => setNote(e.target.value)}
            placeholder="e.g. Pre-season friendly" data-testid="exclude-note" />
        </label>
        {error && <p className="text-pb-red text-sm" role="alert">{error}</p>}
      </div>
    </Modal>
  )
}

// "Count this match again?"
export function RestoreConfirm({ row, onCancel, onDone }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const go = async () => {
    setSaving(true)
    setError(null)
    try {
      onDone(await api.restoreMatchToStats(row.id))
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }
  return (
    <Modal
      onClose={saving ? undefined : onCancel}
      width={480}
      title="Count this match in career stats again?"
      subtitle="Every figure goes back the way it was before you excluded it."
      footer={(
        <>
          <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={go} disabled={saving} data-testid="confirm-restore">
            {saving ? 'Saving…' : 'Count it again'}
          </Button>
        </>
      )}
    >
      <div className="pb-2 space-y-3" data-testid="restore-confirm">
        <div className="rounded-lg border border-pb-hairline p-3"><MatchLine m={row} link={false} /></div>
        {error && <p className="text-pb-red text-sm" role="alert">{error}</p>}
      </div>
    </Modal>
  )
}

// A toast with an Undo button and a bar that runs down to when it goes.
export function UndoToast({ toast, onClose }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const timer = useRef(null)

  useEffect(() => {
    if (!toast) return undefined
    setBusy(false)
    setError(null)
    timer.current = setTimeout(onClose, UNDO_MS)
    return () => clearTimeout(timer.current)
  }, [toast, onClose])

  if (!toast) return null
  const undo = async () => {
    clearTimeout(timer.current)
    setBusy(true)
    setError(null)
    try {
      await toast.undo()
      onClose()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }
  return (
    <div
      key={toast.id}
      className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[120] w-[min(440px,calc(100vw-32px))] bg-pb-surface border rounded-[10px] overflow-hidden ch-rise"
      style={{ borderColor: TINT.borderStrong, boxShadow: '0 8px 40px rgba(0,0,0,0.6)' }}
      role="status" data-testid="undo-toast"
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center"
          style={{ background: TINT.chip, color: 'var(--pb-accent-ink)' }}>
          <Icon name={toast.icon || 'check'} size={15} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13.5px] font-semibold" style={{ color: 'var(--pb-accent-ink)' }}>{toast.title}</span>
          {toast.body && <span className="block text-[12.5px] text-pb-dim truncate">{toast.body}</span>}
          {error && <span className="block text-[12px] text-pb-red">{error}</span>}
        </span>
        {toast.undo && (
          <button type="button" onClick={undo} disabled={busy} data-testid="toast-undo"
            className="shrink-0 rounded-md px-3 py-1.5 text-[13px] font-semibold disabled:opacity-50"
            style={{ background: 'var(--pb-accent)', color: ON_ACCENT }}>
            {busy ? 'Undoing…' : 'Undo'}
          </button>
        )}
        <button type="button" onClick={onClose} className="text-pb-faint hover:text-pb-text shrink-0" aria-label="Dismiss">✕</button>
      </div>
      {!busy && (
        <div className="h-[3px]" style={{ background: TINT.pill }}>
          <div className="h-full origin-left" style={{
            background: 'var(--pb-accent)',
            animation: `sxDrain ${UNDO_MS}ms linear forwards`,
          }} />
        </div>
      )}
      <style>{'@keyframes sxDrain { from { transform: scaleX(1) } to { transform: scaleX(0) } }'}</style>
    </div>
  )
}

function useUndoToast() {
  const [toast, setToast] = useState(null)
  const show = useCallback(t => setToast({ ...t, id: Date.now() }), [])
  const close = useCallback(() => setToast(null), [])
  return [toast, show, close]
}

function ExcludedRow({ row, onRestore }) {
  const p = dateParts(row.entered_at)
  return (
    <li className="py-3.5 border-b border-pb-hairline last:border-b-0" data-testid="excluded-row">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-[260px]">
          <MatchLine m={row} />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 ml-[64px]">
            <Badge toneKey="block">Not in career stats</Badge>
            {row.note && <span className="text-[12px] text-pb-dim break-words">“{row.note}”</span>}
            <span className="text-[11.5px] text-pb-faintest">
              Excluded{row.entered_by_name ? ` by ${row.entered_by_name}` : ''}{p ? ` on ${p.long}` : ''}
            </span>
          </div>
        </div>
        <div className="flex gap-2 shrink-0 ml-[64px] sm:ml-0">
          <Button variant="soft" size="sm" as={Link} to={`/games/${row.game_id}`}>Scorecard</Button>
          <Button variant="secondary" size="sm" icon="undo" onClick={() => onRestore(row)} data-testid="restore-row">
            Count it again
          </Button>
        </div>
      </div>
    </li>
  )
}

// The Manual entries tab: paste a link, check the match, exclude it; the list of matches left out.
export function ExcludedMatchesTab() {
  const [rows, setRows] = useState(null)
  const [link, setLink] = useState('')
  const [preview, setPreview] = useState(null)
  const [finding, setFinding] = useState(false)
  const [error, setError] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [restoring, setRestoring] = useState(null)
  const [toast, showToast, closeToast] = useUndoToast()

  const load = useCallback(async () => {
    try {
      setRows((await api.getStatExclusions()).exclusions || [])
    } catch (e) {
      setRows([])
      setError(e.message)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const find = async e => {
    e?.preventDefault()
    if (!link.trim()) return
    setFinding(true)
    setError(null)
    setPreview(null)
    try {
      setPreview(await api.lookupStatExclusion(link.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setFinding(false)
    }
  }

  const excludedNow = out => {
    setConfirming(false)
    setPreview(null)
    setLink('')
    load()
    const id = out.exclusion.id
    showToast({
      title: 'Match excluded from career stats',
      body: matchTitle(out.match),
      undo: async () => { await api.restoreMatchToStats(id); await load() },
    })
  }

  const restoredNow = (row) => {
    setRestoring(null)
    load()
    showToast({
      icon: 'undo',
      title: 'Match counted in career stats again',
      body: matchTitle(row),
      undo: async () => { await api.excludeMatchFromStats({ link: row.game_id, note: row.note }); await load() },
    })
  }

  return (
    <div className="space-y-5" data-testid="excluded-matches">
      <section className="rounded-xl border border-pb-hairline bg-pb-surface p-4 sm:p-5">
        <div className="flex items-start gap-3 mb-4">
          <span className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: TINT.chip, color: 'var(--pb-accent-ink)' }}>
            <Icon name="filter" size={17} />
          </span>
          <div className="min-w-0">
            <h2 className="font-display font-bold text-[17px] text-pb-text leading-snug">Exclude a match from career stats</h2>
            <p className="text-[13px] text-pb-faint mt-0.5 max-w-2xl">
              For friendlies, pre-season cups and social games that sit in Play Cricket but shouldn't count.
              The match stays on your Results and its scorecard. Only your club's players lose it.
            </p>
          </div>
        </div>

        <form onSubmit={find} className="flex flex-col sm:flex-row gap-2">
          <TextInput
            value={link}
            onChange={e => { setLink(e.target.value); setError(null) }}
            placeholder="Paste a play.cricket.com.au or BetterCricket match link"
            className="flex-1 min-w-0"
            aria-label="Match link"
            data-testid="exclude-link"
          />
          <Button type="submit" variant="primary" disabled={finding || !link.trim()} data-testid="find-match">
            {finding ? 'Finding…' : 'Find match'}
          </Button>
        </form>
        {error && <p className="text-pb-red text-[13px] mt-2" role="alert" data-testid="exclude-error">{error}</p>}

        {preview && (
          <div className="mt-4 rounded-xl border p-4 ch-rise" style={{ borderColor: TINT.border, background: TINT.rowWash }}
            data-testid="match-preview">
            <MatchLine m={preview} />
            <div className="mt-4"><TakeawayStrip totals={preview.totals} /></div>
            <div className="mt-3"><PlayerChips players={preview.players} /></div>
            <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
              {preview.exclusion ? (
                <>
                  <Badge toneKey="block">Already excluded</Badge>
                  <Button variant="secondary" icon="undo"
                    onClick={() => setRestoring({ ...preview, id: preview.exclusion.id, note: preview.exclusion.note })}>
                    Count it again
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="quiet" onClick={() => { setPreview(null); setLink('') }}>Cancel</Button>
                  <Button variant="danger" onClick={() => setConfirming(true)} data-testid="exclude-match">
                    Exclude from career stats
                  </Button>
                </>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-pb-hairline bg-pb-surface p-4 sm:p-5">
        <div className="flex items-baseline justify-between gap-3 mb-1">
          <h3 className="font-display font-bold text-[15px] text-pb-text">Excluded matches</h3>
          {rows?.length > 0 && <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">{rows.length} MATCH{rows.length === 1 ? '' : 'ES'}</span>}
        </div>
        {rows === null && <div className="py-6"><PbSpinner /></div>}
        {rows?.length === 0 && (
          <Empty>No matches excluded. Every match your players played counts in their career stats.</Empty>
        )}
        {rows?.length > 0 && (
          <ul>{rows.map(r => <ExcludedRow key={r.id} row={r} onRestore={setRestoring} />)}</ul>
        )}
      </section>

      {confirming && preview && (
        <ExcludeConfirm match={preview} onCancel={() => setConfirming(false)} onDone={excludedNow} />
      )}
      {restoring && (
        <RestoreConfirm row={restoring} onCancel={() => setRestoring(null)} onDone={() => {
          const row = restoring
          setPreview(null)
          setLink('')
          restoredNow(row)
        }} />
      )}
      <UndoToast toast={toast} onClose={closeToast} />
    </div>
  )
}

// The match page: everyone sees that the club left the match out; an admin of a club that played in
// it can exclude it or count it again, with the same confirm and undo as the Manual entries tab.
export function MatchStatsExclusion({ gameId, excluded, clubName, adminClubName, canEdit, onChanged }) {
  const [info, setInfo] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [restoring, setRestoring] = useState(null)
  const [toast, showToast, closeToast] = useUndoToast()

  const load = useCallback(() => {
    if (!canEdit) return
    // Refused for a match the admin's club did not play: then there is nothing for them to do here.
    api.lookupStatExclusion(gameId).then(setInfo).catch(() => setInfo(null))
  }, [canEdit, gameId])
  useEffect(() => { load() }, [load])

  const changed = () => { load(); onChanged?.() }
  const mine = info?.exclusion
  const showBanner = excluded || !!mine
  const t = tone('block')

  if (!showBanner && !info) return null
  return (
    <>
      {showBanner ? (
        <div className="mb-4 rounded-xl border px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-2"
          style={{ borderColor: t.edge, background: t.soft }} data-testid="stats-excluded-banner">
          <span className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'rgba(239,91,91,0.18)', color: t.ink }}>
            <Icon name="filter" size={15} />
          </span>
          <div className="min-w-0 flex-1 basis-[220px]">
            <p className="font-mono text-[10px] tracking-wide2 uppercase" style={{ color: t.ink }}>Not counted in career stats</p>
            <p className="text-[13px] text-pb-dim">
              {(mine ? adminClubName || clubName : clubName) || 'The club'} has left this match out of its players' career stats.
              {mine?.note ? ` ${mine.note}.` : ''}
            </p>
          </div>
          {mine && (
            <Button variant="secondary" size="sm" icon="undo" data-testid="match-restore"
              onClick={() => setRestoring({ ...info, id: mine.id, note: mine.note })}>
              Count it again
            </Button>
          )}
        </div>
      ) : (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-dashed border-pb-hairline2 px-4 py-2.5"
          data-testid="stats-exclude-bar">
          <p className="text-[12.5px] text-pb-faint min-w-0">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest mr-2">ADMIN</span>
            A friendly or pre-season game? Leave it out of your players' career stats.
          </p>
          <Button variant="quiet-danger" size="sm" onClick={() => setConfirming(true)} data-testid="match-exclude">
            Exclude from career stats
          </Button>
        </div>
      )}

      {confirming && info && (
        <ExcludeConfirm match={info} onCancel={() => setConfirming(false)} onDone={out => {
          setConfirming(false)
          changed()
          const id = out.exclusion.id
          showToast({
            title: 'Match excluded from career stats',
            body: matchTitle(out.match),
            undo: async () => { await api.restoreMatchToStats(id); changed() },
          })
        }} />
      )}
      {restoring && (
        <RestoreConfirm row={restoring} onCancel={() => setRestoring(null)} onDone={() => {
          const row = restoring
          setRestoring(null)
          changed()
          showToast({
            icon: 'undo',
            title: 'Match counted in career stats again',
            body: matchTitle(row),
            undo: async () => { await api.excludeMatchFromStats({ link: row.game_id, note: row.note }); changed() },
          })
        }} />
      )}
      <UndoToast toast={toast} onClose={closeToast} />
    </>
  )
}
