import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Btn, Card, Field, Select } from '../../lib/presskit'
import { useToast } from '../../contexts/ToastContext'

// Player Cards: the club's switches, and who is in the card pool. A card is a collectable of a player's career
// figures that the club's players open from packs on their own page. Everything here is a club decision: cards
// on or off, whether juniors are in (off until the club says so), how many weekly packs a player gets, which
// timezone the week turns over in, and which players sit out. The cards themselves are built from the club's
// own figures and need nothing set up.

const EXCLUDED = {
  private: 'Hidden from the public site (or removed at their request)',
  junior: 'Junior player, and juniors are switched off',
}

function Toggle({ on, onChange, label, hint, disabled }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange(!on)}
        className="mt-0.5 relative shrink-0 w-10 h-6 rounded-full transition disabled:opacity-50"
        style={{ background: on ? 'var(--pb-accent)' : 'var(--pb-hairline2, #475569)' }}>
        <span className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all" style={{ left: on ? 18 : 2 }} />
      </button>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-pb-text">{label}</span>
        {hint && <span className="block text-[12.5px] text-pb-faint mt-0.5">{hint}</span>}
      </span>
    </label>
  )
}

export default function AdminPlayerCards() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('')
  const [only, setOnly] = useState('all') // all | hidden | out
  const [copied, setCopied] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(() => api.getPlayerCardSettings().then(setData).catch((e) => setError(e?.message || 'Could not load Player Cards.')), [])
  useEffect(() => { load() }, [load])

  const save = async (patch) => {
    setSaving(true)
    try {
      setData(await api.updatePlayerCardSettings(patch))
      toast?.success?.('Saved')
    } catch (e) {
      toast?.error?.(e?.message || 'Could not save that.')
    } finally {
      setSaving(false)
    }
  }
  const hide = async (p, hidden) => {
    try {
      setData(await api.setPlayerCardHidden(p.id, hidden))
    } catch (e) {
      toast?.error?.(e?.message || 'Could not change that player.')
    }
  }
  const findMore = async () => {
    setRefreshing(true)
    try {
      const { made } = await api.refreshPlayerCardSpecials()
      const n = Object.values(made || {}).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0)
      toast?.success?.(n ? 'Special cards updated' : 'No new special cards to make')
    } catch (e) {
      toast?.error?.(e?.message || 'Could not look through the history.')
    } finally {
      setRefreshing(false)
    }
  }

  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return (data?.players || []).filter((p) => {
      if (q && !(p.display_name || '').toLowerCase().includes(q)) return false
      if (only === 'hidden') return p.hidden
      if (only === 'out') return !p.in_pool
      return true
    })
  }, [data, filter, only])

  const link = data?.link?.path ? `${window.location.origin}${data.link.path}` : null
  const s = data?.settings

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl" data-player-cards-admin>
        <h1 className="font-display font-bold text-2xl text-pb-text">Player Cards</h1>
        <p className="text-sm text-pb-faint mt-1 mb-5">
          Every player gets a collectable card of their career figures. Players open packs of other players' cards from their own player page: one pack a week, more for runs, wickets and dismissals, and a Duck Pack when it goes wrong.
        </p>
        {error && <div role="alert" className="text-sm text-pb-red mb-4">{error}</div>}
        {!data && !error && <div className="text-sm text-pb-faint">Loading…</div>}

        {data && (
          <div className="space-y-4">
            <Card title="Settings">
              <div className="space-y-4">
                <Toggle on={s.enabled} disabled={saving} onChange={(v) => save({ enabled: v })} label="Player Cards are on"
                  hint="Switching them off hides the cards and the packs from your players. Nothing they have collected is lost." />
                <Toggle on={s.include_juniors} disabled={saving} onChange={(v) => save({ include_juniors: v })} label="Include junior players"
                  hint="Off by default. When on, juniors have cards and can be pulled from packs. Check with their families first." />
                <div className="grid sm:grid-cols-2 gap-3">
                  <Field label="Weekly packs per player">
                    <Select value={s.weekly_packs} disabled={saving} onChange={(e) => save({ weekly_packs: Number(e.target.value) })} aria-label="Weekly packs per player">
                      {Array.from({ length: data.max_weekly_packs + 1 }, (_, i) => <option key={i} value={i}>{i === 1 ? '1 (the default)' : i}</option>)}
                    </Select>
                  </Field>
                  <Field label="The week turns over on Monday in">
                    <Select value={s.timezone || ''} disabled={saving} onChange={(e) => save({ timezone: e.target.value || null })} aria-label="Timezone">
                      <option value="">{`Default (${s.effective_timezone})`}</option>
                      {data.timezones.map((t) => <option key={t.id} value={t.id}>{t.label} ({t.id.split('/')[1].replace('_', ' ')})</option>)}
                    </Select>
                  </Field>
                </div>
                <p className="text-[12.5px] text-pb-faint">A weekly pack that is not opened by the end of the week is gone. Packs earned for runs, wickets and dismissals wait until they are opened.</p>
              </div>
            </Card>

            <Card title="Where players find them">
              {link ? (
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-[12.5px] bg-pb-surface2 rounded px-2 py-1 break-all min-w-0" data-player-page-link>{link}</code>
                  <Btn sm onClick={() => { navigator.clipboard?.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1800) }}>{copied ? 'Copied' : 'Copy link'}</Btn>
                </div>
              ) : <p className="text-sm text-pb-faint">The link appears once the page has loaded.</p>}
              <p className="text-[12.5px] text-pb-faint mt-2">Players pick their name and enter the last 4 digits of their mobile number, as on the availability page. Mobile numbers are kept on the Players page. A player with no number on file cannot sign in until one is added.</p>
            </Card>

            <Card title={`Special cards`} action={<Btn sm onClick={findMore} disabled={refreshing}>{refreshing ? 'Looking…' : 'Look for new ones'}</Btn>}>
              <p className="text-[12.5px] text-pb-faint">Centuries, half centuries, five-wicket hauls, hat-tricks, debuts, games milestones and club awards each get a card, made from your history and kept up to date as games come in. The player it is for is given a copy, and everyone else can pull it from a pack. Cards are only ever added: a score corrected later does not take one away.</p>
            </Card>

            <Card title={`Players in the card pool (${data.pool.size} of ${data.pool.players})`}>
              <div className="flex flex-wrap gap-2 mb-3">
                <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a player" aria-label="Find a player"
                  className="bg-pb-surface2 border border-pb-hairline2 rounded px-2.5 py-1.5 text-sm min-w-0 flex-1" />
                <Select value={only} onChange={(e) => setOnly(e.target.value)} className="!w-auto" aria-label="Show">
                  <option value="all">Everyone</option>
                  <option value="hidden">Hidden by us</option>
                  <option value="out">Not in the pool</option>
                </Select>
              </div>
              <div className="rounded border pb-hairline divide-y divide-pb-hairline max-h-[420px] overflow-y-auto">
                {rows.length === 0 && <div className="p-4 text-sm text-pb-faint">No players match.</div>}
                {rows.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 px-3 py-2" data-card-player={p.id}>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-pb-text truncate">{p.display_name}</div>
                      <div className="text-[11.5px] text-pb-faint">
                        {p.excluded ? EXCLUDED[p.excluded]
                          : p.hidden ? 'Hidden by the club'
                            : p.in_pool ? `${p.matches} matches · rarity ${p.rarity} (${p.tier})`
                              : 'No matches yet. Has a card, cannot be pulled from a pack'}
                      </div>
                    </div>
                    {!p.excluded && (
                      <Btn sm onClick={() => hide(p, !p.hidden)}>{p.hidden ? 'Show' : 'Hide'}</Btn>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-[12.5px] text-pb-faint mt-2">Hiding a player takes their card out of every pack and gallery. They keep their own collection, and showing them again brings the card back.</p>
            </Card>
          </div>
        )}
      </div>
    </BetterStatsLayout>
  )
}
