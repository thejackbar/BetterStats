import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { rollupSeasons } from '../lib/seasonRollup'
import { bowlingLabel, BAT_HANDS } from '../lib/watchlistOptions'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PLAYER_COLORS, PlayerAvatar, getRowHighlights } from '../components/ScoutUi'
import { Btn, Segmented } from '../../pages/admin/betterselect/ui'

const MAX_PLAYERS = 5

const WINDOW_PRESETS = [
  { key: 'all', label: 'All time' },
  { key: 'season', label: 'This season' },
  { key: 'last_season', label: 'Last season' },
  { key: 'last2', label: 'Last 2 seasons' },
  { key: 'last5', label: 'Last 5 seasons' },
]

function windowLabel(key) {
  return (WINDOW_PRESETS.find((w) => w.key === key) || WINDOW_PRESETS[0]).label.toUpperCase()
}

function sliceForWindow(seasons, key) {
  const sorted = [...(seasons || [])].sort((a, b) => (b.year || 0) - (a.year || 0))
  if (key === 'season') return sorted.slice(0, 1)
  if (key === 'last_season') return sorted.slice(1, 2)
  if (key === 'last2') return sorted.slice(0, 2)
  if (key === 'last5') return sorted.slice(0, 5)
  return sorted
}

const TABS = [
  { id: 'batting', label: 'BATTING' },
  { id: 'bowling', label: 'BOWLING' },
  { id: 'fielding', label: 'FIELDING' },
  { id: 'career', label: 'CAREER' },
  { id: 'recruiting', label: 'RECRUITING' },
]

const METRICS = {
  batting: [
    ['innings', 'Innings', true],
    ['runs', 'Runs', true],
    ['average', 'Average', true],
    ['strike_rate', 'Strike rate', true],
    ['high_score', 'High score', true],
    ['fifties', '50s', true],
    ['hundreds', '100s', true],
    ['ducks', 'Ducks', false],
  ],
  bowling: [
    ['wickets', 'Wickets', true],
    ['overs', 'Overs', true],
    ['economy', 'Economy', false],
    ['bowling_average', 'Bowling avg', false],
    ['best', 'Best figures', true],
    ['five_fors', '5-fors', true],
    ['maidens', 'Maidens', true],
  ],
  fielding: [
    ['catches', 'Catches', true],
    ['catches_wk', 'Wk catches', true],
    ['stumpings', 'Stumpings', true],
    ['run_outs', 'Run outs', true],
  ],
  career: [
    ['matches', 'Matches', true],
    ['runs', 'Runs', true],
    ['wickets', 'Wickets', true],
    ['catches', 'Catches', true],
    ['fifties', '50s', true],
    ['hundreds', '100s', true],
    ['five_fors', '5-fors', true],
  ],
}

const RECRUITING_FIELDS = [
  ['visa_status', 'Visa / eligibility'],
  ['transfer_preference', 'Transfer preference'],
  ['availability_window', 'Availability'],
  ['fee_expectations', 'Fee expectations'],
  ['agent_contact', 'Agent / contact'],
]

function batHandLabel(code) {
  const found = BAT_HANDS.find(([c]) => c === code)
  return found ? found[1] : null
}

