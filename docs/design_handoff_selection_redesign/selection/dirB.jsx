/* Direction B — "Dual Rail" (balanced flow, richer cards)
 * Two equal columns — Available pool ↔ Selected XI — with a clear flow between
 * them. Bigger player cards, a colour edge by availability, prominent form.
 */
function AvailMini({ players }) {
  const tally = {};
  players.forEach((p) => { tally[p.availability] = (tally[p.availability] || 0) + 1; });
  const segs = BS.AVAIL_ORDER.filter((s) => tally[s]);
  const total = players.length || 1;
  return (
    <div style={{ display: 'flex', height: 5, borderRadius: 999, overflow: 'hidden', background: 'var(--pb-surface2)', width: 92 }} title={segs.map((s) => `${tally[s]} ${BS.AVAIL[s].label.toLowerCase()}`).join(' · ')}>
      {segs.map((s) => <span key={s} style={{ flexGrow: tally[s], background: BS.AVAIL[s].token, opacity: s === 'NO_RESPONSE' ? 0.5 : 1 }} />)}
    </div>
  );
}

function CardB({ p, kind, idx, sel, drag, onClick }) {
  const m = BS.AVAIL[p.availability];
  const unavail = p.availability === 'UNAVAILABLE';
  const f = BS.formOf(p);
  const dragItem = kind === 'pool' ? { kind: 'pool', player: p } : { kind: 'slot', idx, player: p };
  return (
    <div className={'bs-bcard' + (unavail ? ' off' : '')}
      {...(kind === 'pool' && !unavail ? drag.bind(dragItem) : {})}
      onClick={unavail ? undefined : (onClick ? drag.clickGuard(onClick) : undefined)}>
      <span className="bs-bedge" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : m.token }} />
      {kind === 'slot' && <span {...drag.bind(dragItem)} className="bs-grip" title="Drag to reorder / off"><Icon name="grip" size={14} /></span>}
      <div style={{ position: 'relative' }}><Avatar p={p} size={40} /><span style={{ position: 'absolute', right: -1, bottom: -1 }}><Dot status={p.availability} size={11} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 14.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          {p.id === sel.capId && <Tag>C</Tag>}{p.id === sel.wkId && <Tag tone="amber">WK</Tag>}
          {p.tier > 1 && <Tag tone="faint">{p.squad.replace('Applecross ', '')}</Tag>}
        </div>
        <div style={{ fontSize: 12, color: 'var(--pb-dim)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{BS.roleLine(p)}</div>
        {p.availability_reason && <div style={{ fontSize: 11, color: 'var(--pb-faint)', marginTop: 1 }}>{p.availability_reason}</div>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3, flexShrink: 0 }}>
        <FormBars p={p} h={16} />
        {kind === 'pool' && <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, fontWeight: 600, color: f.token }}>{f.label}</span>}
      </div>
      {kind === 'pool'
        ? <span className="bs-bact add" title="Add to XI"><Icon name="arrow" size={16} /></span>
        : (
          <div className="bs-bact-xi">
            <button className={'bs-cap' + (p.id === sel.capId ? ' on' : '')} title="Captain" onClick={(e) => { e.stopPropagation(); sel.toggleCap(p.id); }}>C</button>
            <button className={'bs-wk' + (p.id === sel.wkId ? ' on' : '')} title="Keeper" onClick={(e) => { e.stopPropagation(); sel.toggleWk(p.id); }}>WK</button>
            <button className="bs-x" title="Remove" onClick={(e) => { e.stopPropagation(); sel.removeAt(idx); }}><Icon name="close" size={14} /></button>
          </div>
        )}
    </div>
  );
}

