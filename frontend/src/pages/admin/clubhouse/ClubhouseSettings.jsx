import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import { Button, FilterPill, Caption, SectionHeading } from '../../../components/admin/ui'
import { useIntroSettings, INTRO_MODES, INTROS } from './intro'

// Settings — for now, the screen-introduction flag.
//
// A club officer asked for this directly: the introduction pages help a new
// committee and irritate a practised one. It is stored per person, not per
// club, so a treasurer joining in March still gets shown around even if the
// rest of the committee turned them off in October.

export default function ClubhouseSettings() {
  const { mode, setMode, seenCount, resetSeen } = useIntroSettings()
  const active = INTRO_MODES.find(m => m.key === mode) || INTRO_MODES[1]
  const total = Object.keys(INTROS).length

  return (
    <BetterClubhouseLayout title="Settings" caption="Yours, not the club's">
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
      </div>
    </BetterClubhouseLayout>
  )
}
