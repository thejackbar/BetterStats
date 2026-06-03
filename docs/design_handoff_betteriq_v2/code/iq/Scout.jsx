/* BetterIQ — Opposition Scout (flagship). Picker → two-phase dossier report. */
const { useState: useStateS, useEffect: useEffectS, useMemo: useMemoS } = React;

function n2(v, d = '—') { return (v === null || v === undefined) ? d : v; }
function a2(v) { return (v === null || v === undefined) ? '—' : Number(v).toFixed(2); }

/* ── Picker ──────────────────────────────────────────────────────────────── */
function ScoutPicker({ onPick }) {
  const [q, setQ] = useStateS('');
  const filtered = useMemoS(() => {
    const t = q.trim().toLowerCase();
    return t ? IQ_OPPONENTS.filter(o => o.name.toLowerCase().includes(t)) : IQ_OPPONENTS;
  }, [q]);
  return (
    <div className="iq-fade">
      <div className="iq-eyebrow mb-3">Upcoming</div>
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4 mb-9">
        {IQ_UPCOMING.map((fx, i) => (
          <button key={fx.fixture_id} onClick={() => onPick({ opponent: fx.opp_key, name: fx.opponent_name, fixtureId: fx.fixture_id })}
            className="iq-card text-left p-4 transition group iq-rise hover:-translate-y-0.5" style={{ animationDelay: `${i * 55}ms` }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
            <div className="flex items-center justify-between"><span className="iq-mono text-[10px] uppercase tracking-wider text-pb-faint">{fx.played_on}</span><Tag tone={fx.coverage === 'rich' ? 'accent' : 'faint'}>{fx.coverage === 'rich' ? 'History' : 'Partial'}</Tag></div>
            <div className="iq-display font-bold text-[18px] mt-2.5">{fx.opponent_name}</div>
            <div className="text-pb-faint text-[12px] mt-1">{fx.home_away} · {fx.venue}</div>
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="iq-eyebrow">All opponents ({IQ_OPPONENTS.length})</div>
        <Search value={q} onChange={setQ} placeholder="Search opponents…" className="w-full max-w-xs" />
      </div>
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((o, i) => (
          <button key={o.opp_key} onClick={() => onPick({ opponent: o.opp_key, name: o.name })}
            className="iq-card text-left px-4 py-3.5 transition flex items-center justify-between gap-2 iq-rise" style={{ animationDelay: `${i * 30}ms` }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
            <div className="min-w-0">
              <div className="iq-display font-semibold truncate">{o.name}</div>
              <div className="text-pb-faint text-[11.5px] mt-0.5 iq-num">{o.meetings} meetings · last {o.last_played.slice(0, 4)}</div>
            </div>
            {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Command strip — the report hero ─────────────────────────────────────── */
function CommandStrip({ h2h, lm }) {
  const lmColor = lm.result === 'WIN' ? 'var(--pb-brand)' : lm.result === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-amber)';
  return (
    <div className="iq-card iq-accent-card overflow-hidden iq-rise">
      <div className="relative grid lg:grid-cols-[auto_1fr_auto]">
        {/* Gauge */}
        <div className="flex flex-col items-center justify-center p-6 md:p-7 lg:border-r" style={{ borderColor: 'var(--pb-hairline)' }}>
          <Gauge value={h2h.win_pct} size={138} label="Win rate" color="var(--pb-accent)" />
          <div className="text-pb-faint text-[11.5px] mt-2 iq-num">{h2h.meetings} meetings</div>
        </div>
        {/* W-L-D */}
        <div className="p-6 md:p-7 flex flex-col justify-center">
          <div className="iq-eyebrow mb-3">All-time record</div>
          <div className="flex items-end gap-6">
            <div><div className="iq-headline iq-num" style={{ fontSize: 'clamp(34px,4vw,48px)', color: 'var(--pb-brand)' }}><CountUp value={h2h.wins} /></div><div className="iq-eyebrow mt-1.5">Won</div></div>
            <div><div className="iq-headline iq-num" style={{ fontSize: 'clamp(34px,4vw,48px)', color: 'var(--pb-red)' }}><CountUp value={h2h.losses} /></div><div className="iq-eyebrow mt-1.5">Lost</div></div>
            <div><div className="iq-headline iq-num" style={{ fontSize: 'clamp(34px,4vw,48px)', color: 'var(--pb-amber)' }}><CountUp value={h2h.draws + h2h.ties} /></div><div className="iq-eyebrow mt-1.5">Drawn</div></div>
          </div>
          <div className="mt-4 max-w-md"><SplitBar h={10} segments={[{ label: 'Won', value: h2h.wins, color: 'var(--pb-brand)' }, { label: 'Lost', value: h2h.losses, color: 'var(--pb-red)' }, { label: 'Drawn', value: h2h.draws + h2h.ties, color: 'var(--pb-amber)' }]} /></div>
          <div className="flex items-center gap-3 mt-5">
            <span className="iq-eyebrow">Recent</span><ResultPills form={h2h.recent_form} size={22} />
            <span className="text-pb-faint text-[11.5px] ml-1">last 5 · most recent right</span>
          </div>
        </div>
        {/* Last meeting */}
        <div className="p-6 md:p-7 lg:border-l flex flex-col justify-center" style={{ borderColor: 'var(--pb-hairline)', background: 'color-mix(in srgb, var(--pb-accent) 4%, transparent)', minWidth: 220 }}>
          <div className="flex items-center justify-between"><div className="iq-eyebrow">Last meeting</div><span className="text-pb-faint text-[11px]">{lm.played_at}</span></div>
          <div className="iq-headline mt-2.5" style={{ fontSize: 30, color: lmColor }}>{lm.result}</div>
          <div className="iq-num text-pb-dim text-[13px] mt-1">{lm.our_runs} vs {lm.opp_runs}</div>
          <div className="text-[11.5px] text-pb-faintest mt-0.5">{lm.venue}</div>
          <div className="mt-3 pt-3 space-y-1 text-[12.5px]" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
            <div><span className="text-pb-faint">Top bat:</span> {lm.our_top_bat.name} <span className="iq-num font-semibold">{lm.our_top_bat.runs}</span></div>
            <div><span className="text-pb-faint">Top bowl:</span> {lm.our_top_bowl.name} <span className="iq-num font-semibold">{lm.our_top_bowl.wickets}/{lm.our_top_bowl.runs}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Game plan ───────────────────────────────────────────────────────────── */
function PlanTile({ label, name, sub, tone }) {
  const color = tone === 'remove' ? 'var(--pb-red)' : tone === 'see' ? 'var(--pb-amber)' : 'var(--pb-brand)';
  return (
    <div className="p-4" style={{ background: 'var(--pb-surface2)', borderRadius: 12, border: '1px solid var(--pb-hairline)' }}>
      <div className="iq-eyebrow" style={{ color }}>{label}</div>
      <div className="iq-display font-bold text-[16px] mt-2">{name || '—'}</div>
      {sub && <div className="text-pb-faint text-[11.5px] mt-1 leading-snug">{sub}</div>}
    </div>
  );
}
function GamePlan({ plan }) {
  return (
    <Card accent eyebrow="The game plan" title="How to beat them" right={<Tag tone="accent">Synthesised</Tag>}>
      <div className="iq-display font-bold text-[clamp(18px,2.2vw,24px)] leading-snug mb-5" style={{ letterSpacing: '-0.01em', maxWidth: 640 }}>{plan.one_liner}</div>
      <div className="grid sm:grid-cols-3 gap-3 mb-5">
        <PlanTile label="Remove early" tone="remove" name={plan.remove_early.name} sub={plan.remove_early.why} />
        <PlanTile label="See off" tone="see" name={plan.see_off.name} sub={plan.see_off.why} />
        <PlanTile label="Target" tone="target" name={plan.target_bowler.name} sub={`leaks at econ ${plan.target_bowler.economy}`} />
      </div>
      <div className="space-y-2 text-[13.5px]">
        <div className="flex gap-2.5"><Icon name="info" size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--pb-red)' }} /><span><span className="text-pb-faint">Watch:</span> {plan.key_warning}</span></div>
        <div className="flex gap-2.5"><Icon name="check" size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--pb-brand)' }} /><span><span className="text-pb-faint">Our edge:</span> Hartley (418 @ 52.3), Whitlock (19w @ 14.6) — both own this match-up.</span></div>
      </div>
      <Note>Synthesised from scorecards — a starting plan, not gospel.</Note>
    </Card>
  );
}

/* ── Our record + venue ──────────────────────────────────────────────────── */
function OurRecord({ performers }) {
  return (
    <Card eyebrow="Selection intel" title="Our record against them">
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <div className="iq-eyebrow mb-2.5">Bat well vs them</div>
          <div className="space-y-2">
            {performers.batting.map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-3">
                <span className={`text-[13.5px] whitespace-nowrap ${p.active ? '' : 'text-pb-faint'}`}>{p.name}{!p.active && ' ·'}</span>
                <span className="iq-num text-pb-dim text-[12.5px] whitespace-nowrap shrink-0">{p.runs} @ {a2(p.average)}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="iq-eyebrow mb-2.5">Bowl well vs them</div>
          <div className="space-y-2">
            {performers.bowling.map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-3">
                <span className={`text-[13.5px] whitespace-nowrap ${p.active ? '' : 'text-pb-faint'}`}>{p.name}{!p.active && ' ·'}</span>
                <span className="iq-num text-pb-dim text-[12.5px] whitespace-nowrap shrink-0">{p.wickets}w @ {a2(p.average)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="text-pb-faintest text-[11px] mt-4">· = no longer active</div>
    </Card>
  );
}
function VenueCard({ venues }) {
  return (
    <Card eyebrow="vs this opponent" title="By venue">
      <div className="space-y-3">
        {venues.map((v, idx) => {
          const losses = v.losses || 0;
          const tone = v.wins > losses ? 'var(--pb-brand)' : v.wins < losses ? 'var(--pb-red)' : 'var(--pb-amber)';
          const pct = (v.wins / v.played) * 100;
          return (
            <div key={idx}>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-[13px] truncate">{v.venue}</span>
                <span className="iq-num text-[12.5px] whitespace-nowrap" style={{ color: tone }}>{v.wins}–{losses}<span className="text-pb-faintest">/{v.played}</span></span>
              </div>
              <Bar pct={pct} color={tone} h={6} delay={idx * 0.08} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* ── Match-up heatmap ────────────────────────────────────────────────────── */
function Matchups({ matchups }) {
  const rows = matchups.bowler_dominance;
  const [view, setView] = useStateS('matrix');
  return (
    <Card eyebrow="our hold over their batters" title="Bowler match-ups"
      right={<Segmented sm value={view} onChange={setView} options={[{ value: 'matrix', label: 'Matrix' }, { value: 'list', label: 'List' }]} />}>
      <div className="text-pb-faint text-[12px] mb-3">Times our bowlers have dismissed their batters — a selection edge. Darker = stronger hold.</div>
      {view === 'matrix' ? <Heatmap rows={rows} /> : (
        <div className="overflow-x-auto iq-scroll -mx-1">
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
              <th className="py-1.5 px-1 font-medium">Our bowler</th><th className="py-1.5 px-1 font-medium">Their batter</th>
              <th className="py-1.5 px-1 font-medium text-right">Out</th><th className="py-1.5 px-1 font-medium">How</th><th className="py-1.5 px-1 font-medium text-right">Runs</th>
            </tr></thead>
            <tbody>
              {rows.map((m, idx) => (
                <tr key={idx} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <td className="py-2 px-1 font-medium">{m.bowler}</td><td className="py-2 px-1">{m.batter}</td>
                  <td className="py-2 px-1 text-right iq-num font-semibold">{m.dismissals}×</td>
                  <td className="py-2 px-1 text-pb-faint text-[11.5px] capitalize">{m.how.join(', ')}</td>
                  <td className="py-2 px-1 text-right iq-num text-pb-faint">{m.runs_made}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ── Win / lose ──────────────────────────────────────────────────────────── */
function WinLose({ win, lose }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card eyebrow="patterns" title="How they win">
        <ul className="space-y-2.5">{win.map((b, i) => <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug"><span style={{ color: 'var(--pb-brand)' }}>▲</span><span>{b}</span></li>)}</ul>
      </Card>
      <Card eyebrow="patterns" title="How they lose">
        <ul className="space-y-2.5">{lose.map((b, i) => <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug"><span style={{ color: 'var(--pb-red)' }}>▼</span><span>{b}</span></li>)}</ul>
      </Card>
    </div>
  );
}

/* ── Partnerships (where they wobble) ────────────────────────────────────── */
function Partnerships({ partnerships, insight }) {
  const max = Math.max(1, ...partnerships.map(p => p.avg_partnership));
  const ord = k => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`);
  return (
    <Card accent eyebrow="avg partnership by wicket" title="Where they wobble">
      <div className="space-y-2.5">
        {partnerships.map((p, idx) => {
          const weak = p.avg_partnership < 20;
          return (
            <div key={p.wicket} className="flex items-center gap-3 text-[13px]">
              <span className="w-7 text-pb-faint shrink-0 iq-mono text-[11px]">{ord(p.wicket)}</span>
              <div className="flex-1"><Bar pct={(p.avg_partnership / max) * 100} color={weak ? 'var(--pb-red)' : 'var(--pb-accent)'} h={9} delay={idx * 0.06} /></div>
              <span className="w-8 text-right iq-num shrink-0 font-semibold" style={{ color: weak ? 'var(--pb-red)' : 'var(--pb-text)' }}>{p.avg_partnership}</span>
            </div>
          );
        })}
      </div>
      <div className="text-pb-dim text-[12.5px] mt-4 leading-relaxed">{insight}</div>
    </Card>
  );
}

/* ── Squad tables ────────────────────────────────────────────────────────── */
function SquadTable({ dossier }) {
  const [tab, setTab] = useStateS('batting');
  const bat = dossier.batting, bowl = dossier.bowling;
  return (
    <Card eyebrow={`squad · ${dossier.selected_team_name}`} title="Their squad"
      right={<Segmented sm value={tab} onChange={setTab} options={[{ value: 'batting', label: 'Batting' }, { value: 'bowling', label: 'Bowling' }]} />}>
      <div className="overflow-x-auto iq-scroll -mx-1">
        {tab === 'batting' ? (
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
              <th className="py-2 px-1.5 font-medium">Batter</th><th className="py-2 px-1.5 font-medium text-right">Inns</th><th className="py-2 px-1.5 font-medium text-right">Runs</th>
              <th className="py-2 px-1.5 font-medium text-right">Avg</th><th className="py-2 px-1.5 font-medium text-right">SR</th><th className="py-2 px-1.5 font-medium text-right">HS</th>
              <th className="py-2 px-1.5 font-medium text-right">50/100</th><th className="py-2 px-1.5 font-medium text-right">vs us</th>
            </tr></thead>
            <tbody>
              {bat.map(p => (
                <tr key={p.player_id} style={{ borderTop: '1px solid var(--pb-hairline)' }} className="transition-colors hover:bg-pb-surface2">
                  <td className="py-2.5 px-1.5 font-medium whitespace-nowrap">{p.name} {p.form === 'hot' && <Icon name="flame" size={13} className="inline" style={{ color: 'var(--pb-red)' }} />}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{p.innings}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num font-semibold">{p.runs}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num">{a2(p.average)}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{n2(p.strike_rate)}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num">{n2(p.high_score)}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{p.fifties}/{p.hundreds}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-[11.5px]">{p.vs_us ? `${p.vs_us.runs}@${a2(p.vs_us.average)}` : <span className="text-pb-faintest">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
              <th className="py-2 px-1.5 font-medium">Bowler</th><th className="py-2 px-1.5 font-medium text-right">Ov</th><th className="py-2 px-1.5 font-medium text-right">Wkts</th>
              <th className="py-2 px-1.5 font-medium text-right">Avg</th><th className="py-2 px-1.5 font-medium text-right">Econ</th><th className="py-2 px-1.5 font-medium text-right">Best</th><th className="py-2 px-1.5 font-medium text-right">vs us</th>
            </tr></thead>
            <tbody>
              {bowl.map(p => (
                <tr key={p.player_id} style={{ borderTop: '1px solid var(--pb-hairline)' }} className="transition-colors hover:bg-pb-surface2">
                  <td className="py-2.5 px-1.5 font-medium whitespace-nowrap">{p.name}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{p.overs}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num font-semibold">{p.wickets}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num">{a2(p.average)}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{a2(p.economy)}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num">{p.best}</td>
                  <td className="py-2.5 px-1.5 text-right iq-num text-[11.5px]">{p.vs_us ? `${p.vs_us.wickets}w@${a2(p.vs_us.average)}` : <span className="text-pb-faintest">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}

/* ── Building state ──────────────────────────────────────────────────────── */
function BuildingCard({ oppName }) {
  return (
    <div className="iq-card iq-accent-card p-8 text-center iq-fade">
      <div className="inline-block iq-spin" style={{ width: 30, height: 30, borderRadius: 99, border: '3px solid var(--pb-surface3)', borderTopColor: 'var(--pb-accent)', marginBottom: 14 }} />
      <div className="iq-display font-bold text-[16px]">Building their dossier…</div>
      <div className="text-pb-faint text-[13px] mt-1.5 max-w-md mx-auto">Pulling {oppName}'s recent scorecards and their record against us. The head-to-head above is ready now.</div>
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────────────── */
function Scout({ selection, onClearSelection, onCheatSheet }) {
  const [selected, setSelected] = useStateS(selection || null);
  const [building, setBuilding] = useStateS(false);

  useEffectS(() => { if (selection) { setSelected(selection); } }, [selection]);
  useEffectS(() => {
    if (!selected) return;
    setBuilding(true);
    const t = setTimeout(() => setBuilding(false), 1700);
    return () => clearTimeout(t);
  }, [selected]);

  const pick = (sel) => setSelected(sel);
  const clear = () => { setSelected(null); onClearSelection && onClearSelection(); };

  if (!selected) return <ScoutPicker onPick={pick} />;

  const oppName = selected.name || IQ_REPORT.opponent.name;
  const report = IQ_REPORT;
  const dossier = IQ_DOSSIER;

  return (
    <div>
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>Scouting report</div>
          <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(28px,3.4vw,40px)' }}>{oppName}</h2>
          <div className="text-pb-faint text-[12.5px] mt-1.5 iq-num">1st Grade · {dossier.teams[0].matches} matches this season</div>
        </div>
        <div className="flex items-center gap-2.5">
          <Btn variant="ghost" sm icon="back" onClick={clear}>Change opponent</Btn>
          <Btn variant="ghost" sm icon="print" onClick={onCheatSheet}>Cheat sheet</Btn>
          <Btn variant="soft" sm icon="bolt">Refresh</Btn>
        </div>
      </div>

      <div className="space-y-5">
        <CommandStrip h2h={report.head_to_head} lm={report.last_meeting} />

        {building ? <BuildingCard oppName={oppName} /> : (
          <div className="space-y-5 iq-fade">
            <GamePlan plan={dossier.game_plan} />

            <div className="grid gap-5 lg:grid-cols-2">
              <KeyPlayersCard title="Danger batters" subtitle="their top run-scorers this season" players={dossier.danger_batters} kind="bat" />
              <KeyPlayersCard title="Danger bowlers" subtitle="their leading wicket-takers" players={dossier.danger_bowlers} kind="bowl" />
            </div>

            <Card eyebrow="threat profiles vs grade average" title="Their two biggest threats">
              <div className="grid gap-6 sm:grid-cols-2">
                {[{ id: 'm1', name: 'Cooper Voss', tag: 'Top-order bat' }, { id: 'm6', name: 'Reece Mockridge', tag: 'Strike bowler' }].map(p => (
                  <div key={p.id} className="flex flex-col items-center">
                    <div className="text-center mb-1"><div className="iq-display font-bold text-[15px]">{p.name}</div><div className="iq-eyebrow">{p.tag}</div></div>
                    {radarFor(p.id) && <Radar axes={radarFor(p.id).axes} values={radarFor(p.id).values} baseline={[50, 50, 50, 50, 50, 50]} size={236} color="var(--pb-red)" />}
                  </div>
                ))}
              </div>
              <Note>Each axis normalised 0–100 against the grade average (dashed ring). The further the shape reaches, the bigger the threat.</Note>
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <OurRecord performers={report.our_performers} />
              <VenueCard venues={report.venues} />
            </div>

            <Matchups matchups={report.matchups} />

            <WinLose win={dossier.how_they_win} lose={dossier.how_they_lose} />

            <div className="grid gap-5 lg:grid-cols-2 items-start">
              <Card eyebrow="this season" title="How they get out"><StackedBar data={dossier.dismissal_breakdown} /></Card>
              <Partnerships partnerships={dossier.partnerships} insight={dossier.partnership_insight} />
            </div>

            <Card eyebrow="typical innings shape · estimate" title="When they score" right={<Tag tone="accent">Avg {IQ_VIZ.phases_opp.total}</Tag>}>
              <PhaseStrip phases={IQ_VIZ.phases_opp.phases} total={IQ_VIZ.phases_opp.total} />
              <div className="text-pb-dim text-[13px] mt-4 leading-relaxed">{IQ_VIZ.phases_opp.insight}</div>
              <Note>Phase split is estimated from innings scorecards — we don't hold ball-by-ball, so treat over-ranges as indicative.</Note>
            </Card>

            <SquadTable dossier={dossier} />

            <Card eyebrow="not in recent squad" title="Historically hurt us">
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {dossier.historical_threats.map(p => (
                  <span key={p.player_id} className="text-[13.5px]">{p.name} <span className="text-pb-faint iq-num">{p.runs} @ {n2(p.average)}</span></span>
                ))}
              </div>
            </Card>

            <Note>{dossier.coverage.notes.join(' ')} · built {new Date(dossier.built_at).toLocaleString()}</Note>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { Scout });
