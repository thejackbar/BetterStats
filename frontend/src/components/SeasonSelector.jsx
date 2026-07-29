import { formatSeason } from '../lib/cricketFormat'

export default function SeasonSelector({
  seasons = [],
  grades = [],
  selectedSeason,
  setSelectedSeason,
  selectedGrade,
  setSelectedGrade,
  finalsOnly = false,
  setFinalsOnly = () => {},
  captainOnly = false,
  setCaptainOnly = () => {},
  gender = null,
  setGender = () => {},
  overseas = null,
  setOverseas = () => {},
  showOverseasFilter = false,
  showGenderFilter = true,
  showFinalsFilter = true,
  showCaptainFilter = true,
}) {
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {/* Season - always shown */}
      {seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Season</label>
          <select
            value={selectedSeason || ''}
            onChange={e => setSelectedSeason(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All seasons</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
          </select>
        </div>
      )}

      {/* Visual divider when there are secondary filters */}
      {(grades.length > 0 || seasons.length > 0) && (
        <div className="h-5 w-px bg-pb-hairline mx-1 hidden sm:block" />
      )}

      {/* Grade */}
      {grades.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Grade</label>
          <select
            value={selectedGrade || ''}
            onChange={e => setSelectedGrade(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All grades</option>
            {grades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </div>
      )}

      {/* Gender filter - pill toggle */}
      {showGenderFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Gender</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: null, label: 'All' },
              { value: 'Male', label: 'Men' },
              { value: 'Female', label: 'Women' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setGender(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  gender === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Games - pill toggle */}
      {showFinalsFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Games</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: false, label: 'All' },
              { value: true, label: 'Finals' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setFinalsOnly(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  finalsOnly === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Overseas filter - pill toggle */}
      {showOverseasFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Overseas</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: null, label: 'All' },
              { value: 'exclude', label: 'Local' },
              { value: 'only', label: 'Overseas' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setOverseas(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  overseas === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Captain filter - pill toggle */}
      {showCaptainFilter && seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Captain</label>
          <div className="flex items-center border pb-hairline rounded overflow-hidden">
            {[
              { value: false, label: 'All' },
              { value: true, label: 'Captain' },
            ].map(opt => (
              <button
                key={opt.label}
                onClick={() => setCaptainOnly(opt.value)}
                className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                  captainOnly === opt.value
                    ? 'bg-pb-accent/15 text-pb-accent'
                    : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
