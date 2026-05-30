/* bs-ladders.jsx — league standings per grade, with form guide and our-team
   highlight. Read-only (synced from CA). */

const BS_LADDERS = {
  'A-Grade': [
    { team: 'Applecross', p: 8, w: 6, l: 2, pts: 30, form: ['W', 'W', 'L', 'W', 'W'], us: true },
    { team: 'Melville', p: 8, w: 6, l: 2, pts: 28, form: ['W', 'L', 'W', 'W', 'W'] },
    { team: 'Nedlands', p: 8, w: 5, l: 3, pts: 24, form: ['L', 'W', 'W', 'L', 'W'] },
    { team: 'Fremantle', p: 8, w: 4, l: 4, pts: 20, form: ['W', 'L', 'L', 'W', 'L'] },
    { team: 'Cottesloe', p: 8, w: 4, l: 4, pts: 18, form: ['L', 'W', 'L', 'W', 'L'] },
    { team: 'UWA', p: 8, w: 3, l: 5, pts: 14, form: ['L', 'L', 'W', 'L', 'W'] },
    { team: 'Willetton', p: 8, w: 2, l: 6, pts: 12, form: ['L', 'L', 'L', 'W', 'L'] },
    { team: 'Bicton', p: 8, w: 1, l: 7, pts: 6, form: ['L', 'L', 'L', 'L', 'W'] },
  ],
  'B-Grade': [
    { team: 'Fremantle', p: 8, w: 7, l: 1, pts: 32, form: ['W', 'W', 'W', 'W', 'L'] },
    { team: 'Melville', p: 8, w: 5, l: 3, pts: 24, form: ['W', 'W', 'L', 'W', 'L'] },
    { team: 'Applecross', p: 8, w: 5, l: 3, pts: 22, form: ['L', 'W', 'W', 'L', 'W'], us: true },
    { team: 'Nedlands', p: 8, w: 4, l: 4, pts: 18, form: ['W', 'L', 'L', 'W', 'W'] },
    { team: 'Attadale', p: 8, w: 2, l: 6, pts: 10, form: ['L', 'L', 'W', 'L', 'L'] },
    { team: 'Bicton', p: 8, w: 1, l: 7, pts: 6, form: ['L', 'L', 'L', 'L', 'W'] },
  ],
  'C-Grade': [
    { team: 'Applecross', p: 8, w: 7, l: 1, pts: 34, form: ['W', 'W', 'W', 'L', 'W'], us: true },
    { team: 'Melville', p: 8, w: 6, l: 2, pts: 28, form: ['W', 'W', 'L', 'W', 'W'] },
    { team: 'UWA', p: 8, w: 4, l: 4, pts: 18, form: ['L', 'W', 'L', 'W', 'L'] },
    { team: 'Cottesloe', p: 8, w: 3, l: 5, pts: 14, form: ['L', 'L', 'W', 'L', 'W'] },
    { team: 'Willetton', p: 8, w: 2, l: 6, pts: 10, form: ['L', 'W', 'L', 'L', 'L'] },
    { team: 'Mt Pleasant', p: 8, w: 2, l: 6, pts: 8, form: ['L', 'L', 'L', 'W', 'L'] },
  ],
  'D-Grade': [
    { team: 'Willetton', p: 8, w: 6, l: 2, pts: 28, form: ['W', 'W', 'W', 'L', 'W'] },
    { team: 'Bicton', p: 8, w: 6, l: 2, pts: 26, form: ['W', 'L', 'W', 'W', 'W'] },
    { team: 'Attadale', p: 8, w: 5, l: 3, pts: 22, form: ['W', 'W', 'L', 'L', 'W'] },
    { team: 'Mt Pleasant', p: 8, w: 4, l: 4, pts: 18, form: ['L', 'W', 'W', 'L', 'L'] },
    { team: 'Applecross', p: 8, w: 3, l: 5, pts: 14, form: ['L', 'L', 'W', 'W', 'L'], us: true },
    { team: 'Fremantle', p: 8, w: 1, l: 7, pts: 6, form: ['L', 'L', 'L', 'L', 'W'] },
  ],
};
const ORD = (n) => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');

