/**
 * BetterStats Cloudflare Worker — Open Graph injection for social crawlers
 *
 * Intercepts GET requests from social-media link crawlers (Facebook, WhatsApp,
 * Twitter, LinkedIn, Telegram, Discord, iMessage). For recognised page routes
 * it fetches lightweight API data from the backend, strips the generic
 * placeholder OG tags from the static index.html, and injects page-specific
 * ones before returning the HTML.
 *
 * All other requests (real users, assets, API calls) pass through unchanged.
 *
 * Deployment:
 *   wrangler deploy
 * Route (Cloudflare dashboard → Workers → Routes):
 *   betterstats.bltbox.com/*
 */

const SITE = 'https://betterstats.bltbox.com'

// Crawler User-Agent patterns — extend as needed
const CRAWLER_RE = /facebookexternalhit|Facebot|Twitterbot|WhatsApp|LinkedInBot|TelegramBot|Discordbot|Applebot|Slackbot-LinkExpanding|Pinterest|Embedly|redditbot|Googlebot|bingbot/i

// Second path segment values that indicate a club-scoped page
const CLUB_SECTIONS = new Set([
  'dashboard', 'players', 'leaderboard', 'records',
  'compare', 'statlab', 'yearbook', 'yearbooks', 'games',
])

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// ── Route detection ──────────────────────────────────────────────────────────

function parseRoute(pathname) {
  const segments = pathname.split('/').filter(Boolean)

  // /players/:uuid
  if (segments[0] === 'players' && UUID_RE.test(segments[1] ?? '')) {
    return { type: 'player', playerId: segments[1] }
  }

  // /:clubSlug/<section>
  if (segments.length >= 2 && CLUB_SECTIONS.has(segments[1])) {
    return { type: 'club', clubSlug: segments[0] }
  }

  return null
}

// ── API fetches ──────────────────────────────────────────────────────────────

const WORKER_UA = 'BetterStats-OGWorker/1.0'

async function apiFetch(path) {
  const res = await fetch(`${SITE}${path}`, {
    headers: { 'User-Agent': WORKER_UA },
    cf: { cacheTtl: 300, cacheEverything: true }, // edge-cache API responses for 5 min
  })
  if (!res.ok) return null
  return res.json()
}

async function fetchPlayerMeta(playerId) {
  // Two parallel, lightweight calls — no need for the heavy /stats endpoint
  const player = await apiFetch(`/api/players/${playerId}`)
  if (!player) return null

  const org = player.organisation_id
    ? await apiFetch(`/api/organisations/${player.organisation_id}`)
    : null

  const name = player.display_name || player.name || 'Player'
  const clubName = org?.name ?? ''

  return {
    title: `${name} — BetterStats`,
    description: clubName
      ? `${name}'s career batting, bowling and fielding records at ${clubName} on BetterStats.`
      : `${name}'s career cricket statistics on BetterStats.`,
    image: player.photo_url || org?.logo_url || null,
    type: 'profile',
  }
}

async function fetchClubMeta(clubSlug) {
  const club = await apiFetch(`/api/clubs/${clubSlug}`)
  if (!club) return null

  return {
    title: `${club.name} — BetterStats`,
    description: `${club.name} cricket statistics — batting, bowling and fielding leaderboards, records, and player profiles on BetterStats.`,
    image: club.logo_url || null,
    type: 'website',
  }
}

// ── HTML injection ───────────────────────────────────────────────────────────

function escAttr(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function buildOgTags(meta, pageUrl) {
  const lines = [
    `<meta property="og:site_name" content="BetterStats" />`,
    `<meta property="og:type" content="${escAttr(meta.type ?? 'website')}" />`,
    `<meta property="og:title" content="${escAttr(meta.title)}" />`,
    `<meta property="og:description" content="${escAttr(meta.description)}" />`,
    `<meta property="og:url" content="${escAttr(pageUrl)}" />`,
    `<meta name="twitter:card" content="${meta.image ? 'summary_large_image' : 'summary'}" />`,
    `<meta name="twitter:title" content="${escAttr(meta.title)}" />`,
    `<meta name="twitter:description" content="${escAttr(meta.description)}" />`,
  ]
  if (meta.image) {
    lines.push(`<meta property="og:image" content="${escAttr(meta.image)}" />`)
    lines.push(`<meta name="twitter:image" content="${escAttr(meta.image)}" />`)
  }
  return lines.join('\n    ')
}

function injectOgTags(html, meta, pageUrl) {
  // Strip generic placeholder OG/Twitter tags that ship with index.html
  const stripped = html.replace(
    /<meta\s+(?:property|name)="(?:og:|twitter:)[^"]*"[^>]*\/?>\n?/gi,
    '',
  )

  const tags = buildOgTags(meta, pageUrl)
  return stripped.replace('</head>', `    <!-- OG: injected by BetterStats Worker -->\n    ${tags}\n  </head>`)
}

// ── Worker entry ─────────────────────────────────────────────────────────────

export default {
  async fetch(request) {
    const url = new URL(request.url)

    // Only intercept HTML page GETs from crawlers
    const ua = request.headers.get('User-Agent') ?? ''
    if (request.method !== 'GET' || !CRAWLER_RE.test(ua)) {
      return fetch(request)
    }

    const route = parseRoute(url.pathname)
    if (!route) return fetch(request)

    // Fetch meta and the origin HTML concurrently
    const [meta, originRes] = await Promise.all([
      route.type === 'player'
        ? fetchPlayerMeta(route.playerId)
        : fetchClubMeta(route.clubSlug),
      fetch(request),
    ])

    // If anything went wrong, serve the original response unchanged
    if (!meta || !originRes.ok) return originRes

    const html = await originRes.text()
    const injected = injectOgTags(html, meta, request.url)

    return new Response(injected, {
      status: originRes.status,
      headers: {
        'content-type': 'text/html; charset=utf-8',
        // Cache crawler responses at the edge for 5 min — avoids hammering
        // the API on every Facebook re-scrape of the same URL
        'cache-control': 'public, max-age=300',
        'vary': 'User-Agent',
      },
    })
  },
}
