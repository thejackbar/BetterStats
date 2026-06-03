/* BetterIQ — Player trends: form movers + a summary-first deep dive (tabbed). */
const { useState: useStateTr } = React;

function MoverList({ title, tone, items, metric }) {
  const color = tone === 'up' ? 'var(--pb-brand)' : 'var(--pb-red)';
  return (
    <div>
      <div className="iq-eyebrow mb-2.5" style={{ color }}>{title}</div>
      <div className="space-y-2">
        {items.map(p => (
          <div key={p.id} className="flex items-center justify-between gap-2">
            <span className="font-medium text-[13.5px] truncate">{p.name}</span>
            <span className="flex items-center gap-2 shrink-0">
              <span className="iq-num text-pb-faint text-[12px] whitespace-nowrap">{Number(p.was).toFixed(2)}→{Number(p.now).toFixed(2)}</span>
              <Delta value={p.metric === 'avg' ? -p.delta : p.delta} decimals={2} />
            </span>
          </div>
        ))}
        {!items.length && <Empty>—</Empty>}
      </div>
    </div>
  );
}

function TrendSummary({ pl }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <Initials name={pl.name} size={56} tone="accent" />
        <div>
          <h2 className="iq-headline" style={{ fontSize: 30 }}>{pl.name}</h2>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-pb-faint text-[13px] whitespace-nowrap">{pl.role}</span>
            {pl.verdict.map(v => <Tag key={v} tone="accent">{v}</Tag>)}
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr] items-start">
        <Card eyebrow="this season" title="Season">
          <div className="grid grid-cols-3 gap-4">
            <Stat label="Runs" value={pl.season.runs} big />
            <Stat label="Average" value={pl.season.avg} decimals={2} count={false} />
            <Stat label="Strike rate" value={pl.season.sr} count={false} />
          </div>
          <div className="mt-5 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
            <div className="flex items-center justify-between mb-1"><span className="iq-eyebrow" style={{ fontSize: 9 }}>Last 5 innings</span><span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{pl.form5.join('  ')}</span></div>
            <Sparkline key={pl.id} values={pl.form5} h={50} dots />
          </div>
        </Card>
        <Card eyebrow="whole career" title="Career">
          <div className="grid grid-cols-3 gap-y-4 gap-x-3">
            <Stat label="Matches" value={pl.career.matches} /><Stat label="Runs" value={pl.career.runs} /><Stat label="Average" value={pl.career.avg} decimals={2} count={false} />
            <Stat label="100s" value={pl.career.hundreds} /><Stat label="50s" value={pl.career.fifties} /><Stat label="High score" value={pl.career.hs} />
          </div>
        </Card>
      </div>
    </div>
  );
}

