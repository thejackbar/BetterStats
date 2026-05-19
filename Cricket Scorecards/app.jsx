// App — wires data + tweaks into the six templates, lays them out on a DesignCanvas.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "palette": "crimson",
  "teamName": "APPLECROSS",
  "teamMonogram": "AC",
  "opponentName": "NOTTINGHAMSHIRE",
  "opponentMonogram": "NCC",
  "round": "ROUND 7",
  "venue": "Heathcote Reserve",
  "date": "SAT 30 MAY",
  "time": "2:30 PM",
  "competition": "PREMIER T20",
  "season": "2025–26"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const palette = window.PALETTES[t.palette] || window.PALETTES.midnight;
  const team = {
    name: t.teamName,
    short: t.teamMonogram,
    monogram: t.teamMonogram,
    logo: "assets/team-logo.webp",
  };
  const opponent = {
    name: t.opponentName,
    short: t.opponentMonogram,
    monogram: t.opponentMonogram,
    logo: "assets/opponent-logo.png",
  };
  const match = {
    competition: t.competition,
    round: t.round,
    venue: t.venue,
    date: t.date,
    time: t.time,
    season: t.season,
  };
  const players = window.SAMPLE_PLAYERS;

  const common = { team, opponent, match, players, palette };

  const paletteOptions = Object.entries(window.PALETTES).map(([k, v]) => ({
    value: k,
    label: v.name,
  }));

  // Palette swatches for the TweakColor picker (uses arrays = palette mode)
  const paletteSwatches = Object.values(window.PALETTES).map(p => [p.primary, p.accent, p.ink]);
  const paletteByPrimary = {};
  Object.entries(window.PALETTES).forEach(([k, v]) => { paletteByPrimary[v.primary] = k; });

  return (
    <>
      <DesignCanvas>
        <DCSection id="lineup-templates" title="Lineup Posts" subtitle="Nine 1080×1080 squad/XI designs · open the artboard menu (•••) to download PNG/JPG · drag to reorder">
          <DCArtboard id="t1" label="01 · Hero + Squad List" width={1080} height={1080}>
            <T1_HeroList {...common} />
          </DCArtboard>
          <DCArtboard id="t2" label="02 · Trading Card Grid" width={1080} height={1080}>
            <T2_CardGrid {...common} />
          </DCArtboard>
          <DCArtboard id="t3" label="03 · Side Image + Numbered XI" width={1080} height={1080}>
            <T3_SideNumbered {...common} />
          </DCArtboard>
          <DCArtboard id="t4" label="04 · Probable XI · Batting Order" width={1080} height={1080}>
            <T4_BattingOrder {...common} />
          </DCArtboard>
          <DCArtboard id="t5" label="05 · Brutalist Typography" width={1080} height={1080}>
            <T5_Brutalist {...common} />
          </DCArtboard>
          <DCArtboard id="t6" label="06 · Diagonal Poster" width={1080} height={1080}>
            <T6_Diagonal {...common} />
          </DCArtboard>
          <DCArtboard id="t7" label="07 · Captain Spotlight" width={1080} height={1080}>
            <T7_CaptainSpotlight {...common} />
          </DCArtboard>
          <DCArtboard id="t8" label="08 · Asymmetric Mosaic" width={1080} height={1080}>
            <T8_Mosaic {...common} />
          </DCArtboard>
          <DCArtboard id="t9" label="09 · Festival Flyer" width={1080} height={1080}>
            <T9_Flyer {...common} />
          </DCArtboard>
        </DCSection>

        <DCSection id="companion-templates" title="Match Day Companions" subtitle="Single-moment posts for the rest of the match cycle">
          <DCArtboard id="c1" label="C1 · Captain Announce" width={1080} height={1080}>
            <C1_CaptainAnnounce player={featuredOf(players)} team={team} opponent={opponent} match={match} palette={palette} />
          </DCArtboard>
          <DCArtboard id="c2" label="C2 · Toss Won" width={1080} height={1080}>
            <C2_TossWon toss={window.SAMPLE_TOSS} team={team} opponent={opponent} match={match} palette={palette} />
          </DCArtboard>
          <DCArtboard id="c3" label="C3 · Man of the Match" width={1080} height={1080}>
            <C3_ManOfMatch motm={window.SAMPLE_MOTM} team={team} opponent={opponent} match={match} palette={palette} />
          </DCArtboard>
          <DCArtboard id="c4" label="C4 · Final Score" width={1080} height={1080}>
            <C4_FinalScore result={window.SAMPLE_RESULT} team={team} opponent={opponent} match={match} palette={palette} />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Team palette" />
        <TweakColor
          label="Colorway"
          value={[palette.primary, palette.accent, palette.ink]}
          options={paletteSwatches}
          onChange={(swatches) => {
            const primary = Array.isArray(swatches) ? swatches[0] : swatches;
            const key = paletteByPrimary[primary];
            if (key) setTweak('palette', key);
          }}
        />

        <TweakSection label="Teams" />
        <TweakText label="Team name" value={t.teamName}
          onChange={(v) => setTweak('teamName', v.toUpperCase())} />
        <TweakText label="Team monogram" value={t.teamMonogram}
          onChange={(v) => setTweak('teamMonogram', v.toUpperCase().slice(0, 3))} />
        <TweakText label="Opponent" value={t.opponentName}
          onChange={(v) => setTweak('opponentName', v.toUpperCase())} />
        <TweakText label="Opp. monogram" value={t.opponentMonogram}
          onChange={(v) => setTweak('opponentMonogram', v.toUpperCase().slice(0, 3))} />

        <TweakSection label="Match info" />
        <TweakText label="Competition" value={t.competition}
          onChange={(v) => setTweak('competition', v)} />
        <TweakText label="Round" value={t.round}
          onChange={(v) => setTweak('round', v)} />
        <TweakText label="Venue" value={t.venue}
          onChange={(v) => setTweak('venue', v)} />
        <TweakText label="Date" value={t.date}
          onChange={(v) => setTweak('date', v)} />
        <TweakText label="Time" value={t.time}
          onChange={(v) => setTweak('time', v)} />
        <TweakText label="Season" value={t.season}
          onChange={(v) => setTweak('season', v)} />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
