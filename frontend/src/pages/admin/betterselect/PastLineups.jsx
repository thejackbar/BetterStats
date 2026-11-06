// BetterSelect → Past Lineups. Pick a team, then scroll back through the sides it
// has named, newest first. Each game shows its XI in batting order and what
// changed against the game before it (who came in, who dropped out). Tap a
// player to follow them down the timeline.
//
// Reads only: nothing here writes a lineup. Older games load a page at a time as
// the sentinel at the bottom scrolls into view (a button does the same).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { PbSpinner } from '../../../lib/presskit'
import usePersistedState from '../../../lib/usePersistedState'
import { Icon, Btn, Chip, Empty, Tag } from './ui'

const PAGE = 8

const fmtDate = (iso) => {
  if (!iso) return ''
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) } catch { return iso }
}
const yearOf = (iso) => (iso || '').slice(0, 4)
const fmtTime = (t) => (t || '').slice(0, 5)

// A player's name as a button that follows them down the page. Declared at module
// level: inside a render it would remount on every pinned change.
function Who({ p, fmt, pinned, onPin, className = '' }) {
  const on = pinned === p.player_id
  return (
    <button type="button" onClick={() => onPin(on ? null : p.player_id)} data-past-player={p.player_id} aria-pressed={on}
      className={`text-left min-w-0 rounded px-1 -mx-1 transition ${on ? 'bg-pb-accent/20 text-pb-accent font-semibold' : 'hover:bg-pb-surface2'} ${className}`}>
      {fmt(p.display_name)}
    </button>
  )
}

function Changes({ vs, fmt, pinned, onPin }) {
  if (!vs) {
    return <div className="text-[12px] text-pb-faint" data-past-first>First side on record for this team.</div>
  }
  const { added, removed } = vs
  if (!added.length && !removed.length) {
    return <div className="text-[12px] text-pb-faint" data-past-same>Same players as {fmtDate(vs.played_on)}.</div>
  }
  return (
    <div className="flex flex-col gap-1 text-[12.5px]" data-past-changes>
      <div className="text-[11px] font-mono uppercase tracking-wide3 text-pb-faint">Changes since {fmtDate(vs.played_on)}</div>
      {added.length > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5" data-past-in>
          <span className="font-display font-semibold text-pb-accent shrink-0">In</span>
          {added.map((p) => <Who key={p.player_id} p={p} fmt={fmt} pinned={pinned} onPin={onPin} />)}
        </div>
      )}
      {removed.length > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5" data-past-out>
          <span className="font-display font-semibold text-pb-red shrink-0">Out</span>
          {removed.map((p) => <Who key={p.player_id} p={p} fmt={fmt} pinned={pinned} onPin={onPin} />)}
        </div>
      )}
    </div>
  )
}

function GameCard({ e, fmt, pinned, onPin }) {
  const inSide = pinned ? e.players.some((p) => p.player_id === pinned) : true
  const opp = e.opponent_name || e.label
  return (
    <article data-past-card={e.fixture_id} data-past-absent={pinned && !inSide ? '1' : undefined}
      className={`pb-card p-3 sm:p-4 flex flex-col gap-3 transition-opacity ${pinned && !inSide ? 'opacity-60' : ''}`}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="font-display font-semibold text-[15px]">
          {fmtDate(e.played_on)}{e.end_on ? ` to ${fmtDate(e.end_on)}` : ''}
        </h3>
        {e.round && <Tag tone="faint">{e.round}</Tag>}
        {e.locked && <Tag tone="faint" title="This side was locked"><Icon name="lock" size={11} /> Locked</Tag>}
        <span className="flex-1" />
        <Link to={`/admin/betterselect/select/${e.fixture_id}`} className="text-[12px] text-pb-dim hover:text-pb-accent shrink-0" data-past-open>
          Open in Selection
        </Link>
      </header>
      <div className="text-[12.5px] text-pb-dim min-w-0">
        {opp ? <span>{e.home_away === 'AWAY' ? 'at' : 'v'} {opp}</span> : <span>Opponent not recorded</span>}
        {e.venue ? <span className="text-pb-faint"> · {e.venue}</span> : null}
        {e.start_time ? <span className="text-pb-faint"> · {fmtTime(e.start_time)}</span> : null}
      </div>
      {pinned && !inSide && <div className="text-[12px] text-pb-faint" data-past-not-in>Not in this side.</div>}

      <ol className="sm:columns-2 gap-x-6 text-[13.5px]" data-past-xi>
        {e.players.map((p, i) => (
          <li key={p.player_id} className="flex items-baseline gap-2 py-[3px] break-inside-avoid min-w-0">
            <span className="w-5 shrink-0 text-right font-mono text-[11px] text-pb-faint">{p.batting_order || i + 1}</span>
            <Who p={p} fmt={fmt} pinned={pinned} onPin={onPin} className="truncate" />
            {p.is_captain && <span className="shrink-0 font-mono text-[10px] font-semibold text-pb-accent" title="Captain">C</span>}
            {p.is_wicket_keeper && <span className="shrink-0 font-mono text-[10px] font-semibold text-pb-amber" title="Wicket-keeper">WK</span>}
          </li>
        ))}
      </ol>
      <div className="border-t border-pb-hairline pt-2">
        <Changes vs={e.vs_previous} fmt={fmt} pinned={pinned} onPin={onPin} />
      </div>
    </article>
  )
}

