/* Direction A — "Team First" (safe / faithful)
 * The XI you're building is the hero: a large ordered list on the left. The
 * pool is a compact picker on the right. Quiet balance strip up top. Role +
 * form replaces the old positional hints.
 */
function FixtureBar({ sel, children }) {
  const F = BS.FIXTURE;
  return (
    <div className="bs-fixbar">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <a className="bs-allteams">← All teams</a>
        <div className="bs-fixsel">@ {F.opponent} · 2026-07-04 <Icon name="chevron" size={13} /></div>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, marginTop: 6 }}>
        <div>
          <h2 style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 23, lineHeight: 1.1, margin: 0 }}>{F.us} <span style={{ color: 'var(--pb-faint)', fontWeight: 600 }}>vs</span> {F.opponent}</h2>
          <div style={{ fontSize: 13.5, color: 'var(--pb-dim)', marginTop: 3 }}>{F.date} · {F.time} · {F.venue} (A) · {F.round}</div>
        </div>
        {children}
      </div>
    </div>
  );
}

function BalanceStrip({ sel }) {
  const b = sel.balance;
  const item = (code, label, low) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '.06em', color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{label}</span>
      <b style={{ fontVariantNumeric: 'tabular-nums', color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b[code]}</b>
    </span>
  );
  const capName = sel.capId ? BS.byId[sel.capId]?.name : null;
  const wkName = sel.wkId ? BS.byId[sel.wkId]?.name : null;
  return (
    <div className="bs-balance">
      {item('BAT', 'BAT')}{item('ALL', 'ALL')}{item('BWL', 'BWL', b.lightBowling)}{item('WKT', 'WK', !b.hasKeeper)}
      <span className="bs-balance-div" />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: capName ? 'var(--pb-text)' : 'var(--pb-faint)' }}>
        <Tag tone={capName ? 'accent' : 'faint'}>C</Tag>{capName || 'No captain'}
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: wkName ? 'var(--pb-text)' : 'var(--pb-amber)' }}>
        <Tag tone={wkName ? 'amber' : 'faint'}>WK</Tag>{wkName || 'No keeper named'}
      </span>
      {b.lightBowling && <><span className="bs-balance-div" /><span style={{ fontSize: 12.5, color: 'var(--pb-amber)', display: 'inline-flex', alignItems: 'center', gap: 6 }}><Icon name="info" size={13} /> Light on bowling</span></>}
    </div>
  );
}

