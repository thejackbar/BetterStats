import { useClubSponsors } from './useClubSponsors'

// A club's own names for its public sections (Fantasy becoming "Froth Fantasy
// Cricket", say), read from the same cached fetch the sponsor list uses.
//   sec.name('leaderboard', 'Leaderboard')  the club's name, or the fallback
//   sec.renamed('leaderboard')              true when the club set a name
//   sec.sponsor('leaderboard')              the linked sponsor card, or null
// Keys match backend services/section_names.SECTIONS.
export function useSectionNames(slug) {
  const data = useClubSponsors(slug)
  const names = (data && data.section_names) || {}
  return {
    name: (key, fallback = null) => (names[key] && names[key].name) || fallback,
    renamed: (key) => !!(names[key] && names[key].name),
    sponsor: (key) => (names[key] && names[key].sponsor) || null,
  }
}

// Public URL segment -> section key, for pages that carry a club slug.
export const PATH_SEGMENT_TO_KEY = {
  leaderboard: 'leaderboard',
  records: 'records',
  statlab: 'statlab',
  premierships: 'premierships',
  'honour-board': 'honour_board',
  ladders: 'ladders',
  players: 'players',
  compare: 'compare',
  yearbook: 'yearbook',
  yearbooks: 'yearbook',
}
