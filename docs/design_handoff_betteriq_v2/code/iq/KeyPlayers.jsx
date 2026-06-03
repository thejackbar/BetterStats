/* BetterIQ — KeyPlayers showcase (the module's signature card).
   Segmented flick-through → featured panel with count-up headline, drawn
   sparkline, and the rule-based analyst read. */
const { useState: useStateK } = React;

function num(v, d = '—') { return (v === null || v === undefined) ? d : v; }
function a2(v) { return (v === null || v === undefined) ? '—' : Number(v).toFixed(2); }

function AlertBadge({ alert }) {
  if (!alert?.level) return null;
  const danger = alert.level === 'danger';
  const color = danger ? 'var(--pb-red)' : 'var(--pb-amber)';
  const reasons = (danger ? alert.danger : alert.caution) || [];
  return (
    <span title={reasons.join(' · ')} className="iq-mono inline-flex items-center gap-1 font-bold uppercase"
      style={{ fontSize: 9.5, letterSpacing: '0.1em', padding: '3px 8px', borderRadius: 6, background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      <Icon name={danger ? 'flame' : 'info'} size={11} />{danger ? 'Danger' : 'Paper tiger?'}
    </span>
  );
}

function KeyPlayersCard({ title, subtitle, players, kind = 'bat' }) {
  const [sel, setSel] = useStateK(0);
  if (!players?.length) return null;
  const list = players.slice(0, 5);
  const i = Math.min(sel, list.length - 1);
  const p = list[i];
  const n = list.length;

  const spark = kind === 'bat'
    ? (p.recent_scores || []).map(s => parseInt(String(s).replace('*', ''), 10) || 0)
    : (p.recent_wickets || []);
  const headline = kind === 'bat' ? p.runs : p.wickets;
  const unit = kind === 'bat' ? 'runs' : 'wkts';
  const sub = kind === 'bat' ? `avg ${a2(p.average)} · SR ${num(p.strike_rate)}` : `avg ${a2(p.average)} · econ ${a2(p.economy)}`;
  const formLabel = p.form === 'hot' ? 'In form' : p.form === 'cold' ? 'Out of form' : null;
  const formColor = p.form === 'hot' ? 'var(--pb-brand)' : p.form === 'cold' ? 'var(--pb-red)' : 'var(--pb-amber)';
  const vs = p.vs_us;

  return (
    <div className="iq-card overflow-hidden" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 28%, transparent)' }}>
      <div className="relative p-5 md:p-6" style={{ background: 'linear-gradient(165deg, color-mix(in srgb, var(--pb-accent) 8%, transparent), transparent 55%)' }}>
        {/* header */}
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="min-w-0">
            <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>{title}</div>
            {subtitle && <div className="text-pb-faint text-[11.5px] truncate mt-1">{subtitle}</div>}
          </div>
          <AlertBadge alert={p.alert} />
        </div>

        {/* segmented flick-through */}
        <div className="relative flex p-1 mb-5" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
          <div className="absolute top-1 bottom-1" style={{
            left: `calc(${i} * ${100 / n}% + 4px)`, width: `calc(${100 / n}% - 8px)`, borderRadius: 9,
            background: 'color-mix(in srgb, var(--pb-accent) 22%, transparent)',
            border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)',
            transition: 'left .32s cubic-bezier(.34,1.3,.5,1)' }} />
          {list.map((pl, idx) => (
            <button key={pl.player_id || idx} onClick={() => setSel(idx)}
              className="relative z-10 flex-1 text-center truncate iq-display font-semibold transition-colors"
              style={{ padding: '7px 4px', borderRadius: 9, fontSize: 12, color: idx === i ? 'var(--pb-text)' : 'var(--pb-dim)' }}>
              {surname(pl.name)}
            </button>
          ))}
        </div>

        {/* featured */}
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="iq-display font-bold text-[20px] leading-tight truncate">{p.name}</span>
              {formLabel && <span className="iq-mono shrink-0" style={{ fontSize: 9.5, padding: '2px 7px', borderRadius: 99, background: `color-mix(in srgb, ${formColor} 16%, transparent)`, color: formColor }}>{formLabel}</span>}
            </div>
            <div className="text-pb-faint text-[12.5px] mt-1 iq-num">{sub}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="iq-headline" style={{ fontSize: 'clamp(38px,5vw,52px)', lineHeight: 0.9 }}>
              <CountUp value={headline || 0} /><span className="text-pb-faint" style={{ fontSize: 14, fontWeight: 500, marginLeft: 4 }}>{unit}</span>
            </div>
            {vs && (kind === 'bat'
              ? (vs.runs ? <div className="text-pb-faint text-[11.5px] iq-num mt-1">{vs.runs} @ {a2(vs.average)} vs us</div> : null)
              : (vs.wickets ? <div className="text-pb-faint text-[11.5px] iq-num mt-1">{vs.wickets}w @ {a2(vs.average)} vs us</div> : null))}
          </div>
        </div>

        {/* sparkline */}
        <div className="mt-4 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
          <div className="flex items-center justify-between mb-1">
            <span className="iq-eyebrow" style={{ fontSize: 9 }}>Last 5</span>
            <span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>
              {kind === 'bat' ? (p.recent_scores || []).join('  ') : (p.recent_wickets || []).map(w => `${w}w`).join('  ')}
            </span>
          </div>
          <Sparkline key={p.player_id + i} values={spark} h={48} dots stroke="var(--pb-accent)" />
        </div>

        {/* analyst read */}
        {p.key_note && (
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid color-mix(in srgb, var(--pb-accent) 16%, transparent)' }}>
            <div className="text-[13.5px] leading-snug">{p.key_note}</div>
            {p.plan && <div className="text-[12.5px] mt-2.5 leading-snug"><span className="text-pb-faint">Plan:</span> <span className="font-semibold">{p.plan}</span></div>}
            <div className="flex items-center gap-1.5 mt-2.5">
              {p.risk && <span className="iq-mono uppercase" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 5, background: `color-mix(in srgb, ${p.risk === 'high' ? 'var(--pb-red)' : p.risk === 'medium' ? 'var(--pb-amber)' : 'var(--pb-faint)'} 16%, transparent)`, color: p.risk === 'high' ? 'var(--pb-red)' : p.risk === 'medium' ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{p.risk} risk</span>}
              {p.confidence && <span className="iq-mono uppercase text-pb-faint" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 5, border: '1px solid var(--pb-hairline2)' }}>{p.confidence} conf</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { KeyPlayersCard });
