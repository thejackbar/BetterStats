// App — wires data + tweaks into the six templates, lays them out on a DesignCanvas.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "palette": "crimson",
  "teamName": "APPLECROSS",
  "teamFullName": "APPLECROSS CRICKET CLUB",
  "teamMonogram": "AC",
  "opponentName": "NOTTINGHAMSHIRE",
  "opponentMonogram": "NCC",
  "round": "ROUND 7",
  "venue": "Heathcote Reserve",
  "date": "SAT 30 MAY",
  "time": "2:30 PM",
  "competition": "PREMIER T20",
  "season": "2025–26",
  "featuredIdx": 0,
  "milestoneValue": "200",
  "milestoneUnit": "GAMES",
  "milestoneReason": "200TH GAME FOR THE CLUB",
  "milestoneDetail": "15 seasons · 4,872 runs · 38 fifties · 6 centuries",
  "announceKind": "APPOINTMENT",
  "announceHeadline": "NAMED CAPTAIN",
  "announceSubheadline": "FOR THE 2025–26 SEASON"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const palette = window.PALETTES[t.palette] || window.PALETTES.midnight;
  const team = {
    name: t.teamName,
    fullName: t.teamFullName,
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

  // Featured-player picker is shared between Milestone (T7) and Mosaic (T8).
  const featuredIdx = Math.max(0, Math.min(t.featuredIdx ?? 0, players.length - 1));
  const featuredPlayer = players[featuredIdx];

  const milestone = {
    player:  featuredPlayer,
    value:   t.milestoneValue,
    unit:    t.milestoneUnit,
    reason:  t.milestoneReason,
    detail:  t.milestoneDetail,
  };

  const announcement = {
    kind:        t.announceKind,
    headline:    t.announceHeadline,
    subheadline: t.announceSubheadline,
    player:      featuredPlayer,
  };

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
          <DCArtboard id="t7" label="07 · Milestone Spotlight" width={1080} height={1080}>
            <T7_CaptainSpotlight {...common} milestone={milestone} />
          </DCArtboard>
          <DCArtboard id="t8" label="08 · Asymmetric Mosaic" width={1080} height={1080}>
            <T8_Mosaic {...common} featuredIdx={featuredIdx} />
          </DCArtboard>
          <DCArtboard id="t9" label="09 · Festival Flyer" width={1080} height={1080}>
            <T9_Flyer {...common} />
          </DCArtboard>
        </DCSection>

        <DCSection id="companion-templates" title="Match Day Companions" subtitle="Single-moment posts for the rest of the match cycle">
          <DCArtboard id="c1" label="C1 · Announcement" width={1080} height={1080}>
            <C1_CaptainAnnounce announcement={announcement} team={team} opponent={opponent} match={match} palette={palette} />
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
        <TweakText label="Full club name" value={t.teamFullName}
          onChange={(v) => setTweak('teamFullName', v.toUpperCase())} />
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

        <TweakSection label="Featured player (T7, T8)" />
        <TweakSelect label="Player"
          value={String(featuredIdx)}
          options={players.map((p, i) => ({ value: String(i), label: `${p.first} ${p.last}` }))}
          onChange={(v) => setTweak('featuredIdx', parseInt(v, 10))} />

        <TweakSection label="Milestone (T7)" />
        <TweakText label="Big number" value={t.milestoneValue}
          onChange={(v) => setTweak('milestoneValue', v)} />
        <TweakText label="Unit" value={t.milestoneUnit}
          onChange={(v) => setTweak('milestoneUnit', v.toUpperCase())} />
        <TweakText label="Reason" value={t.milestoneReason}
          onChange={(v) => setTweak('milestoneReason', v.toUpperCase())} />
        <TweakText label="Detail line" value={t.milestoneDetail}
          onChange={(v) => setTweak('milestoneDetail', v)} />

        <TweakSection label="Announcement (C1)" />
        <TweakText label="Kind chip" value={t.announceKind}
          onChange={(v) => setTweak('announceKind', v.toUpperCase())} />
        <TweakText label="Headline" value={t.announceHeadline}
          onChange={(v) => setTweak('announceHeadline', v.toUpperCase())} />
        <TweakText label="Subheadline" value={t.announceSubheadline}
          onChange={(v) => setTweak('announceSubheadline', v.toUpperCase())} />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
