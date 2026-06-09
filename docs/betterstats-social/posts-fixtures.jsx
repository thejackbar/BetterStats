// ─────────────────────────────────────────────────────────────────────────────
// FIXTURES ROUNDUP — 3 variations (1080×1080)
//   A · Fixtures List   — clean factual rows (Midnight)
//   B · Match-day Hype  — diagonal poster (Crimson)
//   C · Fixtures Grid   — 2×3 cards (Cobalt)
// ─────────────────────────────────────────────────────────────────────────────

const { Post, Grain, Halftone, Stripes, Shield, Monogram, Slab, Kicker, Bug, SponsorFooter, AutoFit, DISPLAY, MONO, BODY, WIN, LOSS, TIE } = window;

// ── A · FIXTURES LIST ─────────────────────────────────────────────────────────
function FixtureList({ pal }) {
  const m = window.ROUND_META;
  const rows = window.FIXTURES;
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={26} angle={0} />
      {/* watermark */}
      <div style={{ position: 'absolute', right: -40, bottom: 60, fontFamily: DISPLAY, fontSize: 560, lineHeight: 0.8, color: pal.ink, opacity: 0.04, letterSpacing: -16, userSelect: 'none' }}>R9</div>

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 30px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={30} style={{ padding: '9px 18px' }}>FIXTURES</Slab>
          <Kicker color={pal.accent} size={14} style={{ marginTop: 14 }}>{`// ${m.round} · ${m.date} · ${m.comp}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 1, lineHeight: 1 }}>{window.CLUB.name}</div>
            <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 2, color: pal.ink, opacity: 0.6, marginTop: 4 }}>SAT FIXTURES</div>
          </div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={74} />
        </div>
      </div>

      {/* rows */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 196, bottom: 150, display: 'flex', flexDirection: 'column' }}>
        {rows.map((r, i) => {
          const home = r.ha === 'H';
          return (
            <div key={i} style={{ flex: 1, display: 'grid', gridTemplateColumns: '162px minmax(0,1fr) 206px', alignItems: 'center', gap: 18, borderBottom: i < rows.length - 1 ? `1px solid ${pal.ink}1a` : 'none' }}>
              <div>
                <div style={{ width: 30, height: 4, background: pal.accent, marginBottom: 8 }} />
                <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 0.5, lineHeight: 0.95 }}>{r.grade}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 20, letterSpacing: 2, color: home ? pal.accent : pal.ink, opacity: home ? 1 : 0.55, width: 40, flexShrink: 0 }}>{home ? 'VS' : '@'}</span>
                <Monogram text={r.oppMono} size={50} fg={pal.ink} bg={`${pal.ink}12`} ring={`${pal.ink}33`} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontFamily: DISPLAY, fontSize: 31, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</div>
                  <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.5, color: pal.ink, opacity: 0.55, marginTop: 4 }}>{home ? 'HOME' : 'AWAY'}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 27, letterSpacing: 1, lineHeight: 1, color: pal.accent, whiteSpace: 'nowrap' }}>{r.time}</div>
                <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1.5, color: pal.ink, opacity: 0.7, marginTop: 5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.venue}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="fl-g" />
    </Post>
  );
}

// ── B · MATCH-DAY HYPE (diagonal poster) ──────────────────────────────────────
function FixtureHype({ pal }) {
  const m = window.ROUND_META;
  const rows = window.FIXTURES;
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.07} size={10} />
      {/* giant round numeral */}
      <div style={{ position: 'absolute', right: -90, top: 150, fontFamily: DISPLAY, fontSize: 900, lineHeight: 0.7, color: pal.accent, opacity: 0.1, letterSpacing: -20, userSelect: 'none' }}>9</div>

      {/* diagonal top banner */}
      <div style={{ position: 'absolute', left: -200, width: 1600, top: 30, height: 268, background: pal.accent, transform: 'rotate(-5deg)', transformOrigin: 'top left' }} />
      <div style={{ position: 'absolute', left: 56, top: 82, zIndex: 3 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pal.primary, fontWeight: 700 }}>{`// ${m.round} · ${m.comp}`}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: 96, lineHeight: 0.86, letterSpacing: -1, color: pal.primary, marginTop: 6 }}>THIS<br />SATURDAY</div>
      </div>
      <div style={{ position: 'absolute', right: 56, top: 70, zIndex: 3, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 26, letterSpacing: 1, color: pal.primary, textAlign: 'right' }}>{m.date}</div>
        <Shield monogram={window.CLUB.mono} color={pal.primary} size={86} />
      </div>

      {/* stacked games */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 360, bottom: 150, display: 'flex', flexDirection: 'column', gap: 0 }}>
        {rows.map((r, i) => {
          const home = r.ha === 'H';
          return (
            <div key={i} style={{ flex: 1, display: 'grid', gridTemplateColumns: '52px 150px minmax(0,1fr) 184px', alignItems: 'center', gap: 20, padding: '0 6px', borderTop: `2px solid ${pal.ink}22` }}>
              <div style={{ fontFamily: MONO, fontSize: 22, letterSpacing: 1, color: pal.accent }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 0.5, lineHeight: 0.95 }}>{r.grade}</div>
              <div style={{ minWidth: 0, display: 'flex', alignItems: 'center', gap: 14 }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 22, letterSpacing: 1, color: home ? pal.accent : pal.ink, opacity: home ? 1 : 0.5, flexShrink: 0 }}>{home ? 'V' : '@'}</span>
                <div style={{ flex: 1, minWidth: 0, fontFamily: DISPLAY, fontSize: 38, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 26, color: pal.ink, lineHeight: 1, whiteSpace: 'nowrap' }}>{r.time}</div>
                <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.2, color: pal.ink, opacity: 0.6, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.venue} · {home ? 'H' : 'A'}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* footer diagonal */}
      <div style={{ position: 'absolute', left: -200, bottom: -28, width: 1600, height: 150, background: pal.secondary, transform: 'rotate(-2deg)', transformOrigin: 'bottom left' }} />
      <div style={{ position: 'absolute', left: 56, right: 56, bottom: 30, zIndex: 3 }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.32} id="fh-g" />
    </Post>
  );
}

