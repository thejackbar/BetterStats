// Search an online library of open-licence icons and pick one for a post.
//
// The club's server does the searching (see services/icon_library.py), so the
// picture a post keeps is a data URI from our own origin: it exports, it does not
// depend on the library being up again, and a saved template keeps it.
//
// Props:
//   onPick({ id, name, dataUri, coloured }) — called once the SVG is in hand
//   accent   hex of the club accent, offered as a colour for single-colour icons
//   dark     true when the post surface is dark (so "ink" defaults to white)
import { useEffect, useRef, useState } from 'react'
import { api } from '../../../lib/api'

const TOPICS = ['Halloween', 'Golf', 'Trophy', 'Food', 'Beer', 'Music', 'Cricket', 'Party', 'Quiz', 'Kids', 'Meeting', 'Raffle']

export default function IconSearch({ onPick, accent = '#f0b000', dark = true }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)   // null = nothing searched yet
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [color, setColor] = useState(dark ? '#ffffff' : '#111111')
  const [picking, setPicking] = useState('')
  const seq = useRef(0)

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults(null); setError(''); setLoading(false); return undefined }
    const mine = ++seq.current
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const r = await api.searchIcons(term)
        if (seq.current !== mine) return
        setResults(r.icons || []); setError('')
      } catch (e) {
        if (seq.current !== mine) return
        setResults([]); setError(e?.message || 'Could not search the icon library.')
      } finally {
        if (seq.current === mine) setLoading(false)
      }
    }, 350)
    return () => clearTimeout(t)
  }, [q])

  const pick = async (icon) => {
    setPicking(icon.id); setError('')
    try {
      const dataUri = await api.iconDataUri(icon.id, icon.coloured ? null : color)
      onPick({ id: icon.id, name: icon.name, dataUri, coloured: icon.coloured })
    } catch (e) {
      setError(e?.message || 'Could not get that icon.')
    } finally { setPicking('') }
  }

  const swatches = [['White', '#ffffff'], ['Dark', '#111111'], ['Accent', accent]]

  return (
    <div className="flex flex-col gap-2.5" data-testid="icon-search">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search icons: pumpkin, golf, trophy…" data-testid="icon-query"
        className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest" />
      <div className="flex flex-wrap gap-1">
        {TOPICS.map((t) => (
          <button key={t} onClick={() => setQ(t)}
            className="px-2 py-0.5 rounded-full border pb-hairline font-mono text-[9px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text hover:border-pb-accent">{t}</button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint">Line icons</span>
        {swatches.map(([label, hex]) => (
          <button key={hex} onClick={() => setColor(hex)} title={label} aria-label={`${label} line icons`}
            className="w-5 h-5 rounded-full border"
            style={{ background: hex, borderColor: color === hex ? 'var(--pb-accent)' : 'var(--pb-hairline)', boxShadow: color === hex ? '0 0 0 1px var(--pb-accent)' : 'none' }} />
        ))}
        <span className="font-mono text-[9px] text-pb-faintest">Colour icons keep their own.</span>
      </div>

      {loading && <p className="font-mono text-[10px] text-pb-faintest animate-pulse">Searching…</p>}
      {error && <p className="text-[11px] text-red-400" role="alert">{error}</p>}
      {results && !loading && !error && results.length === 0 && (
        <p className="text-[11px] text-pb-faint leading-relaxed" data-testid="icon-empty">
          Nothing for “{q.trim()}”. Try a simpler word, or one of the topics above.
        </p>
      )}
      {results && results.length > 0 && (
        <div className="grid grid-cols-4 gap-1.5" data-testid="icon-results">
          {results.map((i) => (
            <button key={i.id} onClick={() => pick(i)} disabled={!!picking} title={`${i.name} · ${i.set}`} data-testid="icon-result"
              className="aspect-square rounded border pb-hairline hover:border-pb-accent flex items-center justify-center p-1.5 disabled:opacity-50 relative"
              style={{ background: dark ? '#14161d' : '#f1efe9' }}>
              <img src={api.iconUrl(i.id, i.coloured ? null : color)} alt={i.name} loading="lazy" className="max-w-full max-h-full object-contain" />
              {picking === i.id && <span className="absolute inset-0 grid place-items-center text-[9px] font-mono text-pb-text bg-black/40">…</span>}
            </button>
          ))}
        </div>
      )}
      <p className="font-mono text-[9px] leading-relaxed text-pb-faintest">
        From the open Noto, Fluent Emoji, Phosphor, Lucide, Tabler and Material Design Icons sets, free to use on your club's posts.
      </p>
    </div>
  )
}
