// "Your season": the player's latest season as three small panels (batting,
// bowling, fielding) and the form of their last few innings. Same grade scope and
// rate rules as their public profile; a rate that rests on only some of the
// innings carries a dagger, as it does there.
import { Muted, Section, Stat, fmtShort } from './ui'

const dash = (v) => (v === null || v === undefined ? '-' : v)

// A rate that counts only the innings with balls recorded gets a dagger.
function Rate({ value, partial }) {
  if (value === null || value === undefined) return '-'
  return partial ? <span title="Counts only the innings with balls recorded">{value}†</span> : value
}

function Panel({ title, id, children }) {
  return (
    <div data-season-panel={id} className="mt-3 first:mt-0">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">{title}</div>
      {children}
    </div>
  )
}

// The last few innings as bars, oldest on the left so the eye reads it as a trend.
// Not out gets a star; a duck is flagged. Height is runs against the best of the
// five, with a floor so a duck still draws something.
function BattingForm({ innings }) {
  const list = [...innings].reverse()
  const top = Math.max(20, ...list.map((i) => i.runs))
  return (
    <div className="flex items-end gap-1.5 h-[64px]" data-form-batting>
      {list.map((i, n) => {
        const h = Math.max(4, Math.round((i.runs / top) * 40))
        const tone = i.runs >= 50 ? 'var(--pb-positive)' : i.runs === 0 && !i.not_out ? 'var(--pb-red)' : 'var(--pb-accent)'
        return (
          <div key={`${i.date}-${n}`} className="flex-1 min-w-0 flex flex-col items-center justify-end gap-1"
            title={i.date ? fmtShort(i.date.slice(0, 10)) : undefined}>
            <span className="font-display font-bold text-[12px] leading-none">{i.runs}{i.not_out ? '*' : ''}</span>
            <span className="w-full max-w-[34px] rounded-t" style={{ height: h, background: tone }} />
          </div>
        )
      })}
    </div>
  )
}

function BowlingForm({ spells }) {
  return (
    <div className="flex flex-wrap gap-1.5" data-form-bowling>
      {[...spells].reverse().map((s, n) => (
        <span key={`${s.date}-${n}`} className="font-display font-bold text-[13px] rounded-lg px-2.5 py-1"
          title={s.date ? fmtShort(s.date.slice(0, 10)) : undefined}
          style={s.wickets >= 3
            ? { background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }
            : { background: 'var(--pb-surface2)' }}>
          {s.wickets}/{s.runs}
        </span>
      ))}
    </div>
  )
}

export default function SeasonDashboard({ data }) {
  const s = data.season
  if (!s) {
    return (
      <Section title="Your season">
        <Muted data-no-season>No games recorded for you yet.</Muted>
      </Section>
    )
  }
  // A page from before the panels existed sends only the flat figures.
  const bat = s.batting || {}
  const bowl = s.bowling || {}
  const field = s.fielding || {}
  const form = s.form || { batting: [], bowling: [] }
  const batted = (bat.innings || 0) > 0 || s.runs > 0
  const bowled = (bowl.overs || 0) > 0 || s.wickets > 0
  const fielded = (field.catches || 0) + (field.run_outs || 0) + (field.stumpings || 0) > 0
  return (
    <Section title={s.season ? `Your season: ${s.season}` : 'Your season'} className="relative">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="font-display font-bold text-[30px] leading-none" data-season-matches>{s.matches}</span>
        <span className="text-sm text-pb-dim">{s.matches === 1 ? 'match' : 'matches'}</span>
        {data.player?.profile_path && (
          <a href={data.player.profile_path} className="ml-auto text-[12.5px] font-semibold shrink-0" style={{ color: 'var(--pb-accent)' }}>Full stats →</a>
        )}
      </div>

      {batted && (
        <Panel title="Batting" id="batting">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Runs" value={s.runs} />
            <Stat label="Average" value={dash(s.batting_average)} />
            <Stat label="Strike rate" value={<Rate value={bat.strike_rate} partial={bat.strike_rate_partial} />} />
            <Stat label="High score" value={dash(s.high_score)} />
            <Stat label="50s / 100s" value={`${bat.fifties || 0} / ${bat.hundreds || 0}`} />
            <Stat label="4s / 6s" value={`${bat.fours || 0} / ${bat.sixes || 0}`} />
          </div>
        </Panel>
      )}

      {bowled && (
        <Panel title="Bowling" id="bowling">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Wickets" value={s.wickets} />
            <Stat label="Economy" value={<Rate value={bowl.economy} partial={bowl.economy_partial} />} />
            <Stat label="Average" value={dash(bowl.average)} />
            <Stat label="Best" value={s.best_bowling || '-'} />
            <Stat label="Overs" value={dash(bowl.overs)} />
            <Stat label="Maidens" value={dash(bowl.maidens)} />
          </div>
        </Panel>
      )}

      {fielded && (
        <Panel title="Fielding" id="fielding">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Catches" value={field.catches || 0} />
            <Stat label="Run outs" value={field.run_outs || 0} />
            <Stat label="Stumpings" value={field.stumpings || 0} />
          </div>
        </Panel>
      )}

      {form.batting.length > 0 && (
        <Panel title={`Last ${form.batting.length} innings`} id="form-batting">
          <BattingForm innings={form.batting} />
        </Panel>
      )}
      {form.bowling.length > 0 && (
        <Panel title={`Last ${form.bowling.length} spells`} id="form-bowling">
          <BowlingForm spells={form.bowling} />
        </Panel>
      )}

      <div className="text-[11.5px] text-pb-faintest mt-3">
        {s.auto_shown ? 'Counts the grades you have played. ' : 'Counts the grade types your club shows in its public stats. '}
        Your latest season with games. Last innings and spells count every grade you play for the club.
        {(bat.strike_rate_partial || bowl.economy_partial) ? ' † rests on the innings with balls recorded.' : ''}
      </div>
    </Section>
  )
}
