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
}) {
  return (
    <div className="flex flex-wrap gap-3 items-center">
      {seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Season</label>
          <select
            value={selectedSeason || ''}
            onChange={e => setSelectedSeason(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All seasons</option>
            {seasons.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      )}
      {grades.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Grade</label>
          <select
            value={selectedGrade || ''}
            onChange={e => setSelectedGrade(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="">All grades</option>
            {grades.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>
      )}
      {seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Games</label>
          <select
            value={finalsOnly ? 'finals' : 'all'}
            onChange={e => setFinalsOnly(e.target.value === 'finals')}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="all">All games</option>
            <option value="finals">Finals only</option>
          </select>
        </div>
      )}
      {seasons.length > 0 && (
        <div className="flex items-center gap-2">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Captain</label>
          <select
            value={captainOnly ? 'captain' : 'all'}
            onChange={e => setCaptainOnly(e.target.value === 'captain')}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            <option value="all">All players</option>
            <option value="captain">As captain</option>
          </select>
        </div>
      )}
    </div>
  )
}
