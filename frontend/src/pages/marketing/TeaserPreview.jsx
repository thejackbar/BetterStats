import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { getVisitorId } from '../../lib/visitor'
import brandWhite from '../../assets/bettercricket-white.svg'
import { SUPPORT_EMAIL } from '../../data/marketing'

// A prospect club's own season, built from Cricket Australia's public figures
// and reached by a link we emailed them (or an ad). It exists to make one thing
// easy: TAP ANYTHING and you are invited to claim the club through the trial
// wizard. Every tile is therefore a button, and every button opens the same
// sheet.
//
// What it leads with is decided server side (club_teaser.presentation): an
// individual's numbers first, because those are always something to be proud
// of, and the season record and ladder only where they flatter. A club at the
// foot of its ladder is not shown the foot of its ladder as the hook.
//
// Forced dark (its own data-theme wrapper), mobile first: the email and the ads
// this is reached from are opened on a phone.

const SHEET_ID = 'teaser-claim-sheet'
const PREVIEW_ROWS = 3   // rows shown in full; the rest are dimmed, claiming unlocks them

function fmtNum(n) {
  return Number(n || 0).toLocaleString()
}

function setRobots(content) {
  let el = document.querySelector('meta[name="robots"]#teaser-robots')
  if (!el) {
    document.querySelectorAll('meta[name="robots"]').forEach((m) => m.remove())
    el = document.createElement('meta')
    el.name = 'robots'
    el.id = 'teaser-robots'
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

// A tile. Always a button: the whole card is the invitation.
function Tile({ section, title, onTap, children, footer = 'See every player and every season' }) {
  return (
    <button type="button" data-tile={section} onClick={() => onTap(section)}
            className="group w-full text-left rounded-2xl border border-pb-hairline bg-pb-surface p-4 sm:p-5 transition-colors hover:border-accent focus-visible:outline-none focus-visible:border-accent">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-pb-dim">{title}</h2>
      </div>
      {children}
      <div className="mt-3 pt-3 border-t border-pb-hairline text-xs font-semibold text-accent flex items-center gap-1.5">
        <span>{footer}</span>
        <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">→</span>
      </div>
    </button>
  )
}

function Row({ n, name, main, sub, dim }) {
  return (
    <li className={`flex items-baseline gap-3 py-1.5 ${dim ? 'opacity-45' : ''}`}>
      <span className="w-4 shrink-0 text-xs font-mono text-pb-dim tabular-nums">{n}</span>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-pb-text">{name}</span>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-pb-text">{main}</span>
      <span className="shrink-0 w-24 text-right text-xs text-pb-dim tabular-nums">{sub}</span>
    </li>
  )
}

function List({ rows }) {
  return (
    <ol>
      {rows.slice(0, 5).map((r, i) => <Row key={r.name + i} n={i + 1} dim={i >= PREVIEW_ROWS} {...r} />)}
    </ol>
  )
}

export default function TeaserPreview() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)      // null loading, false = not found
  const [sheet, setSheet] = useState(false)
  const viewed = useRef(false)
  const primaryRef = useRef(null)
  const lastFocus = useRef(null)

  useEffect(() => {
    let alive = true
    api.publicTeaser(token)
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(false) })
    return () => { alive = false }
  }, [token])

  const name = data?.club?.name || 'Your club'
  const seasonName = data?.season?.name || 'this season'

  useEffect(() => {
    if (!data) return
    document.title = `${name}: your ${seasonName} | BetterCricket`
    setRobots('noindex, nofollow')
    if (viewed.current) return
    viewed.current = true
    api.publicTeaserEvent(token, 'view', null, getVisitorId()).catch(() => {})
    if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
      window.fbq('track', 'ViewContent', { content_name: 'Club teaser page', content_category: 'club_teaser' })
    }
  }, [data, name, seasonName, token])

  const openSheet = (section) => {
    lastFocus.current = document.activeElement
    api.publicTeaserEvent(token, section ? 'tile' : 'claim_open', section || 'header', getVisitorId()).catch(() => {})
    if (section) api.publicTeaserEvent(token, 'claim_open', section, getVisitorId()).catch(() => {})
    setSheet(true)
  }
  const closeSheet = () => {
    setSheet(false)
    lastFocus.current?.focus?.()
  }

  useEffect(() => {
    if (!sheet) return undefined
    const onKey = (e) => { if (e.key === 'Escape') closeSheet() }
    document.addEventListener('keydown', onKey)
    primaryRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [sheet])

  const registered = data?.registered
  const goClaim = () => {
    api.publicTeaserEvent(token, 'claim_go', null, getVisitorId()).catch(() => {})
    navigate(registered ? `/${registered.slug}` : `/trial?teaser=${encodeURIComponent(token)}`)
  }

  const batting = useMemo(() => (data?.batting || []).map((b) => ({
    name: b.name, main: `${fmtNum(b.runs)} runs`,
    sub: b.average != null ? `avg ${b.average}` : '',
  })), [data])
  const bowling = useMemo(() => (data?.bowling || []).map((b) => ({
    name: b.name, main: `${fmtNum(b.wickets)} wkts`,
    sub: b.best ? `best ${b.best}` : (b.average != null ? `avg ${b.average}` : ''),
  })), [data])
  const fielding = useMemo(() => (data?.fielding || []).map((f) => ({
    name: f.name, main: `${f.catches} catches`,
    sub: [f.stumpings ? `${f.stumpings} st` : '', f.run_outs ? `${f.run_outs} ro` : ''].filter(Boolean).join(' · '),
  })), [data])

  if (data === null) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text" data-theme="dark">
        <div className="max-w-[720px] mx-auto px-4 pt-16 space-y-3" aria-busy="true" data-testid="teaser-loading">
          {[120, 220, 160].map((h) => <div key={h} className="rounded-2xl bg-pb-surface animate-pulse" style={{ height: h }} />)}
        </div>
      </div>
    )
  }
  if (data === false) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-6" data-theme="dark">
        <div className="max-w-sm text-center" data-testid="teaser-missing">
          <img src={brandWhite} alt="BetterCricket" className="h-8 mx-auto mb-6" />
          <h1 className="text-xl font-semibold mb-2">This link is not valid any more</h1>
          <p className="text-sm text-pb-dim mb-5">
            It may have been copied wrongly. You can still find your club and start a free trial.
          </p>
          <Link to="/trial" className="inline-block rounded-lg bg-accent text-[#08110b] px-4 py-2.5 text-sm font-semibold">Find your club</Link>
        </div>
      </div>
    )
  }

  const { hero, record, ladders_shown: ladders, club, history } = data
  const place = [club.suburb, club.state].filter(Boolean).join(', ')
  const ctaLabel = registered ? `Open ${name}'s site` : `Claim ${name} free`
  const seasonsBack = history?.seasons_listed > 1 && history?.first_year ? history.first_year : null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text pb-28" data-theme="dark" data-testid="teaser-page">
      <header className="border-b border-pb-hairline">
        <div className="max-w-[720px] mx-auto px-4 h-14 flex items-center justify-between gap-3">
          <img src={brandWhite} alt="BetterCricket" className="h-6 w-auto" />
          <button type="button" data-testid="teaser-header-cta" onClick={() => openSheet(null)}
                  className="rounded-lg border border-accent/50 bg-accent/10 text-accent px-3 py-1.5 text-xs font-semibold hover:bg-accent/20">
            {registered ? 'Open your site' : 'Claim your club'}
          </button>
        </div>
      </header>

      <main className="max-w-[720px] mx-auto px-4 pt-7 sm:pt-10">
        <p className="text-[11px] font-mono uppercase tracking-[0.16em] text-accent mb-2">{seasonName}</p>
        <h1 className="text-3xl sm:text-4xl font-bold leading-tight tracking-tight" data-testid="teaser-club">{name}</h1>
        <p className="mt-1.5 text-sm text-pb-dim">
          {[place, club.association].filter(Boolean).join(' · ')}
        </p>

        {registered && (
          <div className="mt-5 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm" data-testid="teaser-registered">
            {name} is already on BetterCricket. <Link className="font-semibold underline" to={`/${registered.slug}`}>Open the club's site</Link>.
          </div>
        )}

        {hero && (
          <button type="button" data-tile="hero" onClick={() => openSheet('hero')}
                  className="group mt-6 w-full text-left rounded-3xl border border-accent/30 p-5 sm:p-7 transition-colors hover:border-accent focus-visible:outline-none focus-visible:border-accent"
                  style={{ background: 'linear-gradient(140deg, color-mix(in srgb, var(--pb-accent) 16%, var(--pb-surface)) 0%, var(--pb-surface) 70%)' }}>
            <span className="text-[11px] font-mono uppercase tracking-[0.14em] text-pb-dim">
              {hero.kind === 'runs' ? 'Top run-scorer' : 'Leading wicket-taker'}
            </span>
            <span className="mt-2 flex items-end gap-2.5">
              <span className="text-6xl sm:text-7xl font-bold leading-none tabular-nums" data-testid="teaser-hero-value">{fmtNum(hero.value)}</span>
              <span className="pb-1.5 text-lg text-pb-dim">{hero.unit}</span>
            </span>
            <span className="mt-3 block text-lg font-semibold" data-testid="teaser-hero-player">{hero.player}</span>
            {hero.detail && <span className="mt-0.5 block text-sm text-pb-dim">{hero.detail}</span>}
            <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
              Their whole career is on the club's own site <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">→</span>
            </span>
          </button>
        )}

        <div className="mt-4 grid gap-4">
          {record && (
            <Tile onTap={openSheet} section="record" title="The season" footer="Every result, every round">
              <div className="grid grid-cols-3 gap-3 text-center" data-testid="teaser-record">
                {[['Played', record.played], ['Won', record.won], ['Lost', record.lost]].map(([l, v]) => (
                  <div key={l} className="rounded-xl bg-pb-surface2 py-3">
                    <div className="text-2xl font-bold tabular-nums">{fmtNum(v)}</div>
                    <div className="text-[11px] font-mono uppercase tracking-wider text-pb-dim">{l}</div>
                  </div>
                ))}
              </div>
            </Tile>
          )}
          {ladders?.length > 0 && (
            <Tile onTap={openSheet} section="ladder" title="On the ladder" footer="Full ladders and every fixture">
              <ul data-testid="teaser-ladders">
                {ladders.map((l) => (
                  <li key={l.grade} className="flex items-baseline justify-between gap-3 py-1.5">
                    <span className="min-w-0 truncate text-sm font-medium">{l.grade}</span>
                    <span className="shrink-0 text-sm tabular-nums">
                      <strong className="font-semibold">{l.place}</strong>
                      <span className="text-pb-dim"> of {l.teams}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Tile>
          )}
          {batting.length > 0 && <Tile onTap={openSheet} section="batting" title="Batting"><List rows={batting} /></Tile>}
          {bowling.length > 0 && <Tile onTap={openSheet} section="bowling" title="Bowling"><List rows={bowling} /></Tile>}
          {fielding.length > 0 && <Tile onTap={openSheet} section="fielding" title="Fielding"><List rows={fielding} /></Tile>}
          {data.records?.length > 0 && (
            <Tile onTap={openSheet} section="records" title="Season best" footer="All-time records and honour boards">
              <ul>
                {data.records.map((r) => (
                  <li key={r.label} className="flex items-baseline justify-between gap-3 py-1.5">
                    <span className="min-w-0 flex-1 truncate text-sm">{r.label}</span>
                    <span className="shrink-0 text-sm font-semibold tabular-nums">{r.value}</span>
                    <span className="shrink-0 w-24 text-right text-xs text-pb-dim truncate">{r.player}</span>
                  </li>
                ))}
              </ul>
            </Tile>
          )}
        </div>

        <p className="mt-8 text-xs text-pb-dim leading-relaxed">
          These figures come from Cricket Australia's public match data for {seasonName}. Something not right?{' '}
          <a className="underline" href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(`${name} teaser page`)}`}>Tell us</a>.
        </p>
      </main>

      <div className="fixed bottom-0 inset-x-0 z-30 border-t border-pb-hairline bg-[color-mix(in_srgb,var(--pb-bg)_95%,transparent)] backdrop-blur">
        <div className="max-w-[720px] mx-auto px-4 py-3 flex items-center gap-3">
          <p className="hidden sm:block flex-1 text-sm text-pb-dim">
            {registered ? 'Already set up.' : 'Free, about 3 minutes, no card.'}
          </p>
          <button type="button" data-testid="teaser-bar-cta" onClick={() => openSheet(null)}
                  className="flex-1 sm:flex-none rounded-xl bg-accent text-[#08110b] px-5 py-3 text-sm font-semibold hover:opacity-90">
            {ctaLabel}
          </button>
        </div>
      </div>

      {sheet && (
        <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center" role="presentation">
          <div className="absolute inset-0 bg-black/60" onClick={closeSheet} data-testid="teaser-sheet-backdrop" />
          <div id={SHEET_ID} role="dialog" aria-modal="true" aria-labelledby="teaser-sheet-title" data-testid="teaser-sheet"
               className="relative w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl border border-pb-hairline bg-pb-surface p-6 shadow-2xl">
            <h2 id="teaser-sheet-title" className="text-xl font-bold leading-snug">
              {registered ? `${name} is already on BetterCricket` : `This is ${name}'s season. Make it yours.`}
            </h2>
            {registered ? (
              <p className="mt-2 text-sm text-pb-dim">Open the club's own site to see every player, record and result.</p>
            ) : (
              <ul className="mt-3 space-y-2 text-sm text-pb-dim">
                {seasonsBack && <li>Every player's career, back to {seasonsBack}.</li>}
                <li>Leaderboards, records and a club website that update after every match.</li>
                <li>Free trial, no card, about 3 minutes to set up.</li>
              </ul>
            )}
            <div className="mt-5 flex flex-col gap-2">
              <button ref={primaryRef} type="button" data-testid="teaser-sheet-go" onClick={goClaim}
                      className="rounded-xl bg-accent text-[#08110b] px-5 py-3 text-sm font-semibold hover:opacity-90">
                {ctaLabel}
              </button>
              <button type="button" data-testid="teaser-sheet-close" onClick={closeSheet}
                      className="rounded-xl px-5 py-2.5 text-sm text-pb-dim hover:text-pb-text">
                Not now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
