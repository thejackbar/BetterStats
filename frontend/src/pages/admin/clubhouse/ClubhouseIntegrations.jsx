import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { MODULE } from '../../../lib/modules'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import { Button, Badge, Caption, Note, SectionHeading } from '../../../components/admin/ui'
import ScreenIntro, { useScreenIntro, INTROS } from './intro'

// Integrations — every outside connection the club runs on, with a live status.
//
// Square used to be connected on two different screens, one under fees and one
// under stock, with no sign on either that the other existed (it is one
// connection per club, and always was). Xero sat on a third, the email provider
// on a fourth. They are one list now; each row still opens the screen that
// actually owns the setup, so nothing was reimplemented to get here.

function statusOf(s, { connectedKey = 'connected' } = {}) {
  if (!s) return { tone: 'calm', label: 'Unknown', detail: 'Could not read the connection.' }
  if (s.configured === false) return { tone: 'calm', label: 'Unavailable', detail: 'Not configured on this platform yet.' }
  if (!s[connectedKey]) return { tone: 'warn', label: 'Not connected', detail: 'Nothing is flowing in or out yet.' }
  return { tone: 'ok', label: 'Connected', detail: null }
}

function Row({ name, blurb, to, state, extra, action }) {
  return (
    <div className="bg-pb-surface border border-pb-hairline rounded-[10px] px-4 py-3.5 flex items-start gap-3.5 flex-wrap">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="font-display font-semibold text-[14.5px] text-pb-text">{name}</span>
          <Badge toneKey={state.tone}>{state.label}</Badge>
        </div>
        <div className="text-[12.5px] text-pb-dim mt-1 leading-[1.6]">{extra || state.detail || blurb}</div>
      </div>
      <Button as={Link} to={to} size="inline" variant={state.tone === 'ok' ? 'secondary' : 'primary'} className="shrink-0">
        {action || (state.tone === 'ok' ? 'Manage' : 'Set up')}
      </Button>
    </div>
  )
}

export default function ClubhouseIntegrations() {
  const { hasModule } = useAuth()
  const intro = useScreenIntro('integrations')
  const [square, setSquare] = useState(null)
  const [xero, setXero] = useState(null)
  const [email, setEmail] = useState(null)
  const [loading, setLoading] = useState(true)

  const hasFees = hasModule(MODULE.FEES)
  const hasMerch = hasModule(MODULE.MERCH)
  const hasComms = hasModule(MODULE.COMMS)

  useEffect(() => {
    let live = true
    const ok = p => p.catch(() => null)
    // Square is one connection per club; either module's status endpoint
    // reports it, so ask whichever the club actually holds.
    Promise.all([
      hasMerch ? ok(api.merchSquareStatus()) : hasFees ? ok(api.feeSquareStatus()) : null,
      hasFees ? ok(api.feeXeroStatus()) : null,
      hasComms ? ok(api.commsGetSettings()) : null,
    ]).then(([sq, xr, em]) => {
      if (!live) return
      setSquare(sq); setXero(xr); setEmail(em); setLoading(false)
    })
    return () => { live = false }
  }, [hasFees, hasMerch, hasComms])

  if (intro.showing) {
    return (
      <BetterClubhouseLayout title="Integrations"
        actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.integrations} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterClubhouseLayout>
    )
  }

  const connected = [square?.connected, xero?.connected, email?.from_name].filter(Boolean).length

  return (
    <BetterClubhouseLayout
      title="Integrations"
      caption={loading ? 'Checking connections' : `${connected} connected`}
      onHelp={intro.reopen}
    >
      <div className="max-w-[52rem]">
        <Caption>Money in</Caption>
        <div className="flex flex-col gap-2 mt-2.5">
          {(hasMerch || hasFees) && (
            <Row
              name="Square" to={hasMerch ? '/admin/merch/square' : '/admin/fees/square'}
              blurb="Take payments and mirror canteen and bar stock from the till."
              state={statusOf(square)}
              extra={square?.connected
                ? `${square.location_name || square.location_id || 'Connected'}${square.environment === 'sandbox' ? ' · sandbox' : ''}${square.last_sync_at ? ` · last synced ${new Date(square.last_sync_at).toLocaleDateString()}` : ''}`
                : null}
            />
          )}
          {hasFees && (
            <Row
              name="Xero" to="/admin/fees/xero"
              blurb="Pull bank transactions in and match them against what members owe."
              state={statusOf(xero)}
              extra={xero?.connected ? (xero.tenant_name ? `Connected to ${xero.tenant_name}` : 'Connected') : null}
            />
          )}
        </div>

        {hasComms && (
          <>
            <Caption className="mt-7">Messages out</Caption>
            <div className="flex flex-col gap-2 mt-2.5">
              <Row
                name="Email sending" to="/admin/comms/settings"
                blurb="The sender name, reply-to address and footer every campaign goes out with."
                state={email?.from_name
                  ? { tone: 'ok', label: 'Configured', detail: null }
                  : { tone: 'warn', label: 'Needs a sender', detail: 'Set a sender name and reply-to before your first send.' }}
                extra={email?.from_name ? `Sending as ${email.from_name}${email.reply_to ? ` · replies to ${email.reply_to}` : ''}` : null}
              />
            </div>
          </>
        )}

        <SectionHeading className="mt-8 mb-2">One connection, not one per screen</SectionHeading>
        <Note toneKey="calm" className="max-w-[56ch]">
          Square authorises the club, not a module. Connecting it here is what both the till mirror and
          member payments use. Connecting it twice was never possible; it only ever looked that way because
          two screens each asked for it.
        </Note>
      </div>
    </BetterClubhouseLayout>
  )
}
