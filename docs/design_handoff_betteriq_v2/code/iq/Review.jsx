/* BetterIQ — Match review: an automatic post-match read of a completed game. */
const { useState: useStateRv } = React;

function GameReviewDetail({ g, onScout }) {
  const won = g.result === 'WIN';
  const color = won ? 'var(--pb-brand)' : 'var(--pb-red)';
  return (
    <div className="iq-fade space-y-5">
      {/* scoreline */}
      <Card accent>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>Match review · {g.date}</div>
            <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(24px,3vw,34px)' }}>vs {g.opp}</h2>
            <div className="text-pb-faint text-[12.5px] mt-1.5">{g.grade} · {g.venue}</div>
          </div>
          <div className="text-right">
            <div className="iq-headline" style={{ fontSize: 26, color }}>{g.result}</div>
            <div className="text-pb-dim text-[13px] mt-0.5">{g.margin}</div>
          </div>
        </div>
        <div className="flex items-center gap-5 mt-5 pt-5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
          <div><div className="iq-eyebrow mb-1">Applecross</div><div className="iq-headline iq-num" style={{ fontSize: 28 }}>{g.us_score}</div></div>
          <div className="text-pb-faintest text-2xl">vs</div>
          <div><div className="iq-eyebrow mb-1">{g.opp}</div><div className="iq-headline iq-num" style={{ fontSize: 28, color: 'var(--pb-dim)' }}>{g.them_score}</div></div>
        </div>
      </Card>

      {/* turning point */}
      <Card eyebrow="the synthesis" title="What changed the game">
        <div className="text-[15px] leading-relaxed">{g.turning_point}</div>
      </Card>

      {/* top performers */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="top scorers" title="Batting">
          <div className="space-y-2.5">
            {g.top_bat.map((p, i) => (
              <div key={p.name} className="flex items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="iq-num text-pb-faint w-4">{i + 1}</span><span className="font-semibold text-[14px]">{p.name}</span></div><span className="iq-num text-pb-dim text-[13px]">{p.score}</span></div>
            ))}
          </div>
        </Card>
        <Card eyebrow="leading wicket-takers" title="Bowling">
          <div className="space-y-2.5">
            {g.top_bowl.map((p, i) => (
              <div key={p.name} className="flex items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="iq-num text-pb-faint w-4">{i + 1}</span><span className="font-semibold text-[14px]">{p.name}</span></div><span className="iq-num font-semibold text-[13.5px]">{p.fig}</span></div>
            ))}
          </div>
        </Card>
      </div>

      {/* trio */}
      <div className="grid gap-5 sm:grid-cols-3">
        <Card eyebrow="best stand"><div className="font-semibold text-[14px] leading-snug">{g.best_partnership}</div></Card>
        <Card eyebrow="extras conceded"><div className="iq-headline iq-num" style={{ fontSize: 26 }}>{g.extras}</div></Card>
        <Card eyebrow="key collapse"><div className="font-semibold text-[13.5px] leading-snug">{g.collapse}</div></Card>
      </div>

      <Note>Read generated from the scorecard — no ball-by-ball, so phase/pressure detail isn't available.</Note>
    </div>
  );
}

function Review({ onScout }) {
  const [sel, setSel] = useStateRv('g1');
  const g = IQ_GAME_REVIEW; // detail shown for the selected (mocked to last meeting)
  return (
    <div className="iq-fade">
      <PageIntro>An automatic read of every completed game — the scoreline, what swung it, and who delivered.</PageIntro>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr] items-start">
        {/* recent games list */}
        <div className="iq-card p-2 lg:sticky lg:top-20">
          <div className="iq-eyebrow px-2 py-2">Recent games</div>
          <div className="space-y-0.5">
            {IQ_REVIEW_GAMES.map(rg => {
              const on = rg.id === sel;
              const c = rg.result === 'W' ? 'var(--pb-brand)' : 'var(--pb-red)';
              return (
                <button key={rg.id} onClick={() => setSel(rg.id)}
                  className="w-full flex items-center gap-3 px-2.5 py-2.5 text-left transition" style={{ borderRadius: 9, background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}>
                  <span className="iq-mono inline-flex items-center justify-center font-bold shrink-0" style={{ width: 22, height: 22, fontSize: 11, borderRadius: 6, color: c, background: `color-mix(in srgb, ${c} 16%, transparent)` }}>{rg.result}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-[13.5px] truncate" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>vs {rg.opp}</div>
                    <div className="text-pb-faint text-[11px] iq-num">{rg.grade} · {rg.date}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <GameReviewDetail g={g} onScout={onScout} />
      </div>
    </div>
  );
}

Object.assign(window, { Review });
