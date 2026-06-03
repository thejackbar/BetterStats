/* BetterIQ — Match preview: a fast pre-game one-pager (instant data only). */
const { useState: useStatePv } = React;

function PerfStat({ value, unit, avg }) {
  return (
    <div className="text-right shrink-0">
      <div className="iq-num font-semibold text-[15px] leading-none">{value}<span className="text-pb-faint font-normal text-[11px] ml-1">{unit}</span></div>
      <div className="iq-num text-pb-faint text-[11px] mt-1">avg {Number(avg).toFixed(2)}</div>
    </div>
  );
}

function PvFixtureBar({ onScout, onCheatSheet }) {
  const p = IQ_PREVIEW;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div className="flex items-center gap-4 flex-wrap">
        <span className="iq-headline" style={{ fontSize: 'clamp(24px,3vw,34px)' }}>vs {p.opponent}</span>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-pb-dim">
          <span className="inline-flex items-center gap-1.5"><Icon name="fixtures" size={14} className="text-pb-faint" />{p.when}</span>
          <span className="inline-flex items-center gap-1.5"><Icon name="target" size={14} className="text-pb-faint" />{p.home_away} · {p.venue}</span>
          <span className="iq-mono text-pb-faint">{p.grade}</span>
        </div>
      </div>
      <div className="flex items-center gap-2.5">
        <Btn variant="ghost" sm icon="print" onClick={onCheatSheet}>Cheat sheet</Btn>
        <Btn variant="primary" sm icon="search" onClick={() => onScout({ opp_key: 'melville', opponent_name: 'Melville' })}>Full scout</Btn>
      </div>
    </div>
  );
}

