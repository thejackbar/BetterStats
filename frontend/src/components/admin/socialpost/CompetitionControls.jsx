// Controls an association socials workspace uses in place of a club's own data
// sources. A workspace has no club games, players or BetterSelect: every post is
// built from a play.cricket.com.au link, and the link names a whole grade round
// (backend: services/social_competition.py).
import { useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import ImageEditorModal from '../../ImageEditorModal'

const BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

const BTN = 'px-3 py-1.5 rounded text-xs font-mono tracking-wide2 shrink-0 disabled:opacity-50'
const BTN_STYLE = { background: 'var(--pb-accent)', color: 'var(--pb-bg)' }

export const COMPETITION_LINK_HELP =
  'Paste a match link or the grade\'s Matches page link from play.cricket.com.au. A match link pulls that match\'s round; a grade link pulls the round it has picked, or the next round if none is picked.'

// One link box, shared by every workspace import so the wording and the PlayHQ
// warning read the same everywhere.
export function CompetitionLinkInput({ onFetch, busy, label = 'Paste a match or grade link', button = 'Fetch' }) {
  const [link, setLink] = useState('')
  const go = () => { const q = link.trim(); if (q) onFetch(q) }
  return (
    <>
      <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-1.5">{label}</p>
      <div className="flex gap-2">
        <input value={link} onChange={(e) => setLink(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()}
          placeholder="play.cricket.com.au match or grade link" aria-label={label}
          className="flex-1 min-w-0 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text font-mono placeholder:text-pb-faintest" />
        <button onClick={go} disabled={busy} className={BTN} style={BTN_STYLE}>{busy ? 'Loading…' : button}</button>
      </div>
    </>
  )
}

export function PlayhqNotice({ notice }) {
  if (notice?.kind !== 'playhq') return null
  return (
    <div className="mt-2 p-2.5 rounded border border-amber-400/50 bg-amber-400/10">
      <p className="font-mono text-[9px] text-amber-400 leading-relaxed">{notice.message}</p>
    </div>
  )
}

// Matches Cricket Australia served with no scorecard, left out of the post.
export function SkippedNote({ skipped }) {
  if (!skipped?.length) return null
  return (
    <p className="font-mono text-[9px] mt-1.5 text-amber-400 leading-relaxed" data-testid="competition-skipped">
      Cricket Australia has no scorecard yet for {skipped.join(', ')}, so {skipped.length === 1 ? 'it is' : 'they are'} not in this post. Fetch again later, or add {skipped.length === 1 ? 'it' : 'them'} in Content.
    </p>
  )
}

// Lineup: the round's matches, each with both sides; picking a side loads that
// side's published team as the post's lineup.
export function CompetitionLineupBox({ onPick }) {
  const [state, setState] = useState({ status: null, data: null, notice: null })
  const fetchRound = async (q) => {
    setState({ status: 'loading', data: null, notice: null })
    try {
      const data = await api.getSocialCompetitionLineups(q)
      if (data.kind === 'round') { setState({ status: 'ok', data, notice: null }); return }
      setState({ status: data.kind === 'playhq' ? null : (data.message || 'Could not read that link'), data: null, notice: data.kind === 'playhq' ? data : null })
    } catch (e) {
      setState({ status: e?.message || 'failed', data: null, notice: null })
    }
  }
  const matches = state.data?.matches || []
  return (
    <div className="flex flex-col gap-2" data-testid="competition-lineups">
      <CompetitionLinkInput onFetch={fetchRound} busy={state.status === 'loading'} />
      <PlayhqNotice notice={state.notice} />
      {state.status && state.status !== 'loading' && state.status !== 'ok' && (
        <p className="font-mono text-[9px] text-pb-faint">✗ {state.status}</p>
      )}
      {state.status === 'ok' && (
        <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mt-1">
          {[state.data.grade, state.data.round].filter(Boolean).join(' · ')} · pick a side
        </p>
      )}
      {state.status === 'ok' && !matches.length && (
        <p className="text-pb-faintest text-[11px]">No matches in that round.</p>
      )}
      <div className="flex flex-col gap-1.5 max-h-[320px] overflow-y-auto">
        {matches.map((m) => (
          <div key={m.match_id} className="px-3 py-2 rounded-lg border pb-hairline bg-pb-surface2">
            <div className="font-mono text-[9px] text-pb-faint mb-1.5">{[m.date, m.venue].filter(Boolean).join(' · ')}</div>
            <div className="flex flex-wrap gap-1.5">
              {m.teams.map((t) => (
                <button key={t.id} onClick={() => onPick(m, t)} disabled={!t.published}
                  className="flex-1 min-w-0 text-left px-2 py-1.5 rounded border pb-hairline bg-pb-surface hover:border-pb-accent disabled:opacity-50 disabled:cursor-not-allowed">
                  <span className="block text-pb-text text-[12px] truncate">{t.label}</span>
                  <span className="block font-mono text-[9px] text-pb-faint">{t.is_home ? 'Home' : 'Away'}{t.published ? ` · ${t.players.length} named` : ' · not named yet'}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// The smallest cap a grade can still fill a team with: 11 players from 8 clubs
// needs at least 2 a club. 0 when the club count is not known yet.
export function smallestCap(clubs, size) {
  return clubs > 0 ? Math.ceil(size / clubs) : 0
}

// Team of the week: the most players one club may have in the team. 0 is no cap.
// Once a round is pulled, a cap the grade's clubs cannot fill the team with is
// greyed out and says why (`clubs` in the round, `size` of the team).
export function TotwClubCap({ cap, onChange, busy, clubs = 0, size = 11 }) {
  const opts = [0, 1, 2, 3, 4]
  const least = smallestCap(clubs, size)
  const tooSmall = (n) => n > 0 && least > 0 && n < least
  return (
    <div className="mb-4" data-testid="totw-club-cap">
      <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide2 mb-1.5">Most players from one club</p>
      <div className="flex flex-wrap gap-1.5">
        {opts.map((n) => {
          const on = cap === n
          const off = tooSmall(n)
          return (
            <button key={n} type="button" onClick={() => onChange(n)} aria-pressed={on} disabled={busy || off}
              title={off ? `${clubs} clubs cannot fill a team of ${size} at ${n} each` : undefined}
              data-testid={`totw-cap-${n}`}
              className="px-3 min-h-8 rounded border font-mono text-[10px] tracking-wide2 transition-colors disabled:opacity-60"
              style={on
                ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent, var(--pb-bg))', borderColor: 'var(--pb-accent)' }
                : { background: 'transparent', color: 'var(--pb-faint)', borderColor: 'var(--pb-hairline, currentColor)' }}>
              {n === 0 ? 'No limit' : n}
            </button>
          )
        })}
      </div>
      <p className="text-pb-faintest text-[10px] mt-1.5 leading-relaxed">
        {cap > 0
          ? `The best ${cap} from each club make the team first. Anyone past that drops below the rest, so you can still swap them in by hand.`
          : 'The best performers on points, whichever club they play for.'}
      </p>
      {least > 1 && (
        <p className="text-pb-faintest text-[10px] mt-1 leading-relaxed" data-testid="totw-cap-floor">
          This round has {clubs} clubs, so a team of {size} needs at least {least} from a club.
          {tooSmall(cap) ? ` A cap of ${cap} cannot be met: the places it leaves are shared out across the clubs in turn.` : ''}
        </p>
      )}
    </div>
  )
}

// The workspace's crest library: every club a pull has named, with the crest a
// post draws. Each crest is fetched once from Cricket Australia with its plain
// background taken off; here a person can pick how it is cut out (plain, on a
// white edge, or the original picture), set
// the club's colour, or put in a crest of their own (cut out in the image
// editor). Nothing here is changed by a later pull. `version` re-reads the list
// after a pull has added clubs; `onChanged` tells the editor to pull again so
// the post shows the change.
// How a kept crest is drawn. Auto picks the white edge for a crest whose dark
// lettering or outline would disappear on a dark post, else the plain cut-out.
const CUT_CHOICES = [
  { key: 'auto', label: 'Auto' },
  { key: 'plain', label: 'Cut out' },
  { key: 'edge', label: 'White edge' },
  { key: 'original', label: 'Original' },
]
const CUT_NOTE = {
  auto: 'Background taken off, chosen for you',
  plain: 'Background taken off',
  edge: 'Background taken off, on a white edge',
  original: 'Original picture',
}
const styleOf = (c) => (!c.useCleaned ? 'original' : (c.cutStyle || 'auto'))

export function CrestLibrary({ version = 0, onChanged }) {
  const [state, setState] = useState({ status: 'loading', crests: [] })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState('')
  const fileRef = useRef(null)
  const pickFor = useRef(null)
  useEffect(() => {
    let live = true
    api.getSocialCrests()
      .then((d) => { if (live) setState({ status: 'ok', crests: d?.crests || [] }) })
      .catch((e) => { if (live) setState({ status: e?.message || 'failed', crests: [] }) })
    return () => { live = false }
  }, [version])
  const src = (u) => (u && u.startsWith('/api/') ? `${BASE_URL}${u.slice(4)}` : u)
  const done = (d) => { setState({ status: 'ok', crests: d?.crests || [] }); setBusy(''); onChanged?.() }
  const fail = (e) => { setBusy(''); setState((s) => ({ ...s, status: e?.message || 'failed' })) }
  const patch = (c, fields) => { setBusy(c.caOrgId); api.patchSocialCrest(c.caOrgId, fields).then(done).catch(fail) }
  const upload = (c, file) => { setBusy(c.caOrgId); return api.uploadSocialCrest(c.caOrgId, file).then(done).catch(fail) }
  const crests = state.crests
  return (
    <div className="pb-card p-4 flex flex-col gap-2" data-testid="crest-library">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center justify-between text-left">
        <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Club crests · {crests.length}</span>
        <span className="font-mono text-[10px] text-pb-faint">{open ? 'Hide' : 'Show'}</span>
      </button>
      <p className="text-pb-faintest text-[10px] leading-relaxed">
        Every club a pull names is kept here with its background taken off, and every post uses it. A later pull never changes your choices. After a change, fetch the link again to put it on the post.
      </p>
      {state.status !== 'ok' && state.status !== 'loading' && <p className="font-mono text-[9px] text-amber-400">✗ {state.status}</p>}
      {open && state.status === 'ok' && !crests.length && (
        <p className="text-pb-faintest text-[11px]">No clubs yet. Pull a round and its clubs come in.</p>
      )}
      {open && crests.map((c) => (
        <div key={c.caOrgId} className="flex items-center gap-3 p-2 rounded border pb-hairline bg-pb-surface2" data-testid="crest-row">
          <div className="w-12 h-12 rounded shrink-0 grid place-items-center" style={{ background: '#11151c' }}>
            <img src={src(c.logo)} alt={c.name} className="max-w-[44px] max-h-[44px] object-contain" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-pb-text text-[12px] truncate">{c.name || 'Club'}</div>
            <div className="font-mono text-[9px] text-pb-faint">
              {c.uploaded ? 'Your crest' : c.cleaned ? (CUT_NOTE[styleOf(c)] || '') : 'As Cricket Australia has it'}
            </div>
            {!c.uploaded && c.cleaned && (
              <div className="flex flex-wrap gap-1 mt-1" role="group" aria-label={`${c.name} crest style`}>
                {CUT_CHOICES.map((o) => {
                  const on = styleOf(c) === o.key
                  return (
                    <button key={o.key} type="button" aria-pressed={on} disabled={busy === c.caOrgId}
                      onClick={() => !on && patch(c, o.key === 'original' ? { use_cleaned: false } : { cut_style: o.key })}
                      data-testid={`crest-style-${o.key}`}
                      className="px-1.5 py-0.5 rounded border font-mono text-[9px]"
                      style={on
                        ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent, var(--pb-bg))', borderColor: 'var(--pb-accent)' }
                        : { color: 'var(--pb-faint)', borderColor: 'var(--pb-hairline, currentColor)' }}>
                      {o.label}
                    </button>
                  )
                })}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <button type="button" disabled={busy === c.caOrgId} onClick={() => setEditing({ crest: c, source: src(c.uploaded || c.original || c.logo) })}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text underline">Edit</button>
              <button type="button" disabled={busy === c.caOrgId} onClick={() => { pickFor.current = c; fileRef.current?.click() }}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text underline">Replace</button>
              {c.uploaded && (
                <button type="button" disabled={busy === c.caOrgId} onClick={() => patch(c, { drop_upload: true })}
                  className="font-mono text-[9px] text-pb-faint hover:text-pb-text underline">Back to Cricket Australia's</button>
              )}
            </div>
          </div>
          <label className="flex flex-col items-center gap-0.5 shrink-0" title={c.colourByHand ? 'Colour set by hand' : 'Colour read from the crest'}>
            <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(c.colour || '') ? c.colour : '#888888'}
              onChange={(e) => patch(c, { colour: e.target.value })} disabled={busy === c.caOrgId}
              className="w-7 h-7 rounded cursor-pointer border-0 bg-transparent p-0" aria-label={`${c.name} colour`} />
            {c.colourByHand
              ? <button type="button" onClick={() => patch(c, { colour: null })} className="font-mono text-[8px] text-pb-faintest underline">auto</button>
              : <span className="font-mono text-[8px] text-pb-faintest">{c.colour ? 'auto' : 'none'}</span>}
          </label>
        </div>
      ))}
      <input ref={fileRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f && pickFor.current) setEditing({ crest: pickFor.current, source: f }) }} />
      <ImageEditorModal open={!!editing} source={editing?.source} title={`Crest · ${editing?.crest?.name || ''}`}
        aspect={null} outputType="image/png" outputName="crest.png" maxOutputSize={600}
        onCancel={() => setEditing(null)}
        onApply={async (file) => { const c = editing.crest; setEditing(null); await upload(c, file) }} />
    </div>
  )
}
