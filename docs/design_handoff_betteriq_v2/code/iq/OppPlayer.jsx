/* BetterIQ — Opposition player: scout one opponent player across a club. */
const { useState: useStateOP, useMemo: useMemoOP } = React;

function buildOppIndex() {
  const map = new Map();
  for (const b of IQ_DOSSIER.batting) map.set(b.player_id, { id: b.player_id, name: b.name, bat: b, bowl: null });
  for (const w of IQ_DOSSIER.bowling) {
    const e = map.get(w.player_id) || { id: w.player_id, name: w.name, bat: null, bowl: null };
    e.bowl = w; map.set(w.player_id, e);
  }
  return map;
}

function TagPill({ label, value, on }) {
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2.5" style={{ background: 'var(--pb-surface2)', borderRadius: 10, border: `1px solid ${on ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline)'}` }}>
      <span className="iq-mono uppercase text-pb-faint" style={{ fontSize: 9.5, letterSpacing: '0.1em' }}>{label}</span>
      <span className="font-semibold text-[13px]" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{value}</span>
    </div>
  );
}

function OppPlayerDetail({ entry, rich }) {
  const bat = entry.bat, bowl = entry.bowl;
  const spark = (bat?.recent_scores || []).map(s => parseInt(String(s).replace('*', ''), 10) || 0);
  const t = rich?.tags;
  return (
    <div className="iq-fade space-y-5">
      {/* header */}
      <div className="flex items-center gap-4">
        <Initials name={entry.name} size={52} tone="accent" />
        <div>
          <div className="flex items-center gap-2"><h2 className="iq-headline" style={{ fontSize: 28 }}>{entry.name}</h2>{t?.danger && <Tag tone="red">Danger</Tag>}</div>
          <div className="text-pb-faint text-[13px] mt-1">{t?.role || (bowl && bat ? 'All-rounder' : bowl ? 'Bowler' : 'Batter')} · Melville</div>
        </div>
      </div>

      {/* signature viz: radar + scoring zones */}
      {(radarFor(entry.id) || IQ_VIZ.zones[entry.id]) && (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {radarFor(entry.id) && (
            <Card eyebrow="profile vs grade average" title="Player radar">
              <div className="flex justify-center"><Radar axes={radarFor(entry.id).axes} values={radarFor(entry.id).values} baseline={[50, 50, 50, 50, 50, 50]} size={248} color="var(--pb-red)" /></div>
            </Card>
          )}
          {IQ_VIZ.zones[entry.id] && (
            <Card eyebrow="where he scores · scout-entered" title="Scoring zones">
              <div className="flex justify-center"><WagonWheel sectors={IQ_VIZ.zones[entry.id].sectors} hand={IQ_VIZ.zones[entry.id].hand} color="var(--pb-red)" /></div>
              <div className="text-pb-dim text-[12.5px] mt-3 leading-relaxed">{IQ_VIZ.zones[entry.id].note}</div>
            </Card>
          )}
        </div>
      )}

      {/* stat clusters */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {bat && (
          <Card eyebrow="this season" title="Batting">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Runs" value={bat.runs} /><Stat label="Average" value={bat.average} decimals={2} count={false} /><Stat label="Strike rate" value={bat.strike_rate} count={false} />
              <Stat label="High score" value={bat.high_score} /><Stat label="50s / 100s" value={`${bat.fifties}/${bat.hundreds}`} count={false} /><Stat label="Innings" value={bat.innings} />
            </div>
            <div className="mt-5 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
              <div className="flex items-center justify-between mb-1"><span className="iq-eyebrow" style={{ fontSize: 9 }}>Last 5</span><span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{(bat.recent_scores || []).join('  ')}</span></div>
              <Sparkline key={entry.id} values={spark} h={46} dots />
            </div>
          </Card>
        )}
        {bowl && (
          <Card eyebrow="this season" title="Bowling">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Wickets" value={bowl.wickets} /><Stat label="Average" value={bowl.average} decimals={2} count={false} /><Stat label="Economy" value={bowl.economy} decimals={2} count={false} />
              <Stat label="Best" value={bowl.best} count={false} /><Stat label="Overs" value={bowl.overs} /><Stat label="Recent" value={(bowl.recent_wickets || []).reduce((a, b) => a + b, 0)} suffix="w" />
            </div>
          </Card>
        )}
        {rich?.get_out && (
          <Card eyebrow="dismissal patterns" title="How he gets out">
            <StackedBar data={rich.get_out.map(g => ({ ...g, count: g.pct }))} />
          </Card>
        )}
      </div>

      {/* record vs us */}
      {rich?.vs_us && (
        <Card accent eyebrow="our record on him" title="vs Applecross">
          <div className="flex flex-wrap items-end gap-8">
            <div><div className="iq-headline iq-num" style={{ fontSize: 34 }}>{rich.vs_us.runs}</div><div className="iq-eyebrow mt-1">Runs vs us</div></div>
            <div><div className="iq-headline iq-num" style={{ fontSize: 34, color: 'var(--pb-brand)' }}>{Number(rich.vs_us.avg).toFixed(2)}</div><div className="iq-eyebrow mt-1">Average</div></div>
            <div className="min-w-0 flex-1"><div className="iq-eyebrow mb-1">Dismissed by</div><div className="text-[14px] font-medium">{rich.vs_us.dismissed_by}</div></div>
          </div>
        </Card>
      )}

      {/* scouting tags */}
      <Card eyebrow="manual scouting metadata" title="Scouting tags" right={<Btn variant="soft" sm icon="check">Save</Btn>}>
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          <TagPill label="Bats" value={t?.hand || '—'} />
          <TagPill label="Bowls" value={t?.bowl_type || '—'} />
          <TagPill label="Role" value={t?.role || '—'} />
          <TagPill label="Keeper" value={t?.keeper ? 'Yes' : 'No'} />
          <TagPill label="Danger flag" value={t?.danger ? 'Flagged' : 'No'} on={t?.danger} />
          <TagPill label="Bowling arm" value={t?.bowl_arm || '—'} />
        </div>
        <div className="mt-3">
          <div className="iq-eyebrow mb-2">Scouting notes</div>
          <textarea defaultValue={t?.notes || ''} rows={3}
            className="w-full p-3.5 text-[13.5px] leading-relaxed resize-none outline-none"
            style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 12, color: 'var(--pb-text)', fontFamily: 'var(--iq-font-body)' }} />
        </div>
      </Card>
    </div>
  );
}

