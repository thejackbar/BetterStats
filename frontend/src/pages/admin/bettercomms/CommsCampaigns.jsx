import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Note, Empty, SearchInput } from '../../../components/admin/ui'
import { CrudPanes, RecordListPane, DetailPane } from '../clubhouse/crudShell'
import ScreenIntro, { useScreenIntro, INTROS } from '../clubhouse/intro'

// Emails — the club's drafts and sends.
//
// Two routes, one screen: /admin/comms lists them, /admin/comms/:id opens one.
// Both render this, so opening an email keeps the others in view beside it
// rather than replacing the page — the same master–detail shape Segments,
// Lists and Templates use. Every existing link into a specific email
// (a segment's or list's "Email these N now", the Roster's, a bookmark) still
// works untouched, because the URL did not change.
//
// The composer itself is lazy — an officer glancing at the list should not pay
// for the HTML editor and its formatter until they actually open something.
const EmailDetail = lazy(() => import('./CommsCompose'))

const STATUS_TONE = { draft: 'calm', sending: 'accent', sent: 'ok', error: 'block' }

function fmtDate(s) {
  if (!s) return ''
  try { return new Date(s).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return '' }
}

// The rail line under an email's name: what state it is in, when, and how the
// send went. The amber dot beside it is the consistency-warning flag the old
// list row spelled out in words — the warnings themselves are listed in full on
// the email, which is the only place they can be acted on.
function subLine(c) {
  const bits = []
  if (c.status === 'sent') bits.push(`Sent ${fmtDate(c.sent_at || c.created_at)}`)
  else if (c.status === 'sending') bits.push('Sending now')
  else if (c.status === 'error') bits.push(`Send failed ${fmtDate(c.created_at)}`)
  else bits.push(`Draft · created ${fmtDate(c.created_at)}`)

  const e = c.engagement
  if (e && (e.sent > 0 || e.bounced > 0 || e.unsub_supp > 0)) {
    if (e.sent > 0) bits.push(`${e.sent} delivered`)
    if (e.bounced > 0) bits.push(`${e.bounced} bounced`)
    if (e.unsub_supp > 0) bits.push(`${e.unsub_supp} unsub`)
  }
  return bits.join(' · ')
}

export default function CommsCampaigns() {
  const navigate = useNavigate()
  const { id } = useParams()
  // A deep link to one email goes straight to it. The introduction belongs to
  // arriving at the screen itself, which is what a sidebar click does.
  const intro = useScreenIntro(id ? null : 'emails')
  const [campaigns, setCampaigns] = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => (
    api.commsListCampaigns().then(setCampaigns).catch(e => setError(e.message))
  ), [])

  useEffect(() => {
    Promise.all([
      load(),
      api.commsGetSettings().then(setSettings).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [load])

  // A send runs as a background task on the server, so a freshly-sent email sits
  // at "sending" here until it flips to "sent". Poll while anything is in flight
  // so the rail updates on its own without a manual refresh.
  const anySending = campaigns.some(c => c.status === 'sending')
  useEffect(() => {
    if (!anySending) return
    const t = setInterval(() => { api.commsListCampaigns().then(setCampaigns).catch(() => {}) }, 3000)
    return () => clearInterval(t)
  }, [anySending])

  const newEmail = async () => {
    setCreating(true)
    setError('')
    try {
      const c = await api.commsCreateCampaign({ subject: '', body_html: '', audience: { type: '' } })
      await load()
      navigate(`/admin/comms/${c.id}`, { state: { skipIntro: true } })
    } catch (e) {
      setError(e.message)
    } finally { setCreating(false) }
  }

  const items = useMemo(() => campaigns.map(c => ({
    id: c.id,
    name: c.name || c.subject || '(no subject)',
    sub: subLine(c),
    flag: (c.warnings?.length || 0) > 0,
    // Only a send has a number worth showing; a draft's zero is noise.
    figure: c.stats?.recipients > 0 ? c.stats.recipients : undefined,
  })), [campaigns])

  const live = settings?.provider?.live
  const [q, setQ] = useState('')

  if (intro.showing) {
    return (
      <BetterCommsLayout title="Emails" actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.emails} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterCommsLayout>
    )
  }

  return (
    <BetterCommsLayout
      title="Emails"
      caption={`Drafts and sends · ${campaigns.length} total`}
      onHelp={intro.reopen}
      // Search under the heading, with Bookmarks and the actions on that line.
      twoRow
      filters={<SearchInput wide value={q} onChange={setQ} placeholder="Search emails by name or subject…" />}
      actions={<>
        <Button as={Link} to="/admin/comms/templates">Templates</Button>
        <Button variant="primary" onClick={newEmail} disabled={creating}>
          {creating ? 'Creating…' : 'New email'}
        </Button>
      </>}
      bare
    >
      <CrudPanes>
        <RecordListPane
          items={items} loading={loading} selId={id || null} query={q}
          onSelect={cid => navigate(`/admin/comms/${cid}`, { state: { skipIntro: true } })}
          emptyText="No emails yet. Send your first newsletter or announcement to the club."
        >
          {settings && !live && (
            <Note toneKey="warn" title="Preview mode">
              No email provider is connected yet, so sends are logged but <strong>not delivered</strong>. Connect a
              free provider in{' '}
              <Link to="/admin/comms/settings" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Email settings</Link>
              {' '}to go live.
            </Note>
          )}
          <Note toneKey="calm">
            An email goes to one audience, and that audience is one of your{' '}
            <Link to="/admin/comms/segments" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>segments</Link>
            {' '}or one of your{' '}
            <Link to="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>lists</Link>.
            Nothing sends until you press Send.
          </Note>
        </RecordListPane>

        <DetailPane>
          {error && <Note toneKey="block" className="mb-4">{error}</Note>}
          {!id ? (
            <Empty>Pick an email, or start a new one.</Empty>
          ) : (
            <Suspense fallback={<Empty>Loading…</Empty>}>
              <EmailDetail
                key={id} id={id}
                onChanged={load}
                onDeleted={() => { load(); navigate('/admin/comms') }}
                onSent={(recipients) => { load(); navigate('/admin/comms', { state: { sent: recipients } }) }}
              />
            </Suspense>
          )}
        </DetailPane>
      </CrudPanes>
    </BetterCommsLayout>
  )
}