function Ladder({ rows, context }) {
  return (
    <Card eyebrow="grade ladder" title="Where we sit">
      <div className="overflow-x-auto iq-scroll -mx-1">
        <table className="w-full text-[13.5px]">
          <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
            <th className="py-1.5 px-2 font-medium text-center">#</th><th className="py-1.5 px-2 font-medium">Club</th>
            <th className="py-1.5 px-2 font-medium text-right">P</th><th className="py-1.5 px-2 font-medium text-right">W</th>
            <th className="py-1.5 px-2 font-medium text-right">L</th><th className="py-1.5 px-2 font-medium text-right">Pts</th>
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.team} style={{ borderTop: '1px solid var(--pb-hairline)', background: r.us ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : 'transparent' }}>
                <td className="py-2.5 px-2 text-center iq-num font-semibold" style={{ color: r.us ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>{r.pos}</td>
                <td className="py-2.5 px-2 font-semibold">{r.team} {r.us && <Tag tone="accent" className="ml-1">Us</Tag>}</td>
                <td className="py-2.5 px-2 text-right iq-num text-pb-faint">{r.played}</td>
                <td className="py-2.5 px-2 text-right iq-num">{r.won}</td>
                <td className="py-2.5 px-2 text-right iq-num">{r.lost}</td>
                <td className="py-2.5 px-2 text-right iq-num font-bold">{r.pts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-pb-dim text-[12.5px] mt-3">{context}</div>
    </Card>
  );
}

function Preview({ onScout, onNavigate, onCheatSheet }) {
  const p = IQ_PREVIEW, h2h = IQ_REPORT.head_to_head, lm = IQ_REPORT.last_meeting;
  const danger = IQ_DOSSIER.danger_batters.slice(0, 2).concat(IQ_DOSSIER.danger_bowlers.slice(0, 1));
  const edge = [...IQ_REPORT.our_performers.batting.slice(0, 2), ...IQ_REPORT.our_performers.bowling.slice(0, 1)];
  return (
    <div className="iq-fade">
      <PageIntro>A 60-second read before the game — the essentials, fast. For the full dossier (danger men, match-ups, game plan) open the scout.</PageIntro>
      <PvFixtureBar onScout={onScout} onCheatSheet={onCheatSheet} />

      <div className="space-y-5">
        {/* The lean */}
        <Card accent eyebrow="The lean" title="What matters on Saturday" right={<Tag tone="accent">Synthesised</Tag>}>
          <ul className="space-y-3">
            {p.lean.map((l, i) => (
              <li key={i} className="flex gap-3 text-[14.5px] leading-snug">
                <span className="iq-num shrink-0 font-bold" style={{ color: 'var(--pb-accent)', width: 18 }}>{i + 1}</span>
                <span>{l}</span>
              </li>
            ))}
          </ul>
        </Card>

        {/* Ladder + H2H */}
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          <Ladder rows={p.ladder} context={p.ladder_context} />
          <Card eyebrow={`${h2h.meetings} meetings`} title="Head-to-head">
            <div className="flex items-end gap-6">
              <div><div className="iq-headline iq-num" style={{ fontSize: 40, color: 'var(--pb-brand)' }}><CountUp value={h2h.wins} /></div><div className="iq-eyebrow mt-1.5">Won</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 40, color: 'var(--pb-red)' }}><CountUp value={h2h.losses} /></div><div className="iq-eyebrow mt-1.5">Lost</div></div>
              <div className="ml-auto flex flex-col items-end gap-1.5"><div className="iq-eyebrow">Recent</div><ResultPills form={h2h.recent_form} size={20} /></div>
            </div>
            <div className="mt-4"><SplitBar h={10} segments={[{ label: 'W', value: h2h.wins, color: 'var(--pb-brand)' }, { label: 'L', value: h2h.losses, color: 'var(--pb-red)' }, { label: 'D', value: h2h.draws + h2h.ties, color: 'var(--pb-amber)' }]} /></div>
            <div className="mt-4 pt-4 text-[13px]" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <span className="text-pb-faint">Last meeting:</span> <span className="font-semibold" style={{ color: 'var(--pb-brand)' }}>{lm.result}</span> <span className="iq-num text-pb-dim">· {lm.our_runs} vs {lm.opp_runs} · {lm.played_at}</span>
            </div>
          </Card>
        </div>

        {/* Danger + edge */}
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          <Card eyebrow="watch them" title="Their danger players" right={<Btn variant="ghost" sm onClick={() => onScout({ opp_key: 'melville', opponent_name: 'Melville' })}>Full scout</Btn>}>
            <div className="space-y-2.5">
              {danger.map(d => (
                <div key={d.player_id} className="flex items-center justify-between gap-3 py-1">
                  <div className="flex items-center gap-3 min-w-0"><Initials name={d.name} size={32} /><span className="font-semibold truncate">{d.name}</span></div>
                  <PerfStat value={d.runs || d.wickets} unit={d.runs ? 'runs' : 'wkts'} avg={d.average} />
                </div>
              ))}
            </div>
          </Card>
          <Card eyebrow="our edge" title="Players who own this match-up">
            <div className="space-y-2.5">
              {edge.map(e => (
                <div key={e.player_id} className="flex items-center justify-between gap-3 py-1">
                  <div className="flex items-center gap-3 min-w-0"><Initials name={e.name} size={32} tone="accent" /><span className="font-semibold truncate">{e.name}</span></div>
                  <PerfStat value={e.runs || e.wickets} unit={e.runs ? 'runs' : 'wkts'} avg={e.average} />
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Par callout */}
        <Card eyebrow="set the target" title="Par at this ground">
          <div className="flex items-center gap-5 flex-wrap">
            <div className="iq-headline iq-num" style={{ fontSize: 'clamp(40px,5vw,60px)', color: 'var(--pb-accent)' }}><CountUp value={p.par.score} /></div>
            <div className="text-pb-dim text-[13.5px] max-w-sm leading-relaxed">{p.par.note} Bat first if you win the toss — they've only chased 230+ twice all season.</div>
          </div>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Preview });
