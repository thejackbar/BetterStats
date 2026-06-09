/* BetterStats — Players admin · player detail modal
 * Recreates the modal the user is happy with, plus: prev/next player nav
 * (flip through the roster without closing), Esc/arrow keys, position counter.
 */
const { useState, useEffect, useRef } = React;
const { Icon: MIcon, Avatar: MAvatar, Btn: MBtn, Field, TextInput, SelectInput, Toggle } = window;

function Snap({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ fontSize: 12, color: 'var(--pb-faint)' }}>{label}</div>
      {children}
    </div>
  );
}
function StatPill({ children, tone }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 42, height: 38, padding: '0 9px',
      borderRadius: 9, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)',
      fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 600, color: tone || 'var(--pb-text)' }}>{children}</span>
  );
}

function PlayerModal({ player, index, total, onClose, onPrev, onNext }) {
  const [p, setP] = useState(player);
  const dirtyRef = useRef(false);
  useEffect(() => { setP(player); dirtyRef.current = false; }, [player]);
  const set = (k, v) => { dirtyRef.current = true; setP((x) => ({ ...x, [k]: v })); };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft' && (e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT')) onPrev();
      else if (e.key === 'ArrowRight' && (e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT')) onNext();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, onPrev, onNext]);

  const months = ['1 Jul', '4 Jul', '11 Jul', '18 Jul'];
  const roleLine = [PD.roleNoun(p), p.batting_hand, p.bowl].filter(Boolean).join('  ·  ');

  return ReactDOM.createPortal(
    <div className="pm-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="pm-modal bs-scroll" role="dialog" aria-modal="true">
        {/* ── header ─────────────────────────────────────────── */}
        <div className="pm-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, minWidth: 0 }}>
            <MAvatar p={p} size={68} />
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
                <h2 style={{ margin: 0, fontFamily: 'var(--display)', fontWeight: 700, fontSize: 30, letterSpacing: '-.02em' }}>{p.last}, {p.first}</h2>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 13, letterSpacing: '.04em', color: 'var(--pb-accent)' }}>{p.squadShort} squad</span>
              </div>
              <div style={{ marginTop: 6, fontSize: 15, color: 'var(--pb-dim)' }}>
                {roleLine}{p.opener && <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--pb-accent)', letterSpacing: '.06em', marginLeft: 12 }}>OPENER</span>}
              </div>
              <a className="pm-link" href="#" onClick={(e) => e.preventDefault()}>View public profile →</a>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            <div className="pm-nav">
              <button onClick={onPrev} title="Previous player (←)"><MIcon name="chevL" size={17} /></button>
              <span>{index + 1} <i>/ {total}</i></span>
              <button onClick={onNext} title="Next player (→)"><MIcon name="chevR" size={17} /></button>
            </div>
            <MBtn variant="primary" onClick={onClose}>Save changes</MBtn>
            <button className="pm-x" onClick={onClose} title="Close (Esc)"><MIcon name="close" size={20} /></button>
          </div>
        </div>

        {/* ── body ───────────────────────────────────────────── */}
        <div className="pm-body">
          {/* left — selection snapshot */}
          <div className="pm-col pm-snap">
            <div className="pm-eyebrow">Selection snapshot</div>

            <Snap label="Availability — next 4 weeks">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
                {months.map((m, i) => {
                  const av = p.avail[i];
                  return (
                    <div key={m} style={{ borderRadius: 11, padding: '12px 8px 14px', textAlign: 'center',
                      border: `1px solid ${av ? 'color-mix(in srgb, var(--pb-accent) 38%, transparent)' : 'var(--pb-hairline)'}`,
                      background: av ? 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' : 'var(--pb-surface2)' }}>
                      <div style={{ fontSize: 13, color: 'var(--pb-dim)', marginBottom: 10 }}>{m}</div>
                      <span style={{ display: 'inline-block', width: 13, height: 13, borderRadius: '50%',
                        background: av ? 'var(--pb-accent)' : 'transparent', border: av ? 'none' : '1.5px solid var(--pb-faintest)' }} />
                    </div>
                  );
                })}
              </div>
            </Snap>

            <Snap label="Squad & eligibility">
              <div style={{ fontSize: 14 }}>
                <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.squad}</span>
                <span style={{ color: 'var(--pb-faint)' }}>  assigned · suggested first for {p.squad} fixtures</span>
              </div>
            </Snap>

            <Snap label="Recent form">
              <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '10px 14px', alignItems: 'center' }}>
                <span className="pm-formlab">Batting</span>
                <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>{p.recentBat.map((v, i) => <StatPill key={i}>{v}</StatPill>)}</div>
                <span className="pm-formlab">Bowling</span>
                <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>{p.recentBowl.map((v, i) => <StatPill key={i} tone="var(--pb-dim)">{v}</StatPill>)}</div>
                <span className="pm-formlab">Catches</span>
                <div style={{ fontSize: 14 }}><b style={{ fontSize: 18 }}>{p.catches}</b> <span style={{ color: 'var(--pb-faint)' }}>this season</span></div>
              </div>
            </Snap>

            <Snap label="Last picked">
              <div style={{ fontSize: 16 }}>{p.lastPlayed || <span style={{ color: 'var(--pb-faint)' }}>Not yet selected</span>}</div>
            </Snap>

            <div style={{ height: 1, background: 'var(--pb-hairline)' }} />

            <Snap label="Net attendance">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <b style={{ fontSize: 18 }}>{p.netSessions}</b><span style={{ color: 'var(--pb-faint)', fontSize: 13 }}>sessions</span>
                <b style={{ fontSize: 18, marginLeft: 14, color: 'var(--pb-accent)' }}>{p.netBatted}</b><span style={{ color: 'var(--pb-faint)', fontSize: 13 }}>batted</span>
              </div>
            </Snap>
          </div>

          {/* right — details form */}
          <div className="pm-col pm-details">
            <div className="pm-eyebrow">Details</div>
            <div className="pm-grid">
              <Field label="Display name" hint="(blank = synced)" span={2}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <TextInput placeholder="First" value={p.dnFirst || ''} onChange={(e) => set('dnFirst', e.target.value)} />
                  <TextInput placeholder="Last" value={p.dnLast || ''} onChange={(e) => set('dnLast', e.target.value)} />
                </div>
              </Field>
              <Field label="Squad (selection pool)"><SelectInput value={p.squad} onChange={(v) => set('squad', v)} options={PD.SQUADS} /></Field>
              <Field label="Role"><SelectInput value={p.player_role} onChange={(v) => set('player_role', v)} options={PD.ROLES} /></Field>
              <Field label="Batting hand"><SelectInput value={p.batting_hand} onChange={(v) => set('batting_hand', v)} options={['Right handed', 'Left handed']} /></Field>
              <Field label="Bowling"><SelectInput value={p.bowl || 'Does not bowl'} onChange={(v) => set('bowl', v === 'Does not bowl' ? null : v)} options={['Does not bowl', 'Right-arm fast', 'Right-arm fast-medium', 'Right-arm medium', 'Right-arm off spin', 'Right-arm leg spin', 'Left-arm fast-medium', 'Left-arm medium', 'Left-arm orthodox', 'Left-arm wrist spin']} /></Field>
              <Field label="Gender"><SelectInput value={p.gender} onChange={(v) => set('gender', v)} options={['Male', 'Female']} /></Field>
              <Field label="Email"><TextInput value={p.email} onChange={(e) => set('email', e.target.value)} /></Field>
              <Field label="Phone" span={2}><TextInput value={p.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 18 }}>
              <Toggle on={!!p.opener} onChange={(v) => set('opener', v)} label="Opening batsman" />
              <Toggle on={!!p.overseas} onChange={(v) => set('overseas', v)} label="Overseas player" />
              <Toggle on={!!p.inactive} onChange={(v) => set('inactive', v)} label="Inactive — hide from availability & selection" />
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

window.PlayerModal = PlayerModal;