function FormDots({ form }) {
  const T = window.BST;
  const col = { W: T.accent, L: T.red, D: T.faintest };
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      {form.map((r, i) => (
        <span key={i} title={r === 'W' ? 'Win' : r === 'L' ? 'Loss' : 'Draw'} style={{ width: 16, height: 16, borderRadius: 5,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: T.mono, fontSize: 9, fontWeight: 700,
          background: r === 'W' ? 'rgba(22,199,132,0.16)' : r === 'L' ? 'rgba(239,91,91,0.16)' : T.surface2,
          color: col[r], border: `1px solid ${r === 'W' ? 'rgba(22,199,132,0.3)' : r === 'L' ? 'rgba(239,91,91,0.3)' : T.hair}` }}>{r}</span>
      ))}
    </span>
  );
}

function LaddersScreen({ onNav }) {
  const T = window.BST;
  const grades = Object.keys(BS_LADDERS);
  const [grade, setGrade] = React.useState('A-Grade');
  const rows = BS_LADDERS[grade];
  const usIdx = rows.findIndex(r => r.us);
  const us = rows[usIdx];
  const cols = [['#', 40, 'left'], ['Team', null, 'left'], ['P', 44, 'right'], ['W', 44, 'right'], ['L', 44, 'right'], ['Pts', 56, 'right'], ['Form', 130, 'right']];

  return (
    <BSShell active="ladders" title="Ladders" subtitle="League standings — synced weekly from Cricket Australia" onNav={onNav}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <Segmented value={grade} onChange={setGrade} options={grades.map(g => ({ value: g, label: g.replace('-Grade', '') }))} />
          {us && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto' }}>
              <span style={{ fontSize: 13, color: T.faint }}>Applecross sit</span>
              <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '6px 13px', borderRadius: 999,
                background: 'rgba(22,199,132,0.12)', border: '1px solid rgba(22,199,132,0.3)' }}>
                <b className="num" style={{ fontFamily: T.display, fontSize: 16, color: T.accent }}>{ORD(usIdx + 1)}</b>
                <span style={{ fontSize: 12, color: T.accent }}>of {rows.length}</span>
              </span>
              <span className="num" style={{ fontSize: 13, color: T.dim }}>{us.w}–{us.l} · {us.pts} pts</span>
            </div>
          )}
        </div>

        <div className="pb-card" style={{ overflow: 'hidden', background: T.surface, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: cols.map(c => c[1] ? c[1] + 'px' : '1fr').join(' '),
            padding: '12px 20px', borderBottom: `1px solid ${T.hair}`, background: T.surface2 }}>
            {cols.map((c, i) => <span key={i} className="eyebrow" style={{ textAlign: c[2] }}>{c[0]}</span>)}
          </div>
          <div className="bs-scroll" style={{ overflow: 'auto', flex: 1 }}>
            {rows.map((r, i) => {
              const promo = i < 2; // top two
              return (
                <div key={r.team} className={i ? 'pb-hair-t' : ''} style={{ display: 'grid',
                  gridTemplateColumns: cols.map(c => c[1] ? c[1] + 'px' : '1fr').join(' '), alignItems: 'center',
                  padding: '13px 20px', background: r.us ? 'rgba(22,199,132,0.07)' : 'transparent' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ width: 3, height: 16, borderRadius: 2, background: promo ? T.accent : 'transparent' }} />
                    <span className="num" style={{ color: T.faint }}>{i + 1}</span>
                  </span>
                  <span style={{ fontWeight: r.us ? 700 : 500, color: r.us ? T.accent : T.text, fontSize: 14 }}>
                    {r.team}{r.us && <span style={{ fontFamily: T.mono, fontSize: 9, color: T.accent, marginLeft: 7 }}>US</span>}
                  </span>
                  <span className="num" style={{ textAlign: 'right', color: T.dim }}>{r.p}</span>
                  <span className="num" style={{ textAlign: 'right', color: T.dim }}>{r.w}</span>
                  <span className="num" style={{ textAlign: 'right', color: T.dim }}>{r.l}</span>
                  <span className="num" style={{ textAlign: 'right', fontWeight: 700, color: T.text }}>{r.pts}</span>
                  <span style={{ display: 'flex', justifyContent: 'flex-end' }}><FormDots form={r.form} /></span>
                </div>
              );
            })}
          </div>
          <div className="pb-hair-t" style={{ padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: T.faintest }}>
            <span style={{ width: 3, height: 12, borderRadius: 2, background: T.accent, display: 'inline-block' }} /> Top two qualify for finals
          </div>
        </div>
      </div>
    </BSShell>
  );
}

Object.assign(window, { LaddersScreen });
