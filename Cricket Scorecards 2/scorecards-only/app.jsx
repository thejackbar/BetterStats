// App — wires the WC Final data into the three scorecard styles
// and lays them out on a DesignCanvas with a dark/light Tweaks toggle.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "scorecardMode": "dark"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const match = window.SAMPLE_FULL_MATCH;
  const dark  = t.scorecardMode === "dark";

  return (
    <>
      <DesignCanvas>
        <DCSection
          id="full-scorecards"
          title="Full Match Scorecards"
          subtitle="1920×1080 · complete batting + bowling for both teams · 2023 ICC World Cup Final · toggle dark/light in Tweaks"
        >
          <DCArtboard id="s1" label="S1 · Broadcast" width={1920} height={1080}>
            <SC1_Broadcast match={match} dark={dark} />
          </DCArtboard>
          <DCArtboard id="s2" label="S2 · Brutalist" width={1920} height={1080}>
            <SC2_Brutalist match={match} dark={dark} />
          </DCArtboard>
          <DCArtboard id="s3" label="S3 · Dashboard" width={1920} height={1080}>
            <SC3_Dashboard match={match} dark={dark} />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Scorecard mode" />
        <TweakRadio
          label="Mode"
          value={t.scorecardMode}
          options={[{ value: "dark", label: "Dark" }, { value: "light", label: "Light" }]}
          onChange={(v) => setTweak('scorecardMode', v)}
        />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
