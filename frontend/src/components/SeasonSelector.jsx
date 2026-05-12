export default function SeasonSelector({
  seasons = [],
  grades = [],
  selectedSeason,
  setSelectedSeason,
  selectedGrade,
  setSelectedGrade,
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
    </div>
  )
}
