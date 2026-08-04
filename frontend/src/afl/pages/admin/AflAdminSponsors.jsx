import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminSponsors() {
  const [sponsors, setSponsors] = useState(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refresh = () => aflApi.listSponsors().then(setSponsors).catch(() => setSponsors([]))
  useEffect(() => { refresh() }, [])

  const add = async () => {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.createSponsor({ name: name.trim(), website_url: url.trim() || null })
      setName('')
      setUrl('')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (s) => {
    if (!window.confirm(`Remove sponsor "${s.name}"?`)) return
    setBusy(true)
    try {
      await aflApi.deleteSponsor(s.id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onLogo = async (s, file) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.uploadSponsorLogo(s.id, file)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const move = async (idx, dir) => {
    if (!sponsors) return
    const next = [...sponsors]
    const j = idx + dir
    if (j < 0 || j >= next.length) return
    ;[next[idx], next[j]] = [next[j], next[idx]]
    setSponsors(next)
    setBusy(true)
    try {
      await aflApi.reorderSponsors(next.map((s, i) => ({ id: s.id, display_order: i })))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (sponsors === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6">
      <SectionTitle>Sponsors ({sponsors.length})</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">The sponsors shown on your public site.</p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      <div className="pb-card p-4 space-y-3 max-w-lg">
        <SectionTitle>Add a sponsor</SectionTitle>
        <input placeholder="Sponsor name" value={name} onChange={e => setName(e.target.value)}
               className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        <input placeholder="Website URL (optional)" value={url} onChange={e => setUrl(e.target.value)}
               className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        <button disabled={busy || !name.trim()} onClick={add}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          Add sponsor
        </button>
      </div>

      <div className="space-y-2">
        {sponsors.map((s, idx) => (
          <div key={s.id} className="pb-card p-3 flex items-center gap-3">
            {s.logo_url
              ? <img src={s.logo_url} alt="" className="h-10 w-10 rounded object-contain bg-pb-surface2" />
              : <span className="h-10 w-10 rounded bg-pb-surface2 flex items-center justify-center text-pb-faint text-xs">No logo</span>}
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{s.name}</div>
              {s.website_url && <a href={s.website_url} target="_blank" rel="noreferrer" className="text-xs text-pb-faint hover:text-pb-dim truncate block">{s.website_url}</a>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button disabled={busy || idx === 0} onClick={() => move(idx, -1)} className="text-pb-faint hover:text-pb-text disabled:opacity-30">↑</button>
              <button disabled={busy || idx === sponsors.length - 1} onClick={() => move(idx, 1)} className="text-pb-faint hover:text-pb-text disabled:opacity-30">↓</button>
              <label className="text-xs text-pb-dim hover:text-pb-text underline cursor-pointer">
                Logo
                <input type="file" accept="image/*" className="hidden"
                       onChange={e => onLogo(s, e.target.files?.[0])} />
              </label>
              <button disabled={busy} onClick={() => remove(s)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">Remove</button>
            </div>
          </div>
        ))}
        {sponsors.length === 0 && <p className="pb-card p-4 text-pb-faint text-sm">No sponsors yet.</p>}
      </div>
    </div>
  )
}