export default function PastLineups() {
  const toast = useToast()
  const fmt = useAdminNameFormat()
  const [params, setParams] = useSearchParams()
  const fixtureParam = params.get('fixture')
  const teamParam = params.get('team')
  const [showJuniors] = usePersistedState('select.juniors', false, (v) => typeof v === 'boolean')
  const [lastTeam, setLastTeam] = usePersistedState('select.pastLineups.team', null, (v) => v === null || typeof v === 'string')

  const [teams, setTeams] = useState(null)
  const [selected, setSelected] = useState(teamParam || null)
  const [team, setTeam] = useState(null)          // the picked team's descriptor, from the feed
  const [entries, setEntries] = useState([])
  const [page, setPage] = useState({ total: 0, hasMore: false, next: 0 })
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [pinned, setPinned] = useState(null)
  const seq = useRef(0)
  const sentinel = useRef(null)

  // 1. The teams that have something to look back at.
  useEffect(() => {
    let live = true
    api.bsPastLineupTeams({ hideJuniors: !showJuniors })
      .then((r) => { if (live) setTeams(r.teams || []) })
      .catch((e) => { toast.error(e.message); if (live) setTeams([]) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toast is a new object per render
  }, [showJuniors])

  // 2. Which team: the address (?team=), a fixture's team (?fixture=), the last one
  // looked at, else the top team. Waits for the list so a stale remembered team that
  // no longer has a side is not chosen.
  useEffect(() => {
    if (teams === null || selected) return
    let live = true
    const fallback = () => {
      const keep = teams.find((t) => t.key === lastTeam)
      setSelected((keep || teams[0] || {}).key || null)
    }
    if (fixtureParam) {
      api.bsPastLineups({ fixtureId: fixtureParam, limit: 1, hideJuniors: !showJuniors })
        .then((r) => { if (live) { if (r.team?.key) setSelected(r.team.key); else fallback() } })
        .catch(() => { if (live) fallback() })
    } else {
      fallback()
    }
    return () => { live = false }
  }, [teams, selected, fixtureParam, lastTeam, showJuniors])

  // 3. The first page for the picked team.
  useEffect(() => {
    if (!selected) { setEntries([]); setTeam(null); return }
    const mine = ++seq.current
    setLoading(true); setEntries([]); setPinned(null)
    api.bsPastLineups({ team: selected, limit: PAGE, hideJuniors: !showJuniors })
      .then((r) => {
        if (mine !== seq.current) return
        setTeam(r.team); setEntries(r.entries || [])
        setPage({ total: r.total || 0, hasMore: !!r.has_more, next: r.next_offset || 0 })
      })
      .catch((e) => { if (mine === seq.current) toast.error(e.message) })
      .finally(() => { if (mine === seq.current) setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toast is a new object per render
  }, [selected, showJuniors])

  const loadMore = useCallback(() => {
    if (more || loading || !page.hasMore || !selected) return
    const mine = seq.current
    setMore(true)
    api.bsPastLineups({ team: selected, offset: page.next, limit: PAGE, hideJuniors: !showJuniors })
      .then((r) => {
        if (mine !== seq.current) return
        setEntries((cur) => {
          const seen = new Set(cur.map((x) => x.fixture_id))
          return [...cur, ...(r.entries || []).filter((x) => !seen.has(x.fixture_id))]
        })
        setPage({ total: r.total || 0, hasMore: !!r.has_more, next: r.next_offset || 0 })
      })
      .catch((e) => toast.error(e.message))
      .finally(() => setMore(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toast is a new object per render
  }, [more, loading, page, selected, showJuniors])

  // Scrolling to the bottom brings the next page in.
  useEffect(() => {
    const el = sentinel.current
    if (!el || typeof IntersectionObserver === 'undefined') return undefined
    const io = new IntersectionObserver((hits) => { if (hits.some((h) => h.isIntersecting)) loadMore() }, { rootMargin: '400px' })
    io.observe(el)
    return () => io.disconnect()
  }, [loadMore, entries.length])

  const pick = (key) => {
    setSelected(key); setLastTeam(key)
    setParams({ team: key }, { replace: true })
  }

  const appearances = pinned ? entries.filter((e) => e.players.some((p) => p.player_id === pinned)).length : 0
  const pinnedPlayer = pinned
    ? entries.flatMap((e) => [...e.players, ...(e.vs_previous?.added || []), ...(e.vs_previous?.removed || [])]).find((p) => p.player_id === pinned)
    : null

  let lastYear = null
  return (
    <BetterSelectLayout title="Past Lineups">
      <p className="text-[12.5px] text-pb-faint mb-3 max-w-3xl">
        The sides you confirmed for a team, newest first. Each game shows who came in and who dropped out since the game before. Tap a player to follow them down the page.
      </p>

      {teams === null && <PbSpinner />}
      {teams && teams.length === 0 && (
        <div data-past-none>
          <Empty className="pb-card p-6 text-center">
            No past sides yet. Once you confirm an XI on the Selection board and the game date passes, it shows up here.
          </Empty>
        </div>
      )}

      {teams && teams.length > 0 && (
        <>
          <div className="flex gap-2 overflow-x-auto pb-scroll pb-2 -mx-1 px-1 mb-3" data-past-teams role="tablist" aria-label="Team">
            {teams.map((t) => (
              <Chip key={t.key} label={`${t.name} · ${t.games}`} active={t.key === selected} onClick={() => pick(t.key)} className="shrink-0" />
            ))}
          </div>

          {pinned && (
            <div className="sticky top-0 z-10 mb-3 pb-card px-3 py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]" data-past-following>
              <span className="min-w-0">
                Following <b className="text-pb-accent">{pinnedPlayer ? fmt(pinnedPlayer.display_name) : 'player'}</b>
                {' '}· in {appearances} of the {entries.length} game{entries.length === 1 ? '' : 's'} shown
              </span>
              <span className="flex-1" />
              <Btn sm variant="ghost" icon="close" onClick={() => setPinned(null)} data-past-unfollow>Stop following</Btn>
            </div>
          )}

          {loading && <PbSpinner />}
          {!loading && selected && entries.length === 0 && (
            <Empty className="pb-card p-6 text-center">This team has no saved sides yet.</Empty>
          )}

          <div className="flex flex-col gap-3 max-w-4xl" data-past-list>
            {team && entries.length > 0 && (
              <div className="text-[12px] text-pb-faint" data-past-summary>
                {team.name}: {page.total} game{page.total === 1 ? '' : 's'} on record, showing the latest {entries.length}.
              </div>
            )}
            {entries.map((e) => {
              const y = yearOf(e.played_on)
              const head = y !== lastYear
              lastYear = y
              return (
                <div key={e.fixture_id} className="flex flex-col gap-3">
                  {head && <div className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint pt-1" data-past-year>{y}</div>}
                  <GameCard e={e} fmt={fmt} pinned={pinned} onPin={setPinned} />
                </div>
              )
            })}
            <div ref={sentinel} aria-hidden="true" className="h-px" />
            {more && <PbSpinner />}
            {page.hasMore && !more && (
              <div className="flex justify-center pb-4">
                <Btn variant="soft" icon="history" onClick={loadMore} data-past-more>Load older games</Btn>
              </div>
            )}
            {!page.hasMore && entries.length > 0 && !loading && (
              <div className="text-center text-[12px] text-pb-faint pb-4" data-past-end>That is every side on record for this team.</div>
            )}
          </div>
        </>
      )}
    </BetterSelectLayout>
  )
}
