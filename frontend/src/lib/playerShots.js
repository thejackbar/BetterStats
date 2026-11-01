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

// The photo a collectable CARD shows. The server decides it by card type (`player_cards.card_shot`: the profile photo in a circle for a
// plain card, the hero photo or the action shot filling the card for an Epic, Legendary or special one) and sends it as `card.shot`:
// 'hero', 'action' or 'profile'. A payload without `shot` (an older server) falls back to the hero position's own answer. Returns the
// URL of the full-card photo, or null when the card shows the profile photo.
export function cardShotUrl(card) {
  if (!card) return null
  if (card.shot === 'profile') return null
  if (card.shot === 'hero') return card.hero_photo_url || heroShotUrl(card)
  if (card.shot === 'action') return card.action_photo_url || heroShotUrl(card)
  return heroShotUrl(card)
}

// Which shot `heroShotUrl` would use: 'hero', 'action' or null. Lets a screen say what is showing.
export function heroShotKind(p) {
  const url = heroShotUrl(p)
  if (!url) return null
  return url === p.action_photo_url && url !== p.hero_photo_url ? 'action' : 'hero'
}

// A card draws a photo at a few hundred pixels, but the file is stored as uploaded (up to 8 MB). `?w=` on a player photo URL asks the server
// for a copy no wider than that (it rounds up to one of a few sizes and keeps them), so a card downloads tens of kilobytes, not megabytes.
// Any other URL (a logo, a pack picture, a photo from somewhere else) is returned as it is.
export const CARD_HERO_W = 800   // the hero position is 340 px wide: twice that for a sharp screen
export const CARD_HEAD_W = 480   // the headshot circle is 150 to 170 px
const PLAYER_PHOTO = /^\/api\/images\/players\/[^/?#]+\/(photo|hero-photo|action-photo)(\?|$)/
export function sizedPhoto(url, w) {
  if (!url || !w || !PLAYER_PHOTO.test(url) || /[?&]w=/.test(url)) return url
  return `${url}${url.includes('?') ? '&' : '?'}w=${w}`
}
