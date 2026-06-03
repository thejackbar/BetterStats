/* BetterIQ — Overview screen */
const { useMemo: useMemoO } = React;

function HeroNextMatch({ fx, h2h, onScout }) {
  return (
    <div className="iq-card iq-accent-card overflow-hidden iq-rise">
      <div className="relative grid md:grid-cols-[1.4fr_1fr]">
        {/* Left: statement */}
        <div className="p-7 md:p-9">
          <div className="flex items-center gap-2 iq-eyebrow"><Icon name="bolt" size={13} style={{ color: 'var(--pb-accent)' }} />Your club's analytics brain</div>
          <h2 className="iq-headline mt-4" style={{ fontSize: 'clamp(30px,3.6vw,46px)', maxWidth: 560 }}>
            Read the game<br/>before it's played.
          </h2>
          <p className="text-pb-dim mt-4 leading-relaxed" style={{ maxWidth: 460, fontSize: 14.5 }}>
            The deep-dive most clubs — and plenty of pro teams — don't have. BetterIQ reads the data your club already holds and pulls opponent form live from the same source. No manual entry.
          </p>
          <div className="flex flex-wrap items-center gap-2.5 mt-6">
            <Btn variant="primary" icon="search" onClick={() => onScout(fx)}>Scout {fx.opponent_name}</Btn>
            <Btn variant="soft" icon="fixtures">Match preview</Btn>
          </div>
        </div>
        {/* Right: next fixture focus */}
        <div className="relative p-7 md:p-9 md:border-l" style={{ borderColor: 'var(--pb-hairline)', background: 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' }}>
          <div className="iq-eyebrow">Next fixture</div>
          <div className="flex items-baseline gap-2 mt-3">
            <span className="iq-mono text-pb-faint text-[13px]">vs</span>
            <span className="iq-headline" style={{ fontSize: 28 }}>{fx.opponent_name}</span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3 text-[13px] text-pb-dim">
            <span className="inline-flex items-center gap-1.5"><Icon name="fixtures" size={14} className="text-pb-faint" />{fx.played_on}</span>
            <span className="inline-flex items-center gap-1.5"><Icon name="target" size={14} className="text-pb-faint" />{fx.home_away} · {fx.venue}</span>
          </div>
          <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
            <div className="flex items-center justify-between">
              <div className="iq-eyebrow">Head-to-head</div>
              <div className="text-[11px] text-pb-faint iq-num">{h2h.meetings} meetings</div>
            </div>
            <div className="flex items-end gap-4 mt-2.5">
              <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}><CountUp value={h2h.wins} /></div><div className="iq-eyebrow mt-1">Won</div></div>
              <div className="text-pb-faintest pb-2 text-xl">–</div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}><CountUp value={h2h.losses} /></div><div className="iq-eyebrow mt-1">Lost</div></div>
              <div className="ml-auto flex flex-col items-end gap-1.5">
                <div className="iq-eyebrow">Recent</div>
                <ResultPills form={h2h.recent_form} size={20} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FixtureCard({ fx, onScout, i }) {
  const partial = fx.coverage !== 'rich';
  return (
    <button onClick={() => onScout(fx)}
      className="iq-card text-left p-4 transition group iq-rise hover:-translate-y-0.5"
      style={{ animationDelay: `${80 + i * 60}ms`, cursor: 'pointer' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
      <div className="flex items-center justify-between gap-2">
        <span className="iq-mono text-[10px] uppercase tracking-wider text-pb-faint">{fx.played_on}</span>
        <Tag tone={partial ? 'faint' : 'accent'}>{partial ? 'Partial' : 'History'}</Tag>
      </div>
      <div className="iq-display font-bold text-[18px] mt-2.5 leading-tight">{fx.opponent_name}</div>
      <div className="text-pb-faint text-[12px] mt-1">{fx.home_away} · {fx.venue}</div>
      <div className="flex items-center justify-between mt-3.5 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        <span className="iq-mono text-[10.5px] text-pb-faint">{fx.team}</span>
        <span className="inline-flex items-center gap-1 text-[12px] font-semibold transition-colors" style={{ color: 'var(--pb-accent)' }}>
          Scout <Icon name="arrow" size={13} className="transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </button>
  );
}

function MvpRow({ p, rank, max, onOpen }) {
  const pct = (p.score / max) * 100;
  const top = rank === 1;
  return (
    <button onClick={onOpen} className="w-full flex items-center gap-4 px-2 py-3 text-left transition rounded-xl hover:bg-pb-surface2 iq-rise"
      style={{ animationDelay: `${rank * 45}ms` }}>
      <div className="iq-headline iq-num shrink-0 text-center" style={{ width: 30, fontSize: top ? 22 : 18, color: top ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>{rank}</div>
      <div className="flex items-center justify-center shrink-0 iq-display font-bold"
        style={{ width: 38, height: 38, borderRadius: 10, fontSize: 12.5, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)', color: 'var(--pb-dim)' }}>
        {p.name.replace(/^[A-Z]\.\s*/, '').slice(0, 2).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="iq-display font-semibold text-[14.5px] truncate">{p.name}</span>
          <span className="iq-headline iq-num shrink-0" style={{ fontSize: 17, color: top ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{p.score}</span>
        </div>
        <div className="flex items-center gap-2.5 mt-1.5">
          <div className="flex-1"><Bar pct={pct} delay={rank * 0.05} color={top ? 'var(--pb-accent)' : 'color-mix(in srgb, var(--pb-accent) 55%, var(--pb-faint))'} h={5} /></div>
        </div>
        <div className="text-pb-faint text-[11.5px] mt-1.5 iq-num">{p.sub}</div>
      </div>
    </button>
  );
}

const CAPS = [
  { icon: 'search', title: 'Opposition analysis', desc: 'Full scouting dossiers — danger men, game plans, match-ups.', route: 'opposition' },
  { icon: 'selection', title: 'Selection analysis', desc: 'Check the balance of a saved XI and justify the pick.', route: 'selection' },
  { icon: 'trend', title: 'Player trends', desc: 'Form movers, development and statistical deep-dives.', route: 'trends' },
  { icon: 'teams', title: 'Team analysis', desc: 'How your club itself wins and loses, season by season.', route: 'team' },
];

function CapCard({ c, i, onNavigate }) {
  return (
    <button onClick={() => onNavigate(c.route)} className="iq-card text-left p-5 iq-rise transition w-full" style={{ animationDelay: `${i * 50}ms` }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
      <div className="flex items-center justify-between">
        <div className="flex items-center justify-center" style={{ width: 36, height: 36, borderRadius: 10, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', color: 'var(--pb-accent)' }}>
          <Icon name={c.icon} size={18} />
        </div>
        <Icon name="arrow" size={15} className="text-pb-faint" />
      </div>
      <div className="iq-display font-bold text-[15px] mt-3.5">{c.title}</div>
      <div className="text-pb-faint text-[12.5px] mt-1.5 leading-relaxed">{c.desc}</div>
    </button>
  );
}

function SectionHead({ children, sub }) {
  return (
    <div className="flex items-end justify-between gap-3 mb-4 mt-10">
      <h2 className="iq-display font-bold text-[19px]" style={{ letterSpacing: '-0.01em' }}>{children}</h2>
      {sub && <span className="text-pb-faint text-[12.5px]">{sub}</span>}
    </div>
  );
}

/* ── Club pulse: form + momentum trajectory ──────────────────────────────── */
function ClubPulse({ form, seasonLbl }) {
  const labels = form.points_curve.map((_, i) => (i % 3 === 0 ? `R${i + 1}` : ''));
  return (
    <Card eyebrow={`season ${seasonLbl || form.season}`} title="Club form" className="iq-rise"
      right={<Tag tone={form.streak.startsWith('Won') ? 'win' : 'red'}>{form.streak}</Tag>}>
      <div className="flex flex-wrap items-center gap-5">
        <DonutStat value={form.win_pct} label="Win rate" sub={`Ladder ${form.ladder_pos}/${form.ladder_total} · ▲${form.ladder_move}`} />
        <div className="flex-1 min-w-[140px]">
          <div className="iq-eyebrow mb-2">Last 10</div>
          <ResultPills form={form.last10} size={20} />
          <div className="text-pb-faint text-[12px] mt-2.5 iq-num">Net runs <span className="font-semibold" style={{ color: 'var(--pb-brand)' }}>{form.run_diff}</span> this season</div>
        </div>
      </div>
      <div className="mt-5 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        <div className="iq-eyebrow mb-1.5">Points trajectory</div>
        <AreaChart points={form.points_curve} labels={labels} h={140} yLabel="pts" />
      </div>
    </Card>
  );
}

/* ── This-week workflow loop ─────────────────────────────────────────────── */
const WEEK_STATE = {
  ready: { c: 'var(--pb-accent)', label: 'Ready' },
  attention: { c: 'var(--pb-amber)', label: 'Needs you' },
  upcoming: { c: 'var(--pb-faint)', label: 'Upcoming' },
  locked: { c: 'var(--pb-faintest)', label: 'After match' },
};
function WeeklyLoop({ steps, onNavigate }) {
  return (
    <Card eyebrow="your week" title="Match-week workflow" className="iq-rise" style={{ animationDelay: '60ms' }}>
      <div className="space-y-1">
        {steps.map((s, i) => {
          const st = WEEK_STATE[s.state];
          const clickable = !!s.route;
          return (
            <button key={i} disabled={!clickable} onClick={() => clickable && onNavigate(s.route)}
              className="w-full flex items-center gap-3.5 px-2 py-2.5 text-left transition" style={{ borderRadius: 10, cursor: clickable ? 'pointer' : 'default' }}
              onMouseEnter={e => { if (clickable) e.currentTarget.style.background = 'var(--pb-surface2)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}>
              <div className="relative flex flex-col items-center shrink-0">
                <span className="flex items-center justify-center iq-mono font-bold" style={{ width: 26, height: 26, borderRadius: 99, fontSize: 11, color: st.c, background: `color-mix(in srgb, ${st.c} 16%, transparent)`, border: `1px solid color-mix(in srgb, ${st.c} 40%, transparent)` }}>{i + 1}</span>
                {i < steps.length - 1 && <span style={{ position: 'absolute', top: 26, height: 18, width: 1.5, background: 'var(--pb-hairline2)' }} />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[14px]">{s.step}</div>
                <div className="text-pb-faint text-[12px]">{s.label}</div>
              </div>
              <span className="iq-mono shrink-0" style={{ fontSize: 9.5, padding: '2px 7px', borderRadius: 6, color: st.c, background: `color-mix(in srgb, ${st.c} 14%, transparent)` }}>{st.label}</span>
              {clickable && <Icon name="chevron" size={14} className="text-pb-faint shrink-0" />}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

/* ── Last result mini ────────────────────────────────────────────────────── */
function LastResult({ lm, onNavigate }) {
  const won = lm.result === 'WIN';
  const c = won ? 'var(--pb-brand)' : 'var(--pb-red)';
  return (
    <button onClick={() => onNavigate('review')} className="iq-card iq-accent-card text-left p-5 transition iq-rise w-full" style={{ animationDelay: '120ms' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
      <div className="flex items-center justify-between"><div className="iq-eyebrow">Last result</div><Icon name="chevron" size={15} className="text-pb-faint" /></div>
      <div className="flex items-baseline gap-2.5 mt-2.5">
        <span className="iq-headline" style={{ fontSize: 22, color: c }}>{lm.result}</span>
        <span className="iq-headline" style={{ fontSize: 20 }}>vs {IQ_REPORT.opponent.name}</span>
      </div>
      <div className="iq-num text-pb-dim text-[13px] mt-1.5">{lm.our_runs} vs {lm.opp_runs}</div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 pt-3 text-[12.5px]" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        <span><span className="text-pb-faint">Top bat</span> {lm.our_top_bat.name} <span className="iq-num font-semibold">{lm.our_top_bat.runs}</span></span>
        <span><span className="text-pb-faint">Top bowl</span> {lm.our_top_bowl.name} <span className="iq-num font-semibold">{lm.our_top_bowl.wickets}/{lm.our_top_bowl.runs}</span></span>
      </div>
    </button>
  );
}

/* ── Top movers teaser ───────────────────────────────────────────────────── */
function MoversTeaser({ onNavigate }) {
  const m = IQ_TRENDS.movers;
  const rows = [
    ...m.bat_rising.slice(0, 2).map(p => ({ ...p, dir: 'up', kind: 'bat' })),
    ...m.bowl_rising.slice(0, 1).map(p => ({ ...p, dir: 'up', kind: 'bowl' })),
    ...m.bat_falling.slice(0, 1).map(p => ({ ...p, dir: 'down', kind: 'bat' })),
  ];
  return (
    <Card eyebrow="form movers" title="Who's trending"
      right={<Btn variant="ghost" sm onClick={() => onNavigate('trends')}>All trends</Btn>}>
      <div className="space-y-1">
        {rows.map((p, i) => (
          <div key={p.id} className="flex items-center justify-between gap-3 px-2 py-2.5" style={{ borderRadius: 9, background: i % 2 ? 'transparent' : 'var(--pb-surface2)' }}>
            <div className="flex items-center gap-3 min-w-0"><Initials name={p.name} size={32} tone={p.dir === 'up' ? 'accent' : undefined} /><div className="min-w-0"><div className="font-semibold text-[13.5px] truncate">{p.name}</div><div className="text-pb-faint text-[11px]">{p.kind === 'bat' ? 'Batting avg' : 'Bowling avg'}</div></div></div>
            <Delta value={p.kind === 'bowl' ? -p.delta : p.delta} decimals={2} />
          </div>
        ))}
      </div>
    </Card>
  );
}

function Overview({ onScout, onNavigate, ctx }) {
  const maxMvp = useMemoO(() => Math.max(...IQ_MVP.map(m => m.score)), []);
  const nextFx = IQ_UPCOMING[0];
  const form = IQ_CLUB_FORM;
  const seasonLbl = ctx ? (typeof seasonLabel === 'function' ? seasonLabel(ctx.season) : ctx.season.to) : form.season;
  return (
    <div>
      <HeroNextMatch fx={nextFx} h2h={IQ_REPORT.head_to_head} onScout={onScout} />

      {/* Club pulse */}
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start mt-6">
        <ClubPulse form={form} seasonLbl={seasonLbl} />
        <div className="space-y-5">
          <LastResult lm={IQ_REPORT.last_meeting} onNavigate={onNavigate} />
          <WeeklyLoop steps={form.this_week} onNavigate={onNavigate} />
        </div>
      </div>

      <SectionHead sub="Tap to open a full dossier">Scout your next opponent</SectionHead>
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {IQ_UPCOMING.map((fx, i) => <FixtureCard key={fx.fixture_id} fx={fx} onScout={onScout} i={i} />)}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr] items-start">
        <div>
          <SectionHead sub="season impact · 0–100">Club MVPs</SectionHead>
          <Card>
            <div className="-mx-2 -my-1">
              {IQ_MVP.map((p, i) => <MvpRow key={p.player_id} p={p} rank={i + 1} max={maxMvp} onOpen={() => onNavigate('trends')} />)}
            </div>
            <Note>A blended whole-season value measure — runs, wickets, impact in results — not current form.</Note>
          </Card>
        </div>
        <div>
          <SectionHead sub="this season vs career">Form movers</SectionHead>
          <MoversTeaser onNavigate={onNavigate} />
          <SectionHead sub="jump in">Explore</SectionHead>
          <div className="grid gap-3.5 sm:grid-cols-2">
            {CAPS.map((c, i) => <CapCard key={c.title} c={c} i={i} onNavigate={onNavigate} />)}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Overview });
