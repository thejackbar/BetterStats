/* BetterIQ — global context bar: Season + Team filters that persist across
   pages, plus a season-RANGE selector (timeline + presets) for cross-season
   comparison. Lives directly under the header on every applicable page. */
const { useState: useStateCx, useRef: useRefCx, useEffect: useEffectCx } = React;

const SEASONS = ['2024/25', '2023/24', '2022/23', '2021/22', '2020/21']; // newest first
const SEASONS_CHRON = [...SEASONS].reverse();                            // oldest first
const TEAMS = ['1st Grade', '2nd Grade', '3rd Grade', 'All grades'];
const CURRENT_SEASON = SEASONS[0];

/* default ctx */
const DEFAULT_CTX = { team: '1st Grade', season: { mode: 'single', from: CURRENT_SEASON, to: CURRENT_SEASON } };

function seasonLabel(s) {
  if (!s) return CURRENT_SEASON;
  if (s.mode === 'single') return s.to;
  const i0 = SEASONS_CHRON.indexOf(s.from), i1 = SEASONS_CHRON.indexOf(s.to);
  const span = Math.abs(i1 - i0) + 1;
  if (span === SEASONS.length) return 'All seasons';
  return `${s.from} → ${s.to}`;
}
function seasonSpanCount(s) {
  if (!s || s.mode === 'single') return 1;
  return Math.abs(SEASONS_CHRON.indexOf(s.to) - SEASONS_CHRON.indexOf(s.from)) + 1;
}

/* ── Popover shell ───────────────────────────────────────────────────────── */
function Popover({ trigger, children, width = 300, align = 'left' }) {
  const [open, setOpen] = useStateCx(false);
  return (
    <div className="relative">
      <div onClick={() => setOpen(o => !o)}>{trigger(open)}</div>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute z-40 mt-2 iq-card p-3.5" style={{ width, [align]: 0, boxShadow: 'var(--iq-card-shadow)' }}>
            {typeof children === 'function' ? children(() => setOpen(false)) : children}
          </div>
        </>
      )}
    </div>
  );
}

function PillTrigger({ icon, label, sub, open, accent }) {
  return (
    <button className="flex items-center gap-2.5 transition" style={{
      background: 'var(--pb-surface2)', border: `1px solid ${open ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`,
      borderRadius: 10, padding: '7px 12px', height: 38 }}>
      <Icon name={icon} size={15} style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-faint)' }} />
      <span className="text-left leading-none">
        {sub && <span className="iq-eyebrow block" style={{ fontSize: 8, marginBottom: 2 }}>{sub}</span>}
        <span className="iq-display font-semibold text-[13px]" style={{ color: 'var(--pb-text)' }}>{label}</span>
      </span>
      <Icon name="chevron" size={13} className="text-pb-faint" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />
    </button>
  );
}

