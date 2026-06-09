const { DesignCanvas, DCSection, DCArtboard, DCPostIt } = window;
const {
  FixtureList, FixtureHype, FixtureGrid, FixtureBoard, FixtureHeadline, FixtureSchedule,
  ResultMarginHero, ResultBroadcast, ResultVersusColumns, ResultStar, ResultInningsBars, ResultTicket,
  ResultsList, ResultsScoreboard, ResultsRecord, ResultsHeadline, ResultsBoard, ResultsSplit,
  PALETTES,
} = window;
const P = PALETTES;

function App() {
  return (
    <DesignCanvas>
      <DCSection id="fixtures" title="Fixtures Roundup" subtitle="Weekend / round fixtures — one post, all grades. Three layouts, shown across palettes.">
        <DCArtboard id="fx-list-mid" label="List · Midnight" width={1080} height={1080}><FixtureList pal={P.midnight} /></DCArtboard>
        <DCArtboard id="fx-list-for" label="List · Forest" width={1080} height={1080}><FixtureList pal={P.forest} /></DCArtboard>
        <DCArtboard id="fx-hype-crm" label="Match-day Hype · Crimson" width={1080} height={1080}><FixtureHype pal={P.crimson} /></DCArtboard>
        <DCArtboard id="fx-hype-rust" label="Match-day Hype · Rust" width={1080} height={1080}><FixtureHype pal={P.rust} /></DCArtboard>
        <DCArtboard id="fx-grid-cob" label="Grid · Cobalt" width={1080} height={1080}><FixtureGrid pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="fx-grid-gra" label="Grid · Graphite" width={1080} height={1080}><FixtureGrid pal={P.graphite} /></DCArtboard>
        <DCArtboard id="fx-board-cob" label="Board · Cobalt" width={1080} height={1080}><FixtureBoard pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="fx-headline-mid" label="Headline · Midnight" width={1080} height={1080}><FixtureHeadline pal={P.midnight} /></DCArtboard>
        <DCArtboard id="fx-sched-rust" label="Schedule · Rust" width={1080} height={1080}><FixtureSchedule pal={P.rust} /></DCArtboard>
      </DCSection>

      <DCSection id="result" title="Single Result" subtitle="New single-match result layouts (beyond the existing Final Score / C4). Scores · margin · top performers · player of the match.">
        <DCArtboard id="rs-hero-for" label="Margin Hero · Forest" width={1080} height={1080}><ResultMarginHero pal={P.forest} /></DCArtboard>
        <DCArtboard id="rs-hero-mid" label="Margin Hero · Midnight" width={1080} height={1080}><ResultMarginHero pal={P.midnight} /></DCArtboard>
        <DCArtboard id="rs-cast-cob" label="Broadcast · Cobalt" width={1080} height={1080}><ResultBroadcast pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="rs-cast-crm" label="Broadcast · Crimson" width={1080} height={1080}><ResultBroadcast pal={P.crimson} /></DCArtboard>
        <DCArtboard id="rs-vs-mid" label="Versus Columns · Midnight" width={1080} height={1080}><ResultVersusColumns pal={P.midnight} /></DCArtboard>
        <DCArtboard id="rs-vs-gra" label="Versus Columns · Graphite" width={1080} height={1080}><ResultVersusColumns pal={P.graphite} /></DCArtboard>
        <DCArtboard id="rs-star-crm" label="Star of the Day · Crimson" width={1080} height={1080}><ResultStar pal={P.crimson} /></DCArtboard>
        <DCArtboard id="rs-bars-cob" label="Innings Bars · Cobalt" width={1080} height={1080}><ResultInningsBars pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="rs-ticket-rust" label="Match Ticket · Rust" width={1080} height={1080}><ResultTicket pal={P.rust} /></DCArtboard>
      </DCSection>

      <DCSection id="results-roundup" title="Results Roundup" subtitle="Weekend / round results — one post, all grades, win/loss colour-coded.">
        <DCArtboard id="rr-list-mid" label="Weekend Wrap · Midnight" width={1080} height={1080}><ResultsList pal={P.midnight} /></DCArtboard>
        <DCArtboard id="rr-list-cob" label="Weekend Wrap · Cobalt" width={1080} height={1080}><ResultsList pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="rr-board-gra" label="W/L Scoreboard · Graphite" width={1080} height={1080}><ResultsScoreboard pal={P.graphite} /></DCArtboard>
        <DCArtboard id="rr-board-for" label="W/L Scoreboard · Forest" width={1080} height={1080}><ResultsScoreboard pal={P.forest} /></DCArtboard>
        <DCArtboard id="rr-rec-crm" label="Record Strip · Crimson" width={1080} height={1080}><ResultsRecord pal={P.crimson} /></DCArtboard>
        <DCArtboard id="rr-rec-rust" label="Record Strip · Rust" width={1080} height={1080}><ResultsRecord pal={P.rust} /></DCArtboard>
        <DCArtboard id="rr-headline-for" label="Headline Result · Forest" width={1080} height={1080}><ResultsHeadline pal={P.forest} /></DCArtboard>
        <DCArtboard id="rr-board-cob" label="Results Board · Cobalt" width={1080} height={1080}><ResultsBoard pal={P.cobalt} /></DCArtboard>
        <DCArtboard id="rr-split-mid" label="Win/Loss Split · Midnight" width={1080} height={1080}><ResultsSplit pal={P.midnight} /></DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