export default function ScoutCompare() {
  const [params, setParams] = useSearchParams()
  const [allPlayers, setAllPlayers] = useState(undefined)
  const [comparison, setComparison] = useState(undefined)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('batting')
  const [windowKey, setWindowKey] = useState('all')
  const [shareState, setShareState] = useState(null) // { url } | { error }
  const [sharing, setSharing] = useState(false)

  const selectedIds = useMemo(() => (params.get('players') || '').split(',').filter(Boolean), [params])

  useEffect(() => { scoutApi.listPlayers().then(setAllPlayers).catch((err) => setError(err.message)) }, [])

  useEffect(() => {
    if (selectedIds.length === 0) { setComparison({ players: [] }); return }
    scoutApi.getComparison(selectedIds).then(setComparison).catch((err) => setError(err.message))
  }, [selectedIds.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (id) => {
    const set = new Set(selectedIds)
    if (set.has(id)) set.delete(id)
    else if (set.size < MAX_PLAYERS) set.add(id)
    const next = [...set]
    setShareState(null)
    setParams(next.length ? { players: next.join(',') } : {})
  }

  const players = comparison?.players || []
  const hasEnough = players.length >= 2

  const windowedByPlayer = useMemo(() => {
    const map = {}
    for (const p of players) map[p.id] = rollupSeasons(sliceForWindow(p.stats?.seasons, windowKey))
    return map
  }, [players, windowKey])

  const share = async () => {
    setSharing(true)
    setShareState(null)
    try {
      const res = await scoutApi.shareComparison(selectedIds)
      const url = `${window.location.origin}/betterscout/share-compare/${res.share_token}`
      setShareState({ url })
    } catch (err) {
      setShareState({ error: err.message })
    } finally {
      setSharing(false)
    }
  }

  return (
    <ScoutModuleLayout
      title="Compare players"
      caption={`Up to ${MAX_PLAYERS} players · window presets are season-based only. BetterScout has season rollups, not ball-by-ball`}
      actions={hasEnough ? (
        <>
          <Btn onClick={() => window.print()}>Export as one-page PDF</Btn>
          <Btn variant="primary" onClick={share} disabled={sharing}>{sharing ? 'Sharing…' : 'Share read-only link'}</Btn>
        </>
      ) : null}
    >
      <style>{`
        @media print {
          .scout-no-print { display: none !important; }
          .scout-print-area { box-shadow: none !important; }
          body { background: white !important; }
        }
      `}</style>

      {error && <p className="text-sm text-pb-red mb-4">{error}</p>}

      <div className="pb-card p-4 mb-4 scout-no-print">
        <div className="flex flex-wrap items-center gap-2">
          {(allPlayers || []).map((p) => {
            const active = selectedIds.includes(p.id)
            const disabled = !active && selectedIds.length >= MAX_PLAYERS
            return (
              <button
                key={p.id} onClick={() => toggle(p.id)} disabled={disabled}
                className="text-sm px-3 py-1.5 rounded-full border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                style={active
                  ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }
                  : { borderColor: 'var(--pb-hairline2)' }}
              >
                {p.name}
              </button>
            )
          })}
          {allPlayers && allPlayers.length === 0 && (
            <p className="text-sm text-pb-faint">
              Nobody tracked yet. <Link to="/betterscout/app/discover" className="underline" style={{ color: 'var(--pb-accent)' }}>discover a player</Link> to get started.
            </p>
          )}
        </div>
        {selectedIds.length === 1 && <p className="text-xs text-pb-faint mt-2">Add at least one more player to compare.</p>}
      </div>

      {shareState?.url && (
        <div className="pb-card px-4 py-3 mb-4 flex items-center gap-3 scout-no-print">
          <input readOnly value={shareState.url} onFocus={(e) => e.target.select()} className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-2.5 py-1.5 text-xs font-mono" />
          <button onClick={() => navigator.clipboard?.writeText(shareState.url)} className="text-xs px-2.5 py-1.5 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text whitespace-nowrap">Copy</button>
        </div>
      )}
      {shareState?.error && <p className="text-sm text-pb-red mb-4 scout-no-print">{shareState.error}</p>}

      {!hasEnough && (
        <div className="pb-card py-12 text-center scout-no-print">
          <p className="text-pb-faint text-sm">
            {selectedIds.length === 0 ? 'Pick at least 2 players to start comparing.' : 'Pick one more player to start comparing.'}
          </p>
        </div>
      )}

      {hasEnough && (
        <div className="scout-print-area space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3 scout-no-print">
            <Segmented value={windowKey} onChange={setWindowKey} options={WINDOW_PRESETS.map((w) => ({ value: w.key, label: w.label }))} />
          </div>

          <div className="pb-card overflow-hidden">
            <div className="flex overflow-x-auto scout-no-print" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
              {TABS.map((tab) => (
                <button
                  key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`font-mono text-[11px] tracking-wide2 px-5 py-3 transition-colors ${activeTab === tab.id ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'}`}
                  style={activeTab === tab.id ? { borderBottom: '2px solid var(--pb-accent)', marginBottom: '-1px' } : { borderBottom: '2px solid transparent', marginBottom: '-1px' }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full" style={{ tableLayout: 'fixed', minWidth: `${110 + players.length * 140}px` }}>
                <colgroup>
                  <col style={{ width: '130px' }} />
                  {players.map((_, i) => <col key={i} />)}
                </colgroup>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
                    <th className="py-4 pl-4 text-left align-bottom">
                      <span className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Stat</span>
                    </th>
                    {players.map((p, idx) => {
                      const bowl = bowlingLabel(p.bowling_action, p.bowling_type)
                      const chips = [p.role, batHandLabel(p.batting_hand), bowl && bowl !== '—' ? bowl : null].filter(Boolean)
                      return (
                        <th key={p.id} className="py-4 px-3 text-center align-bottom" style={{ borderLeft: '1px solid var(--pb-hairline)' }}>
                          <div className="flex flex-col items-center gap-1.5">
                            <PlayerAvatar name={p.name} photoUrl={p.photo_url} size={42} ringColor={PLAYER_COLORS[idx % PLAYER_COLORS.length]} />
                            <Link to={`/betterscout/app/players/${p.id}`} className="font-semibold text-xs leading-tight hover:opacity-75 block" style={{ color: PLAYER_COLORS[idx % PLAYER_COLORS.length] }}>
                              {p.name}
                            </Link>
                            <span className="font-mono text-[9px] text-pb-faint uppercase truncate max-w-[110px]">{p.club_name || '—'}</span>
                            {chips.length > 0 && <span className="text-[9.5px] text-pb-faintest leading-tight">{chips.join(' · ')}</span>}
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {activeTab !== 'recruiting' && METRICS[activeTab].map(([key, label, higher], rowIdx) => {
                    const values = players.map((p) => windowedByPlayer[p.id]?.[key])
                    const highlights = getRowHighlights(values, higher)
                    return (
                      <tr key={key} style={rowIdx > 0 ? { borderTop: '1px solid var(--pb-hairline)' } : {}}>
                        <td className="py-3 pl-4 align-middle"><span className="font-mono text-[10px] tracking-wide text-pb-faint">{label}</span></td>
                        {players.map((p, i) => {
                          const v = values[i]
                          const h = highlights[i]
                          return (
                            <td key={p.id} className="py-3 px-3 text-center align-middle" style={{
                              borderLeft: '1px solid var(--pb-hairline)',
                              background: h === 'best' ? 'rgba(34,197,94,0.14)' : h === 'worst' ? 'rgba(239,68,68,0.14)' : undefined,
                            }}>
                              <span className="font-mono text-[14px] font-bold" style={{
                                color: h === 'best' ? '#86efac' : h === 'worst' ? '#fca5a5' : v != null ? 'var(--pb-text)' : 'var(--pb-faintest)',
                              }}>
                                {v ?? '—'}
                              </span>
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}

                  {activeTab === 'recruiting' && (
                    <>
                      <tr className="scout-no-print">
                        <td colSpan={players.length + 1} className="px-4 py-2 text-xs text-pb-faint bg-pb-surface2">
                          Internal only: never leaves the org on a share link.
                        </td>
                      </tr>
                      {RECRUITING_FIELDS.map(([key, label], rowIdx) => (
                        <tr key={key} style={rowIdx > 0 ? { borderTop: '1px solid var(--pb-hairline)' } : {}}>
                          <td className="py-3 pl-4 align-middle"><span className="font-mono text-[10px] tracking-wide text-pb-faint">{label}</span></td>
                          {players.map((p) => (
                            <td key={p.id} className="py-3 px-3 text-center align-middle text-sm" style={{ borderLeft: '1px solid var(--pb-hairline)' }}>
                              {p.recruiting?.[key] || <span className="text-pb-faintest">—</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-center text-pb-faintest font-mono text-[10px] tracking-wide2 scout-no-print">
            GREEN = BEST · RED = WORST · {windowLabel(windowKey)}
          </p>
        </div>
      )}
    </ScoutModuleLayout>
  )
}
