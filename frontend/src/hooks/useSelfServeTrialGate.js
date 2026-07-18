import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

/**
 * Gates every public "start a trial" CTA (the website's "Request access" and
 * "Get your club on BetterCricket" buttons) behind the All Clubs -> General
 * Settings "Self-serve trials enabled" checkbox
 * (platform_settings.self_serve_registration_enabled) — the same flag
 * routers/public_self_serve.py and the /trial landing page (Trial.jsx) key
 * off via api.publicSelfServeStatus().
 *
 *  - enabled === true  -> trigger() opens SelfServeTrialModal with
 *    publicMode set (components/admin/SelfServeTrialModal.jsx).
 *  - enabled === false (or the status call fails/hasn't resolved yet) ->
 *    trigger() falls back to "/contact", matching how these CTAs behaved
 *    before this flow existed, and matching Trial.jsx's own off-state
 *    redirect.
 *
 * One network call per mount — call sites that render several CTAs on the
 * same page should share a single hook instance rather than calling this
 * once per button.
 */
export function useSelfServeTrialGate() {
  const navigate = useNavigate()
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [defaultTrialDays, setDefaultTrialDays] = useState(14)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    let alive = true
    api.publicSelfServeStatus()
      .then((s) => {
        if (!alive) return
        setEnabled(!!s?.enabled)
        setDefaultTrialDays(s?.default_trial_days ?? 14)
      })
      .catch(() => { if (alive) setEnabled(false) })   // 404 while the flag is off
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const trigger = () => {
    if (enabled) setModalOpen(true)
    else navigate('/contact')
  }

  return { enabled, loading, defaultTrialDays, modalOpen, setModalOpen, trigger }
}
