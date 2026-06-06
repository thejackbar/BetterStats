import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { PbSpinner, Card, Btn } from '../../../lib/presskit'

const kb = (n) => n ? `${Math.round(n / 1024)} KB` : '—'

export default function KlubproSponsors({ clubMapping }) {
  const toast = useToast()
  const cm = clubMapping.id
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [dry, setDry] = useState(null)
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    setData(null); setDry(null)
    try {
      const d = await api.kpSponsors(cm)
      setData(d)
      // pre-select everything not already imported
      const imported = new Set((d.betterstats_sponsors || []).map(s => s.klubpro_sponsor_id).filter(Boolean))
      const pre = new Set((d.klubpro_sponsors || [])
        .filter(s => !imported.has(s.klubpro_sponsor_id))
        .map(s => s.klubpro_sponsor_id))
      setSelected(pre)
    } catch (e) { toast.error(e.message) }
  }, [cm, toast])

  useEffect(() => { load() }, [load])

  const importedSet = useMemo(
    () => new Set((data?.betterstats_sponsors || []).map(s => s.klubpro_sponsor_id).filter(Boolean)),
    [data]
  )

  const toggle = (id) => {
    setDry(null)
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const selectableIds = useMemo(
    () => (data?.klubpro_sponsors || []).filter(s => !importedSet.has(s.klubpro_sponsor_id)).map(s => s.klubpro_sponsor_id),
    [data, importedSet]
  )
  const allSelected = selectableIds.length > 0 && selectableIds.every(id => selected.has(id))

  const toggleAll = () => {
    setDry(null)
    setSelected(allSelected ? new Set() : new Set(selectableIds))
  }

  const runDryRun = async () => {
    const ids = [...selected]
    if (!ids.length) { toast.info('Select at least one sponsor.'); return }
    try {
      const r = await api.kpSponsorDryRun(cm, ids)
      setDry(r)
    } catch (e) { toast.error(e.message) }
  }

  const runImport = async () => {
    const ids = dry ? dry.to_insert.map(s => s.klubpro_sponsor_id) : [...selected]
    if (!ids.length) { toast.info('Nothing to import.'); return }
    if (!window.confirm(`Import ${ids.length} sponsor(s)? This can be rolled back from History.`)) return
    setImporting(true)
    try {
      const r = await api.kpSponsorImport(cm, [...selected])
      toast.success(`Imported — ${r.inserted} inserted, ${r.skipped} skipped`)
      await load()
    } catch (e) { toast.error(e.message) } finally { setImporting(false) }
  }

  if (!data) return <PbSpinner message="Loading sponsors…" />

  const sponsors = data.klubpro_sponsors || []
  const selectableCount = selectableIds.length

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[13px] text-pb-dim">
            {sponsors.length} staged · {importedSet.size} already imported · {selected.size} selected
          </div>
          <div className="flex gap-2">
            <Btn sm onClick={toggleAll} disabled={!selectableCount}>{allSelected ? 'Deselect all' : 'Select all'}</Btn>
            <Btn onClick={runDryRun} disabled={!selected.size}>Dry run</Btn>
            <Btn primary disabled={!selected.size || importing} onClick={runImport}>
              {importing ? 'Importing…' : 'Import selected'}
            </Btn>
          </div>
        </div>
      </Card>

      {dry && (
        <Card title={`Dry-run — ${dry.to_insert.length} to insert, ${dry.duplicate_skip.length} duplicate(s) skipped`}>
          {dry.to_insert.length === 0
            ? <p className="text-pb-faint text-sm">Nothing new to insert (all selected sponsors already imported).</p>
            : <div className="flex flex-wrap gap-x-4 gap-y-1">
                {dry.to_insert.map(s => <span key={s.klubpro_sponsor_id} className="text-[13px]" style={{ color: 'var(--pb-accent)' }}>+ {s.sponsor_name}</span>)}
              </div>}
        </Card>
      )}

      <div className="space-y-2">
        {sponsors.map(s => {
          const isImported = importedSet.has(s.klubpro_sponsor_id)
          const isSel = selected.has(s.klubpro_sponsor_id)
          return (
            <Card key={s.klubpro_sponsor_id} pad="p-3" className={isImported ? 'opacity-60' : ''}>
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={isImported || isSel} disabled={isImported}
                  onChange={() => toggle(s.klubpro_sponsor_id)}
                  className="w-4 h-4 accent-[var(--pb-accent)] shrink-0" />
                <div className="w-16 h-10 bg-white/5 border border-pb-hairline2 rounded flex items-center justify-center shrink-0 overflow-hidden">
                  {s.logo_found
                    ? <img src={api.kpSponsorImageUrl(s.klubpro_sponsor_id)} alt={s.sponsor_name} className="max-w-full max-h-full object-contain" />
                    : <span className="text-pb-faintest text-[10px]">no logo</span>}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-pb-text">{s.sponsor_name}</span>
                    {isImported && <span className="font-mono text-[10px] text-green-300 border border-green-400/30 rounded px-1.5 py-0.5">IMPORTED</span>}
                  </div>
                  <div className="text-[11px] text-pb-faint mt-0.5">
                    {s.contact_name || '—'} · {s.email || '—'} · seq {s.sequence ?? '—'} · {kb(s.logo_bytes)}
                  </div>
                </div>
              </div>
            </Card>
          )
        })}
        {!sponsors.length && <Card><p className="text-pb-faint text-sm">No staged sponsors for this club.</p></Card>}
      </div>
    </div>
  )
}
