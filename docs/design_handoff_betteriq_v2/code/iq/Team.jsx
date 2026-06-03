/* BetterIQ — Team analysis: the opposition lens, pointed at us. */
const { useState: useStateTm } = React;

function WinLoseList({ items, tone }) {
  const color = tone === 'win' ? 'var(--pb-brand)' : 'var(--pb-red)';
  const glyph = tone === 'win' ? '▲' : '▼';
  return <ul className="space-y-2.5">{items.map((b, i) => <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug"><span style={{ color }}>{glyph}</span><span>{b}</span></li>)}</ul>;
}

function SeasonCompare({ season }) {
  const span = SEASONS_CHRON.filter((s, i) => {
    const lo = Math.min(SEASONS_CHRON.indexOf(season.from), SEASONS_CHRON.indexOf(season.to));
    const hi = Math.max(SEASONS_CHRON.indexOf(season.from), SEASONS_CHRON.indexOf(season.to));
    return i >= lo && i <= hi;
  });
  const wp = IQ_TEAM.season_winpct;
  const first = wp[span[0]], last = wp[span[span.length - 1]];
  const max = Math.max(...span.map(s => wp[s]));
  return (
    <Card accent eyebrow={`comparing ${span.length} seasons`} title="Win rate over time"
      right={<Delta value={last - first} suffix="pts" />}>
      <div className="flex items-end gap-3 h-32 mt-1">
        {span.map((s, i) => (
          <div key={s} className="flex-1 flex flex-col items-center justify-end h-full">
            <span className="iq-num font-bold text-[14px] mb-1">{wp[s]}%</span>
            <div className="w-full" style={{ height: `${(wp[s] / max) * 100}%`, minHeight: 10, borderRadius: '6px 6px 0 0',
              background: i === span.length - 1 ? 'var(--pb-accent)' : 'color-mix(in srgb, var(--pb-accent) 42%, var(--pb-surface3))',
              animation: `iq-grow .7s cubic-bezier(.22,.61,.36,1) ${i * 0.07}s both`, transformOrigin: 'bottom' }} />
            <span className="iq-mono mt-2 text-pb-faint" style={{ fontSize: 10 }}>{s.slice(2)}</span>
            <span className="iq-mono text-pb-faintest" style={{ fontSize: 9 }}>{IQ_TEAM.season_record[s]}</span>
          </div>
        ))}
      </div>
      <Note>A clear upward trajectory — win rate has climbed every season across the selected range.</Note>
    </Card>
  );
}

function TeamOverview({ o, season }) {
  const isRange = season && season.mode === 'range';
  return (
    <div className="space-y-5">
      {isRange && <SeasonCompare season={season} />}
      <div className="grid gap-5 lg:grid-cols-[auto_1fr] items-stretch">
        <Card className="flex items-center justify-center">
          <div className="flex flex-col items-center px-4">
            <Gauge value={o.record.win_pct} size={130} label="Win rate" />
            <div className="iq-num text-pb-faint text-[12.5px] mt-2">{o.record.won}–{o.record.lost} from {o.record.played}</div>
          </div>
        </Card>
        <div className="grid gap-5 sm:grid-cols-2">
          <Card eyebrow="patterns" title="How we win"><WinLoseList items={o.win} tone="win" /></Card>
          <Card eyebrow="patterns" title="How we lose"><WinLoseList items={o.lose} tone="loss" /></Card>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="approach" title="Bat first vs chase">
          <div className="flex items-end gap-8 mb-4">
            <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{o.bat_first.won}/{o.bat_first.played}</div><div className="iq-eyebrow mt-1.5">Batting first</div></div>
            <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-amber)' }}>{o.chase.won}/{o.chase.played}</div><div className="iq-eyebrow mt-1.5">Chasing</div></div>
          </div>
          <div className="text-pb-dim text-[13px] leading-relaxed">We're markedly stronger setting a total — win first, bat first.</div>
        </Card>
        <Card eyebrow="what score wins" title={`Par: ${o.par}`}>
          <div className="space-y-2.5">
            {o.bands.map((b, i) => (
              <div key={b.band} className="flex items-center gap-3 text-[13px]">
                <span className="iq-mono text-pb-faint w-16 shrink-0">{b.band}</span>
                <div className="flex-1"><Bar pct={b.win} color={b.win >= 70 ? 'var(--pb-brand)' : b.win >= 45 ? 'var(--pb-amber)' : 'var(--pb-red)'} delay={i * 0.06} h={10} /></div>
                <span className="iq-num w-10 text-right font-semibold shrink-0">{b.win}%</span>
              </div>
            ))}
          </div>
          <Note>{o.par_note}</Note>
        </Card>
      </div>

      <Card eyebrow="home vs away" title="By venue">
        <div className="grid sm:grid-cols-2 gap-4">
          {o.venues.map(v => (
            <div key={v.venue}>
              <div className="flex items-center justify-between mb-1.5"><span className="text-[13.5px]">{v.venue}</span><span className="iq-num text-[13px]" style={{ color: v.w > v.l ? 'var(--pb-brand)' : 'var(--pb-red)' }}>{v.w}–{v.l}<span className="text-pb-faintest">/{v.p}</span></span></div>
              <Bar pct={(v.w / v.p) * 100} color={v.w > v.l ? 'var(--pb-brand)' : 'var(--pb-red)'} h={7} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TeamBatting({ b }) {
  const max = Math.max(...b.partnerships.map(p => p.avg));
  const ord = k => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`);
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-3">
        <Card eyebrow="profile" title="Team batting"><div className="grid grid-cols-1 gap-3"><Stat label="Avg score" value={b.profile.avg_score} /><KV label="Run rate" value={b.profile.run_rate} /><KV label="Top-4 share" value={`${b.profile.top4_share}%`} /></div></Card>
        <Card eyebrow="conversion" title="Our starts"><div className="grid grid-cols-1 gap-3"><Stat label="Reach 20" value={b.starts.reached20} count={false} /><KV label="Converted to 50" value={b.starts.converted50} /></div></Card>
        <Card eyebrow="partnerships" title="Avg by wicket">
          <div className="space-y-1.5">
            {b.partnerships.map((p, i) => (
              <div key={p.w} className="flex items-center gap-2 text-[12px]"><span className="iq-mono text-pb-faint w-6 shrink-0">{ord(p.w)}</span><div className="flex-1"><Bar pct={(p.avg / max) * 100} delay={i * 0.05} h={7} /></div><span className="iq-num w-7 text-right shrink-0">{p.avg}</span></div>
            ))}
          </div>
        </Card>
      </div>
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="our most productive" title="Best partnership pairs">
          <div className="space-y-3">
            {b.best_pairs.map(p => (
              <div key={p.pair} className="flex items-center justify-between gap-3"><span className="font-semibold text-[14px]">{p.pair}</span><span className="iq-num text-pb-dim text-[13px]">avg {p.avg} · {p.runs} runs</span></div>
            ))}
          </div>
        </Card>
        <Card accent eyebrow="the recurring wobble" title="Collapse analysis"><div className="text-[14px] leading-relaxed">{b.collapse}</div></Card>
      </div>
    </div>
  );
}

function TeamBowling({ b }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-3">
        <Card eyebrow="summary" title="Attack overall"><div className="grid grid-cols-1 gap-3"><Stat label="Bowling avg" value={b.summary.avg} decimals={2} count={false} /><KV label="Economy" value={b.summary.econ} /><KV label="Strike rate" value={b.summary.sr} /></div></Card>
        <Card eyebrow="discipline" title="Extras"><div className="grid grid-cols-1 gap-3"><Stat label="Extras / innings" value={b.discipline.extras_per_inns} decimals={1} count={false} /><KV label="Wides" value={b.discipline.wides} /><KV label="No-balls" value={b.discipline.no_balls} /></div></Card>
        <Card eyebrow="wicket-taking" title="Quality"><div className="grid grid-cols-1 gap-3"><Stat label="Top-order wkts" value={b.wickets.top_order} count={false} /><KV label="Bowled / lbw" value={b.wickets.bowled_lbw} /></div></Card>
      </div>
      <Card eyebrow="who does what" title="Attack structure">
        <div className="space-y-3">
          {b.attack.map((a, i) => (
            <div key={a.name} className="flex items-center gap-3">
              <Initials name={a.name} size={34} />
              <div className="min-w-0 flex-1"><div className="flex items-center justify-between"><span className="font-semibold text-[14px]">{a.name}</span><span className="iq-num text-pb-faint text-[12px]">{a.share}% of wkts</span></div><div className="text-pb-faint text-[11.5px] mb-1">{a.role}</div><Bar pct={a.share * 2.5} delay={i * 0.06} h={6} /></div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TeamPlayers({ p }) {
  return (
    <div className="grid gap-5 lg:grid-cols-3 items-start">
      <Card eyebrow="leadership" title="Captaincy">
        {p.captaincy.map(c => (
          <div key={c.name}><div className="flex items-baseline justify-between"><span className="font-semibold text-[14px]">{c.name}</span><span className="iq-num font-bold" style={{ color: 'var(--pb-brand)' }}>{c.as_capt}</span></div><div className="text-pb-dim text-[12.5px] mt-1">{c.note}</div></div>
        ))}
      </Card>
      <Card eyebrow="role-adjusted" title="All-rounders">
        <div className="space-y-3">
          {p.all_rounders.map((a, i) => (
            <div key={a.name} className="flex items-center gap-3"><Initials name={a.name} size={32} /><div className="flex-1"><div className="flex items-center justify-between"><span className="font-semibold text-[13.5px]">{a.name}</span><span className="iq-num font-bold text-[13px]" style={{ color: 'var(--pb-accent)' }}>{a.rating}</span></div><Bar pct={a.rating} delay={i * 0.06} h={5} /></div></div>
          ))}
        </div>
      </Card>
      <Card eyebrow="in the field" title="Top fielders">
        <div className="space-y-2.5">
          {p.fielders.map(f => (
            <div key={f.name} className="flex items-center justify-between gap-2"><span className="font-medium text-[13.5px]">{f.name}</span><span className="iq-num text-pb-dim text-[12px]">{f.label}</span></div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TeamAnalysis({ ctx }) {
  const t = IQ_TEAM;
  const [tab, setTab] = useStateTm('overview');
  const tabs = [{ value: 'overview', label: 'Overview' }, { value: 'batting', label: 'Batting' }, { value: 'bowling', label: 'Bowling' }, { value: 'players', label: 'Players' }];
  const season = ctx ? ctx.season : null;
  return (
    <div className="iq-fade">
      <PageIntro>Everything you point at an opponent, pointed at us — how Applecross actually wins and loses. Use the season filter above to compare across years.</PageIntro>

      <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={tabs} /></div>
      {tab === 'overview' && <TeamOverview o={t.overview} season={season} />}
      {tab === 'batting' && <TeamBatting b={t.batting} />}
      {tab === 'bowling' && <TeamBowling b={t.bowling} />}
      {tab === 'players' && <TeamPlayers p={t.players} />}
    </div>
  );
}

Object.assign(window, { TeamAnalysis });
