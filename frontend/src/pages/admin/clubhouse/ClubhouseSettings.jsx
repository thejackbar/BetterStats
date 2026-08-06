import { useState, useEffect } from 'react'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import { Button, FilterPill, Caption, SectionHeading } from '../../../components/admin/ui'
import { useIntroSettings, INTRO_MODES, INTROS } from './intro'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { CAP } from '../../../lib/capabilities'

// Settings — one flag that is yours, and one that is the club's.
//
// The screen-introduction flag is per PERSON: the introduction pages help a new
// committee and irritate a practised one, so a treasurer joining in March still
// gets shown around even if the rest of the committee turned them off in
// October. Who may open an uploaded document is per CLUB, and only the people
// who can manage settings may change it.

const DOC_RULES = [
  {
    value: true,
    label: 'Office bearers only',
    note: 'An uploaded document opens for whoever uploaded it, committee members holding an Office Bearer role, and the main admin. Everyone else on the committee sees the title and a lock.',
  },
  {
    value: false,
    label: 'Any committee member',
    note: 'Anyone who can reach the committee register can open an uploaded document.',
  },
]

function DocumentAccessPanel() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SETTINGS)
  const [value, setValue] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.adminGetSettings()
      .then(s => setValue(!!s.committee_docs_office_bearer_only))
      .catch(() => setValue(null))
  }, [])

  async function choose(next) {
    if (next === value || !canEdit) return
    const previous = value
    setValue(next); setSaving(true)
    try {
      await api.adminPatchSettings({ committee_docs_office_bearer_only: next })
    } catch (e) {
      setValue(previous)   // put the control back where it was, not where the click left it
      toast.error(e.message)
    } finally { setSaving(false) }
  }

  const active = DOC_RULES.find(r => r.value === value)

  return (
    <div className="bg-pb-surface border border-pb-hairline rounded-[10px] p-6 mt-4">
      <Caption>The club's</Caption>
      <SectionHeading className="mt-2">Who can open an uploaded document</SectionHeading>
      <p className="text-[13.5px] text-pb-dim mt-2 leading-[1.65]" style={{ maxWidth: '56ch', textWrap: 'pretty' }}>
        A committee document can be a link to where the club already keeps the file, or the file itself.
        This decides who can open and download the ones uploaded here.
      </p>

      <div className="flex items-center gap-2 mt-5 flex-wrap">
        {DOC_RULES.map(r => (
          <FilterPill key={String(r.value)} active={value === r.value}
            onClick={() => choose(r.value)}>{r.label}</FilterPill>
        ))}
        {saving && <span className="font-mono text-[10px] text-pb-faintest">saving…</span>}
      </div>
      {active && (
        <div className="text-[12.5px] text-pb-dim mt-3 leading-[1.6]" style={{ maxWidth: '56ch' }}>
          {active.note}
        </div>
      )}

      <div className="text-[12.5px] text-pb-faint mt-5 leading-[1.6]" style={{ maxWidth: '56ch' }}>
        This never applies to a document added as a <b className="text-pb-dim">link</b>. That file lives on
        someone else's Drive or Dropbox, so its address is all we hold and whoever has the address can open it.
        Upload a document instead if it needs to be kept to the office bearers.
      </div>

      {!canEdit && (
        <div className="font-mono text-[10px] text-pb-faintest mt-4">
          Only someone who can manage settings can change this.
        </div>
      )}
    </div>
  )
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

function DiaryYearPanel() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SETTINGS)
  const [month, setMonth] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.adminGetSettings().then(s => setMonth(Number(s.diary_start_month) || 7)).catch(() => setMonth(null))
  }, [])

  async function choose(next) {
    const previous = month
    setMonth(next); setSaving(true)
    try { await api.adminPatchSettings({ diary_start_month: next }) }
    catch (e) { setMonth(previous); toast.error(e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="bg-pb-surface border border-pb-hairline rounded-[10px] p-6 mt-4">
      <Caption>The club's</Caption>
      <SectionHeading className="mt-2">When the Club Diary year starts</SectionHeading>
      <p className="text-[13.5px] text-pb-dim mt-2 leading-[1.65]" style={{ maxWidth: '56ch', textWrap: 'pretty' }}>
        The diary lays a year out from this month. July suits a club that plans around the
        cricket season; January suits one that runs to the calendar.
      </p>
      <div className="flex items-center gap-2 mt-4 flex-wrap">
        <select value={month ?? 7} disabled={!canEdit || month === null}
          onChange={e => choose(Number(e.target.value))}
          className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm">
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
        {saving && <span className="font-mono text-[10px] text-pb-faintest">saving…</span>}
      </div>
      {month && (
        <div className="text-[12.5px] text-pb-dim mt-3 leading-[1.6]" style={{ maxWidth: '56ch' }}>
          A diary year runs {MONTHS[month - 1]} to {MONTHS[(month + 10) % 12]}.
        </div>
      )}
      {!canEdit && (
        <div className="font-mono text-[10px] text-pb-faintest mt-4">
          Only someone who can manage settings can change this.
        </div>
      )}
    </div>
  )
}

export default function ClubhouseSettings() {
  const { mode, setMode, seenCount, resetSeen } = useIntroSettings()
  const active = INTRO_MODES.find(m => m.key === mode) || INTRO_MODES[1]
  const total = Object.keys(INTROS).length

  return (
    <BetterClubhouseLayout title="Settings" caption="Yours, and the club's">
      <div className="max-w-[52rem]">
        <div className="bg-pb-surface border border-pb-hairline rounded-[10px] p-6">
          <Caption>Screen introductions</Caption>
          <SectionHeading className="mt-2">Show an introduction when a screen opens</SectionHeading>
          <p className="text-[13.5px] text-pb-dim mt-2 leading-[1.65]" style={{ maxWidth: '56ch', textWrap: 'pretty' }}>
            A one-page explanation of what a screen is for and what it replaced. Today never shows one — it
            is the front door — and following an action from Today goes straight to the work.
          </p>

          <div className="flex items-center gap-2 mt-5 flex-wrap">
            {INTRO_MODES.map(m => (
              <FilterPill key={m.key} active={mode === m.key} onClick={() => setMode(m.key)}>
                {m.label}
              </FilterPill>
            ))}
          </div>
          <div className="text-[12.5px] text-pb-dim mt-3 leading-[1.6]" style={{ maxWidth: '56ch' }}>
            {active.note}
          </div>

          {mode === 'once' && (
            <div className="mt-5 pt-4 border-t border-pb-hairline flex items-center gap-3 flex-wrap">
              <span className="text-[12.5px] text-pb-dim">
                {seenCount === 0
                  ? `None of the ${total} screens have introduced themselves yet.`
                  : `${seenCount} of ${total} screens have introduced themselves.`}
              </span>
              {seenCount > 0 && <Button size="sm" onClick={resetSeen}>Show them all again</Button>}
            </div>
          )}

          <div className="text-[12.5px] text-pb-faint mt-5 leading-[1.6]" style={{ maxWidth: '56ch' }}>
            Whatever this is set to, the <b className="text-pb-dim">?</b> beside a screen title reopens that
            screen's introduction on demand.
          </div>
        </div>

        <DocumentAccessPanel />
        <DiaryYearPanel />
      </div>
    </BetterClubhouseLayout>
  )
}
