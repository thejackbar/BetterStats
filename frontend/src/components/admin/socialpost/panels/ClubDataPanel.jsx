// Club-data panel — live blocks that pull the club's own numbers onto the
// canvas, grouped into "from a player profile" and "from the club". Adds a data
// block via onAdd('data', { kind }). The player kinds all read one playerId,
// set from the inspector's player picker.
import { BLANK_DATA } from '../../../../social/blank-template'

const GROUPS = [
  { key: 'player', label: 'From a player profile' },
  { key: 'club', label: 'From the club' },
]

const DESC = {
  playerphoto: 'Their headshot, linked to the profile',
  playername: 'Name lockup with optional role',
  player: 'Career stat tiles',
  fixtures: 'This week, all grades',
  results: 'Latest results, win/loss coded',
  record: 'Season W · L · D',
  scorecard: 'A match summary',
}

export default function ClubDataPanel({ onAdd }) {
  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((g) => (
        <div key={g.key}>
          <div className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint mb-2">{g.label}</div>
          <div className="flex flex-col gap-1.5">
            {BLANK_DATA.filter((d) => d.group === g.key).map((d) => (
              <button key={d.kind} onClick={() => onAdd('data', { kind: d.kind })}
                className="text-left px-3 py-2 rounded-lg border pb-hairline bg-pb-surface2 hover:border-pb-accent transition-colors">
                <div className="text-pb-text text-[12px] font-medium leading-tight">{d.name}</div>
                <div className="text-pb-faint text-[10px] leading-tight mt-0.5">{DESC[d.kind]}</div>
              </button>
            ))}
          </div>
        </div>
      ))}
      <p className="text-pb-faintest text-[10px] leading-relaxed">
        Live data. Fixtures, results and scorecards come from those tabs; pick the player for a player block on the canvas.
      </p>
    </div>
  )
}
