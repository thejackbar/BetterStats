// Shared data for the layout-parts probe. Rich on purpose: every conditional a
// layout has (photo, stats, sponsors, win and loss, points) should be on, or a
// part inside it can never show it is wired up.
export const PHOTO = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAGUlEQVR4nGM4saAiKm8aJsmAVRRIMgxKHQCMoGfBF+ppNwAAAABJRU5ErkJggg=='
export const LOGO = PHOTO
// The editor hands a layout a palette whose primary is #rrggbb99 once a background is active; tests of the veil use that.
export const pal = { primary: '#102040', secondary: '#183060', accent: '#f0b000', ink: '#ffffff', name: 'probe' }
export const team = { name: 'HOME CC', fullName: 'Home Cricket Club', short: 'HCC', mono: 'HCC', monogram: 'HCC', logo: LOGO }
export const opponent = { name: 'AWAY CC', fullName: 'Away Cricket Club', short: 'ACC', mono: 'ACC', monogram: 'ACC', logo: LOGO }
export const match = { competition: 'PREMIER T20', round: 'ROUND 5', venue: 'HEATHCOTE RESERVE', date: 'SAT 26 SEP', time: '1:00 PM', season: '2025/26' }
export const meta = { round: 'ROUND 5', date: 'SAT 26 SEP', comp: 'PREMIER T20', season: '2025/26', label: 'SAT 26 SEP', heading: 'SENIOR' }
export const club = { name: 'Home Cricket Club', short: 'HCC', mono: 'HCC', logo: LOGO }
export const players = Array.from({ length: 15 }, (_, i) => ({
  id: `p${i + 1}`, _id: `p${i + 1}`, first: `First${i + 1}`, last: `Last${i + 1}`, short: `F. LAST${i + 1}`, name: `First${i + 1} Last${i + 1}`,
  number: i + 1, role: ['BAT', 'BOWL', 'AR', 'WK'][i % 4], headshot: PHOTO, photo: PHOTO, grade: '1ST GRADE',
  isCaptain: i === 0, isVC: i === 1, isWK: i === 3, debut: i === 2,
  totw: { line: '87 (54) · 2/22', grade: '1ST GRADE', opp: 'AWAY CC', points: 120 - i },
}))
export const sponsors = [
  { id: 's1', name: 'Sponsor One', logo: LOGO }, { id: 's2', name: 'Sponsor Two', logo: LOGO }, { id: 's3', name: 'Sponsor Three', logo: LOGO },
]
// A mix of wins and losses so a win colour and a loss colour are both on screen.
export const fixtures = Array.from({ length: 6 }, (_, i) => ({
  id: `f${i}`, grade: `${i + 1}ND GRADE`, opp: `OPPONENT ${i + 1}`, oppMono: `O${i + 1}`, date: 'SAT 26 SEP', time: '1:00 PM', venue: 'HEATHCOTE RESERVE', home: i % 2 === 0, categories: ['senior'],
}))
export const results = Array.from({ length: 6 }, (_, i) => ({
  id: `r${i}`, grade: `${i + 1}ND GRADE`, opp: `OPPONENT ${i + 1}`, oppMono: `O${i + 1}`, outcome: i % 3 === 2 ? 'L' : 'W', winner: i % 3 === 2 ? 'them' : 'us',
  us: `${180 + i}/6`, them: `${150 + i}/9`, margin: 'BY 30 RUNS', date: 'SAT 26 SEP', categories: ['senior'],
  topBat: { name: 'F. LAST1', line: '87 (54)' }, topBowl: { name: 'F. LAST2', line: '3/22' },
}))
export const FOLLOW = { widths: [[1080, 1080], [1080, 1350], [1080, 1920]] }
