// A player has three photographs: the profile photo (a square headshot, `photo_url`), the hero photo
// (`hero_photo_url`, tall) and the action shot (`action_photo_url`, mid-shot). The hero position on a card, a share
// card and a post is filled by the hero photo or the action shot, never the headshot: a club pins one per player
// (`hero_source`: 'hero' or 'action'), and with nothing pinned the hero photo comes first. A pinned shot the player
// does not have falls back to the other one, so a choice can never leave a hole. Every surface that draws the hero
// position calls this, so the answer is the same on a card, a share card and a post.
export const HERO_SOURCES = ['hero', 'action']

export function pickHero(shots, pref) {
  const order = pref === 'action' ? ['action', 'hero'] : ['hero', 'action']
  for (const k of order) if (shots?.[k]) return shots[k]
  return null
}

// From a player or card payload as the API sends it.
export function heroShotUrl(p) {
  if (!p) return null
  return pickHero({ hero: p.hero_photo_url, action: p.action_photo_url }, p.hero_source)
}

// Which shot `heroShotUrl` would use: 'hero', 'action' or null. Lets a screen say what is showing.
export function heroShotKind(p) {
  const url = heroShotUrl(p)
  if (!url) return null
  return url === p.action_photo_url && url !== p.hero_photo_url ? 'action' : 'hero'
}
