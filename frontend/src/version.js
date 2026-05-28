// SITE_VERSION is derived from the highest-sorted entry in src/data/changelog/.
// Don't hand-edit a version here — drop a new file in the changelog folder
// instead. This keeps version bumps conflict-free across parallel branches.
import { CHANGELOG } from './data/changelog'

export const SITE_VERSION = CHANGELOG[0]?.version ?? 'unknown'