function OppPlayer({ onScout }) {
  const index = useMemoOP(() => buildOppIndex(), []);
  const all = useMemoOP(() => [...index.values()], [index]);
  const [sel, setSel] = useStateOP('m1');
  const [q, setQ] = useStateOP('');
  const t = q.trim().toLowerCase();
  const matches = (t ? all.filter(p => p.name.toLowerCase().includes(t)) : all);
  const entry = index.get(sel);
  const rich = sel === 'm1' ? IQ_OPP_PLAYER : null;

  return (
    <div className="iq-fade">
      <PageIntro>Scout any individual in an opponent's squad — their form, how they get out, their record against us, and your own scouting notes that travel with them.</PageIntro>

      {/* club + player pickers */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex items-center gap-2">
          <span className="iq-eyebrow">Club</span>
          <span className="px-3 py-1.5 iq-display font-semibold text-[13px]" style={{ borderRadius: 99, background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>Melville</span>
        </div>
        <Search value={q} onChange={setQ} placeholder="Search their squad…" className="w-full max-w-xs" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr] items-start">
        {/* player list */}
        <div className="iq-card p-2 lg:sticky lg:top-20">
          <div className="iq-eyebrow px-2 py-2">Squad ({all.length})</div>
          <div className="max-h-[60vh] overflow-y-auto iq-scroll">
            {matches.map(p => {
              const on = p.id === sel;
              return (
                <button key={p.id} onClick={() => { setSel(p.id); setQ(''); }}
                  className="w-full flex items-center justify-between gap-2 px-2.5 py-2 text-left transition" style={{ borderRadius: 9, background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}>
                  <span className="font-medium text-[13.5px] truncate" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{p.name}</span>
                  <span className="iq-mono text-pb-faint shrink-0" style={{ fontSize: 10.5 }}>{p.bat?.runs ? `${p.bat.runs}r` : ''}{p.bowl?.wickets ? ` ${p.bowl.wickets}w` : ''}</span>
                </button>
              );
            })}
            {matches.length === 0 && <Empty className="px-2.5 py-2">No match.</Empty>}
          </div>
        </div>

        {entry ? <OppPlayerDetail entry={entry} rich={rich} /> : <Empty>Pick a player.</Empty>}
      </div>
    </div>
  );
}

Object.assign(window, { OppPlayer });
