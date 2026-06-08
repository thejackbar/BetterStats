/* Direction C — "Team Sheet" (bold / editorial)
 * The XI is a printed-looking team sheet with a big numbered spine — the hero.
 * You draft into it from a grid of player cards below. Condensed display type,
 * ruled rows, strong masthead.
 */
const COND = 'var(--display)';

function SheetRow({ i, id, sel, drag }) {
  const p = id ? BS.byId[id] : null;
  const isFocus = sel.focus === i;
  const hovered = drag.hover === 'slot:' + i;
  return (
    <div data-drop-kind="slot" data-drop-idx={i}
      onClick={() => !p && sel.setFocus(i)}
      className={'bs-sheetrow' + (p ? ' filled' : ' empty') + (isFocus && !p ? ' focus' : '') + (hovered ? ' hover' : '')}>
      <span className="bs-sheetnum" style={{ color: p ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>{i + 1}</span>
      {p ? (
        <>
          <span {...drag.bind({ kind: 'slot', idx: i, player: p })} className="bs-grip" title="Drag to reorder / off"><Icon name="grip" size={15} /></span>
          <div style={{ position: 'relative' }}><Avatar p={p} size={38} /><span style={{ position: 'absolute', right: -1, bottom: -1 }}><Dot status={p.availability} size={11} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span className="bs-sheetname">{p.name}</span>
              {id === sel.capId && <Tag>C</Tag>}{id === sel.wkId && <Tag tone="amber">WK</Tag>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 1, minWidth: 0 }}>
              <span style={{ fontSize: 12.5, color: 'var(--pb-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{BS.roleLine(p)}</span>
              <span style={{ flexShrink: 0 }}><FormChip p={p} /></span>
            </div>
          </div>
          <div className="bs-slotbtns">
            <button className={'bs-cap' + (id === sel.capId ? ' on' : '')} title="Captain" onClick={(e) => { e.stopPropagation(); sel.toggleCap(id); }}>C</button>
            <button className={'bs-wk' + (id === sel.wkId ? ' on' : '')} title="Keeper" onClick={(e) => { e.stopPropagation(); sel.toggleWk(id); }}>WK</button>
            <button className="bs-x" title="Remove" onClick={(e) => { e.stopPropagation(); sel.removeAt(i); }}><Icon name="close" size={15} /></button>
          </div>
        </>
      ) : (
        <div className="bs-sheetempty">
          <span style={{ fontFamily: COND, fontSize: 14, letterSpacing: '0', color: isFocus ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>
            {isFocus ? 'Tap a card below to draft here' : hovered ? 'Drop to draft' : 'Open slot'}
          </span>
        </div>
      )}
    </div>
  );
}

function TrayCard({ p, sel, drag }) {
  const m = BS.AVAIL[p.availability];
  const unavail = p.availability === 'UNAVAILABLE';
  const f = BS.formOf(p);
  return (
    <div className={'bs-traycard' + (unavail ? ' off' : '')}
      {...(unavail ? {} : drag.bind({ kind: 'pool', player: p }))}
      onClick={unavail ? undefined : drag.clickGuard(() => sel.addPlayer(p))}>
      <span className="bs-trayedge" style={{ background: p.availability === 'NO_RESPONSE' ? 'var(--pb-faintest)' : m.token }} />
      <div style={{ position: 'relative' }}><Avatar p={p} size={34} /><span style={{ position: 'absolute', right: -1, bottom: -1 }}><Dot status={p.availability} size={10} style={{ boxShadow: '0 0 0 2px var(--pb-surface)' }} /></span></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          {p.tier > 1 && <Tag tone="faint">{p.squad.replace('Applecross ', '')}</Tag>}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--pb-dim)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{BS.roleLine(p)}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}><FormBars p={p} h={13} /><span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, fontWeight: 600, color: f.token }}>{f.label}</span></div>
      </div>
      {!unavail && <span className="bs-traydraft"><Icon name="plus" size={14} /></span>}
    </div>
  );
}

function DirectionC({ sel, flash }) {
  const drag = useDrag();
  const f = useFilters();
  const pool = usePool(sel, f);
  const poolHover = drag.hover === 'pool';
  const F = BS.FIXTURE;
  const b = sel.balance;

  return (
    <div className="dirC">
      {/* Masthead */}
      <div className="bs-masthead">
        <div className="bs-masthead-l">
          <div className="bs-mast-kicker">Team sheet · {F.round}</div>
          <h2 className="bs-mast-title">{F.us} <span>vs</span> {F.opponent}</h2>
          <div className="bs-mast-sub">{F.date} · {F.time} · {F.venue} (A)</div>
        </div>
        <div className="bs-masthead-r">
          <div className="bs-mast-count"><b>{sel.count}</b><span>/ 11</span></div>
          <div className="bs-mast-balance">
            {['BAT', 'ALL', 'BWL', 'WKT'].map((c) => {
              const low = (c === 'BWL' && b.lightBowling) || (c === 'WKT' && !b.hasKeeper);
              return <span key={c}><i style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>{c === 'WKT' ? 'WK' : c}</i> <b style={{ color: low ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{b[c]}</b></span>;
            })}
          </div>
        </div>
      </div>

      {/* The sheet */}
      <div className="bs-sheet">
        <div className="bs-sheet-head">
          <span style={{ fontFamily: COND, fontSize: 15, fontWeight: 700, letterSpacing: '-.01em' }}>Batting order</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button className="bs-minibtn" onClick={sel.autofill}><Icon name="bolt" size={13} />Auto-fill</button>
            <button className="bs-minibtn" onClick={sel.clearXI}><Icon name="undo" size={13} />Clear</button>
          </div>
        </div>
        <div>{sel.slots.map((id, i) => <SheetRow key={i} i={i} id={id} sel={sel} drag={drag} />)}</div>
        <div className="bs-sheet-foot">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: sel.capId ? 'var(--pb-text)' : 'var(--pb-faint)' }}><Tag tone={sel.capId ? 'accent' : 'faint'}>C</Tag>{sel.capId ? BS.byId[sel.capId].name : 'No captain named'}</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: sel.wkId ? 'var(--pb-text)' : 'var(--pb-amber)' }}><Tag tone={sel.wkId ? 'amber' : 'faint'}>WK</Tag>{sel.wkId ? BS.byId[sel.wkId].name : 'No keeper named'}</span>
        </div>
      </div>

      {/* Draft pool */}
      <div className="bs-tray">
        <div className="bs-tray-head">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <h3 style={{ fontFamily: COND, fontSize: 16, fontWeight: 700, letterSpacing: '-.01em', margin: 0 }}>Draft pool</h3>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--pb-faint)' }}>tap a card to draft · or drag up onto a slot</span>
          </div>
          <div style={{ width: 'min(420px, 100%)' }}>
            <FilterControls f={f} count={pool.length} total={BS.POOL.length - sel.count} />
          </div>
        </div>
        <div className={'bs-tray-grid' + (poolHover ? ' droptarget' : '')} data-drop-kind="pool">
          {pool.map((p) => <TrayCard key={p.id} p={p} sel={sel} drag={drag} />)}
          {pool.length === 0 && <div style={{ padding: 18, color: 'var(--pb-faint)', fontSize: 13 }}>No players match.</div>}
        </div>
        {poolHover && <div className="bs-drophint" style={{ marginTop: 10 }}>Drop here to remove from the XI</div>}
      </div>
    </div>
  );
}
window.DirectionC = DirectionC;
