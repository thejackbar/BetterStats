// Shared by the Player Cards browser suites: moving round the page the way a player does.
const SCREEN = { home: 'home', book: 'book', club: 'club', packs: 'packs', swaps: 'swaps', how: 'how' }

// Tap a place in the sidebar, the rail or the bottom bar, whichever is showing. On a phone, Club cards has no slot of its own
// (it shares Cards with My cards), so it is reached through the switch at the top of that screen.
export async function goNav(page, key) {
  const nav = page.locator(`[data-nav="${key}"]:visible`).first()
  if (await nav.count()) await nav.click()
  else if (key === 'club') { await page.locator('[data-nav="book"]:visible').first().click(); await page.locator('[data-switch="club"]').click() }
  else throw new Error(`no visible way to ${key}`)
  await page.waitForSelector(`[data-screen="${SCREEN[key] || key}"]`, { timeout: 15000 })
  await page.waitForTimeout(250)
}

export const cardsUrl = (base, token, route = '') => `${base}/playerdash/${token}/cards${route}`
