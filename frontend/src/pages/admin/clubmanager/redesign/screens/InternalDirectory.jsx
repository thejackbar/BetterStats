import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, initials } from '../ui'

// BetterCricket's OWN directory, shown in place of the club Directory while a
// super admin is working on the outreach organisation.
//
// ⚠ This is the platform surface. It is a SEPARATE screen from Directory.jsx
// rather than a mode inside it, deliberately: PROJECT_RULES.md requires the
// club build never to carry BetterCricket's sales fields or copy, and two
// components with two data sources cannot be got wrong at runtime the way one
// component with a flag can. Its route is super-admin-only in App.jsx.
//
// The data is NOT the whole Clubs Directory (/admin/super/marketing) — that is
// the superset scraped from PlayHQ and we do not email all of it. It is the
// contacts actually exported into the outreach org, which is exactly what a
// campaign here can reach. Clubs view is those contacts grouped by their linked
// directory club.

const inp = {
  background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8,
  padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none', width: '100%',
}
const btnP = { padding: '7px 13px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#0a0d14', cursor: 'pointer' }
const btnS = { padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }
const pill = (on, tone) => ({
  padding: '5px 11px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
  border: `1px solid ${on ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`,
  background: on ? 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' : 'transparent',
  color: on ? (tone === 'amber' ? C.warn : C.accent) : C.dim,
})
const cap = { fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 8 }

// The internal attributes a contact carries on top of an ordinary one. Each is
// stored as a merge_vars override (EDITABLE_MERGE_KEYS server-side) that falls
// back to the linked directory club, so editing one here never rewrites the
// club record every other contact reads from.
const INTERNAL_FIELDS = [
  { key: 'club', label: 'CLUB' },
  { key: 'association', label: 'ASSOCIATION' },
  { key: 'utm_code', label: 'UTM CODE' },
  { key: 'state', label: 'STATE' },
  { key: 'website', label: 'WEBSITE' },
  { key: 'first_name', label: 'FIRST NAME (MERGE)' },
]

const TAGS = [
  ['is_junior', 'Junior'], ['is_carnival', 'Carnival'], ['is_school', 'School'],
  ['is_rep', 'Rep'], ['is_cricket_au', 'Cricket AU'], ['emailed', 'Emailed'],
]

function Field({ label, value, onChange, placeholder }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginBottom: 3 }}>{label}</div>
      <input value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} style={inp} />
    </label>
  )
}

