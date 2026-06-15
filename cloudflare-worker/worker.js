/**
 * Better Cricket Cloudflare Worker — permanent redirect old domain → canonical
 *
 * The public site moved to the "Better Cricket" brand at betterat.cricket. This
 * worker sits on the old betterstats.cricket and permanently redirects every
 * request to the same path and query string on betterat.cricket, so the old
 * domain's accumulated link equity consolidates onto the canonical one and old
 * links keep working.
 *
 * Per-page Open Graph cards for social crawlers are now handled server-side by
 * the backend (backend/app/routers/og_preview.py via the nginx social-crawler
 * rewrite), so the old OG-injection logic this worker used to do is retired.
 *
 * GET/HEAD use 301 (the conventional permanent move search engines consolidate
 * on); other methods use 308 so the method and body are preserved on the rare
 * write that still hits the old host.
 *
 * Deployment:
 *   wrangler deploy
 * Route (Cloudflare dashboard → Workers → Routes):
 *   betterstats.cricket/*
 */

const CANONICAL_ORIGIN = 'https://betterat.cricket'

export default {
  async fetch(request) {
    const url = new URL(request.url)
    const target = CANONICAL_ORIGIN + url.pathname + url.search
    const status = request.method === 'GET' || request.method === 'HEAD' ? 301 : 308
    return new Response(null, {
      status,
      headers: {
        Location: target,
        'Cache-Control': 'public, max-age=3600',
      },
    })
  },
}
