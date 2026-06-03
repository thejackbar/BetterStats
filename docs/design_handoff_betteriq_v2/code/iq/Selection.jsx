/* BetterIQ — Selection analysis.
   The loop: BetterSelect holds the saved XI → players set availability →
   BetterIQ rebuilds the best-available XI (respecting role balance and the
   eligibility pool) and shows the diff, so the pick is justified and current. */
const { useState: useStateSel, useMemo: useMemoSel } = React;

const SPINNERS = new Set(['p3', 'p13']); // Whitlock, Tahir
const ROLE_CHIP = {
  BAT: { c: 'var(--pb-dim)', bg: 'var(--pb-surface2)' },
  WKT: { c: 'var(--pb-amber)', bg: 'color-mix(in srgb, var(--pb-amber) 14%, transparent)' },
  ALL: { c: 'var(--pb-accent)', bg: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' },
  BWL: { c: 'var(--iq-c-wkts)', bg: 'color-mix(in srgb, var(--iq-c-wkts) 14%, transparent)' },
};
const primaryRole = p => p.roles.includes('WKT') ? 'WKT' : p.roles[0];
const batScore = p => (p.bat_avg || 0) + (p.formAvg || 0) * 0.5 + (p.fifties || 0) * 2 + (p.hundreds || 0) * 5;
const bowlScore = p => (p.wkts || 0) * 1.4 + (40 - (p.bowl_avg || 40));
const allScore = p => batScore(p) * 0.55 + bowlScore(p) * 0.7;
const keeperScore = p => (p.bat_avg || 0) + (p.dismissals || 0) * 0.4;
const valueOf = p => { const r = primaryRole(p); return r === 'WKT' ? keeperScore(p) : r === 'BWL' ? bowlScore(p) : r === 'ALL' ? allScore(p) : batScore(p); };

function buildXI(squad, availMap, includeMaybe) {
  const pool = squad.filter(p => availMap[p.id] === 'available' || (includeMaybe && availMap[p.id] === 'maybe'));
  const used = new Set();
  const take = (arr, n) => { const out = []; for (const p of arr) { if (out.length >= n) break; if (!used.has(p.id)) { out.push(p); used.add(p.id); } } return out; };
  const byRole = role => pool.filter(p => primaryRole(p) === role);
  const keeper = take(byRole('WKT').sort((a, b) => keeperScore(b) - keeperScore(a)), 1);
  const bowlers = take(byRole('BWL').sort((a, b) => bowlScore(b) - bowlScore(a)), 3);
  const allr = take(byRole('ALL').sort((a, b) => allScore(b) - allScore(a)), 2);
  const bats = take(byRole('BAT').sort((a, b) => batScore(b) - batScore(a)), 5);
  let xi = [...keeper, ...bowlers, ...allr, ...bats];
  if (xi.length < 11) { const rest = pool.filter(p => !used.has(p.id)).sort((a, b) => valueOf(b) - valueOf(a)); xi = xi.concat(take(rest, 11 - xi.length)); }
  return xi.sort((a, b) => (a.order - b.order) || (batScore(b) - batScore(a)));
}

function balanceOf(xi) {
  const bowlers = xi.filter(p => primaryRole(p) === 'BWL');
  const allr = xi.filter(p => primaryRole(p) === 'ALL');
  const bowlContrib = [...bowlers, ...allr];
  const spin = bowlContrib.filter(p => SPINNERS.has(p.id)).length;
  return {
    bats: xi.filter(p => primaryRole(p) === 'BAT').length,
    allr: allr.length,
    bowlers: bowlers.length,
    keeper: xi.filter(p => primaryRole(p) === 'WKT').length,
    pace: bowlContrib.length - spin, spin,
    openers: xi.filter(p => p.order <= 2).length,
    depth: xi.filter(p => ['BAT', 'WKT', 'ALL'].includes(primaryRole(p))).length,
  };
}

/* ── Availability tri-state control ──────────────────────────────────────── */
const AV_OPTS = [{ k: 'available', label: 'In', c: 'var(--pb-brand)' }, { k: 'maybe', label: '?', c: 'var(--pb-amber)' }, { k: 'unavailable', label: 'Out', c: 'var(--pb-red)' }];
function AvailToggle({ value, onChange }) {
  return (
    <div className="inline-flex p-[2px] gap-0.5" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 8 }}>
      {AV_OPTS.map(o => {
        const on = o.k === value;
        return (
          <button key={o.k} onClick={() => onChange(o.k)} className="iq-mono font-bold transition"
            style={{ fontSize: 10.5, padding: '3px 9px', borderRadius: 6, color: on ? o.c : 'var(--pb-faint)', background: on ? `color-mix(in srgb, ${o.c} 16%, transparent)` : 'transparent' }}>{o.label}</button>
        );
      })}
    </div>
  );
}

function RoleChip({ role }) {
  const c = ROLE_CHIP[role] || ROLE_CHIP.BAT;
  return <span className="iq-mono font-bold" style={{ fontSize: 9.5, padding: '2px 6px', borderRadius: 5, color: c.c, background: c.bg }}>{role}</span>;
}