// ── C · FIXTURES GRID (2×3 cards) ─────────────────────────────────────────────
function FixtureGrid({ pal }) {
  const m = window.ROUND_META;
  const rows = window.FIXTURES;
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={12} />
      <Stripes color={pal.accent} opacity={0.03} gap={30} angle={-18} />

      {/* header */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontFamily: DISPLAY, fontSize: 76, letterSpacing: -1, lineHeight: 0.9 }}>FIXTURES</div>
          <Kicker color={pal.accent} size={15} style={{ marginTop: 8 }}>{`// ${m.round} · ${m.comp}`}</Kicker>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 24, color: pal.accent }}>{m.date}</div>
          <Shield monogram={window.CLUB.mono} color={pal.ink} size={66} />
        </div>
      </div>

      {/* grid */}
      <div style={{ position: 'absolute', left: 56, right: 56, top: 188, bottom: 142, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr 1fr', gap: 18 }}>
        {rows.map((r, i) => {
          const home = r.ha === 'H';
          return (
            <div key={i} style={{ position: 'relative', background: pal.secondary, borderTop: `3px solid ${pal.accent}`, padding: '20px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap' }}>{r.grade}</div>
                <span style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.5, padding: '4px 9px', borderRadius: 3, background: home ? pal.accent : `${pal.ink}1a`, color: home ? pal.primary : pal.ink, fontWeight: 700, flexShrink: 0 }}>{home ? 'HOME' : 'AWAY'}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <Shield monogram={window.CLUB.mono} color={pal.ink} size={46} />
                <span style={{ fontFamily: DISPLAY, fontSize: 22, color: pal.accent, opacity: 0.9 }}>v</span>
                <Monogram text={r.oppMono} size={46} fg={pal.ink} bg={`${pal.ink}14`} ring={`${pal.ink}33`} />
                <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 0.95, minWidth: 0, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderTop: `1px solid ${pal.ink}1a`, paddingTop: 12 }}>
                <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1.2, color: pal.ink, opacity: 0.7 }}>{r.venue}</div>
                <div style={{ fontFamily: DISPLAY, fontSize: 26, color: pal.ink, lineHeight: 1 }}>{r.time}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* footer */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '20px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="fg-g" />
    </Post>
  );
}