function SeasonByseason({ seasons, season }) {
  const inSpan = yr => {
    if (!season || season.mode !== 'range') return true;
    const idx = SEASONS_CHRON.findIndex(s => s.slice(2) === yr);
    const lo = Math.min(SEASONS_CHRON.indexOf(season.from), SEASONS_CHRON.indexOf(season.to));
    const hi = Math.max(SEASONS_CHRON.indexOf(season.from), SEASONS_CHRON.indexOf(season.to));
    return idx >= lo && idx <= hi;
  };
  const isRange = season && season.mode === 'range';
  const spanRows = seasons.filter(s => inSpan(s.yr));
  const dRuns = spanRows.length > 1 ? spanRows[spanRows.length - 1].runs - spanRows[0].runs : 0;
  const dAvg = spanRows.length > 1 ? spanRows[spanRows.length - 1].avg - spanRows[0].avg : 0;
  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start">
      <Card eyebrow="runs per season" title="Trajectory"
        right={isRange && <Delta value={dRuns} suffix=" runs" />}>
        <AreaChart points={seasons.map(s => s.runs)} labels={seasons.map(s => s.yr)} h={190} yLabel="runs" />
        {isRange
          ? <Note>Over {seasonLabel(season)}: <b style={{ color: 'var(--pb-text)' }}>{dRuns >= 0 ? '+' : ''}{dRuns} runs</b> and <b style={{ color: 'var(--pb-text)' }}>{dAvg >= 0 ? '+' : ''}{dAvg.toFixed(2)} average</b> across the range.</Note>
          : <Note>Five seasons of steady climb — a player still trending up, not plateauing.</Note>}
      </Card>
      <Card eyebrow="the numbers" title="Season by season">
        <div className="space-y-0.5">
          <div className="grid grid-cols-[1fr_auto_auto] gap-4 iq-eyebrow pb-2" style={{ fontSize: 9 }}>
            <span>Season</span><span className="text-right w-12">Runs</span><span className="text-right w-12">Avg</span>
          </div>
          {seasons.map(s => {
            const on = inSpan(s.yr);
            return (
              <div key={s.yr} className="grid grid-cols-[1fr_auto_auto] gap-4 items-center py-2 text-[13.5px]" style={{ borderTop: '1px solid var(--pb-hairline)', opacity: on ? 1 : 0.4 }}>
                <span className="iq-mono text-pb-dim flex items-center gap-2">{s.yr}{on && isRange && <span style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--pb-accent)' }} />}</span>
                <span className="iq-num text-right w-12 font-semibold">{s.runs}</span>
                <span className="iq-num text-right w-12 text-pb-dim">{s.avg.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function DeepDive({ pl }) {
  const d = pl.deep;
  const radar = radarFor(pl.id);
  return (
    <div className="grid gap-5 lg:grid-cols-2 items-start">
      {radar && (
        <Card eyebrow="profile vs grade average" title="Player radar">
          <div className="flex flex-col items-center">
            <Radar axes={radar.axes} values={radar.values} baseline={[50, 50, 50, 50, 50, 50]} size={250} />
            <div className="flex items-center gap-4 mt-2 text-[11.5px]">
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: 'var(--pb-accent)', borderRadius: 2 }} />{surname(pl.name)}</span>
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 0, borderTop: '1.5px dashed var(--pb-faint)' }} />Grade average</span>
            </div>
          </div>
          <Note>Each axis normalised 0–100 against the grade average (the dashed ring at 50).</Note>
        </Card>
      )}
      <Card eyebrow="career shape" title="Form & reliability">
        <div className="grid grid-cols-3 gap-3 mb-5">
          {[['Peak', pl.shape.peak], ['Consistency', pl.shape.consistency], ['Trend', pl.shape.trend]].map(([k, v]) => (
            <div key={k}><div className="iq-eyebrow" style={{ fontSize: 8.5 }}>{k}</div><div className="font-semibold text-[13.5px] mt-1.5 leading-tight">{v}</div></div>
          ))}
        </div>
        <div className="iq-eyebrow mb-2">Innings range (percentiles)</div>
        <div className="flex items-end gap-2 h-20">
          {[['Floor', d.reliability.floor], ['Median', d.reliability.median], ['Ceiling', d.reliability.ceiling]].map(([lab, v], i) => (
            <div key={lab} className="flex-1 flex flex-col items-center justify-end h-full">
              <span className="iq-num font-bold text-[15px] mb-1">{v}</span>
              <div className="w-full" style={{ height: `${(v / d.reliability.ceiling) * 100}%`, background: i === 1 ? 'var(--pb-accent)' : 'color-mix(in srgb, var(--pb-accent) 45%, var(--pb-surface3))', borderRadius: '6px 6px 0 0', minHeight: 8 }} />
              <span className="iq-eyebrow mt-1.5" style={{ fontSize: 8.5 }}>{lab}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card eyebrow="milestones" title="Closing in on">
        <div className="space-y-3">
          {pl.milestones.map(m => (
            <div key={m.label} className="flex items-center justify-between gap-3 py-1">
              <div className="min-w-0 flex-1"><div className="font-semibold text-[14px] leading-tight">{m.label}</div><div className="text-pb-faint text-[12px] mt-1">needs {m.need}</div></div>
              <Tag tone="accent" className="shrink-0">{m.eta}</Tag>
            </div>
          ))}
        </div>
      </Card>

      <Card eyebrow="how he scores" title="Starts & conversion">
        <div className="space-y-0.5">
          <KV label="50 → 100 conversion" value={d.conversion.fifties_to_100} />
          <KV label="Starts wasted (20–40)" value={d.conversion.starts_wasted} />
        </div>
        <div className="mt-4 iq-eyebrow mb-2">By situation</div>
        <div className="space-y-0.5">{d.situation.map(s => <KV key={s.k} label={s.k} value={s.v} />)}</div>
      </Card>

      <Card eyebrow="impact" title="Selection value & match-ups">
        <div className="flex items-end gap-6 mb-4">
          <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{d.win_value.with}</div><div className="iq-eyebrow mt-1">With him</div></div>
          <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}>{d.win_value.without}</div><div className="iq-eyebrow mt-1">Without</div></div>
        </div>
        <KV label="By position" value={d.by_position.map(p => `${p.k} ${p.v}`).join(' · ')} />
        <div className="mt-3 iq-eyebrow mb-1.5">Statistically similar</div>
        <div className="flex flex-wrap gap-2">{d.similar.map(s => <span key={s} className="text-[12.5px] px-2.5 py-1" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>{s}</span>)}</div>
      </Card>
    </div>
  );
}

function PlayerSelect({ value, onChange, options, color }) {
  const [open, setOpen] = useStateTr(false);
  const cur = options.find(o => o.id === value);
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-2.5 iq-display font-semibold transition"
        style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)', borderRadius: 10, padding: '8px 12px', fontSize: 13.5, color: 'var(--pb-text)' }}>
        <span style={{ width: 11, height: 11, borderRadius: 99, background: color }} className="shrink-0" />
        {surname(cur?.name || '')}
        <Icon name="chevron" size={14} className="text-pb-faint" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute z-30 mt-1.5 left-0 p-1.5 iq-card" style={{ minWidth: 180, boxShadow: 'var(--iq-card-shadow)' }}>
            {options.map(o => (
              <button key={o.id} onClick={() => { onChange(o.id); setOpen(false); }}
                className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8, background: o.id === value ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
                onMouseEnter={e => { if (o.id !== value) e.currentTarget.style.background = 'var(--pb-surface2)'; }}
                onMouseLeave={e => { if (o.id !== value) e.currentTarget.style.background = 'transparent'; }}>
                <span className="font-medium text-[13.5px]" style={{ color: o.id === value ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{o.name}</span>
                <span className="iq-mono text-pb-faint text-[11px]">{o.runs}r</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CompareRow({ label, a, b, better }) {
  // better: 'a' | 'b' | null
  const c = s => better === s ? 'var(--pb-brand)' : 'var(--pb-text)';
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="iq-num font-semibold text-right text-[15px]" style={{ color: c('a') }}>{a}</div>
      <div className="iq-eyebrow text-center" style={{ fontSize: 9, minWidth: 92 }}>{label}</div>
      <div className="iq-num font-semibold text-[15px]" style={{ color: c('b') }}>{b}</div>
    </div>
  );
}

function CompareView() {
  const opts = ['p1', 'p4', 'p6', 'p7'].map(id => IQ_SQUAD.find(p => p.id === id)).filter(Boolean);
  const [aId, setA] = useStateTr('p1');
  const [bId, setB] = useStateTr('p4');
  const A = IQ_SQUAD.find(p => p.id === aId), B = IQ_SQUAD.find(p => p.id === bId);
  const ra = radarFor(aId), rb = radarFor(bId);
  const cmp = (x, y) => x === y ? null : x > y ? 'a' : 'b';
  const rows = [
    { label: 'Runs', a: A.runs, b: B.runs, better: cmp(A.runs, B.runs) },
    { label: 'Average', a: A.bat_avg.toFixed(2), b: B.bat_avg.toFixed(2), better: cmp(A.bat_avg, B.bat_avg) },
    { label: 'Strike rate', a: A.sr, b: B.sr, better: cmp(A.sr, B.sr) },
    { label: '50s / 100s', a: `${A.fifties}/${A.hundreds || 0}`, b: `${B.fifties}/${B.hundreds || 0}`, better: cmp(A.fifties, B.fifties) },
    { label: 'Form avg (last 5)', a: A.formAvg.toFixed(2), b: B.formAvg.toFixed(2), better: cmp(A.formAvg, B.formAvg) },
    { label: 'vs Melville', a: A.vsOpp.replace('avg ', ''), b: B.vsOpp.replace('avg ', ''), better: null },
  ];
  const AMBER = 'var(--iq-c-amber)';
  return (
    <Card eyebrow="head to head" title="Compare players">
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 mb-5">
        <PlayerSelect value={aId} onChange={setA} options={opts} color="var(--pb-accent)" />
        <span className="iq-mono text-pb-faint text-[12px]">vs</span>
        <PlayerSelect value={bId} onChange={setB} options={opts} color={AMBER} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[auto_1fr] items-center">
        <div className="flex justify-center">
          {ra && rb && <Radar key={aId + bId} axes={ra.axes} values={ra.values} compareValues={rb.values} compareColor={AMBER} size={260} />}
        </div>
        <div>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pb-1">
            <div className="text-right font-bold iq-display truncate" style={{ color: 'var(--pb-accent)' }}>{surname(A.name)}</div>
            <div style={{ minWidth: 92 }} />
            <div className="font-bold iq-display truncate" style={{ color: AMBER }}>{surname(B.name)}</div>
          </div>
          {rows.map(r => <CompareRow key={r.label} {...r} />)}
        </div>
      </div>
      <Note>Greener figure is the stronger of the two. Radar axes normalised against the grade average.</Note>
    </Card>
  );
}

function Trends({ onNavigate, ctx }) {
  const m = IQ_TRENDS.movers;
  const pl = IQ_TRENDS.player;
  const [tab, setTab] = useStateTr('summary');
  const season = ctx ? ctx.season : null;
  return (
    <div className="iq-fade">
      <PageIntro>Who's rising, who's sliding, and the full statistical picture on any player — surfaced up front, not buried.</PageIntro>

      {/* Form movers — surfaced first */}
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr] items-start mb-9">
        <Card eyebrow="this season vs career-before-it" title="Form movers">
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-5">
            <MoverList title="Batting — rising" tone="up" items={m.bat_rising} />
            <MoverList title="Batting — sliding" tone="down" items={m.bat_falling} />
            <MoverList title="Bowling — improving" tone="up" items={m.bowl_rising} />
            <MoverList title="Bowling — slipping" tone="down" items={m.bowl_falling} />
          </div>
          <Note>Deltas compare this season to each player's career average before it. Lower bowling average = improving.</Note>
        </Card>
        <Card eyebrow="ones to watch" title="Emerging">
          <div className="space-y-3.5">
            {IQ_TRENDS.emerging.map(e => (
              <div key={e.id} className="flex gap-3">
                <Initials name={e.name} size={38} />
                <div><div className="font-semibold text-[14px]">{e.name} <span className="text-pb-faint font-normal text-[12px]">· {e.age}yo</span></div><div className="text-pb-dim text-[12.5px] mt-0.5 leading-snug">{e.note}</div></div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Player deep dive */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="iq-display font-bold text-[19px] whitespace-nowrap" style={{ letterSpacing: '-0.01em' }}>Player deep-dive</h2>
        <span className="text-pb-faint text-[12.5px] shrink-0">showing your most valuable bat</span>
      </div>

      <TrendSummary pl={pl} />

      <div className="mt-6 mb-5"><Tabs value={tab} onChange={setTab} tabs={[{ value: 'summary', label: 'Trajectory' }, { value: 'deep', label: 'Deep dive' }, { value: 'compare', label: 'Compare' }]} /></div>
      {tab === 'summary' && <SeasonByseason seasons={pl.seasons} season={season} />}
      {tab === 'deep' && <DeepDive pl={pl} />}
      {tab === 'compare' && <CompareView />}
    </div>
  );
}

Object.assign(window, { Trends });
