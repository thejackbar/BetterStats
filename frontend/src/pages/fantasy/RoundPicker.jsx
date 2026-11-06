// Previous / next arrows around a round dropdown, shared by Round winners and Insights.
// `rounds` is a list of { number, start_date, end_date, status? }; `value` is the selected round number.
const fmtDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
const span = (r) => (!r.start_date ? '' : (!r.end_date || r.end_date === r.start_date ? fmtDay(r.start_date) : `${fmtDay(r.start_date)} to ${fmtDay(r.end_date)}`))

const navBtn = (disabled) => ({
  width: 34, height: 34, borderRadius: '50%', flex: 'none', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.35 : 1,
  background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `700 16px 'Hanken Grotesk'`,
})

export default function RoundPicker({ rounds, value, onChange }) {
  const idx = rounds.findIndex(r => r.number === value)
  const go = (i) => rounds[i] && onChange(rounds[i].number)
  const label = (r) => `Round ${r.number}${r.status === 'live' ? ' (open)' : ''}${span(r) ? ` · ${span(r)}` : ''}`
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 0 12px' }}>
      <button aria-label="Previous round" disabled={idx <= 0} onClick={() => go(idx - 1)} style={navBtn(idx <= 0)}>{'‹'}</button>
      <select aria-label="Round" value={value ?? ''} onChange={e => onChange(Number(e.target.value))} style={{
        flex: 1, minWidth: 0, height: 34, borderRadius: 10, padding: '0 10px', background: 'var(--surface)', color: 'var(--text)',
        border: '1px solid var(--hairline2)', font: `700 13px 'Hanken Grotesk'`,
      }}>
        {rounds.map(r => <option key={r.number} value={r.number}>{label(r)}</option>)}
      </select>
      <button aria-label="Next round" disabled={idx < 0 || idx >= rounds.length - 1} onClick={() => go(idx + 1)} style={navBtn(idx < 0 || idx >= rounds.length - 1)}>{'›'}</button>
    </div>
  )
}