export default function InternalDirectory({ st, patch, narrow }) {
  const [contacts, setContacts] = useState(null)
  const [err, setErr] = useState(null)
  const [view, setView] = useState('people')     // 'people' | 'clubs'
  const [query, setQuery] = useState('')
  const [subFilter, setSubFilter] = useState('all')   // all | subscribed | unsubscribed
  const [selId, setSelId] = useState(null)
  const [selClub, setSelClub] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(null)

  const load = useCallback(() => {
    setErr(null)
    api.commsListContacts({})
      .then(r => setContacts(r?.contacts || r || []))
      .catch(e => { setErr(e?.message || 'Could not load internal contacts'); setContacts([]) })
  }, [])
  useEffect(() => { load() }, [load])

  // Search runs client-side. The list endpoint caps at 50,000 and already
  // searches the directory fields server-side, but filtering in the browser
  // keeps the clubs rollup and the people list agreeing on one filtered set.
  const filtered = useMemo(() => {
    if (!contacts) return []
    const q = query.trim().toLowerCase()
    return contacts.filter(c => {
      if (subFilter === 'subscribed' && !c.subscribed) return false
      if (subFilter === 'unsubscribed' && c.subscribed) return false
      if (selClub && (c.club || '') !== selClub) return false
      if (!q) return true
      return [c.name, c.email, c.club, c.association, c.utm_code, c.state, c.website]
        .some(v => (v || '').toLowerCase().includes(q))
    })
  }, [contacts, query, subFilter, selClub])

  const clubs = useMemo(() => {
    const by = new Map()
    filtered.forEach(c => {
      const name = c.club || ', No club recorded, '
      let g = by.get(name)
      if (!g) {
        g = { name, association: c.association, state: c.state, country: c.country,
              utm_code: c.utm_code, website: c.website, score: c.club_engagement_score,
              tier: c.club_engagement_tier, views: c.club_views, contacts: 0, subscribed: 0, suppressed: 0 }
        by.set(name, g)
      }
      g.contacts++
      if (c.subscribed) g.subscribed++
      if (c.suppressed) g.suppressed++
      // Directory attributes come off whichever contact has them — they all
      // resolve from the same linked club unless someone set an override.
      INTERNAL_FIELDS.forEach(f => { if (!g[f.key] && c[f.key]) g[f.key] = c[f.key] })
    })
    return [...by.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [filtered])

  const sel = selId ? filtered.find(c => c.id === selId) || contacts?.find(c => c.id === selId) : null

  useEffect(() => {
    if (!sel) { setDraft(null); return }
    const d = { name: sel.name || '', email: sel.email || '' }
    INTERNAL_FIELDS.forEach(f => { d[f.key] = sel[f.key] || '' })
    setDraft(d)
  }, [selId])   // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!sel || !draft) return
    setSaving(true)
    try {
      const merge_vars = {}
      INTERNAL_FIELDS.forEach(f => { merge_vars[f.key] = draft[f.key] })
      await api.commsUpdateContact(sel.id, { name: draft.name, email: draft.email, merge_vars })
      setToast('Saved.')
      load()
    } catch (e) {
      setToast(e?.message || 'Could not save')
    } finally { setSaving(false); setTimeout(() => setToast(null), 2600) }
  }

  const setSubscribed = async (on) => {
    if (!sel) return
    try { await api.commsUpdateContact(sel.id, { subscribed: on }); load() }
    catch (e) { setToast(e?.message || 'Could not change'); setTimeout(() => setToast(null), 2600) }
  }

  const total = contacts ? contacts.length : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Internal directory</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>
            BETTERCRICKET&apos;S OWN CONTACTS · {view === 'clubs' ? `${clubs.length} clubs` : `${filtered.length} of ${total} people`}
          </Caption>
        </div>
        <input placeholder="Search name, email, club, association, UTM…" value={query} onChange={e => setQuery(e.target.value)}
          style={{ ...inp, flex: 1, minWidth: 180, maxWidth: 340, width: 'auto' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={() => { setView('people'); setSelClub(null) }} style={pill(view === 'people')}>People</button>
          <button onClick={() => { setView('clubs'); setSelId(null) }} style={pill(view === 'clubs')}>Clubs</button>
          <span style={{ width: 1, height: 18, background: C.hair2, margin: '0 2px' }} />
          {[['all', 'All'], ['subscribed', 'Subscribed'], ['unsubscribed', 'Unsubscribed']].map(([k, l]) => (
            <button key={k} onClick={() => setSubFilter(k)} style={pill(subFilter === k)}>{l}</button>
          ))}
          {selClub && <button onClick={() => setSelClub(null)} style={{ ...pill(true), display: 'inline-flex', alignItems: 'center', gap: 6 }}>Club: {selClub}  ✕</button>}
          <a href="/admin/super/marketing" style={{ ...btnS, textDecoration: 'none' }}>Clubs Directory</a>
        </div>
      </ScreenHeader>

      {toast && (
        <div style={{ padding: '8px 20px', fontSize: 12.5, color: C.dim, borderBottom: `1px solid ${C.hair}`, background: C.surface }}>{toast}</div>
      )}

      {contacts === null && <div style={{ padding: 24, fontSize: 13, color: C.faint }}>Loading BetterCricket&apos;s contacts…</div>}
      {err && <div style={{ padding: 24, fontSize: 13, color: C.warn }}>{err}</div>}

      {contacts !== null && !err && contacts.length === 0 && (
        <div style={{ padding: 24, fontSize: 13.5, color: C.faint, lineHeight: 1.6, maxWidth: '44rem' }}>
          Nothing has been exported into BetterCricket&apos;s contacts yet. The{' '}
          <a href="/admin/super/marketing" style={{ color: 'var(--pb-accent)' }}>Clubs Directory</a>{' '}
          holds every club and officer pulled from PlayHQ; filter it there and export the ones you want to email,
          and they will appear here.
        </div>
      )}

      {contacts !== null && contacts.length > 0 && view === 'clubs' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7, maxWidth: '68rem' }}>
            {clubs.map(g => (
              <div key={g.name} onClick={() => { setSelClub(g.name); setView('people') }}
                style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: '12px 15px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 14.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 140 }}>{g.name}</span>
                  {g.tier && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: C.accent }}>{String(g.tier).toUpperCase()}{g.score != null ? ' ' + g.score : ''}</span>}
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.dim }}>{g.contacts} contact{g.contacts === 1 ? '' : 's'}</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: g.subscribed === g.contacts ? C.ok : C.warn }}>{g.subscribed} subscribed</span>
                </div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 6 }}>
                  {[g.association, g.state, g.country, g.utm_code ? 'UTM ' + g.utm_code : null].filter(Boolean).join(' · ') || 'No directory attributes recorded'}
                </div>
              </div>
            ))}
            {clubs.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No clubs match those filters.</div>}
          </div>
        </div>
      )}

      {contacts !== null && contacts.length > 0 && view === 'people' && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div className="pb-scroll" style={{ width: 300, flex: '0 0 300px', borderRight: `1px solid ${C.hair}`, background: C.surface, overflowY: 'auto', padding: 10 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {filtered.slice(0, 500).map(c => (
                <div key={c.id} onClick={() => setSelId(c.id)}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 8, cursor: 'pointer', border: c.id === selId ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : '1px solid transparent', background: c.id === selId ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : 'transparent' }}>
                  <span style={{ width: 30, height: 30, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 10, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(c.name || c.email)}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: c.suppressed ? C.faint : C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name || c.email}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.club || c.email}</div>
                  </div>
                  {c.suppressed && <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.warn, flexShrink: 0 }} />}
                </div>
              ))}
              {filtered.length === 0 && <div style={{ padding: '20px 12px', fontSize: 13, color: C.faint }}>Nobody matches those filters.</div>}
              {filtered.length > 500 && <div style={{ padding: '10px 12px', fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>SHOWING 500 OF {filtered.length}. SEARCH TO NARROW</div>}
            </div>
          </div>

          {sel && draft ? (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 20 }}>
                <span style={{ width: 52, height: 52, borderRadius: '50%', background: C.surface2, border: `1.5px solid ${C.hair2}`, color: C.dim, fontFamily: MONO, fontSize: 16, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{initials(sel.name || sel.email)}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: 22, letterSpacing: '-0.01em' }}>{sel.name || sel.email}</div>
                  <div style={{ fontSize: 12.5, color: C.faint, marginTop: 3 }}>{sel.email}{sel.club ? '  ·  ' + sel.club : ''}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${sel.subscribed ? C.hair2 : C.warn + '66'}`, color: sel.subscribed ? C.dim : C.warn }}>
                      {sel.subscribed ? 'SUBSCRIBED' : 'UNSUBSCRIBED'}
                    </span>
                    {sel.suppressed && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${C.warn}66`, color: C.warn }}>SUPPRESSED</span>}
                    {TAGS.filter(([k]) => sel[k]).map(([k, label]) => (
                      <span key={k} style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 4, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 28%, transparent)', color: C.accent }}>{label.toUpperCase()}</span>
                    ))}
                  </div>
                </div>
                <button onClick={() => setSubscribed(!sel.subscribed)} style={btnS}>{sel.subscribed ? 'Unsubscribe' : 'Resubscribe'}</button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: narrow ? '1fr' : '1fr 1fr', gap: 22, maxWidth: '60rem' }}>
                <section>
                  <div style={cap}>CONTACT</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <Field label="NAME" value={draft.name} onChange={v => setDraft(d => ({ ...d, name: v }))} />
                    <Field label="EMAIL" value={draft.email} onChange={v => setDraft(d => ({ ...d, email: v }))} />
                  </div>
                </section>

                <section>
                  {/* The attributes that only exist on an internal contact. Each
                      is an override: leave one blank and it falls back to the
                      linked directory club. */}
                  <div style={cap}>INTERNAL ATTRIBUTES</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {INTERNAL_FIELDS.map(f => (
                      <Field key={f.key} label={f.label} value={draft[f.key]}
                        placeholder="From the linked directory club"
                        onChange={v => setDraft(d => ({ ...d, [f.key]: v }))} />
                    ))}
                  </div>
                  <div style={{ fontSize: 11.5, color: C.faintest, lineHeight: 1.5, marginTop: 8 }}>
                    Blank falls back to the linked club in the Clubs Directory. Anything typed here overrides it for
                    this contact only.
                  </div>
                </section>

                <section>
                  <div style={cap}>ENGAGEMENT</div>
                  <div style={{ fontFamily: MONO, fontSize: 11.5, color: C.dim, lineHeight: 1.9 }}>
                    <div>SCORE {sel.club_engagement_score ?? '—'}{sel.club_engagement_tier ? ' · ' + String(sel.club_engagement_tier).toUpperCase() : ''}</div>
                    <div>PAGE VIEWS {sel.club_views ?? '—'}</div>
                    <div>VISITORS {sel.club_visitors ?? '—'}</div>
                    <div>SOURCE {sel.source || '—'}</div>
                  </div>
                  {sel.marketing_club_id && (
                    <a href="/admin/super/marketing" style={{ ...btnS, display: 'inline-block', marginTop: 10, textDecoration: 'none' }}>Open in Clubs Directory</a>
                  )}
                </section>

                <section>
                  <div style={cap}>DELIVERABILITY</div>
                  <div style={{ fontFamily: MONO, fontSize: 11.5, color: C.dim, lineHeight: 1.9 }}>
                    <div>BOUNCED {sel.bounced ? (sel.bounced_at || 'yes') : 'no'}</div>
                    <div>COMPLAINED {sel.complained ? 'yes' : 'no'}</div>
                    <div>EXCLUDED {sel.excluded ? 'yes' : 'no'}</div>
                    <div>UNSUBSCRIBED {sel.unsubscribed_at || (sel.subscribed ? 'no' : 'yes')}</div>
                  </div>
                </section>
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 22 }}>
                <button onClick={save} disabled={saving} style={{ ...btnP, opacity: saving ? 0.6 : 1 }}>{saving ? 'Saving…' : 'Save changes'}</button>
                <button onClick={() => setSelId(null)} style={btnS}>Close</button>
              </div>
            </div>
          ) : (
            <div style={{ flex: 1, padding: 24, fontSize: 13, color: C.faint }}>Pick someone to see and edit their record.</div>
          )}
        </div>
      )}
    </div>
  )
}