function SlotB({ i, id, sel, drag }) {
  const p = id ? BS.byId[id] : null;
  const isFocus = sel.focus === i;
  const hovered = drag.hover === 'slot:' + i;
  return (
    <div className="bs-brow">
      <span className="bs-bnum">{i + 1}</span>
      <div data-drop-kind="slot" data-drop-idx={i} style={{ flex: 1, minWidth: 0 }}
        onClick={() => !p && sel.setFocus(i)}>
        {p ? <CardB p={p} kind="slot" idx={i} sel={sel} drag={drag} />
          : <div className={'bs-bempty' + (isFocus ? ' focus' : '') + (hovered ? ' hover' : '')}>
              <Icon name="plus" size={15} /><span>{isFocus ? 'Tap a player in the pool' : hovered ? 'Drop here' : 'Empty'}</span>
            </div>}
      </div>
    </div>
  );
}

function DirectionB({ sel, flash }) {
  const drag = useDrag();
  const f = useFilters();
  const [mp, setMp] = useState(() => new URLSearchParams(location.search).get('panel') === 'xi' ? 'xi' : 'pool');
  const pool = usePool(sel, f);
  const poolHover = drag.hover === 'pool';

  return (
    <div className="dirB" data-mpanel={mp}>
      <FixtureBar sel={sel}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Segmented sm value={11} onChange={() => {}} options={[{ value: 11, label: '11' }, { value: 12, label: '12' }, { value: 13, label: '13' }, { value: 0, label: 'No limit' }]} />
          <span className="bs-pickpill" style={{ background: sel.count === 11 ? 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' : 'var(--pb-amber)', color: sel.count === 11 ? 'var(--pb-accent)' : '#1b1205' }}>{sel.count} / 11 picked</span>
        </div>
      </FixtureBar>

      <BalanceStrip sel={sel} />

      {/* Mobile-only panel switch */}
      <div className="bs-mtabs">
        <button className={mp === 'pool' ? 'on' : ''} onClick={() => setMp('pool')}><Icon name="player" size={15} />Available pool</button>
        <button className={mp === 'xi' ? 'on' : ''} onClick={() => setMp('xi')}><Icon name="selection" size={15} />Your XI · {sel.count}/11</button>
      </div>

      <div className="dirB-grid">
        {/* POOL */}
        <section className="bs-card bs-pool-sec">
          <header className="bs-cardhead" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <h3 className="bs-cardtitle">Available pool</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><AvailMini players={pool} /><span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--pb-faint)' }}>{pool.length}</span></div>
            </div>
            <FilterControls f={f} count={pool.length} total={BS.POOL.length - sel.count} />
          </header>
          <div className={'bs-blist' + (poolHover ? ' droptarget' : '')} data-drop-kind="pool">
            {pool.map((p) => <CardB key={p.id} p={p} kind="pool" sel={sel} drag={drag} onClick={() => sel.addPlayer(p)} />)}
            {pool.length === 0 && <div style={{ padding: 18, color: 'var(--pb-faint)', fontSize: 13 }}>No players match.</div>}
            {poolHover && <div className="bs-drophint">Drop here to remove from XI</div>}
          </div>
        </section>

        {/* Flow divider */}
        <div className="bs-flow" aria-hidden="true">
          <span className="bs-flowline" />
          <span className="bs-flowbadge"><Icon name="arrow" size={15} /></span>
          <span className="bs-flowline" />
        </div>

        {/* XI */}
        <section className="bs-card bs-xi-sec">
          <header className="bs-cardhead">
            <h3 className="bs-cardtitle">Selected XI <span style={{ color: 'var(--pb-faint)', fontWeight: 500, fontSize: 13 }}>· batting order</span></h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="bs-minibtn" onClick={sel.autofill}><Icon name="bolt" size={13} />Auto-fill</button>
              <button className="bs-minibtn" onClick={sel.clearXI}><Icon name="undo" size={13} />Clear</button>
            </div>
          </header>
          <div className="bs-blist">
            {sel.slots.map((id, i) => <SlotB key={i} i={i} id={id} sel={sel} drag={drag} />)}
          </div>
        </section>
      </div>
    </div>
  );
}
window.DirectionB = DirectionB;
