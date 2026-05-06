import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

function PlayerSearch({ players, selected, onSelect, label }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return players.slice(0, 20)
    return players.filter(p => p.name.toLowerCase().includes(q)).slice(0, 20)
  }, [players, query])

  return (
    <div className="relative">
      <label className="section-label mb-2 block">{label}</label>
      <div className="relative">
        {selected ? (
          <div className="flex items-center gap-2 bg-navy-800 border border-accent/40 rounded-lg px-3 py-2">
            <span className="text-white flex-1">{selected.name}</span>
            <button onClick={() => { onSelect(null); setQuery('') }} className="text-slate-500 hover:text-white">×</button>
          </div>
        ) : (
          <>
            <div className="relative">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder={`Search ${label.toLowerCase()}…`}
                value={query}
                onChange={e => { setQuery(e.target.value); setOpen(true) }}
                onFocus={() => setOpen(true)}
                onBlur={() => setTimeout(() => setOpen(false), 150)}
                className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
              />
            </div>
            {open && filtered.length > 0 && (
              <div className="absolute z-20 w-full mt-1 bg-navy-800 border border-navy-600 rounded-lg shadow-xl max-h-60 overflow-y-auto">
                {filtered.map(p => (
                  <button
                    key={p.id}
                    onMouseDown={() => { onSelect(p); setQuery(''); setOpen(false) }}
                    className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-navy-700 hover:text-white transition-colors"
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const BATTING_METRICS = [
  { key: 'innings', label: 'Innings', higher: true },
  { key: 'total_runs', label: 'Career Runs', higher: true },
  { key: 'average', label: 'Batting Average', higher: true },
  { key: 'strike_rate', label: 'Strike Rate', higher: true },
  { key: 'high_score', label: 'Highest Score', higher: true },
  { key: 'fifties', label: 'Fifties', higher: true },
  { key: 'hundreds', label: 'Hundreds', higher: true },
  { key: 'total_sixes', label: 'Sixes', higher: true },
  { key: 'total_fours', label: 'Fours', higher: true },
  { key: 'ducks', label: 'Ducks', higher: false },
]

const BOWLING_METRICS = [
  { key: 'total_wickets', label: 'Career Wickets', higher: true },
  { key: 'average', label: 'Bowling Average', higher: false },
  { key: 'economy', label: 'Economy Rate', higher: false },
  { key: 'best_figures_wickets', label: 'Best Spell', higher: true },
  { key: 'five_fors', label: 'Five-fors', higher: true },
  { key: 'total_maidens', label: 'Maidens', higher: true },
]

const FIELDING_METRICS = [
  { key: 'total_catches', label: 'Catches', higher: true },
  { key: 'total_run_outs', label: 'Run Outs', higher: true },
  { key: 'total_stumpings', label: 'Stumpings', higher: true },
  { key: 'total_dismissals', label: 'Total Dismissals', higher: true },
]

function CompareRow({ label, v1, v2, higher }) {
  const n1 = parseFloat(v1)
  const n2 = parseFloat(v2)
  const bothValid = !isNaN(n1) && !isNaN(n2) && v1 != null && v2 != null

  let p1win = false
  let p2win = false
  if (bothValid && n1 !== n2) {
    if (higher) {
      p1win = n1 > n2
      p2win = n2 > n1
    } else {
      p1win = n1 < n2
      p2win = n2 < n1
    }
  }

  return (
    <tr className="border-b border-navy-700/50">
      <td className={clsx(
        'px-4 py-3 text-center stat-number font-bold',
        p1win ? 'text-green-400 bg-green-400/10' : 'text-white'
      )}>
        {v1 ?? '—'}
      </td>
      <td className="px-4 py-3 text-center text-xs text-slate-400 font-medium uppercase tracking-wider bg-navy-800/50">
        {label}
      </td>
      <td className={clsx(
        'px-4 py-3 text-center stat-number font-bold',
        p2win ? 'text-green-400 bg-green-400/10' : 'text-white'
      )}>
        {v2 ?? '—'}
      </td>
    </tr>
  )
}

function SectionHeader({ label }) {
  return (
    <tr>
      <td colSpan={3} className="px-4 py-2 text-xs uppercase tracking-widest text-slate-500 font-medium bg-navy-800/80 border-b border-navy-700">
        {label}
      </td>
    </tr>
  )
}

export default function PlayerComparison() {
  const { orgId } = useParams()
  const [players, setPlayers] = useState([])
  const [player1, setPlayer1] = useState(null)
  const [player2, setPlayer2] = useState(null)
  const [stats1, setStats1] = useState(null)
  const [stats2, setStats2] = useState(null)
  const [bat1, setBat1] = useState(null)
  const [bat2, setBat2] = useState(null)
  const [bowl1, setBowl1] = useState(null)
  const [bowl2, setBowl2] = useState(null)
  const [field1, setField1] = useState(null)
  const [field2, setField2] = useState(null)
  const [loading1, setLoading1] = useState(false)
  const [loading2, setLoading2] = useState(false)

  useEffect(() => {
    if (!orgId) return
    api.listPlayers(orgId).then(setPlayers).catch(() => setPlayers([]))
  }, [orgId])

  useEffect(() => {
    if (!player1) { setStats1(null); setBat1(null); setBowl1(null); setField1(null); return }
    setLoading1(true)
    api.getPlayerStats(player1.id).then(data => {
      setBat1(data.career_batting || {})
      setBowl1(data.career_bowling || {})
      setField1(data.career_fielding || {})
    }).catch(() => {}).finally(() => setLoading1(false))
  }, [player1])

  useEffect(() => {
    if (!player2) { setStats2(null); setBat2(null); setBowl2(null); setField2(null); return }
    setLoading2(true)
    api.getPlayerStats(player2.id).then(data => {
      setBat2(data.career_batting || {})
      setBowl2(data.career_bowling || {})
      setField2(data.career_fielding || {})
    }).catch(() => {}).finally(() => setLoading2(false))
  }, [player2])

  const showComparison = player1 && player2

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="display-heading text-4xl md:text-5xl text-white">COMPARE PLAYERS</h1>
          <Link to={`/dashboard/${orgId}`} className="btn-ghost border border-navy-600 text-sm">← Dashboard</Link>
        </div>
      </div>

      {/* Player pickers */}
      <div className="grid md:grid-cols-2 gap-4 mb-8">
        <PlayerSearch players={players} selected={player1} onSelect={setPlayer1} label="Player 1" />
        <PlayerSearch players={players} selected={player2} onSelect={setPlayer2} label="Player 2" />
      </div>

      {!showComparison && (
        <div className="card p-12 text-center">
          <p className="text-slate-500 text-lg">Select two players above to compare their stats</p>
          <p className="text-slate-600 text-sm mt-2">Green highlights show the superior stat</p>
        </div>
      )}

      {showComparison && (loading1 || loading2) && <LoadingSpinner message="Loading stats…" />}

      {showComparison && !loading1 && !loading2 && bat1 && bat2 && (
        <>
          {/* Header */}
          <div className="grid grid-cols-3 gap-0 mb-0">
            <Link to={`/players/${player1.id}`} className="card rounded-b-none border-b-0 p-4 text-center hover:border-accent/50 transition-colors">
              <div className="display-heading text-lg text-white">{player1.name}</div>
              <div className="text-xs text-slate-500 mt-0.5">Player 1</div>
            </Link>
            <div className="flex items-center justify-center">
              <span className="text-slate-600 font-display font-bold text-sm uppercase tracking-widest">vs</span>
            </div>
            <Link to={`/players/${player2.id}`} className="card rounded-b-none border-b-0 p-4 text-center hover:border-accent/50 transition-colors">
              <div className="display-heading text-lg text-white">{player2.name}</div>
              <div className="text-xs text-slate-500 mt-0.5">Player 2</div>
            </Link>
          </div>

          {/* Comparison table */}
          <div className="card rounded-t-none border-t-0 overflow-hidden">
            <table className="w-full">
              <tbody>
                <SectionHeader label="Batting" />
                {BATTING_METRICS.map(m => (
                  <CompareRow
                    key={m.key}
                    label={m.label}
                    v1={bat1[m.key]}
                    v2={bat2[m.key]}
                    higher={m.higher}
                  />
                ))}
                <SectionHeader label="Bowling" />
                {BOWLING_METRICS.map(m => (
                  <CompareRow
                    key={m.key}
                    label={m.label}
                    v1={bowl1?.[m.key]}
                    v2={bowl2?.[m.key]}
                    higher={m.higher}
                  />
                ))}
                <SectionHeader label="Fielding" />
                {FIELDING_METRICS.map(m => (
                  <CompareRow
                    key={m.key}
                    label={m.label}
                    v1={field1?.[m.key]}
                    v2={field2?.[m.key]}
                    higher={m.higher}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-center text-slate-600 text-xs mt-3">
            Green = superior stat · Career totals shown
          </p>
        </>
      )}
    </div>
  )
}
