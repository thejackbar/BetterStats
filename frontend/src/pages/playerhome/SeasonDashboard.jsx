// "Your season": the player's latest season as three small panels (batting,
// bowling, fielding) and the form of their last few innings. Same grade scope and
// rate rules as their public profile; a rate that rests on only some of the
// innings carries a dagger, as it does there.
import { Muted, Section, fmtShort } from './ui'

const dash = (v) => (v === null || v === undefined ? '-' : v)

// A rate that counts only the innings with balls recorded gets a dagger.
function Rate({ value, partial }) {
  if (value === null || value === undefined) return '-'
  return partial ? <span title="Counts only the innings with balls recorded">{value}†</span> : value
}

// One figure over its label. No box of its own: the panel is the grouping, so the
// numbers read as a table rather than a wall of tiles.
function Fig({ label, children, lead = false }) {
  return (
    <div className="min-w-0">
      <div className={`font-display font-bold leading-none ${lead ? 'text-[24px]' : 'text-[17px]'}`}
        style={lead ? { color: 'var(--pb-accent)' } : undefined}>{children ?? '-'}</div>
      <div className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint mt-1 truncate">{label}</div>
    </div>
  )
}

// A discipline: its name down the left edge, its figures in a row (wrapping to a
// second row on a narrow phone) and a hairline above it.
function Panel({ title, id, children }) {
  return (
    <div data-season-panel={id} className="flex gap-3 py-3 border-t pb-hairline first:border-t-0 first:pt-0">
      <div className="w-[62px] shrink-0 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint pt-1">{title}</div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

const FIGS = 'grid grid-cols-3 gap-x-3 gap-y-3.5'

// The last few innings as bars, oldest on the left so the eye reads it as a trend.
// Not out gets a star; a duck is flagged. Height is runs against the best of the
// five, with a floor so a duck still draws something.
function BattingForm({ innings }) {
  const list = [...innings].reverse()
  const top = Math.max(20, ...list.map((i) => i.runs))
  return (
    <div className="flex items-end gap-1.5 h-[52px]" data-form-batting>
      {list.map((i, n) => {
        const h = Math.max(4, Math.round((i.runs / top) * 30))
        const tone = i.runs >= 50 ? 'var(--pb-positive)' : i.runs === 0 && !i.not_out ? 'var(--pb-red)' : 'var(--pb-accent)'
        return (
          <div key={`${i.date}-${n}`} className="flex-1 min-w-0 flex flex-col items-center justify-end gap-1"
            title={i.date ? fmtShort(i.date.slice(0, 10)) : undefined}>
            <span className="font-display font-bold text-[11.5px] leading-none">{i.runs}{i.not_out ? '*' : ''}</span>
            <span className="w-full max-w-[28px] rounded-t" style={{ height: h, background: tone }} />
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
        <span key={`${s.date}-${n}`} className="font-display font-bold text-[12.5px] rounded-md px-2 py-0.5"
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
  const partial = bat.strike_rate_partial || bowl.economy_partial
  return (
    <Section title={s.season ? `Your season: ${s.season}` : 'Your season'}>
      <div className="flex items-baseline gap-2 mb-3">
        <span className="font-display font-bold text-[26px] leading-none" data-season-matches>{s.matches}</span>
        <span className="text-[13px] text-pb-dim">{s.matches === 1 ? 'match' : 'matches'}</span>
        {data.player?.profile_path && (
          <a href={data.player.profile_path} className="ml-auto text-[12.5px] font-semibold shrink-0" style={{ color: 'var(--pb-accent)' }}>Full stats →</a>
        )}
      </div>

      {batted && (
        <Panel title="Batting" id="batting">
          <div className={FIGS}>
            <Fig label="Runs" lead>{s.runs}</Fig>
            <Fig label="Average">{dash(s.batting_average)}</Fig>
            <Fig label="Strike rate"><Rate value={bat.strike_rate} partial={bat.strike_rate_partial} /></Fig>
            <Fig label="High score">{dash(s.high_score)}</Fig>
            <Fig label="50s / 100s">{`${bat.fifties || 0} / ${bat.hundreds || 0}`}</Fig>
            <Fig label="4s / 6s">{`${bat.fours || 0} / ${bat.sixes || 0}`}</Fig>
          </div>
        </Panel>
      )}

      {bowled && (
        <Panel title="Bowling" id="bowling">
          <div className={FIGS}>
            <Fig label="Wickets" lead>{s.wickets}</Fig>
            <Fig label="Economy"><Rate value={bowl.economy} partial={bowl.economy_partial} /></Fig>
            <Fig label="Average">{dash(bowl.average)}</Fig>
            <Fig label="Best">{s.best_bowling || '-'}</Fig>
            <Fig label="Overs">{dash(bowl.overs)}</Fig>
            <Fig label="Maidens">{dash(bowl.maidens)}</Fig>
          </div>
        </Panel>
      )}

      {fielded && (
        <Panel title="Fielding" id="fielding">
          <div className="text-[13.5px] pt-0.5">
            <b>{field.catches || 0}</b> <span className="text-pb-dim">catches</span>
            <span className="text-pb-faint"> · </span><b>{field.run_outs || 0}</b> <span className="text-pb-dim">run outs</span>
            {(field.stumpings || 0) > 0 && <><span className="text-pb-faint"> · </span><b>{field.stumpings}</b> <span className="text-pb-dim">stumpings</span></>}
          </div>
        </Panel>
      )}

      {form.batting.length > 0 && (
        <Panel title="Form" id="form-batting">
          <div className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint mb-1.5">Last {form.batting.length} innings</div>
          <BattingForm innings={form.batting} />
        </Panel>
      )}
      {form.bowling.length > 0 && (
        <Panel title="Spells" id="form-bowling">
          <div className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint mb-1.5">Last {form.bowling.length} spells</div>
          <BowlingForm spells={form.bowling} />
        </Panel>
      )}

      <div className="text-[11px] text-pb-faintest mt-1 pt-2 border-t pb-hairline">
        {s.auto_shown ? 'Grades you have played' : 'Grade types your club shows publicly'}. Latest season with games. Form counts every grade.{partial ? ' † only innings with balls recorded.' : ''}
      </div>
    </Section>
  )
}