Object.assign(window, { FixtureList, FixtureHype, FixtureGrid, FixtureBoard, FixtureHeadline, FixtureSchedule });

// ── D · FIXTURES BOARD (departure-board / tabular) ────────────────────────────
function FixtureBoard({ pal }) {
  const m = window.ROUND_META;
  const rows = window.FIXTURES;
  const cols = '150px minmax(0,1fr) 122px 184px';
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.05} size={11} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 22px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={30} style={{ padding: '9px 18px' }}>FIXTURES</Slab>
          <Kicker color={pal.ink} size={14} style={{ marginTop: 14, opacity: 0.72 }}>{`// ${m.round} · ${m.date} · ${m.comp}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={74} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 196, display: 'grid', gridTemplateColumns: cols, gap: 18, padding: '0 14px 10px', borderBottom: `1px solid ${pal.ink}22` }}>
        {['GRADE', 'MATCH', 'TIME', 'GROUND'].map((h, i) => (
          <div key={i} style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.8, color: pal.ink, opacity: 0.5, textAlign: i >= 2 ? 'right' : 'left' }}>{h}</div>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 242, bottom: 150, display: 'flex', flexDirection: 'column' }}>
        {rows.map((r, i) => {
          const home = r.ha === 'H';
          return (
            <div key={i} style={{ flex: 1, display: 'grid', gridTemplateColumns: cols, gap: 18, alignItems: 'center', padding: '0 14px', background: i % 2 ? `${pal.ink}08` : 'transparent' }}>
              <div style={{ fontFamily: DISPLAY, fontSize: 26, letterSpacing: 0.5, lineHeight: 0.92 }}>{r.grade}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1, color: home ? pal.accent : pal.ink, opacity: home ? 1 : 0.5, flexShrink: 0, width: 22 }}>{home ? 'VS' : '@'}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</span>
                <span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: 1.2, padding: '2px 7px', borderRadius: 3, border: `1px solid ${pal.ink}30`, color: pal.ink, opacity: 0.6, flexShrink: 0 }}>{home ? 'HOME' : 'AWAY'}</span>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, letterSpacing: 0.5, color: pal.accent, textAlign: 'right', whiteSpace: 'nowrap' }}>{r.time}</div>
              <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1, color: pal.ink, opacity: 0.7, textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.venue}</div>
            </div>
          );
        })}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="fb-g" />
    </Post>
  );
}

// ── E · FIXTURES HEADLINE (feature match + also-on strip) ──────────────────────
function FixtureHeadline({ pal }) {
  const m = window.ROUND_META;
  const rows = window.FIXTURES;
  const feat = rows[0];
  const rest = rows.slice(1);
  const fHome = feat.ha === 'H';
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.03} gap={28} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 22px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={26} style={{ padding: '8px 16px' }}>FIXTURES</Slab>
          <Kicker color={pal.ink} size={13} style={{ marginTop: 12, opacity: 0.72 }}>{`// ${m.round} · ${m.date}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={70} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 198, height: 426, background: pal.secondary, borderTop: `3px solid ${pal.accent}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <Kicker color={pal.accent} size={13} style={{ marginBottom: 22 }}>{`// FEATURE MATCH · ${feat.grade}`}</Kicker>
        <div style={{ display: 'flex', alignItems: 'center', gap: 44 }}>
          <div style={{ textAlign: 'center', width: 280 }}>
            <Shield monogram={window.CLUB.mono} color={pal.ink} size={150} />
            <div style={{ fontFamily: DISPLAY, fontSize: 30, letterSpacing: 0.5, marginTop: 12 }}>{window.CLUB.name}</div>
          </div>
          <div style={{ fontFamily: DISPLAY, fontSize: 60, color: pal.accent, letterSpacing: 1 }}>VS</div>
          <div style={{ textAlign: 'center', width: 280 }}>
            <Shield monogram={feat.oppMono} color={pal.ink} size={150} />
            <AutoFit max={30} min={16} style={{ fontFamily: DISPLAY, letterSpacing: 0.5, marginTop: 12, textAlign: 'center' }}>{feat.opp}</AutoFit>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 26, marginTop: 26, fontFamily: MONO, fontSize: 14, letterSpacing: 1.5, color: pal.ink, opacity: 0.85, alignItems: 'center' }}>
          <span style={{ color: pal.accent, fontWeight: 700 }}>{feat.time}</span><span style={{ opacity: 0.4 }}>·</span><span>{feat.venue}</span><span style={{ opacity: 0.4 }}>·</span><span>{fHome ? 'HOME' : 'AWAY'}</span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 652, bottom: 150 }}>
        <Kicker color={pal.ink} size={12} style={{ opacity: 0.55, marginBottom: 12 }}>{`// ALSO ON ${m.date}`}</Kicker>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 34px' }}>
          {rest.map((r, i) => {
            const home = r.ha === 'H';
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: `1px solid ${pal.ink}14` }}>
                <span style={{ fontFamily: DISPLAY, fontSize: 19, width: 104, flexShrink: 0, lineHeight: 1 }}>{r.grade}</span>
                <span style={{ fontFamily: MONO, fontSize: 11, color: home ? pal.accent : pal.ink, opacity: home ? 1 : 0.5, flexShrink: 0 }}>{home ? 'v' : '@'}</span>
                <span style={{ fontFamily: DISPLAY, fontSize: 20, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</span>
                <span style={{ fontFamily: MONO, fontSize: 12, color: pal.accent, flexShrink: 0 }}>{r.time}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '20px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="fhd-g" />
    </Post>
  );
}

// ── F · FIXTURES SCHEDULE (match-day timeline) ────────────────────────────────
function FixtureSchedule({ pal }) {
  const m = window.ROUND_META;
  const toMin = (t) => { const [hm, ap] = t.split(' '); let [h, mm] = hm.split(':').map(Number); if (ap === 'PM' && h !== 12) h += 12; if (ap === 'AM' && h === 12) h = 0; return h * 60 + mm; };
  const rows = [...window.FIXTURES].sort((a, b) => toMin(a.time) - toMin(b.time));
  return (
    <Post palette={pal}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '46px 56px 26px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: `3px solid ${pal.accent}` }}>
        <div>
          <Slab bg={pal.accent} fg={pal.primary} size={28} style={{ padding: '9px 17px' }}>MATCH-DAY</Slab>
          <Kicker color={pal.ink} size={14} style={{ marginTop: 14, opacity: 0.72 }}>{`// ${m.round} · ${m.date} · ${m.comp}`}</Kicker>
        </div>
        <Shield monogram={window.CLUB.mono} color={pal.ink} size={74} />
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 206, bottom: 150 }}>
        <div style={{ position: 'absolute', left: 158, top: 12, bottom: 12, width: 2, background: `${pal.ink}22` }} />
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          {rows.map((r, i) => {
            const home = r.ha === 'H';
            return (
              <div key={i} style={{ flex: 1, display: 'flex', alignItems: 'center', position: 'relative' }}>
                <div style={{ width: 150, textAlign: 'right', paddingRight: 26, fontFamily: DISPLAY, fontSize: 32, color: pal.accent, lineHeight: 1, flexShrink: 0 }}>{r.time.replace(' ', '')}</div>
                <div style={{ width: 16, height: 16, borderRadius: '50%', background: pal.accent, border: `3px solid ${pal.primary}`, zIndex: 2, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0, paddingLeft: 26, display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span style={{ fontFamily: DISPLAY, fontSize: 26, width: 116, flexShrink: 0, lineHeight: 0.95 }}>{r.grade}</span>
                  <span style={{ fontFamily: MONO, fontSize: 13, color: home ? pal.accent : pal.ink, opacity: home ? 1 : 0.5, flexShrink: 0, width: 24 }}>{home ? 'VS' : '@'}</span>
                  <span style={{ fontFamily: DISPLAY, fontSize: 30, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.opp}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: pal.ink, opacity: 0.6, flexShrink: 0, whiteSpace: 'nowrap' }}>{r.venue} · {home ? 'H' : 'A'}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '22px 56px', background: pal.primary, borderTop: `2px solid ${pal.accent}` }}>
        <SponsorFooter palette={pal} sponsors={window.SPONSORS} />
      </div>
      <Grain opacity={0.3} id="fsch-g" />
    </Post>
  );
}