function Selection({ onNavigate }) {
  const [availMap, setAvailMap] = useStateSel(() => Object.fromEntries(IQ_SQUAD.map(p => [p.id, p.avail])));
  const [includeMaybe, setIncludeMaybe] = useStateSel(false);
  const [sent, setSent] = useStateSel(false);

  const counts = useMemoSel(() => {
    const c = { available: 0, maybe: 0, unavailable: 0 };
    Object.values(availMap).forEach(v => c[v]++); return c;
  }, [availMap]);

  const xi = useMemoSel(() => buildXI(IQ_SQUAD, availMap, includeMaybe), [availMap, includeMaybe]);
  const bal = useMemoSel(() => balanceOf(xi), [xi]);

  const savedIds = useMemoSel(() => new Set(IQ_SELECTION.xi.map(p => p.id)), []);
  const autoIds = new Set(xi.map(p => p.id));
  const inIds = xi.filter(p => !savedIds.has(p.id));
  const outPlayers = IQ_SELECTION.xi.filter(p => !autoIds.has(p.id)).map(p => ({ ...IQ_SQUAD.find(s => s.id === p.id), reason: availMap[p.id] === 'unavailable' ? 'Unavailable' : availMap[p.id] === 'maybe' ? 'Only a maybe' : 'Out-performed' }));
  const bench = IQ_SQUAD.filter(p => !autoIds.has(p.id) && availMap[p.id] !== 'unavailable');

  const warnings = [];
  if (bal.spin < 2) warnings.push({ tone: 'amber', text: `Only ${bal.spin} frontline spinner — spin has taken 41% of wickets at Tompkins Park. Add a second.` });
  if (bal.depth < 7) warnings.push({ tone: 'amber', text: 'Batting depth thins below 7 — a top-order collapse would expose the tail early.' });
  if (bal.openers < 2) warnings.push({ tone: 'red', text: 'Fewer than two recognised openers available.' });
  const changes = inIds.length;

  const setAvail = (id, v) => { setAvailMap(m => ({ ...m, [id]: v })); setSent(false); };

  const balChips = [
    { label: 'Specialist bats', value: bal.bats, ok: bal.bats >= 4 },
    { label: 'All-rounders', value: bal.allr, ok: bal.allr >= 1 },
    { label: 'Bowlers', value: bal.bowlers, ok: bal.bowlers >= 3 },
    { label: 'Pace / spin', value: `${bal.pace} / ${bal.spin}`, warn: bal.spin < 2 },
    { label: 'Keeper', value: bal.keeper, ok: bal.keeper >= 1, warn: bal.keeper < 1 },
    { label: 'Openers', value: bal.openers, ok: bal.openers >= 2 },
  ];

  return (
    <div className="iq-fade">
      <PageIntro>BetterSelect holds the saved XI. Set who's available and BetterIQ rebuilds the best-available side — balanced, in-form and eligible — then shows exactly what changed.</PageIntro>

      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-2"><div className="iq-eyebrow whitespace-nowrap" style={{ color: 'var(--pb-accent)' }}>Best available XI</div><Tag tone="accent">Synced · BetterSelect</Tag></div>
          <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(22px,2.6vw,30px)' }}>{IQ_SELECTION.fixture}</h2>
        </div>
        <div className="flex items-center gap-2.5">
          <Btn variant="ghost" sm icon="fixtures" onClick={() => onNavigate('preview')}>Match preview</Btn>
          <Btn variant="primary" sm icon={sent ? 'check' : 'share'} onClick={() => setSent(true)}>{sent ? 'Sent to BetterSelect' : 'Send XI to BetterSelect'}</Btn>
        </div>
      </div>

      {/* verdict */}
      <Card accent eyebrow="the read" title={changes === 0 ? 'Saved XI is the best available' : `${changes} change${changes > 1 ? 's' : ''} suggested`} className="mb-5">
        <div className="iq-display font-bold leading-snug" style={{ fontSize: 'clamp(16px,1.9vw,21px)', letterSpacing: '-0.01em', maxWidth: 760 }}>
          {changes === 0
            ? 'Everyone\u2019s available and the saved side is already optimal — no changes needed.'
            : `${outPlayers.map(p => surname(p.name)).join(' & ')} drop out; ${inIds.map(p => surname(p.name)).join(' & ')} come in. ${bal.spin >= 2 ? 'The rebuild also restores a second spinner for this ground.' : ''}`}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px] items-start">
        {/* the XI */}
        <Card eyebrow="batting order · auto-built" title="Best available XI"
          right={<span className="iq-mono text-pb-faint text-[11px]">{counts.available} in · {counts.maybe} maybe · {counts.unavailable} out</span>}>
          <div className="space-y-0.5">
            {xi.map((p, i) => {
              const isNew = !savedIds.has(p.id);
              return (
                <div key={p.id} className="flex items-center gap-3 px-2 py-2.5" style={{ borderRadius: 9, background: isNew ? 'color-mix(in srgb, var(--pb-brand) 9%, transparent)' : i % 2 ? 'transparent' : 'var(--pb-surface2)' }}>
                  <span className="iq-num text-pb-faint w-5 text-center shrink-0">{i + 1}</span>
                  <Initials name={p.name} size={32} tone={isNew ? 'accent' : undefined} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2"><span className="font-semibold text-[14px] whitespace-nowrap">{p.name}</span>{isNew && <Tag tone="win">In</Tag>}{SPINNERS.has(p.id) && <span className="iq-mono text-pb-faint" style={{ fontSize: 9 }}>spin</span>}</div>
                    <div className="text-pb-faint text-[11.5px] iq-num">form {p.formAvg.toFixed(2)} · {p.grade === '2nd' ? '2nd XI' : '1st XI'}</div>
                  </div>
                  <RoleChip role={primaryRole(p)} />
                  <span className="iq-num text-pb-dim text-[12.5px] w-12 text-right shrink-0 hidden sm:block">{primaryRole(p) === 'BWL' ? `${p.wkts}w` : `${p.runs}r`}</span>
                </div>
              );
            })}
          </div>
          {(inIds.length > 0 || outPlayers.length > 0) && (
            <div className="mt-4 pt-4 grid sm:grid-cols-2 gap-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              <div>
                <div className="iq-eyebrow mb-2" style={{ color: 'var(--pb-brand)' }}>Coming in</div>
                {inIds.length ? inIds.map(p => <div key={p.id} className="text-[13px] py-0.5">{p.name} <span className="text-pb-faint text-[11.5px]">· {p.grade === '2nd' ? 'promoted' : 'in form'}</span></div>) : <Empty>—</Empty>}
              </div>
              <div>
                <div className="iq-eyebrow mb-2" style={{ color: 'var(--pb-red)' }}>Dropping out</div>
                {outPlayers.length ? outPlayers.map(p => <div key={p.id} className="text-[13px] py-0.5">{p.name} <span className="text-pb-faint text-[11.5px]">· {p.reason}</span></div>) : <Empty>—</Empty>}
              </div>
            </div>
          )}
        </Card>

        {/* balance + warnings */}
        <div className="space-y-5">
          <Card eyebrow="composition" title="Balance">
            <div className="grid grid-cols-2 gap-2.5">
              {balChips.map(b => (
                <div key={b.label} className="px-3 py-2.5" style={{ background: 'var(--pb-surface2)', borderRadius: 10, border: `1px solid ${b.warn ? 'color-mix(in srgb, var(--pb-amber) 38%, transparent)' : 'var(--pb-hairline)'}` }}>
                  <div className="iq-headline iq-num" style={{ fontSize: 21, color: b.warn ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b.value}</div>
                  <div className="iq-eyebrow mt-1" style={{ fontSize: 8.5 }}>{b.label}</div>
                </div>
              ))}
            </div>
            {warnings.length === 0
              ? <div className="flex items-center gap-2 mt-3.5 text-[13px]" style={{ color: 'var(--pb-brand)' }}><Icon name="check" size={15} />Well balanced for this fixture.</div>
              : <div className="space-y-2 mt-3.5">{warnings.map((w, i) => <div key={i} className="flex gap-2 text-[12.5px] leading-snug"><Icon name="info" size={14} className="mt-0.5 shrink-0" style={{ color: w.tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)' }} /><span>{w.text}</span></div>)}</div>}
          </Card>
        </div>
      </div>

      {/* availability manager */}
      <div className="flex items-center justify-between gap-3 mt-9 mb-4">
        <h2 className="iq-display font-bold text-[19px]" style={{ letterSpacing: '-0.01em' }}>Availability</h2>
        <label className="flex items-center gap-2 text-[12.5px] text-pb-dim cursor-pointer select-none">
          <input type="checkbox" checked={includeMaybe} onChange={e => setIncludeMaybe(e.target.checked)} style={{ accentColor: 'var(--pb-accent)', width: 15, height: 15 }} />
          Consider "maybe" players
        </label>
      </div>
      <Card>
        <div className="grid gap-x-8 gap-y-1 lg:grid-cols-2">
          {IQ_SQUAD.map(p => {
            const inXI = autoIds.has(p.id);
            return (
              <div key={p.id} className="flex items-center gap-3 py-2" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
                <Initials name={p.name} size={30} tone={inXI ? 'accent' : undefined} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><span className="font-medium text-[13.5px] whitespace-nowrap">{p.name}</span>{inXI && <span className="iq-mono" style={{ fontSize: 8.5, color: 'var(--pb-accent)' }}>● XI</span>}</div>
                  <div className="text-pb-faint text-[11px] iq-num">{p.grade === '2nd' ? '2nd XI · ' : ''}form {p.formAvg.toFixed(2)}</div>
                </div>
                <RoleChip role={primaryRole(p)} />
                <AvailToggle value={availMap[p.id]} onChange={v => setAvail(p.id, v)} />
              </div>
            );
          })}
        </div>
        <Note>Availability mirrors BetterSelect. Change a status and the XI above rebuilds instantly — eligibility (grade, registration) is enforced from the same pool.</Note>
      </Card>
    </div>
  );
}

Object.assign(window, { Selection });
