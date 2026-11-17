import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'

// The club says what a match was, for its premierships: a normal game, a final or the grand final.
// Premierships are written automatically from grand finals Cricket Australia names "Grand Final". When
// the round is called something else ("Round 16"), or the final was washed out and the club took the
// flag on the ladder, the club tags the match here and the flag follows (services/premierships.py).

const INPUT_CLS = 'w-full min-w-0 bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'

const KINDS = [
  { value: 'grand_final', label: 'Grand final' },
  { value: 'final', label: 'Final' },
  { value: 'normal', label: 'Normal game' },
]
const KIND_LABEL = Object.fromEntries(KINDS.map(k => [k.value, k.label]))

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function outcome(t) {
  if (t.kind !== 'grand_final') return 'Not the decider, so no premiership from this match.'
  if (t.players) return `Premiership recorded for ${t.players} player${t.players === 1 ? '' : 's'}.`
  return t.reason ? `No flag yet: ${t.reason}.` : 'No flag yet.'
}

export default function AdminPremierships() {
  const { user } = useAuth()
  const clubId = user?.club_id
  const [tags, setTags] = useState(null)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({ match: '', kind: 'grand_final', won: false })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [formErr, setFormErr] = useState(null)

  function load() {
    if (!clubId) return
    api.listMatchTags(clubId)
      .then(r => { setTags(r.tags || []); setError(null) })
      .catch(e => setError(e.message))
  }
  useEffect(load, [clubId])

  async function save(e) {
    e.preventDefault()
    if (!form.match.trim()) { setFormErr('Paste a match link from play.cricket.com.au, or its match ID.'); return }
    setBusy(true); setFormErr(null); setMsg(null)
    try {
      const res = await api.setMatchTag(clubId, form.match.trim(), form.kind, form.kind === 'grand_final' && form.won)
      setMsg(`Tagged as ${KIND_LABEL[res.kind].toLowerCase()}. ${outcome(res)}`)
      setForm({ match: '', kind: 'grand_final', won: false })
      load()
    } catch (err) {
      setFormErr(err.message || 'That did not save.')
    } finally {
      setBusy(false)
    }
  }

  async function change(t, kind, won) {
    if (!kind && !window.confirm(
      'Take the tag off this match? Premiership honours written because of it are removed. '
      + 'Flags your club typed by hand stay, unlinked from the match.')) return
    setBusy(true); setMsg(null)
    try {
      await api.setMatchTag(clubId, t.game_id, kind, won)
      load()
    } catch (err) {
      setError(err.message || 'That did not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">Premierships</h1>
        <p className="text-[13px] text-pb-dim mb-5 leading-relaxed">
          Premierships are added automatically when your side wins a match Cricket Australia calls the grand final.
          If a grand final was missed (the round has another name, or it was washed out and you took the flag on the
          ladder), tag the match here. Everyone on the team sheet gets the flag, linked to the match. Tag a match as a
          final or a normal game to stop it counting as a grand final.
        </p>

        <form onSubmit={save} className="pb-card p-4 sm:p-5 mb-6 space-y-3" data-testid="tag-form">
          <label className="block">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">MATCH LINK OR ID</span>
            <input value={form.match} onChange={e => setForm(f => ({ ...f, match: e.target.value }))}
              placeholder="https://play.cricket.com.au/match/…" className={`${INPUT_CLS} mt-1 font-mono`} />
            <span className="block text-[11px] text-pb-faint mt-1">
              Open the match on play.cricket.com.au and copy the link from the address bar.
            </span>
          </label>
          <fieldset>
            <legend className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">THIS MATCH WAS</legend>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {KINDS.map(k => (
                <label key={k.value} className="flex items-center gap-2 text-sm text-pb-text">
                  <input type="radio" name="kind" value={k.value} checked={form.kind === k.value}
                    onChange={() => setForm(f => ({ ...f, kind: k.value }))} />
                  {k.label}
                </label>
              ))}
            </div>
          </fieldset>
          {form.kind === 'grand_final' && (
            <div className="flex items-start gap-2 text-sm text-pb-text">
              <input id="tag-won" type="checkbox" className="mt-1" checked={form.won}
                onChange={e => setForm(f => ({ ...f, won: e.target.checked }))} />
              <label htmlFor="tag-won">
                We won the premiership
                <span className="block text-[11px] text-pb-faint">
                  Only needed when the scorecard shows no winner, such as a washed-out final. Otherwise the result on
                  the card decides it.
                </span>
              </label>
            </div>
          )}
          {formErr && <p className="text-pb-red text-xs">{formErr}</p>}
          {msg && <p className="text-xs" style={{ color: 'var(--pb-accent)' }}>{msg}</p>}
          <div className="flex justify-end">
            <button type="submit" disabled={busy}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
              style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
              {busy ? 'SAVING…' : 'TAG MATCH'}
            </button>
          </div>
        </form>

        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">TAGGED MATCHES</p>
        {error && <p className="text-pb-red text-sm mb-3">{error}</p>}
        {tags && !tags.length && (
          <p className="text-sm text-pb-faint">No matches tagged yet. Grand finals named as such are picked up without a tag.</p>
        )}
        <ul className="space-y-2" data-testid="tag-list">
          {(tags || []).map(t => (
            <li key={t.game_id} className="pb-card p-3 sm:p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <Link to={`/games/${t.game_id}`} className="text-sm text-pb-text hover:underline min-w-0">
                  {[t.grade_name, t.opponent ? `v ${t.opponent}` : null, fmtDate(t.played_at)].filter(Boolean).join(' · ')
                    || 'Match'}
                </Link>
                <span className="font-mono text-[10px] tracking-wide2" style={{ color: 'var(--pb-accent)' }}>
                  {KIND_LABEL[t.kind].toUpperCase()}{t.won ? ' · WON' : ''}
                </span>
              </div>
              {t.round_name && <p className="text-[11px] text-pb-faintest">Round on the card: {t.round_name}</p>}
              <p className="text-[12px] text-pb-dim mt-1">{outcome(t)}</p>
              <div className="flex flex-wrap items-center gap-3 mt-2">
                <select value={t.kind} disabled={busy} aria-label="Change what this match was"
                  onChange={e => change(t, e.target.value, e.target.value === 'grand_final' && t.won)}
                  className="bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-2 py-1">
                  {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
                {t.kind === 'grand_final' && (
                  <label className="flex items-center gap-1.5 text-xs text-pb-dim">
                    <input type="checkbox" checked={t.won} disabled={busy}
                      onChange={e => change(t, 'grand_final', e.target.checked)} />
                    We won
                  </label>
                )}
                <button type="button" disabled={busy} onClick={() => change(t, null, false)}
                  className="ml-auto font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
                  REMOVE TAG
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </BetterStatsLayout>
  )
}