/* ── Team picker ─────────────────────────────────────────────────────────── */
function TeamPicker({ value, onChange, label = 'Team' }) {
  return (
    <Popover width={200} trigger={open => <PillTrigger icon="teams" sub={label} label={value} open={open} />}>
      {close => (
        <div className="space-y-0.5">
          {TEAMS.map(t => (
            <button key={t} onClick={() => { onChange(t); close(); }}
              className="w-full flex items-center justify-between gap-3 px-2.5 py-2 text-left transition" style={{ borderRadius: 8, background: t === value ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
              onMouseEnter={e => { if (t !== value) e.currentTarget.style.background = 'var(--pb-surface2)'; }}
              onMouseLeave={e => { if (t !== value) e.currentTarget.style.background = 'transparent'; }}>
              <span className="font-medium text-[13.5px]" style={{ color: t === value ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{t}</span>
              {t === value && <Icon name="check" size={14} style={{ color: 'var(--pb-accent)' }} />}
            </button>
          ))}
        </div>
      )}
    </Popover>
  );
}

/* ── Season timeline (the range visualiser/selector) ─────────────────────── */
function SeasonTimeline({ season, onChange, mode }) {
  // node click logic: single → set from=to; range → anchor then extend
  const fromI = SEASONS_CHRON.indexOf(season.from);
  const toI = SEASONS_CHRON.indexOf(season.to);
  const lo = Math.min(fromI, toI), hi = Math.max(fromI, toI);
  const [anchor, setAnchor] = useStateCx(null);

  const click = i => {
    if (mode === 'single') { onChange({ mode: 'single', from: SEASONS_CHRON[i], to: SEASONS_CHRON[i] }); return; }
    if (anchor === null) { setAnchor(i); onChange({ mode: 'range', from: SEASONS_CHRON[i], to: SEASONS_CHRON[i] }); }
    else { const a = Math.min(anchor, i), b = Math.max(anchor, i); onChange({ mode: 'range', from: SEASONS_CHRON[a], to: SEASONS_CHRON[b] }); setAnchor(null); }
  };

  return (
    <div className="px-1 pt-2 pb-1">
      <div className="relative flex items-center justify-between">
        {/* track */}
        <div className="absolute left-2 right-2 top-[7px] h-[3px] rounded-full" style={{ background: 'var(--pb-surface3)' }} />
        {mode === 'range' && hi > lo && (
          <div className="absolute top-[7px] h-[3px] rounded-full" style={{ background: 'var(--pb-accent)',
            left: `calc(${(lo / (SEASONS_CHRON.length - 1)) * 100}% )`, right: `calc(${(1 - hi / (SEASONS_CHRON.length - 1)) * 100}%)` }} />
        )}
        {SEASONS_CHRON.map((s, i) => {
          const inSpan = i >= lo && i <= hi;
          const endpoint = (mode === 'single' && i === toI) || (mode === 'range' && (i === lo || i === hi));
          return (
            <button key={s} onClick={() => click(i)} className="relative flex flex-col items-center" style={{ zIndex: 1 }}>
              <span style={{ width: endpoint ? 15 : 11, height: endpoint ? 15 : 11, borderRadius: 99,
                background: endpoint ? 'var(--pb-accent)' : inSpan ? 'color-mix(in srgb, var(--pb-accent) 45%, var(--pb-surface3))' : 'var(--pb-surface3)',
                border: `2px solid ${endpoint || inSpan ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`, transition: 'all .15s' }} />
              <span className="iq-mono mt-2" style={{ fontSize: 9.5, color: inSpan ? 'var(--pb-text)' : 'var(--pb-faint)' }}>{s.slice(2)}</span>
            </button>
          );
        })}
      </div>
      {mode === 'range' && <div className="text-pb-faint text-[11px] mt-3 text-center">{anchor !== null ? 'Pick the other end of the range' : `${seasonSpanCount(season)} season${seasonSpanCount(season) > 1 ? 's' : ''} selected`}</div>}
    </div>
  );
}

function SeasonPicker({ season, onChange, allowRange }) {
  const setMode = m => {
    if (m === 'single') onChange({ mode: 'single', from: season.to, to: season.to });
    else onChange({ mode: 'range', from: SEASONS_CHRON[Math.max(0, SEASONS_CHRON.indexOf(season.to) - 1)], to: season.to });
  };
  const presets = [
    { label: 'This + last', range: ['2023/24', '2024/25'] },
    { label: 'Last 3', range: ['2022/23', '2024/25'] },
    { label: 'All seasons', range: [SEASONS_CHRON[0], CURRENT_SEASON] },
  ];
  return (
    <Popover width={320} trigger={open => <PillTrigger icon="clock" sub="Season" label={seasonLabel(season)} open={open} accent />}>
      {() => (
        <div>
          {allowRange && (
            <div className="mb-3"><Segmented sm value={season.mode} onChange={setMode}
              options={[{ value: 'single', label: 'Single' }, { value: 'range', label: 'Compare' }]} /></div>
          )}
          <SeasonTimeline season={season} onChange={onChange} mode={allowRange ? season.mode : 'single'} />
          {allowRange && season.mode === 'range' && (
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div className="iq-eyebrow mb-2">Quick ranges</div>
              <div className="flex flex-wrap gap-2">
                {presets.map(p => {
                  const active = season.from === p.range[0] && season.to === p.range[1];
                  return (
                    <button key={p.label} onClick={() => onChange({ mode: 'range', from: p.range[0], to: p.range[1] })}
                      className="iq-display font-semibold text-[12px] transition" style={{ padding: '6px 11px', borderRadius: 8,
                        background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
                        color: active ? 'var(--pb-accent)' : 'var(--pb-dim)', border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}` }}>{p.label}</button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </Popover>
  );
}

/* ── Context bar ─────────────────────────────────────────────────────────── */
function ContextBar({ ctx, onChange, filters }) {
  if (!filters || (!filters.team && !filters.season)) return null;
  const isRange = ctx.season.mode === 'range';
  return (
    <div className="sticky z-20 flex items-center gap-3 flex-wrap px-5 md:px-8 py-3"
      style={{ top: 64, background: 'color-mix(in srgb, var(--pb-bg) 86%, transparent)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)', borderBottom: '1px solid var(--pb-hairline)' }}>
      <span className="iq-eyebrow hidden sm:block" style={{ fontSize: 9 }}>Showing</span>
      {filters.team && <TeamPicker value={ctx.team} onChange={t => onChange({ ...ctx, team: t })} label={filters.teamLabel || 'Team'} />}
      {filters.season
        ? <SeasonPicker season={ctx.season} onChange={s => onChange({ ...ctx, season: s })} allowRange={filters.season === 'range'} />
        : <div className="flex items-center gap-2 px-3" style={{ height: 38, borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)' }}>
            <Icon name="clock" size={14} className="text-pb-faint" />
            <span className="iq-display font-semibold text-[13px]">{CURRENT_SEASON}</span>
            <span className="iq-mono text-pb-faint" style={{ fontSize: 10 }}>· current</span>
          </div>}
      {isRange && <Tag tone="accent">Comparing {seasonSpanCount(ctx.season)} seasons</Tag>}
      <div className="ml-auto hidden md:flex items-center gap-1.5 text-pb-faintest text-[11px]">
        <Icon name="info" size={12} />
        <span>Filters apply across BetterIQ</span>
      </div>
    </div>
  );
}

/* per-route filter capability */
const ROUTE_FILTERS = {
  overview: { team: true, season: 'single' },
  preview: { team: true, season: false },
  opposition: { team: true, season: 'range', teamLabel: 'Their grade' },
  'opposition-player': { team: true, season: 'range', teamLabel: 'Their grade' },
  selection: { team: true, season: false },
  trends: { team: true, season: 'range' },
  team: { team: true, season: 'range' },
  review: { team: true, season: 'range' },
};

Object.assign(window, { ContextBar, ROUTE_FILTERS, SEASONS, SEASONS_CHRON, TEAMS, CURRENT_SEASON, DEFAULT_CTX, seasonLabel, seasonSpanCount });