/* Sort menu (lightweight popover) */
function SortMenu({ f }) {
  const [open, setOpen] = useState(false);
  const cur = SORTS.find((s) => s.v === f.sort) || SORTS[0];
  return (
    <div className="bs-sortwrap">
      <button type="button" className="bs-sortbtn" onClick={() => setOpen((o) => !o)} title="Sort pool">
        <Icon name="ladders" size={14} /><span className="bs-hide-xs">{cur.label}</span><Icon name="chevron" size={12} />
      </button>
      {open && (
        <>
          <div className="bs-menuscrim" onClick={() => setOpen(false)} />
          <div className="bs-menu">
            <div className="bs-menulabel">Sort by</div>
            {SORTS.map((s) => (
              <button key={s.v} type="button" className={'bs-menuitem' + (s.v === f.sort ? ' on' : '')} onClick={() => { f.setSort(s.v); setOpen(false); }}>
                <span style={{ width: 14, display: 'inline-flex' }}>{s.v === f.sort && <Icon name="check" size={13} />}</span>{s.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function FChip({ active, onClick, children }) {
  return <button type="button" className={'bs-fchip' + (active ? ' on' : '')} onClick={onClick}>{children}</button>;
}
function FGroup({ label, children }) {
  return <div className="bs-fgroup"><div className="bs-fglabel">{label}</div><div className="bs-fglist">{children}</div></div>;
}

/* Expanded filter system — search · sort · quick chips · panel · active pills */
function FilterControls({ f, count, total }) {
  const [open, setOpen] = useState(false);
  const ROLE_LABEL = { BAT: 'Batter', BWL: 'Bowler', ALL: 'All-rounder', WKT: 'Keeper' };

  const pills = [];
  f.roles.forEach((r) => pills.push({ k: 'r' + r, label: ROLE_LABEL[r], rm: () => f.toggle(f.roles, f.setRoles)(r) }));
  f.avails.forEach((s) => pills.push({ k: 'a' + s, label: BS.AVAIL[s].label, rm: () => f.toggle(f.avails, f.setAvails)(s) }));
  f.bowling.forEach((b) => pills.push({ k: 'b' + b, label: (BOWL_KINDS.find((x) => x.v === b) || {}).label, rm: () => f.toggle(f.bowling, f.setBowling)(b) }));
  f.hands.forEach((h) => pills.push({ k: 'h' + h, label: h === 'RIGHT' ? 'RHB' : 'LHB', rm: () => f.toggle(f.hands, f.setHands)(h) }));
  f.forms.forEach((fm) => pills.push({ k: 'f' + fm, label: (FORM_BUCKETS.find((x) => x.v === fm) || {}).label, rm: () => f.toggle(f.forms, f.setForms)(fm) }));
  f.squads.forEach((s) => pills.push({ k: 's' + s, label: s.replace('Applecross ', ''), rm: () => f.toggle(f.squads, f.setSquads)(s) }));
  if (f.hideUnavail) pills.push({ k: 'hu', label: 'Hide unavailable', rm: () => f.setHideUnavail(false) });

  return (
    <div className="bs-filters">
      <div className="bs-filters-row">
        <Search value={f.q} onChange={f.setQ} placeholder="Search players…" style={{ flex: 1 }} />
        <SortMenu f={f} />
        <button type="button" className={'bs-filterbtn' + (f.activeCount ? ' on' : '')} onClick={() => setOpen((o) => !o)}>
          <Icon name="filter" size={14} /><span className="bs-hide-xs">Filters</span>{f.activeCount ? <span className="bs-fbadge">{f.activeCount}</span> : null}
        </button>
      </div>

      {/* Quick chips — the common moves */}
      <div className="bs-chiprow">
        {[['BAT', 'Bat'], ['BWL', 'Bowl'], ['ALL', 'All'], ['WKT', 'WK']].map(([v, l]) => (
          <FChip key={v} active={f.roles.includes(v)} onClick={() => f.toggle(f.roles, f.setRoles)(v)}>{l}</FChip>
        ))}
        <span className="bs-chipdiv" />
        <FChip active={f.hideUnavail} onClick={() => f.setHideUnavail(!f.hideUnavail)}><Dot status="AVAILABLE" size={7} />Hide unavailable</FChip>
      </div>

      {open && (
        <div className="bs-filterpanel">
          <FGroup label="Availability">
            {BS.AVAIL_ORDER.map((s) => (
              <label key={s} className="bs-check"><input type="checkbox" checked={f.avails.includes(s)} onChange={() => f.toggle(f.avails, f.setAvails)(s)} /><Dot status={s} size={7} />{BS.AVAIL[s].label}</label>
            ))}
          </FGroup>
          <FGroup label="Bowling">
            {BOWL_KINDS.map((b) => (
              <label key={b.v} className="bs-check"><input type="checkbox" checked={f.bowling.includes(b.v)} onChange={() => f.toggle(f.bowling, f.setBowling)(b.v)} />{b.label}</label>
            ))}
          </FGroup>
          <FGroup label="Batting hand">
            {[['RIGHT', 'Right-hand'], ['LEFT', 'Left-hand']].map(([v, l]) => (
              <label key={v} className="bs-check"><input type="checkbox" checked={f.hands.includes(v)} onChange={() => f.toggle(f.hands, f.setHands)(v)} />{l}</label>
            ))}
          </FGroup>
          <FGroup label="Form">
            {FORM_BUCKETS.map((b) => (
              <label key={b.v} className="bs-check"><input type="checkbox" checked={f.forms.includes(b.v)} onChange={() => f.toggle(f.forms, f.setForms)(b.v)} />{b.label}</label>
            ))}
          </FGroup>
          <FGroup label="Squad">
            {BS.SQUADS.map((s) => (
              <label key={s} className="bs-check"><input type="checkbox" checked={f.squads.includes(s)} onChange={() => f.toggle(f.squads, f.setSquads)(s)} />{s.replace('Applecross ', '')}</label>
            ))}
          </FGroup>
        </div>
      )}

      {pills.length > 0 && (
        <div className="bs-pillrow">
          {pills.map((p) => (
            <button key={p.k} type="button" className="bs-pill" onClick={p.rm}>{p.label}<Icon name="close" size={11} /></button>
          ))}
          <button type="button" className="bs-clear" onClick={f.clearAll}>Clear all</button>
        </div>
      )}

      <div className="bs-filtfoot">
        <span style={{ fontSize: 11.5, color: 'var(--pb-faint)', fontVariantNumeric: 'tabular-nums' }}>{count} of {total} shown</span>
      </div>
    </div>
  );
}

/* Pool row */
function PoolRowA({ p, drag, onAdd }) {
  const m = BS.AVAIL[p.availability];
  const unavail = p.availability === 'UNAVAILABLE';
  return (
    <div className={'bs-poolrow' + (unavail ? ' off' : '')}
      {...(unavail ? {} : drag.bind({ kind: 'pool', player: p }))}
      onClick={unavail ? undefined : drag.clickGuard(() => onAdd(p))}
      style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-surface2)' : `color-mix(in srgb, ${m.token} 6%, var(--pb-surface2))` }}>
      <Dot status={p.availability} />
      <Avatar p={p} size={30} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
        <div className="bs-roleline">{BS.roleLine(p)} {p.availability_reason && <span style={{ color: 'var(--pb-faint)' }}>· {p.availability_reason}</span>}</div>
      </div>
      <FormBars p={p} />
      {p.tier > 1 && <Tag tone="faint">{p.squad.replace('Applecross ', '')}</Tag>}
      {!unavail && <span style={{ color: 'var(--pb-faintest)' }}><Icon name="arrowL" size={16} /></span>}
    </div>
  );
}

/* XI slot */
function SlotRowA({ i, id, sel, drag }) {
  const p = id ? BS.byId[id] : null;
  const isFocus = sel.focus === i;
  const hovered = drag.hover === 'slot:' + i;
  return (
    <div data-drop-kind="slot" data-drop-idx={i}
      onClick={() => !id && sel.setFocus(i)}
      className={'bs-slot' + (p ? ' filled' : '') + (isFocus && !p ? ' focus' : '') + (hovered ? ' hover' : '')}>
      <span className="bs-slotnum">{i + 1}</span>
      {p ? (
        <>
          <span {...drag.bind({ kind: 'slot', idx: i, player: p })} className="bs-grip" title="Drag to reorder / off"><Icon name="grip" size={14} /></span>
          <Dot status={p.availability} />
          <Avatar p={p} size={30} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
              {id === sel.capId && <Tag>C</Tag>}{id === sel.wkId && <Tag tone="amber">WK</Tag>}
            </div>
            <div className="bs-roleline" style={{ display: 'flex', alignItems: 'center', gap: 7 }}><span>{BS.roleLine(p)}</span><FormChip p={p} withBars={false} /></div>
          </div>
          <div className="bs-slotbtns">
            <button className={'bs-cap' + (id === sel.capId ? ' on' : '')} title="Captain" onClick={(e) => { e.stopPropagation(); sel.toggleCap(id); }}>C</button>
            <button className={'bs-wk' + (id === sel.wkId ? ' on' : '')} title="Wicket-keeper" onClick={(e) => { e.stopPropagation(); sel.toggleWk(id); }}>WK</button>
            <button className="bs-x" title="Remove" onClick={(e) => { e.stopPropagation(); sel.removeAt(i); }}><Icon name="close" size={14} /></button>
          </div>
        </>
      ) : (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--pb-faintest)' }}>
          <span style={{ fontSize: 12.5 }}>{isFocus ? 'Tap a player to place here' : 'Empty'}</span>
        </div>
      )}
    </div>
  );
}

function DirectionA({ sel, flash }) {
  const drag = useDrag();
  const f = useFilters();
  const pool = usePool(sel, f);
  const poolHover = drag.hover === 'pool';

  return (
    <div className="dirA">
      <FixtureBar sel={sel}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Segmented sm value={11} onChange={() => {}} options={[{ value: 11, label: '11' }, { value: 12, label: '12' }, { value: 13, label: '13' }, { value: 0, label: 'No limit' }]} />
          <span className="bs-pickpill" style={{ background: sel.count === 11 ? 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' : 'var(--pb-amber)', color: sel.count === 11 ? 'var(--pb-accent)' : '#1b1205' }}>{sel.count} / 11 picked</span>
        </div>
      </FixtureBar>

      <BalanceStrip sel={sel} />

      <div className="dirA-grid">
        {/* XI — hero */}
        <section className="bs-card bs-xicard">
          <header className="bs-cardhead">
            <h3 className="bs-cardtitle">Your XI <span style={{ color: 'var(--pb-faint)', fontWeight: 500 }}>· batting order</span></h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="bs-minibtn" onClick={sel.autofill}><Icon name="bolt" size={13} />Auto-fill</button>
              <button className="bs-minibtn" onClick={sel.clearXI}><Icon name="undo" size={13} />Clear</button>
            </div>
          </header>
          <div className="bs-slotlist">
            {sel.slots.map((id, i) => <SlotRowA key={i} i={i} id={id} sel={sel} drag={drag} />)}
          </div>
        </section>

        {/* Pool — picker */}
        <section className="bs-card bs-poolcard">
          <header className="bs-cardhead" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h3 className="bs-cardtitle">Squad pool</h3>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--pb-faint)' }}>tap or drag →</span>
            </div>
            <FilterControls f={f} count={pool.length} total={BS.POOL.length - sel.count} />
          </header>
          <div className={'bs-poollist' + (poolHover ? ' droptarget' : '')} data-drop-kind="pool">
            {pool.map((p) => <PoolRowA key={p.id} p={p} drag={drag} onAdd={sel.addPlayer} />)}
            {pool.length === 0 && <div style={{ padding: 18, color: 'var(--pb-faint)', fontSize: 13 }}>No players match.</div>}
            {poolHover && <div className="bs-drophint">Drop here to remove from XI</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
window.DirectionA = DirectionA;
window.FixtureBar = FixtureBar;
window.BalanceStrip = BalanceStrip;
window.FilterControls = FilterControls;
